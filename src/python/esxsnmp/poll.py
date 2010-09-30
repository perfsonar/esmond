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
from DLNetSNMP import SNMPManager, oid_to_str, str_to_oid, SnmpError
import rrdtool
from pympler.muppy import summary, tracker
from pympler.heapmonitor import _memory_ps, _memory_generic

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

class PollError(Exception):
    pass

class PollUnknownIfIndex(PollError):
    pass

def filter_data(name, data):
    return filter(lambda x: x[0].startswith(name), data)

class PollCorrelator(object):
    """polling correlators correlate an oid to some other field.  this is
    typically used to generate the key needed to store the variable."""

    def __init__(self):
        pass

    def setup(self, data):
        raise NotImplementedError

    def lookup(self, oid, var):
        raise NotImplementedError

    def _table_parse(self, data):
        d = {}
        for (var, val) in data:
            d[var.split('.')[-1]] = remove_metachars(val)
        return d

class IfDescrCorrelator(PollCorrelator):
    """correlates an IfIndex to an it's IfDescr"""

    oids = ['ifDescr', 'ifAlias']

    def setup(self, data, ignore_no_ifalias=True):
        self.xlate = self._table_parse(filter_data('ifDescr', data))

        if ignore_no_ifalias:
            for (var,val) in filter_data('ifAlias', data):
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

class InfIfDescrCorrelator(PollCorrelator):
    """correlates an IfIndex to it's IfDescr with Infinera tweaks.
    
    On the Infinera the tables only contain entries if an interface is
    configured so we want to collect them all, but ifAlias is not set."""

    oids = ['ifDescr']

    def setup(self, data):
        self.xlate = self._table_parse(filter_data('ifDescr', data))

    def lookup(self, oid, var):
        # XXX this sucks
        if oid.name == 'sysUpTime':
            return 'sysUpTime'

        ifIndex = var.split('.')[-1]

        try:
            r = self.xlate[ifIndex]
        except KeyError:
            raise PollUnknownIfIndex(ifIndex)

        if '=' in r:
            r = r.split('=')[1]

        return "/".join((oid.name, r))

class ALUIfDescrCorrelator(IfDescrCorrelator):
    """correlates an IfIndec to it's IfDescr with ALU tweaks.
    
    The ALU doesn't store the interface description in ifAlias like a normal
    box."""

    def setup(self, data, ignore_no_ifalias=False):
        IfDescrCorrelator.setup(self, data, ignore_no_ifalias)

class JnxFirewallCorrelator(PollCorrelator):
    """correlates entries in the jnxFWCounterByteCount tables to a variable
    name"""

    oids = []

    def __init__(self):
        PollCorrelator.__init__(self)
        self.oidex = re.compile('([^"]+)\."([^"]+)"\."([^"]+)"\.(.+)')

    def setup(self, data):
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
    def __init__(self):
        PollCorrelator.__init__(self)
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

    oids = ['cpmCPUTotalPhysicalIndex', 'entPhysicalName']

    def setup(self):
        self.phys_xlate = self._table_parse(
                filter_data('cpmCPUTotalPhysicalIndex', data))
        self.name_xlate = self._table_parse(
                filter_data('entPhysicalName', data))

    def lookup(self, oid, var):
        #
        # this should only raise an exception of there aren't entries in the
        # tables, meaning that this box has only one CPU
        #
        n = self.name_xlate[self.phys_xlate[var.split('.')[-1]]].replace('CPU_of_','')
        if n == '':
            n = 'CPU'
        return "/".join((oid.name,n))

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
                self.persistq.task_done()

    def stop(self):
        self.state = self.REMOVE

class PollManager(object):
    """Manage polling and sending data to be persisted.

    The main polling is done asynchronously in the main thread.  There is a
    second thread which handles the interactions with the persistence
    system."""

    def __init__(self, name, opts, args, config):
        self.name = name
        self.opts = opts
        self.args = args
        self.config = config
        
        self.hostname = socket.gethostname()

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
        self.orig_mem = _memory_ps()
        self.snmp_poller = AsyncSNMPPoller(config=self.config,
                name="espolld.snmp_poller")
        self.pollers = {}

    def start_polling(self):
        self.log.debug("starting, %d devices configured" % len(self.devices))

        signal.signal(signal.SIGINT, self.stop_polling)
        signal.signal(signal.SIGTERM, self.stop_polling)
        self.running = True

        self.threads = {}
        t = PersistThread(self.config, self.persistq)
        
        self._start_thread('persist_thread', t)

        for device in self.devices.itervalues():
            try:
                self.snmp_poller.add_session(device.name, device.community)
            except PollerError, e:
                self.log.error(str(e))
                continue
            for oidset in device.oidsets:
                poller_class = eval(oidset.poller.name)
                try:
                    poller = poller_class(self.config, device, oidset,
                            self.snmp_poller, self.persistq)
                except PollerError, e: # XXX double check error handing
                    self.log.error(str(e))
                    continue

                self.pollers["%s_%s" % (device.name, oidset.name)] = poller
                self.log.debug("added %s %s" % (device.name, oidset.name))

        # XXX memory debugging
        #self.tracker = tracker.SummaryTracker()
        #self.summary0 = self.tracker.s0
        self.last_tracker = time.time()

        while self.running:
            for poller in self.pollers.itervalues():
                poller.run_once()

            # XXX memory debugging
            if time.time() - self.last_tracker > 90:
                #diff = self.tracker.diff(self.summary0)
                mem = _memory_ps()
                self.log.info("mem: %d delta %d" % (mem, mem-self.orig_mem))
                #for i in diff:
                #    self.log.debug("mem: %s %d %d" % tuple(i))
                self.last_tracker = time.time()

            time.sleep(5)

        self.shutdown()

    def _start_thread(self, name, t):
        t.setDaemon(True)
        t.setName(name)
        self.threads[name] = t
        self.log.debug("started thread %s" % name)
        t.start()

    def stop_polling(self, signum, frame):
        self.log.info("stopping (signal: %d)" % (signum, ))
        self.running = False

    def shutdown(self):
        self.log.info("shutting down")

        self.log.info("draining persistq: %d items remain" % (
            self.persistq.qsize(), ))
        self.persistq.join()
        self.log.info("sucessful shutdown: exiting")


class Poller(object):
    """The Poller class is the base for all pollers.

    It provides a simple interface for subclasses:

      begin()            -- called immediately before polling
      collect(oid, data) -- called to perform poll
      finish()           -- called immediately after polling

    All three methods MUST be defined by the subclass.

    """
    def __init__(self, config, device, oidset, poller, persistq):
        self.config = config
        self.device = device
        self.oidset = oidset
        self.poller = poller
        self.persistq = persistq

        self.name = "espolld." + self.device.name + "." + self.oidset.name

        self.next_poll = int(time.time() - 1)
        self.oids = self.oidset.oids
        # in some pollers we poll oids beyond the ones which are used
        # for that poller, so we make a copy in poll_oids
        self.poll_oids = [o.name for o in self.oids]
        self.running = True
        self.log = get_logger(self.name)

        self.count = 0
        self.errors = 0

        self.poller_args = {}
        if self.oidset.poller_args is not None:
            for arg in self.oidset.poller_args.split():
                (var,val) = arg.split('=')
                self.poller_args[var] = val

        self.polling_round = 0

    def __str__(self):
        return '<%s: %s %s>' % (self.__name__, self.device.name,
                self.oidset.name)

    def run_once(self):
        if self.time_to_poll():
            self.log.debug("grabbing data")
            self.begin_time = time.time()
            self.next_poll = self.begin_time + self.oidset.frequency

            self.begin()
            self.collect()

            self.polling_round += 1

    def begin(self):
        """begin is called immeditately before polling is started. 
        
        Sets up things and gets ready for the polling to begin.  In
        particular self.poll_oids should have all the oids that you need for
        the whole run."""

        raise NotImplementedError("must implement begin method")

    def collect(self):
        """collect called once to collect all the OIDs.
        
        Once it all the OIDs have been collected, the finish() method is
        called with the data.  If collect encounters erros the error() method
        is called."""

        self.poller.bulkwalk(self.device.name, self.poll_oids, self.finish,
                self.error)

    def finish(self, data):
        """finish is called once all the data has been retrieved.

        finish() procesess the data and calls save() with the PollResult(s) for
        this polling round it off to be saved."""

        raise NotImplementedError("must implement finish method")

    def error(self, error):
        """error is called if there is an error or a timeout while polling.

        No data will be saved if an error is encountered.  Errors are hard
        failures; every effort is made to recover rather than call error()."""
        self.log.error(error)

    def save(self, pr):
        """Save PollResults."""
        self.persistq.put(pr)

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
    def __init__(self, config, device, oidset, poller, persistq):
        Poller.__init__(self, config, device, oidset, poller, persistq)

    def begin(self):
        pass

    def finish(self, data):
        ts = time.time()
        metadata = dict(tsdb_flags=tsdb.ROW_VALID)

        for oid in self.oidset:
            outdata = filter_data(oid.name, data)

            pr = PollResult(self.oidset.name, self.device.name, oid.name,
                    ts, outdata, metadata)

            self.save(pr)

class CorrelatedTSDBPoller(TSDBPoller):
    """Handles polling of an OIDSet for a device and uses a correlator to
    determine the name of the variable to use to store values."""
    def __init__(self, config, device, oidset, poller, persistq):
        TSDBPoller.__init__(self, config, device, oidset, poller, persistq)

        self.correlator = eval(self.poller_args['correlator'])()
        self.poll_oids.extend(self.correlator.oids)

        self.results = {}

    def begin(self):
        pass

    def finish(self, data):
        self.correlator.setup(data)

        ts = time.time()
        metadata = dict(tsdb_flags=tsdb.ROW_VALID)

        for oid in self.oidset.oids:
            dataout = []
            for var, val in filter_data(oid.name, data):
                try:
                    varname = self.correlator.lookup(oid, var)
                except PollUnknownIfIndex:
                    self.log.error("unknown ifIndex: %s %s" % (var, str(val)))
                    continue

                if varname:
                    dataout.append((varname, val))
                else:
                    if val != 0:
                        pass
                        #self.log.warning("ignoring: %s %s" % (var, str(val)))

            pr = PollResult(self.oidset.name, self.device.name, oid.name,
                    ts, dataout, metadata)

            self.save(pr)

        self.log.debug("grabbed %d vars in %f seconds" %
                        (len(data), time.time() - self.begin_time))


class SQLPoller(Poller):
    def __init__(self, config, device, oidset, poller, persistq):
        Poller.__init__(self, config, device, oidset, poller, persistq)

class IfRefSQLPoller(SQLPoller):
    """Polls all OIDS and creates a IfRef entry then sees if the IfRef entry
    differs from the lastest in the database."""

    def __init__(self, config, device, oidset, poller, persistq):
        SQLPoller.__init__(self, config, device, oidset, poller, persistq)

    def begin(self):
        self.count = 0

    def finish(self, data):
        self.count = len(data)

        ifref_data = {}
        for oid in self.oidset.oids:
            ifref_data[oid.name] = filter_data(oid.name, data)

        pr = PollResult(self.oidset.name, self.device.name, "",
                time.time(), ifref_data, {})

        self.save(pr)

class PollRequest(object):
    def __init__(self, type, callback, errback, walk_oid=None,
            additional_oids=[]):
        self.type = type
        self.callback = callback
        self.errback = errback
        self.walk_oid = walk_oid
        self.additional_oids = additional_oids

        self.results = []

    def append(self, oid, value):
        self.results.append((oid, value))

class AsyncSNMPPoller(object):
    """Manage all polling requests and responses.

    AsyncPoller manages all the polling using DLNetSNMP."""

    def __init__(self, config=None, name="AsyncSNMPPoller", maxrepetitions=25):
        self.maxrepetitions = maxrepetitions
        self.name = name
        self.config = config

        self.reqmap = {}

        self.sessions = SNMPManager(local_dir="/usr/local/share/snmp",
                threaded_processor=True)

        self.log = get_logger(self.name)

        if self.config:
            for mib_dir in self.config.mib_dirs:
                self.log.info("add mib dir %s" % mib_dir)
                self.sessions.add_mib_dir(mib_dir)
            self.sessions.refresh_mibs()

            for mib in self.config.mibs:
                self.log.info("add mib %s" % mib)
                self.sessions.read_module(mib)

        self.sessions.bind('response', '1', None, self._callback)
        self.sessions.bind('timeout', '1', None, self._errback)

    def add_session(self, host, community, version='2', timeout=10,
            retries=1):
        try:
            self.sessions.add_session(host, peername=host, community=community,
                version=version, timeout=timeout, retries=retries,
                results_as_list=True)
        except SnmpError, e:
            raise PollerError(str(e))

    def shutdown(self):
        self.sessions.destroy() # BWAHAHAHAH

    def bulkwalk(self, host, oids, callback, errback):
        """Gathers all rows for the given objects in a table.

        A single SNMP GETBULK is not guaranteed to get all the objects
        referred to by the OID in a table.  `bulkwalk` implements a simple
        mechanism for gathering all rows for the given OIDs using GETBULK
        messages multiple times if necessary."""

        try:
            session = self.sessions[host]
        except KeyError:
            raise PollerError("no session defined for %s" % host)

        oids = [ o for o in oids ]  # make a copy of the oids list

        oid = oids.pop(0)
        #print "oid >%s<" % (oid)
        noid = str_to_oid(oid) # avoid the noid!
        if noid is None:
            # XXX tell someone: raise exception?
            self.log.error("unable to resolve OID: %s" % oid)
            return
        noid = tuple(noid)

        pollreq = PollRequest('bulkwalk', callback, errback,
                walk_oid=noid, additional_oids=oids)
        reqid = self.sessions[host].async_getbulk(0, self.maxrepetitions, [oid])
        self.reqmap[reqid] = pollreq

    def bulkget(self, host, nonrepeaters, maxrepetitions, oids, callback,
            errback):
        pollreq = PollRequest('bulkget', callback, errback)
        reqid = sessions[host].async_getbulk(nonrepeaters, maxrepetitions, oids)
        self.reqmap[reqid] = pollreq

    def get(self, host, oids, callback, errback):
        pollreq = PollRequest('get', callback, errback)
        reqid = sessions[host].async_get(oids)
        self.reqmap[reqid] = pollreq

    # ***
    # *** these methods execute inside the DLNetSNMP session processing thread
    # ***

    def _callback(self, manager, slot, session, reqid, r):
        """_callback manages reponses, performing coalescing for bulkwalks."""

        pollreq = self.reqmap[reqid]

        #print "_callback yo!", pollreq.type, len(r)

        if len(r) == 0:
            #print "_callback NO DATA!!!?!?!?! WTF?!?!?!?!"
            return

        if pollreq.type != 'bulkwalk':
            pollreq.callback(r)
            #print "_callback wtf!"
        else:
            last = ''
            done = False
            for last, v in r:
                if last[:len(pollreq.walk_oid)] != pollreq.walk_oid:
                    done = True
                    break

                soid = oid_to_str(last).split('::')[-1]
                pollreq.results.append((soid, v))

            if done:
                #print '_callback bulkwalk done', last
                if pollreq.additional_oids:
                    #print "MORE", pollreq.additional_oids
                    oid = pollreq.additional_oids.pop(0)
                    #print "2>%s<" % oid
                    pollreq.walk_oid = tuple(str_to_oid(oid))
                    new_reqid = self.sessions[session].async_getbulk(0,
                        self.maxrepetitions, [oid])
                    self.reqmap[new_reqid] = pollreq
                else:
                    pollreq.callback(pollreq.results)
            else:
                #print '_callback bulkwalk not done', last, oid_to_str(last)
                # get more data
                new_reqid = self.sessions[session].async_getbulk(0,
                    self.maxrepetitions, [last])
                self.reqmap[new_reqid] = pollreq

        del self.reqmap[reqid]

    def _errback(self, manager, slot, session, reqid):
        pollreq = self.reqmap[reqid]

        del self.reqmap[reqid]

        # XXX look into getting actual error messages
        pollreq.errback("timeout")

def espoll():
    argv = sys.argv
    oparse = get_opt_parser(default_config_file=get_config_path())
    oparse.usage = "%prog [options] router oidset"
    (opts, args) = oparse.parse_args(args=argv)

    if len(args[1:]) != 2:
        oparse.error("requires router and oidset arguments")

    device_name, oidset_name = args[1:]

    try:
        config = get_config(opts.config_file, opts)
    except ConfigError, e:
        print e
        sys.exit(1)

    init_logging(config.syslog_facility, level=config.syslog_priority,
            debug=opts.debug)

    esxsnmp.sql.setup_db(config.db_uri)
    session = esxsnmp.sql.Session()

    devices = session.query(esxsnmp.sql.Device)
    device = devices.filter(esxsnmp.sql.Device.name == device_name).one()
    if not device:
        print >>sys.stderr, "unknown device: %s" % device_name
        sys.exit(1)

    oidset = session.query(esxsnmp.sql.OIDSet)
    oidset = oidset.filter(esxsnmp.sql.OIDSet.name == oidset_name).one()

    if not oidset:
        print >>sys.stderr, "unknown OIDSet: %s %s" % (device.name,
                oidset_name) 
        sys.exit(1)

    snmp_poller = AsyncSNMPPoller(config=config)
    snmp_poller.add_session(device.name, device.community)

    print "%s %s" % (device.name, oidset.name)

    persistq = Queue.Queue()
    poller_class = eval(oidset.poller.name)
    try:
        poller = poller_class(config, device, oidset, snmp_poller, persistq)
    except PollerError, e:
        print str(e)

    poller.run_once()

    time.sleep(12)

    print "and the queue has:"
    while True:
        try:
            print persistq.get_nowait().data
        except Queue.Empty:
            break

    snmp_poller.shutdown()

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

    init_logging(config.syslog_facility, level=config.syslog_priority,
            debug=opts.debug)

    name = "espolld.manager"

    setproctitle(name)

    if not opts.debug:
        exc_handler = setup_exc_handler(name, config)
        exc_handler.install()

        daemonize(name, config.pid_dir,
                log_stdout_stderr=config.syslog_facility)

    os.umask(0022)

    poller = PollManager(name, opts, args, config)
    poller.start_polling()

