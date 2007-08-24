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
from essnmp.thrift.ttypes import IfRef
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
        f = open(self.file,"r")
        for line in f:
            line = line.strip()
            if line.startswith("#"):
                continue
            (var, val) = line.split()
            if var == "db_uri":
                self.db_uri = val
            elif var == "tsdb_root":
                self.tsdb_root = val
            elif var == "error_email":
                self.error_email = val
            else:
                raise PollError("unknown config option: %s %s" % (var,val))


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
    def __init__(self, config, name, device, oidset):
        self.config = config
        self.name = name
        self.device = device
        self.oidset = oidset

        self.next_poll = int(time.time() - 1)
        self.oids = self.oidset.oids
        self.running = True

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
        raise NotImplementedError("must implement run method")

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


    def run(self):
        while self.running:
            self.log.debug("hello from " + self.name)

            if self.time_to_poll():
                self.log.debug("grabbing data")
                self.next_poll += self.oidset.frequency
                begin = time.time()
                cnt = 0

                try:
                    self.correlator.setup()  # might raise a yapsnmp.GetError

                    for oid in self.oids:
                        vars = self.snmp_session.walk(oid.name)
                        cnt += len(vars)
                        self.store(oid, vars)

                    self.log.debug("grabbed %d vars in %f seconds" % (cnt, time.time() - begin))
                    self.log.debug("next %d" % self.next_poll)
                    self.errors = 0
                except yapsnmp.GetError, e:
                    self.errors += 1
                    if self.errors < 10  or self.errors % 10 == 0:
                        self.log.error("unable to get snmp response after %d tries: %s" % (self.errors, e))
            self.sleep()

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

    def run(self):
        while self.running:
            self.log.debug("hello")
            if self.time_to_poll():
                self.log.debug("grabbing data")
                self.next_poll += self.oidset.frequency
                begin = time.time()
                cnt = 0
                ifref_data = {}

                try:
                    for oid in self.oids:
                        ifref_data[oid.name] = self.snmp_session.walk(oid.name)
                        cnt += len(ifref_data[oid.name])

                    self.store(ifref_data)

                    self.log.debug("grabbed %d vars in %f seconds" % (cnt, time.time() - begin))
                    self.log.debug("next %d" % self.next_poll)
                    self.errors = 0
                except yapsnmp.GetError, e:
                    self.errors += 1
                    if self.errors < 10  or self.errors % 10 == 0:
                        self.log.error("unable to get snmp response after %d tries: %s" % (self.errors, e))

            self.sleep()

    def store(self, ifref_data):
        new_ifrefs = self._build_objs(ifref_data)
        old_ifrefs = self.db_session.query(IfRef).select(
            sqlalchemy.and_(IfRef.c.deviceid==self.device.id, IfRef.c.end_time > 'NOW')
        )

        # iterate through what is currently in the database
        for old_ifref in old_ifrefs:
            import pdb
            #pdb.set_trace()

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

    def _build_objs(self, ifref_data):
        ifref_objs = {}
        ifIndex_map = {}

        for name, val in ifref_data['ifDescr']:
            foo, ifIndex = name.split('.')
            ifIndex_map[ifIndex] = val
            ifref_objs[val] = dict(ifdescr=val, ifindex=int(ifIndex))

        for name, val in ifref_data['ipAdEntIfIndex']:
            foo, ipAddr = name.split('.', 1)
            ifref_objs[ifIndex_map[val]]['ipaddr'] = ipAddr

        remaining_oids = ifref_data.keys()
        remaining_oids.remove('ifDescr')
        remaining_oids.remove('ipAdEntIfIndex')

        for oid in remaining_oids:
            for name, val in ifref_data[oid]:
                if oid in ('ifSpeed', 'ifHighSpeed'):
                    val = int(val)
                foo, ifIndex = name.split('.')
                ifref_objs[ifIndex_map[ifIndex]][oid.lower()] = val

        return ifref_objs

