#!/usr/bin/env python

import os
import signal
import errno
import sys
import time
import re
import sets

import sqlalchemy
import yapsnmp

import tsdb

import esxsnmp.sql

from esxsnmp.util import setproctitle, get_logger, remove_metachars
from esxsnmp.util import daemonize, setup_exc_handler
from esxsnmp.config import get_opt_parser, get_config, get_config_path
from esxsnmp.error import ConfigError
from esxsnmp.rpc.ttypes import IfRef

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
        self.xlate = {}
        for (var,val) in self.session.walk("ifDescr"):
            self.xlate[var.split(".")[-1]] = remove_metachars(val)

    def lookup(self, oid, var):
        # XXX this sucks
        if oid.name == 'sysUpTime':
            return 'sysUpTime'

        ifIndex = var.split('.')[-1]
        try:
            return "/".join((oid.name, self.xlate[ifIndex]))
        except:
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

class PollerChild(object):
    """Container for info about children of the main polling process"""

    SPIN_CYCLE_PERIOD = 30
    MAX_SPIN_CYCLES = 3

    NEW = 0
    RUN = 1
    PENALTY = 2
    REMOVE = 3

    def __init__(self, config, poller, name, device, oidset):
        self.config = config
        self.poller = poller
        self.name = name
        self.device = device
        self.oidset = oidset
        self.pid = None
        self.last_restart = 0
        self.spin_cycles = 0
        self.state = PollerChild.NEW

    def record(self, pid):
        self.pid = pid
        now = time.time()
        if now - self.last_restart < self.SPIN_CYCLE_PERIOD:
            self.spin_cycles += 1
        else:
            self.spin_cycles = 0

        self.last_restart = now
        self.state = PollerChild.RUN

    def run(self):
        self.poller(self.config, self.name, self.device, self.oidset).run()

    def is_spinning(self):
        return self.spin_cycles >= PollerChild.MAX_SPIN_CYCLES

    def is_penalized(self):
        return self.state == PollerChild.PENALTY

    def is_removed(self):
        return self.state == PollerChild.REMOVE

    def penalize(self):
        """Put this child in the penalty box."""
        self.state = PollerChild.PENALTY
        self.pid = None

    def remove(self):
        self.state = PollerChild.REMOVE

class PollManager(object):
    """Starts a polling process for each device"""

    def __init__(self, name, opts, args, config):
        self.name = name
        self.opts = opts
        self.args = args
        self.config = config

        self.log = get_logger(self.name, config.syslog_facility)

        self.running = False
        self.last_reload = time.time()
        self.last_penalty_empty = time.time()

        self.reload_interval = 10
        self.penalty_interval = 45

        esxsnmp.sql.setup_db(self.config.db_uri)

        self.devices = self._get_devices()

        self.children = {}       # maps name to PollerChild instance
        self.child_pid_map = {}  # maps child pid to child name


        if not tsdb.TSDB.is_tsdb(self.config.tsdb_root):
            tsdb.TSDB.create(self.config.tsdb_root)

    def _get_devices(self):
        d = {}
        session = esxsnmp.sql.Session()

        devices = session.query(
                esxsnmp.sql.Device).select("active = 't' AND end_time > 'NOW'")

        for device in devices:
            d[device.name] = device

        session.close()

        return d

    def start_polling(self):
        """Begin polling all routers for all OIDSets"""
        self.log.debug("starting")

        signal.signal(signal.SIGINT, self.stop_polling)
        signal.signal(signal.SIGTERM, self.stop_polling)
        signal.signal(signal.SIGHUP, self.empty_penalty_box)
        self.running = True

        self._start_all_devices()

        while self.running:
            self.log.debug("waiting for a child to die (how morbid!)")
            if len(self.child_pid_map.keys()) > 0:
                try:
                    (rpid,status) = os.waitpid(0, os.WNOHANG)
                except OSError, e:
                    if e.errno == errno.EINTR:
                        self.log.debug("ignoring EINTR")
                        continue
                    else:
                        raise

                if rpid != 0 and self.running: # need to check self.running again, because wait blocks
                    if self.child_pid_map.has_key(rpid):
                        self.log.warn("%s, pid %d died" % (self.children[self.child_pid_map[rpid]].name, rpid))
                        child = self.children[self.child_pid_map[rpid]]
                        del self.child_pid_map[rpid]
                        self.log.debug("%s has spun %d times %f" %
                                (child.name, child.spin_cycles,
                                    child.last_restart))
                        if child.is_spinning():
                            child.penalize()
                            self.log.error("putting %s in penalty box" % child.name)
                        elif child.is_removed():
                            del self.children[child.name]
                        else:
                            self._start_child(child)

            if time.time() - self.last_reload > self.reload_interval:
                self.reload(None, None)

            if time.time() - self.last_penalty_empty > self.penalty_interval:
                self.empty_penalty_box()

            time.sleep(5)

        self.shutdown()

    def _get_child_by_name(self, name):
        for child in self.children.itervalues():
            if child.name == name:
                return child
        
        return None

    def _get_children_by_device(self, device):
        return filter(
                lambda x: x.name == device.name,
                self.children.itervalues())

    def _start_oidset(self, device, oidset):
        poller = eval(oidset.poller.name) # what kind of poller do we need for this OIDSet?
        name = device.name + "_" + oidset.name
        self._start_child(PollerChild(self.config, poller, name, device, oidset))

    def _stop_oidset(self, device, oidset):
        name = device.name + "_" + oidset.name
        child = self._get_child_by_name(name)
        if child is not None:
            self._stop_child(child)

    def _remove_oidset(self, device, oidset):
        name = device.name + "_" + oidset.name
        self.log.info("removing %s" % (name))
        child = self._get_child_by_name(name)
        if child.state == PollerChild.RUN:
            child.remove()
            self._stop_child(child)
        else: # if the child isn't running just dispose of it
            del self.children[child.name]

    def _start_device(self, device):
        for oidset in device.oidsets:
            self._start_oidset(device, oidset)

    def _stop_device(self, device):
        for child in self._get_children_by_device(device):
            self._stop_child(child)

    def _remove_device(self, device):
        for oidset in device.oidsets:
            self._remove_oidset(device, oidset)

    def _start_all_devices(self):
        for device in self.devices.itervalues():
            self._start_device(device)

    def _start_child(self, child):
        self.children[child.name] = child
        pid = os.fork()
        if pid:
            self.child_pid_map[pid] = child.name
            self.log.info("%s started, pid %d" % (child.name,pid))
            child.record(pid)
        else:
            setproctitle("espolld: %s" % child.name)
            child.run()

    def _stop_child(self, child):
        self.log.info("stopping %s, pid %d" % (child.name, child.pid))
        os.kill(child.pid, signal.SIGTERM)

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

        self.log.info("reload")

        new_devices = self._get_devices()
        new_set = sets.Set(new_devices.iterkeys())
        old_set = sets.Set(self.devices.iterkeys())


        for name in new_set.difference(old_set):
            self._start_device(new_devices[name])

        for name in old_set.difference(new_set):
            self._remove_device(self.devices[name])

        for name in new_set.intersection(old_set):
            old_device = self.devices[name]
            new_device = new_devices[name]

            if new_device.community != old_device.community:
                self._stop_device(old_device)
                self._start_device(new_device)

            old_oidset = {}
            for oidset in old_device.oidsets:
                old_oidset[oidset.name] = oidset

            new_oidset = {}
            for oidset in new_device.oidsets:
                new_oidset[oidset.name] = oidset

            old_oidset_names = sets.Set(old_oidset.iterkeys())
            new_oidset_names = sets.Set(new_oidset.iterkeys())

            for oidset in new_oidset_names.difference(old_oidset_names):
                self._start_oidset(old_device, oidset)

            for oidset in old_oidset_names.difference(new_oidset_names):
                self._remove_oidset(old_device, oidset)

        self.devices = new_devices
        self.last_reload = time.time()

    def stop_polling(self, signum, frame):
        self.log.info("shutting down")
        self.running = False

    def shutdown(self):
        self._stop_all_children()
        self.log.debug("exiting")
        sys.exit()

    def __del__(self):
        if len(self.child_pid_map.keys()) > 0:
            self.shutdown()


class Poller(object):
    """The Poller class is the base for all pollers.

    It provides a simple interface for subclasses:

      begin()            -- called immediately before polling
      collect(oid, data) -- called immediately before polling
      finish()           -- called immediately after polling

    All three methods MUST be defined by the subclass.

    """
    def __init__(self, config, name, device, oidset):
        self.config = config
        self.name = name
        self.device = device
        self.oidset = oidset

        self.next_poll = int(time.time() - 1)
        self.oids = self.oidset.oids
        self.running = True

        self.count = 0
        self.snmp_session = yapsnmp.Session(self.device.name, version=2,
                community=self.device.community)

        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGHUP, self.reload)

        self.log = get_logger("espolld: " + self.name, config.syslog_facility)
        self.errors = 0

        self.poller_args = {}
        if self.oidset.poller_args is not None:
            for arg in self.oidset.poller_args.split():
                (var,val) = arg.split('=')
                self.poller_args[var] = val

    def run(self):
        while self.running:
            if self.time_to_poll():
                self.log.debug("grabbing data")
                begin = time.time()
                self.next_poll = begin + self.oidset.frequency

                try:
                    self.begin()

                    for oid in self.oids:
                        self.collect(oid,self.snmp_session.walk(oid.name))

                    self.finish()

                    self.log.debug("grabbed %d vars in %f seconds" %
                            (self.count, time.time() - begin))
                    self.errors = 0
                except yapsnmp.GetError, e:
                    self.errors += 1
                    if self.errors < 10  or self.errors % 10 == 0:
                        self.log.error("unable to get snmp response after %d tries: %s" % (self.errors, e))

            self.sleep()

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

    def stop(self, signum, frame):
        self.running = False
        self.log.info("stopping")
        sys.exit()

    def reload(self, signum, frame):
        self.log.info("if it was implemented, i'd be reloading")

    def time_to_poll(self):
        return time.time() >= self.next_poll

    def sleep(self):
        delay = self.next_poll - int(time.time())

        if delay >= 0:
            time.sleep(delay)
        else:
            self.log.warning("poll %d seconds late" % abs(delay)) 

class TSDBPoller(Poller):
    def __init__(self, config, name, device, oidset):
        Poller.__init__(self, config, name, device, oidset)

        self.tsdb = tsdb.TSDB(self.config.tsdb_root)

        set_name = "/".join((self.device.name, self.oidset.name))
        try:
            self.tsdb_set = self.tsdb.get_set(set_name)
        except tsdb.TSDBSetDoesNotExistError:
            self.tsdb_set = self.tsdb.add_set(set_name)


class SQLPoller(Poller):
    def __init__(self, config, name, device, oidset):
        Poller.__init__(self, config, name, device, oidset)
        esxsnmp.sql.reconnect()


#
# XXX are the oidset, etc vars burdened with sqlalchemy goo? if so, does it
# matter?
#
class CorrelatedTSDBPoller(TSDBPoller):
    """Handles polling of an OIDSet for a device and uses a correlator to
    determine the name of the variable to use to store values."""
    def __init__(self, config, name, device, oidset):
        TSDBPoller.__init__(self, config, name, device, oidset)

        # this is a little hairy, but ends up with an instance of the
        # correlator class initialized with our snmp_session
        self.correlator = eval(self.poller_args['correlator'])(self.snmp_session)
        self.chunk_mapper = eval(self.poller_args['chunk_mapper'])


    def begin(self):
        self.count = 0
        self.correlator.setup()  # might raise a yapsnmp.GetError

    def collect(self, oid, data):
        self.count += len(data)
        self.store(oid, data)

    def finish(self):
        pass

    def store(self, oid, vars):
        ts = time.time()
        # XXX might want to use the ID here instead of expensive exec
        vartype = eval("tsdb.%s" % oid.type.name)

        for (var,val) in vars:
            var = self.correlator.lookup(oid,var)

            try:
                tsdb_var = self.tsdb_set.get_var(var)
            except tsdb.TSDBVarDoesNotExistError:
                tsdb_var = self.tsdb_set.add_var(var, vartype,
                        self.oidset.frequency, self.chunk_mapper)

            tsdb_var.insert(vartype(ts, tsdb.ROW_VALID, val))
            tsdb_var.flush() # XXX is this a good idea?
            #print vartype, var, ts, val, vartype.unpack(vartype(ts, tsdb.ROW_VALID, val).pack())

class IfRefSQLPoller(SQLPoller):
    """Polls all OIDS and creates a IfRef entry then sees if the IfRef entry
    differs from the lastest in the database."""

    def __init__(self, config, name, device, oidset):
        SQLPoller.__init__(self, config, name, device, oidset)
        self.ifref_data = {}

    def begin(self):
        self.count = 0

    def collect(self, oid, data):
        self.ifref_data[oid.name] = data
        self.count += len(self.ifref_data[oid.name])

    def finish(self):
        self.store()

    def store(self):
        db_session = esxsnmp.sql.Session()
        new_ifrefs = self._build_objs()
        old_ifrefs = db_session.query(IfRef).select(
            sqlalchemy.and_(IfRef.c.deviceid==self.device.id, IfRef.c.end_time > 'NOW')
        )

        # iterate through what is currently in the database
        for old_ifref in old_ifrefs:
            # there is an entry in new_ifrefs: has anything changed?
            if new_ifrefs.has_key(old_ifref.ifdescr):
                new_ifref = new_ifrefs[old_ifref.ifdescr]
                attrs = new_ifref.keys()
                attrs.remove('ifdescr')
                changed = False
                # iterate through all attributes
                for attr in attrs:
                    # if the old and new differ update the old
                    if getattr(old_ifref, attr) != new_ifref[attr]:
                        changed = True

                if changed:
                    old_ifref.end_time = 'NOW'
                    new_row = self._new_row_from_obj(new_ifref)
                    db_session.save(new_row)
                    db_session.flush()
                
                del new_ifrefs[old_ifref.ifdescr]
            # no entry in new_ifrefs: interface is gone, update db
            else:
                old_ifref.end_time = 'NOW'
                db_session.flush()

        # anything left in new_ifrefs is a new interface
        for new_ifref in new_ifrefs:
            new_row = self._new_row_from_obj(new_ifrefs[new_ifref])
            b_session.save(new_row)

        db_session.flush()
        db_session.close()

    def _new_row_from_obj(self, obj):
        i = IfRef()
        i.deviceid = self.device.id
        i.begin_time = 'NOW'
        i.end_time = 'Infinity'
        for attr in obj.keys():
            setattr(i, attr, obj[attr])
        return i

    def _build_objs(self):
        ifref_objs = {}
        ifIndex_map = {}

        for name, val in self.ifref_data['ifDescr']:
            foo, ifIndex = name.split('.')
            ifIndex_map[ifIndex] = val
            ifref_objs[val] = dict(ifdescr=val, ifindex=int(ifIndex))

        for name, val in self.ifref_data['ipAdEntIfIndex']:
            foo, ipAddr = name.split('.', 1)
            ifref_objs[ifIndex_map[val]]['ipaddr'] = ipAddr

        remaining_oids = self.ifref_data.keys()
        remaining_oids.remove('ifDescr')
        remaining_oids.remove('ipAdEntIfIndex')

        for oid in remaining_oids:
            for name, val in self.ifref_data[oid]:
                if oid in ('ifSpeed', 'ifHighSpeed'):
                    val = int(val)
                foo, ifIndex = name.split('.')
                ifref_objs[ifIndex_map[ifIndex]][oid.lower()] = val

        return ifref_objs

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

    name = "espolld_manager_quux"

    exc_handler = setup_exc_handler(name, config)
    exc_handler.install()

    setproctitle(name)

    daemonize(name, config.pid_file, logfile="/tmp/plog")

    poller = PollManager(name, opts, args, config)
    poller.start_polling()

