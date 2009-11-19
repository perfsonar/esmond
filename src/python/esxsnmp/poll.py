#!/usr/bin/env python

import os
import signal
import errno
import sys
import time
import re
import sets
import random
import socket
import threading
import Queue

import sqlalchemy
import yapsnmp
import rrdtool
#from guppy import hpy

import tsdb
import tsdb.row
from tsdb.util import rrd_from_tsdb_var
from tsdb.error import TSDBAggregateDoesNotExistError, TSDBVarDoesNotExistError

import esxsnmp.sql

from esxsnmp.util import setproctitle, init_logging, get_logger, remove_metachars
from esxsnmp.util import daemonize, setup_exc_handler
from esxsnmp.config import get_opt_parser, get_config, get_config_path
from esxsnmp.error import ConfigError, PollerError
from esxsnmp.rpc.ttypes import IfRef
from esxsnmp.persist import PollResult, PersistClient

class ThriftClient(object):
    def __init__(self):
        self.transport = TSocket.TSocket('localhost', 9090)
        self.transport = TTransport.TBufferedTransport(self.transport)
        self.protocol = TBinaryProtocol.TBinaryProtocol(self.transport)
        self.client = ESDB.Client(self.protocol)
        self.transport.open()

class PollError(Exception):
    pass

class PollUnknownIfIndex(PollError):
    pass


class PollCorrelator(object):
    """polling correlators correlate an oid to some other field.  this is
    typically used to generate the key needed to store the variable."""

    def __init__(self, session=None):
        self.session = session

    def setup(self):
        raise NotImplementedError

    def lookup(self, oid, var):
        raise NotImplementedError

    def _table_parse(self, table):
        d = {}
        for (var, val) in self.session.walk(table):
            d[var.split('.')[-1]] = remove_metachars(val)
        return d

class IfDescrCorrelator(PollCorrelator):
    """correlates and ifIndex to an it's ifDescr"""

    def setup(self):
        self.xlate = self._table_parse('ifDescr')
        for (var,val) in self.session.walk("ifDescr"):
            ifIndex = var.split(".")[-1]
            self.xlate[ifIndex] = remove_metachars(val)

        for (var,val) in self.session.walk("ifAlias"):
            ifIndex = var.split(".")[-1]
            if not val:
                self.xlate[ifIndex] = None


    def lookup(self, oid, var):
        # XXX this sucks
        if oid.name == 'sysUpTime':
            return 'sysUpTime'

        ifIndex = var.split('.')[-1]

        try:
            r = self.xlate[ifIndex]
            if r:
                return "/".join((oid.name, r))
            else:
                return None

        except KeyError:
            raise PollUnknownIfIndex(ifIndex)

class JnxFirewallCorrelator(PollCorrelator):
    """correlates entries in the jnxFWCounterByteCount tables to a variable
    name"""

    def __init__(self, session=None):
        PollCorrelator.__init__(self,session)
        self.oidex = re.compile('([^"]+)\."([^"]+)"\."([^"]+)"\.(.+)')

    def setup(self):
        pass

    def lookup(self, oid, var):
        (column, filter_name, counter, filter_type) = self.oidex.search(var).groups()
        return "/".join((filter_type, filter_name, counter))

class JnxCOSCorrelator(IfDescrCorrelator):
    """Correlates entries from the COS MIB.

    This is known to work for:

        jnxCosIfqQedBytes
        jnxCosIfqTxedBytes
        jnxCosIfqTailDropPkts
        jnxCosIfqTotalRedDropPkts
    """
    def __init__(self, session=None):
        PollCorrelator.__init__(self,session)
        self.oidex = re.compile('([^.]+)\.(\d+)\."([^"]+)"')

    def lookup(self, oid, var):
        ifIndex = var.split(".")[-2]
        try:
            if_name = self.xlate[ifIndex]
        except KeyError:
            raise PollUnknownIfIndex(ifIndex)

        if if_name:
            m = self.oidex.search(var)
            if not m:
                raise UnableToCorrelate("%s does not match" % var)

            (oid_name, ifindex, queue) = m.groups()

            return "/".join((if_name, oid_name, queue))
        else:
            return None

class CiscoCPUCorrelator(PollCorrelator):
    """Correlates entries in cpmCPUTotal5min to an entry in entPhysicalName
    via cpmCPUTotalPhysicalIndex.  

    See http://www.cisco.com/warp/public/477/SNMP/collect_cpu_util_snmp.html"""

    def setup(self):
        self.phys_xlate = self._table_parse('cpmCPUTotalPhysicalIndex')
        self.name_xlate = self._table_parse('entPhysicalName')

    def lookup(self, oid, var):
        #
        # this should only raise an exception of there aren't entries in the
        # tables, meaning that this box has only one CPU
        #
        n = self.name_xlate[self.phys_xlate[var.split('.')[-1]]].replace('CPU_of_','')
        if n == '':
            n = 'CPU'
        return "/".join((oid.name,n))

class PollerThread(threading.Thread):
    """Container for info about children of the main polling process"""

    SPIN_CYCLE_PERIOD = 30
    MAX_SPIN_CYCLES = 3

    NEW = 0
    RUN = 1
    PENALTY = 2
    REMOVE = 3

    def __init__(self, config, device, persistq):
        threading.Thread.__init__(self)

        self.config = config
        self.device = device
        self.persistq = persistq
        self.name = self.device.name
        self.pid = 0
        self.last_restart = 0
        self.spin_cycles = 0
        self.state = PollerThread.NEW
        self.pollers = {}

        self.log = get_logger("espolld." + self.name)

        for oidset in device.oidsets:
            self.add_oidset(device, oidset)

    def __repr__(self):
        try:
            return '<PollerThread: %s %d state=%d>' % (
                    self.name, self.pid, self.state)
        except:
            return '<PollerThread: BOGUS!>'

    def add_oidset(self, device, oidset):
        poller = eval(oidset.poller.name)
        try:
            self.pollers[oidset.name] = poller(self.config, device, oidset,
                self.persistq)
        except PollerError, e:
            self.log.error(str(e))
            self.state = self.REMOVE
        self.log.debug("add_oidset: %s" % self.pollers.keys())

    def remove_oidset(self, device, oidset):
        if self.pollers.has_key(oidset.name):
            del self.pollers[oidset.name]
        self.log.debug("remove_oidset: %s" % self.pollers.keys())

    def record(self):
        now = time.time()
        if now - self.last_restart < self.SPIN_CYCLE_PERIOD:
            self.spin_cycles += 1
        else:
            self.spin_cycles = 0

        self.last_restart = now
        self.state = self.RUN

    def is_spinning(self):
        return self.spin_cycles >= self.MAX_SPIN_CYCLES

    def is_penalized(self):
        return self.state == self.PENALTY

    def is_removed(self):
        return self.state == self.REMOVE

    def penalize(self):
        """Put this child in the penalty box."""
        self.state = self.PENALTY
        self.pid = None

    def remove(self):
        self.state = self.REMOVE

    # --- these methods are used inside the child thread only ---

    def run(self):
        if self.state == self.NEW:
            self.state = self.RUN

        while self.state == self.RUN:
            for oidset in self.device.oidsets:
                self.pollers[oidset.name].run_once()

            delay = 999
            for poller in self.pollers.itervalues():
                if poller.seconds_until_next_poll() < delay:
                    delay = poller.seconds_until_next_poll()

            if delay > 10:
                delay = 10

            if delay > 0:
                time.sleep(delay)
            elif delay < 0:
                self.log.info("%d seconds late" % abs(delay))

        self.log.info("thread exiting")

    def stop(self):
        self.state = self.REMOVE
        self.log.info("stopping")

    def reload(self):
        self.log.info("if it was implemented, i'd be reloading")

class PersistThread(threading.Thread):
    INIT = 0
    RUN = 1
    REMOVE = 2

    def __init__(self, config, persistq):
        threading.Thread.__init__(self)

        self.config = config
        self.persistq = persistq

        self.state = self.INIT

        self.persister = PersistClient(config)

    def run(self):
        self.state = self.RUN
        while self.state == self.RUN:
            try:
                task = self.persistq.get(block=True)
            except Queue.Empty:
                pass
            else:
                self.persister.put(task)

    def stop(self):
        self.state = self.REMOVE

class ThreadedPollManager(object):
    """Starts a polling thread for each device."""
    def __init__(self, name, opts, args, config):
        self.name = name
        self.opts = opts
        self.args = args
        self.config = config
        
        self.hostname = socket.gethostname()

        self.root_pid = os.getpid()

        self.log = get_logger(self.name)

        self.running = False
        self.last_reload = time.time()
        self.last_penalty_empty = time.time()

        self.reload_interval = 30
        self.penalty_interval = 300

        esxsnmp.sql.setup_db(self.config.db_uri)

        self.devices = esxsnmp.sql.get_devices(
                polling_tag=self.config.polling_tag)

        self.persistq = Queue.Queue()

        if not tsdb.TSDB.is_tsdb(None, self.config.tsdb_root):
            tsdb.TSDB.create(self.config.tsdb_root,
                chunk_prefixes=self.config.tsdb_chunk_prefixes)

        #self.heapy = hpy()
        #self.heapy.setrelheap()

    def start_polling(self):
        self.log.debug("starting, %d devices configured" % len(self.devices))

        signal.signal(signal.SIGINT, self.stop_polling)
        signal.signal(signal.SIGTERM, self.stop_polling)
        signal.signal(signal.SIGHUP, self.empty_penalty_box)
        self.running = True

        self.threads = {}
        t = PersistThread(self.config, self.persistq)
        self._start_thread('persist_thread', t)

        for device in self.devices.itervalues():
            t = PollerThread(self.config, device, self.persistq)
            self._start_thread(device.name, t)

        self.running = True

        #self.last_heap = time.time()

        while self.running:
            time.sleep(5)

            self.log.info("%d items in persistq" % self.persistq.qsize())
            for n,t in self.threads.iteritems():
                t.join(0.0)
                if not t.isAlive() and t.state != t.REMOVE:
                    self.log.error("%s thread died" % n)
                    if t.is_spinning():
                        t.penalize()
                    else:
                        self._restart_thread(n, t)

            """
            now = time.time()
            if now > self.last_heap + 60:
                fname = "/tmp/heapy-%f" % now
                f = open(fname, "w")
                h = self.heapy.heap()
                f.write(str(h))
                f.close()
                self.log.debug(
                    "heap_info: %d objs, %d bytes, file %s" % (len(h.nodes),
                        h.size, fname))
                self.last_heap = now
            """

        self.shutdown()

    def _start_thread(self, name, t):
        t.setDaemon(True)
        t.setName(name)
        self.threads[name] = t
        self.log.debug("started thread %s" % name)
        t.start()

    # XXX this repeats some of the logic from above, proably should be
    # refactored, but a simple refactoring doesn't leap to mind
    def _restart_thread(self, name, old_t):
        del self.threads[name]

        if isinstance(old_t, PollerThread):
            t = PollerThread(self.config, old_t.device, self.persistq)
        elif isinstance(old_t, PersistThread):
            t = PersistThread(self.config, self.persistq)

        self._start_thread(name, t)

    def stop_polling(self, signum, frame):
        self.log.info("stopping (signal: %d)" % (signum, ))
        self.running = False

    def shutdown(self):
        self.log.info("shutting down")

        for n,t in self.threads.iteritems():
            if n == 'persist_thread':
                continue
            t.stop()

        for n,t in self.threads.iteritems():
            if n == 'persist_thread':
                continue
            self.log.debug("joining %s" % t.getName())
            t.join()

        self.log.info("draining persistq: %d items remain" % (
            self.persistq.qsize(), ))
        self.persistq.join()
        self.log.info("sucessful shutdown: exiting")

    def empty_penalty_box(self, signum=None, frame=None):
        self.log.info("emptying penalty box")
        for child in self.children.itervalues():
            if child.is_penalized():
                self.log.debug("unpenalizing %s" % child.name)
                self.start_thread(child)

        self.last_penalty_empty = time.time()

class PollManager(object):
    """Starts a polling process for each device"""

    def __init__(self, name, opts, args, config):
        self.name = name
        self.opts = opts
        self.args = args
        self.config = config
        
        self.hostname = socket.gethostname()

        self.root_pid = os.getpid()

        self.log = get_logger(self.name)

        self.running = False
        self.last_reload = time.time()
        self.last_penalty_empty = time.time()

        self.reload_interval = 30
        self.penalty_interval = 300

        esxsnmp.sql.setup_db(self.config.db_uri)

        self.devices = self._get_devices()

        self.children = {}       # maps name to PollerThread instance
        self.child_pid_map = {}  # maps child pid to child name

        if not tsdb.TSDB.is_tsdb(None, self.config.tsdb_root):
            tsdb.TSDB.create(self.config.tsdb_root,
                chunk_prefixes=self.config.tsdb_chunk_prefixes)

    def _get_devices(self):
        d = {}
        session = esxsnmp.sql.Session()

        if self.config.polling_tag:
            extra = """
                AND device.id IN
                    (SELECT deviceid
                        FROM devicetagmap
                       WHERE devicetagid =
                       (SELECT devicetag.id
                          FROM devicetag
                         WHERE name = '%s'))
            """ % self.config.polling_tag
        else:
            extra = ''

        devices = session.query(
            esxsnmp.sql.Device).filter("""
                active = 't' 
                AND end_time > 'NOW'""" + extra)

        for device in devices:
            d[device.name] = device

        session.close()

        return d

    def start_polling(self):
        """Begin polling all routers for all OIDSets"""
        self.log.debug("starting, %d devices configured" % len(self.devices))

        signal.signal(signal.SIGINT, self.stop_polling)
        signal.signal(signal.SIGTERM, self.stop_polling)
        signal.signal(signal.SIGHUP, self.empty_penalty_box)
        self.running = True

        self._start_all_devices()

        while self.running:
            if len(self.child_pid_map.keys()) > 0:
                try:
                    (rpid,status) = os.waitpid(0, os.WNOHANG)
                except OSError, e:
                    if e.errno == errno.EINTR:
                        self.log.debug("ignoring EINTR")
                        continue
                    else:
                        raise

                if rpid != 0 and self.running:
                    # need to check self.running again, because we might be shutting down
                    if self.child_pid_map.has_key(rpid):
                        self.log.warn("%s, pid %d died" % (
                            self.children[self.child_pid_map[rpid]].name, rpid))
                        child = self.children[self.child_pid_map[rpid]]
                        del self.child_pid_map[rpid]
                        if child.is_spinning():
                            child.penalize()
                            self.log.error("putting %s in penalty box" % child.name)
                        elif child.is_removed():
                            del self.children[child.name]
                        else:
                            self.log.debug("%s has spun %d times %f %d" %
                                (child.name, child.spin_cycles,
                                    child.last_restart, child.state))
                            self._start_child(child)

            if time.time() - self.last_reload > self.reload_interval:
                self.reload(None, None)

            if time.time() - self.last_penalty_empty > self.penalty_interval:
                self.empty_penalty_box()

            time.sleep(5)

        self.shutdown()

    def _start_device(self, device):
        self._start_child(PollerThread(self.config, device))

    def _stop_device(self, device):
        try:
            child = self.children[device.name]
        except KeyError:
            return
        self._stop_child(child)

    def _restart_device(self, device):
        child = self.children[device.name]
        child.device = device
        self._kill_child(child)
        # the main loop will restart the child

    def _start_all_devices(self):
        for device in self.devices.itervalues():
            self._start_device(device)

    def _start_child(self, child):
        self.children[child.name] = child
        # close out SQLAlchemy state
        esxsnmp.sql.engine.dispose()
        pid = os.fork()
        if pid:
            self.child_pid_map[pid] = child.name
            self.log.info("%s started, pid %d" % (child.name,pid))
            child.record(pid)
        else:
            setproctitle("espolld: %s" % child.name)
            child.run()

    def _stop_child(self, child):
        child.remove()
        self._kill_child(child)

    def _kill_child(self, child):
        if child.pid:
            try:
                os.kill(child.pid, signal.SIGTERM)
            except OSError, e:
                self.log.info("tried to kill a dead pid %d, %s: %s" %
                        (child.pid, child.name, e.strerror))

    def _stop_all_children(self):
        for child in self.children.itervalues():
            self._stop_child(child)

    def empty_penalty_box(self):
        self.log.info("emptying penalty box")
        for child in self.children.itervalues():
            if child.is_penalized():
                self.log.debug("unpenalizing %s" % child.name)
                self._start_child(child)

        self.last_penalty_empty = time.time()

    def reload(self, sig, frame):
        """Reload the configuration data and stop, start or restart polling
        processes as necessary."""

        self.log.info("reload: %s" % ",".join(self.children.keys()))

        new_devices = self._get_devices()
        new_device_set = sets.Set(new_devices.iterkeys())
        old_device_set = sets.Set(self.devices.iterkeys())

        for name in new_device_set.difference(old_device_set):
            self._start_device(new_devices[name])

        for name in old_device_set.difference(new_device_set):
            self.log.debug("remove device: %s" % name)
            self._remove_device(self.devices[name])

        # XXX should probably move this into PollerThread
        for name in new_device_set.intersection(old_device_set):
            old_device = self.devices[name]
            new_device = new_devices[name]

            if new_device.community != old_device.community:
                self._restart_device(new_device)
                break

            old_oidset = {}
            for oidset in old_device.oidsets:
                old_oidset[oidset.name] = oidset

            new_oidset = {}
            for oidset in new_device.oidsets:
                new_oidset[oidset.name] = oidset

            old_oidset_names = sets.Set(old_oidset.iterkeys())
            new_oidset_names = sets.Set(new_oidset.iterkeys())

            restart = False
            child = self.children[name]

            for oidset_name in new_oidset_names.difference(old_oidset_names):
                self.log.debug("start oidset: %s %s" % (new_device.name, oidset_name))
                child.add_oidset(new_device, new_oidset[oidset_name])
                restart = True

            for oidset_name in old_oidset_names.difference(new_oidset_names):
                self.log.debug("remove oidset: %s %s" % (old_device.name, oidset_name))
                child.remove_oidset(old_device, old_oidset[oidset_name])
                restart = True

            if restart:
                self._restart_device(new_device)


        self.devices = new_devices
        self.last_reload = time.time()

    def stop_polling(self, signum, frame):
        self.log.info("shutting down (signal: %d)" % (signum, ))
        self.running = False

    def shutdown(self):
        self._stop_all_children()
        self.log.info("exiting")
        sys.exit()

    def __del__(self):
        if os.getpid() == self.root_pid and len(self.child_pid_map.keys()) > 0:
            self.shutdown()


class Poller(object):
    """The Poller class is the base for all pollers.

    It provides a simple interface for subclasses:

      begin()            -- called immediately before polling
      collect(oid, data) -- called immediately before polling
      finish()           -- called immediately after polling

    All three methods MUST be defined by the subclass.

    """
    def __init__(self, config, device, oidset, persistq):
        self.config = config
        self.device = device
        self.oidset = oidset
        self.persistq = persistq

        self.name = "espolld." + self.device.name + "." + self.oidset.name

        self.next_poll = int(time.time() - 1)
        self.oids = self.oidset.oids
        self.running = True
        self.log = get_logger(self.name)

        try:
            self.snmp_session = yapsnmp.Session(self.device.name, version=2,
                community=self.device.community)
        except socket.gaierror, e:
            raise PollerError("host %s unknown: %s" % (self.device.name,
                str(e)))

        self.count = 0
        self.errors = 0

        self.poller_args = {}
        if self.oidset.poller_args is not None:
            for arg in self.oidset.poller_args.split():
                (var,val) = arg.split('=')
                self.poller_args[var] = val

        self.polling_round = 0

    def run_once(self):
        if self.time_to_poll():
            self.log.debug("grabbing data")
            begin = time.time()
            self.next_poll = begin + self.oidset.frequency

            try:
                self.begin()

                for oid in self.oids:
                    self.collect(oid,self.snmp_session.walk(oid.name))

                self.finish()

                self.log.debug("grabbed %d vars in %f seconds yay" %
                        (self.count, time.time() - begin))
                self.errors = 0
            except yapsnmp.GetError, e:
                self.errors += 1
                if self.errors < 10  or self.errors % 10 == 0:
                    self.log.error("unable to get snmp response after %d tries: %s" % (self.errors, e))

            self.polling_round += 1

    def run(self):
        while self.running:
            self.run_once()

            # XXX kludge hack ick!  exit after 480 cycles as
            # a workaround for a memeory leak
            if self.polling_round >= 480:
                self.shutdown()
                sys.exit()

            self.sleep()

        self.shutdown()

    def begin(self):
        """begin is called immeditately before polling is started.  this is
        where you should set up things and collect information needed during
        the run."""

        raise NotImplementedError("must implement begin method")

    def collect(self, oid, data):
        """collect is called for each oid in the oidset with the oid and data
        collected for the oid from the device"""

        raise NotImplementedError("must implement collect method")

    def finish(self):
        """finish is called immediately after polling is done.  any
        finalization code should go here."""

        raise NotImplementedError("must implement finish method")

    def shudown(self):
        """shutdown is called as the poller is shutting down
        it can be used to flush unwritten data before exiting."""
        pass

    def time_to_poll(self):
        return time.time() >= self.next_poll

    def seconds_until_next_poll(self):
        return int(self.next_poll - time.time())

    def sleep(self):
        delay = self.next_poll - int(time.time())

        if delay >= 0:
            time.sleep(delay)
        else:
            self.log.warning("poll %d seconds late" % abs(delay)) 

class TSDBPoller(Poller):
    def __init__(self, config, device, oidset, persistq):
        Poller.__init__(self, config, device, oidset, persistq)

        if self.config.tsdb_chunk_prefixes:
            self.tsdb = tsdb.TSDB(self.config.tsdb_root)
        else:
            self.tsdb = tsdb.TSDB(self.config.tsdb_root)

        set_name = "/".join((self.device.name, self.oidset.name))
        try:
            self.tsdb_set = self.tsdb.get_set(set_name)
        except tsdb.TSDBSetDoesNotExistError:
            self.tsdb_set = self.tsdb.add_set(set_name)

    def begin(self):
        pass

    def collect(self, oid, data):
        ts = time.time()
        metadata = dict(tsdb_flags=tsdb.ROW_VALID)
        outdata = []

        if oid.name == '.1.3.6.1.4.1.21013.1.2.12.1.2.22':
            print "booyah"
            for x in data:
                outdata.append((x[0].replace('.1.3.6.1.4.1.21013.1.2.12.1.2.22',
                    'globalNumStations'), x[1]))
                
        pr = PollResult(self.oidset.name, self.device.name, oid.name,
                    ts, outdata, metadata)

        self.persistq.put(pr)

    def finish(self):
        pass

class SQLPoller(Poller):
    def __init__(self, config, device, oidset, persistq):
        Poller.__init__(self, config, device, oidset, persistq)

#
# XXX are the oidset, etc vars burdened with sqlalchemy goo? if so, does it
# matter?
#
class CorrelatedTSDBPoller(TSDBPoller):
    """Handles polling of an OIDSet for a device and uses a correlator to
    determine the name of the variable to use to store values."""
    def __init__(self, config, device, oidset, persistq):
        TSDBPoller.__init__(self, config, device, oidset, persistq)

        self.correlator = eval(self.poller_args['correlator'])(self.snmp_session)

        if self.poller_args.has_key('aggregates'):
            self.aggregates = self.poller_args['aggregates'].split(',')
        else:
            self.aggregates = None

        self.results = {}

    def begin(self):
        self.count = 0
        self.correlator.setup()  # might raise a yapsnmp.GetError

    def collect(self, oid, data):
        self.count += len(data)
        ts = time.time()
        dataout = []
        metadata = dict(tsdb_flags=tsdb.ROW_VALID)

        for (var,val) in data:
            try:
                varname = self.correlator.lookup(oid,var)
            except PollUnknownIfIndex:
                self.log.error("unknown ifIndex: %s %s" % (var, str(val)))
                continue

            if varname:
                dataout.append((varname, val))
            else:
                if val != "0":
                    self.log.error("ignore: %s %s" % (var, str(val)))

        pr = PollResult(self.oidset.name, self.device.name, oid.name,
                    ts, dataout, metadata)

        self.persistq.put(pr)

    def finish(self):
        pass

class IfRefSQLPoller(SQLPoller):
    """Polls all OIDS and creates a IfRef entry then sees if the IfRef entry
    differs from the lastest in the database."""

    def __init__(self, config, device, oidset, persistq):
        SQLPoller.__init__(self, config, device, oidset, persistq)
        self.ifref_data = {}

    def begin(self):
        self.count = 0

    def collect(self, oid, data):
        self.ifref_data[oid.name] = data
        self.count += len(self.ifref_data[oid.name])

    def finish(self):
        self.store()

    def store(self):
        ts = time.time()
        pr = PollResult(self.oidset.name, self.device.name, "",
                ts, self.ifref_data, {})

        self.persistq.put(pr)

def espoll():
    argv = sys.argv
    oparse = get_opt_parser(default_config_file=get_config_path())
    oparse.add_option("-D", "--device", dest="device", default=None)
    oparse.add_option("-o", "--oid-set", dest="oidset", default=None)
    (opts, args) = oparse.parse_args(args=argv)

    try:
        config = get_config(opts.config_file, opts)
    except ConfigError, e:
        print e
        sys.exit(1)

    esxsnmp.sql.setup_db(config.db_uri)
    session = esxsnmp.sql.Session()

    devices = session.query(esxsnmp.sql.Device)
    if opts.device:
        device = devices.filter(esxsnmp.sql.Device.name == opts.device).one()

    if not device:
        print "no devices selected"
        sys.exit(1)

    print device.name

    oidset = session.query(esxsnmp.sql.OIDSet)
    oidset = oidset.filter(esxsnmp.sql.OIDSet.name == opts.oidset).one()

    if not oidset:
        print "no oidset selected"
        sys.exit(1)

    print "%s %s" % (device.name, oidset.name)

    persistq = Queue.Queue()
    poller_class = eval(oidset.poller.name)
    try:
        poller = poller_class(config, device, oidset, persistq)
    except PollerError, e:
        print str(e)

    poller.run_once()

    while True:
        try:
            print persistq.get_nowait().data
        except Queue.Empty:
            break

def espolld():
    """Entry point for espolld."""
    argv = sys.argv
    oparse = get_opt_parser(default_config_file=get_config_path())
    (opts, args) = oparse.parse_args(args=argv)

    try:
        config = get_config(opts.config_file, opts)
    except ConfigError, e:
        print e
        sys.exit(1)

    init_logging(config.syslog_facility, level=config.syslog_level,
            debug=opts.debug)

    name = "espolld.manager"

    setproctitle(name)

    if not opts.debug:
        exc_handler = setup_exc_handler(name, config)
        exc_handler.install()

        daemonize(name, config.pid_dir, log_stdout_stderr=exc_handler.log)

    os.umask(0022)

    poller = ThreadedPollManager(name, opts, args, config)
    poller.start_polling()

