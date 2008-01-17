#!/usr/bin/env python

import os
import signal
import sys
import time
import re
from traceback import format_exception

import yapsnmp
import sqlalchemy

import essnmp.sql
from essnmp.util import setproctitle, get_logger
from essnmp.rpc.ttypes import IfRef
import tsdb

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

class ESPolldConfig(object):
    def __init__(self, file):
        self.file = file

        self.db_uri = None
        self.tsdb_root = None
        self.error_email = None

        self.read_config()

    def read_config(self):
        """ read in config from INI-style file, requiring section header 'espolld', e.g.:
            [espolld]
            db_uri = db_example_string
            tsdb_root = /var/db/tsdb/
            error_email = me@my.com """
        cfg = ConfigParser.ConfigParser()
        cfg.read(self.file)
        for opt in ('db_uri', 'tsdb_root', 'error_email'):
            exec('self.%s = cfg.get("espolld", "%s")' % (opt, opt))

def remove_metachars(name):
    """remove troublesome metacharacters from ifDescr"""
    for (char,repl) in (("/", "_"), (" ", "_")):
        name = name.replace(char, repl)
    return name

class PollCorrelator(object):
    """polling correlators correlate an oid to some other field.  this is
    typically used to generate the key needed to store the variable."""

    def __init__(self, session=None):
        self.session = session

    def setup(self):
        raise NotImplementedError

    def lookup(self, oid):
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
        (column, filter, counter, type) = self.oidex.search(var).groups()
        return "/".join((type, filter, counter))

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

    def __init__(self, config, poller, name, device, oidset):
        self.config = config
        self.poller = poller
        self.name = name
        self.device = device
        self.oidset = oidset

    def run(self):
        self.poller(self.config, self.name, self.device, self.oidset).run()

class PollManager(object):
    """Starts a polling process for each device"""

    def __init__(self, opts, args, config):
        self.opts = opts
        self.args = args
        self.config = config

        self.running = False

        essnmp.sql.setup_db(self.config.db_uri)
        self.db_session = sqlalchemy.create_session(essnmp.sql.vars['db'])

        self.devices = self.db_session.query(essnmp.sql.Device).select(
            "active = 't' AND end_time > 'NOW'")

        self.children = {}  # dict maps device name to child pid

        self.log = get_logger("poll_manager")

        if not tsdb.TSDB.is_tsdb(self.config.tsdb_root):
            tsdb.TSDB.create(self.config.tsdb_root)

    def start_polling(self):
        """Begin polling all routers for all OIDSets"""
        for device in self.devices:
            for oidset in device.oidsets:
                # what kind of poller do we need for this OIDSet?
                exec("poller = %s" % oidset.poller.name)
                name = device.name + "_" + oidset.name
                self._start_child(PollerChild(self.config, poller, name, device, oidset))

        signal.signal(signal.SIGINT, self.stop_polling)
        signal.signal(signal.SIGTERM, self.stop_polling)
        self.running = True

        while self.running:
            (rpid,status) = os.wait()
            if rpid != 0 and self.running: # need to check self.running again, because wait blocks
                self.log.warn("%s, pid %d died" % (self.children[rpid].name, rpid))
                child = self.children[rpid]
                del self.children[rpid]
                self._start_child(child)
                time.sleep(1)  # don't spin if process keeps dying

    def _start_child(self, child):
        pid = os.fork()
        if pid:
            self.children[pid] = child
            self.log.debug("%s started, pid %d" % (child.name,pid))
        else:
            setproctitle("espolld: %s" % child.name)
            child.run()

    def stop_polling(self, signum, frame):
        self.log.info("shutting down")
        self.log.debug(self.children)
        self.running = False
        for pid in self.children:
            self.log.debug("killing %s %d" % (self.children[pid].name, pid))
            os.kill(pid, signal.SIGTERM)
            (rpid,status) = os.waitpid(pid, os.WNOHANG)
        self.log.debug("exiting")
        sys.exit()

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

        self.log = get_logger("poller " + self.name)
        self.errors = 0

        self.poller_args = {}
        if self.oidset.poller_args is not None:
            for arg in self.oidset.poller_args.split():
                (var,val) = arg.split('=')
                self.poller_args[var] = val

    def run(self):
        while self.running:
            self.log.debug("hello")
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
                    self.log.debug("next %d" % self.next_poll)
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

        essnmp.sql.vars['db'].dispose() # XXX this bears further investigation
        self.db_session = sqlalchemy.create_session(bind_to=essnmp.sql.vars['db'].connect())

#
# XXX are the oidset, etc vars burdened with sqlalchemy goo? if so, does it
# matter?
#
class CorrelatedTSDBPoller(TSDBPoller):
    """Handles polling of an OIDSet for a device and uses a correlator to
    determine the name of the variable to use to store values."""
    def __init__(self, config, name, device, oidset):
        TSDBPoller.__init__(self, config, name, device, oidset)

        exec("self.correlator = %s(self.snmp_session)" %
                self.poller_args['correlator'])

        exec("self.chunk_mapper = %s" % self.poller_args['chunk_mapper'])


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
        exec("vartype = tsdb.%s" % oid.type.name)

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
        new_ifrefs = self._build_objs()
        old_ifrefs = self.db_session.query(IfRef).select(
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
                    self.db_session.save(new_row)
                    self.db_session.flush()
                
                del new_ifrefs[old_ifref.ifdescr]
            # no entry in new_ifrefs: interface is gone, update db
            else:
                old_ifref.end_time = 'NOW'
                self.db_session.flush()

        # anything left in new_ifrefs is a new interface
        for new_ifref in new_ifrefs:
            new_row = self._new_row_from_obj(new_ifrefs[new_ifref])
            self.db_session.save(new_row)

        self.db_session.flush()

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
