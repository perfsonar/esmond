#!/usr/bin/env python

import sys
import threading
import time
import traceback
import socket
from calendar import timegm

from thrift.transport import TSocket, TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer

import tsdb
import tsdb.row
import tsdb.error

import esxsnmp.sql
from esxsnmp.sql import Device, OID, OIDSet, IfRef
from esxsnmp.rpc import ESDB
from esxsnmp.rpc.ttypes import ESDBError
from esxsnmp.ipaclsocket import IPACLSocket
import esxsnmp.rpc.ttypes
from esxsnmp.util import run_server, remove_metachars, init_logging, get_logger
from esxsnmp.config import get_opt_parser, get_config, get_config_path
from esxsnmp.error import ConfigError

class ESDBHandler(object):
    def __init__(self, config):
        self.config = config
        self.session = esxsnmp.sql.Session()
        self.tsdb = tsdb.TSDB(config.tsdb_root)
        self.device_threads = {}
        self.log = get_logger("esdbd")
        self.log.info("starting ESDBHandler")

    def __del__(self):
        self.session.close()

    def list_devices(self, active):
        limit = ""
        if active:
            limit = "device.end_time > 'NOW' AND device.begin_time < 'NOW' AND active = 't'"

        self.log.debug('list_devices')
        r = [d.name for d in
                self.session.query(esxsnmp.sql.Device).filter(limit)]
        return r

    def get_device(self,name):
        return self.session.query(Device).filter_by(name=name).one()

    def get_all_devices(self, active):
        d = {}
        for device in self.list_devices(active):
            d[device] = self.get_device(device)

        return d

    def add_device(self, device):
        self.session.save(device)
        self.session.flush()

    def list_oids(self):
        return [o.name for o in self.session.query(OID)]

    def get_oid(self,name):
        return self.session.query(OID).filter_by(name=name).one()

    def list_oidsets(self):
        return [s.name for s in self.session.query(OIDSet)]

    def get_oidset(self,name):
        return self.session.query(OIDSet).filter_by(name=name).one()

    def select(self, path, begin_time, end_time, flags, cf, resolution):
        """
        Selects data from the variable at path.

        If resolution is None, return the native resolution of the variable.
        """
        begin = time.time()

        msg = "select " + " ".join(map(str,
                   (path, begin_time, end_time, flags, cf, resolution)))
        self.log.debug(msg)
        print msg

        if cf not in  ("AVERAGE", "MIN", "MAX", "RAW"):
            raise esxsnmp.rpc.ttypes.ESDBError(
                    dict(what="unsupported consolidation function",
                        details=cf))

        try:
            var = self.tsdb.get_var(path)
        except TSDBVarDoesNotExistError:
            raise ESDBError(error="unknown var", details=path)

        aggs = var.list_aggregates()
        resolution = str(resolution)
        if cf in ("AVERAGE", "MIN", "MAX"):
            if not resolution in aggs:
                raise ESDBError(dict(error="resolution unavailable",
                        details="resolution=%s cf=%s" % (resolution, cf)))

            var = var.get_aggregate(resolution)
        elif cf == 'RAW':
            if resolution != var.metadata['STEP']:
                raise ESDBError(dict(error="resolution unavaiable",
                        details="raw is %s, requested %s" % \
                                (var.metadata['STEP'], resolution)))
        else:
            raise ESDBError(dict(error="unknown consolidation function",
                    details=cf))

        try:
            data = var.select(int(begin_time), int(end_time))
        except tsdb.TSDBVarEmpty:
            self.log.debug("select: no data")
            raise ESDBError(dict(error="no data", details="no data"))

        l = []

        for datum in data:
            l.append(datum)
      
        result = esxsnmp.rpc.ttypes.VarList()

        if l:
            if isinstance(l[0], esxsnmp.rpc.ttypes.Counter32):
                result.counter32 = l
            elif isinstance(l[0], esxsnmp.rpc.ttypes.Counter64):
                result.counter64 = l
            elif isinstance(l[0], esxsnmp.rpc.ttypes.Gauge32):
                result.gauge32 = l
            elif isinstance(l[0], esxsnmp.rpc.ttypes.Aggregate):
                result.aggregate = l
            else:
                raise esxsnmp.rpc.ttypes.ESDBError(
                        dict(error="unknown return type",
                            details=str(foo.__class__)))

        self.log.debug("select took %fs returned %d items" % (time.time() - begin, len(l)))
        return result

    def get_active_devices(self):
        return self.session.query(Device).filter("end_time > 'NOW' and begin_time < 'NOW'").all()

    def get_interfaces(self, device, all_interfaces):
        """
        Return a list of the most recent IfRef entry for each interface on
        each active device.
        """
        # XXX might be faster to do a join, but need to read up on SQLAlchemy
        # to do that...

        self.log.debug("get_interfaces " + device)
        d = self.session.query(Device).filter_by(name=device).filter(
                "end_time > 'NOW' and begin_time < 'NOW'").one()
        q = """ifref.deviceid = %d
                AND ifref.end_time > 'NOW'
                AND ifref.begin_time < 'NOW'""" % d.id

        if not all_interfaces:
            q += """ AND ifref.ifalias ~* 'show:'"""

        l = self.session.query(IfRef).filter(q).all()
        for i in l:
            if i.ifspeed > 2147483647:
                i.ifspeed = 0 # XXX ifSpeed is unsigned, i32 is signed, sigh
            #print i.device.name, i.ifdescr, i.ifspeed, i.ifhighspeed, i.begin_time, i.end_time
        self.log.debug("done with " + device)

        return l

#
# Make tsdb types Thrifty
#
tsdb.row.Counter32.__bases__ += (esxsnmp.rpc.ttypes.Counter32, )
tsdb.row.Counter64.__bases__ += (esxsnmp.rpc.ttypes.Counter64, )
tsdb.row.Gauge32.__bases__ += (esxsnmp.rpc.ttypes.Gauge32, )
tsdb.row.Aggregate.__bases__ += (esxsnmp.rpc.ttypes.Aggregate, )

class ESDBProcessorFactory(object):
    """Factory for ESDBHandlers."""

    def __init__(self, config):
        self.config = config 

    def getProcessor(self):
        return ESDB.Processor(ESDBHandler(self.config))

class HandlerPerThreadThreadedServer(TServer.TServer):
    def __init__(self, processorFactory, transport, transportFactory,
            protocolFactory, config):

        self.processorFactory = processorFactory

        TServer.TServer.__initArgs__(self, None, transport, transportFactory,
                transportFactory, protocolFactory, protocolFactory)

        self.config = config
        self.log = get_logger("esdbd")
        self.log.info("starting HandlerPerThreadThreadedServer")
        
    def serve(self):
        self.serverTransport.listen()
        while True:
            try:
                client = self.serverTransport.accept()
                t = threading.Thread(target = self.handle, args=(client,))
                t.start()
                self.log.debug("started thread" + t.getName())
            except Exception, x:
                print '%s, %s, %s,' % (type(x), x, traceback.format_exc())
    
    def handle(self, client):
        if not client:
            return

        itrans = self.inputTransportFactory.getTransport(client)
        otrans = self.outputTransportFactory.getTransport(client)
        iprot = self.inputProtocolFactory.getProtocol(itrans)
        oprot = self.outputProtocolFactory.getProtocol(otrans)
        proc = self.processorFactory.getProcessor()
        try:
            while True:
                proc.process(iprot, oprot)
        except TTransport.TTransportException, tx:
            pass
        except Exception, x:
            print '%s, %s, %s' % (type(x), x, traceback.format_exc())
    
        itrans.close()
        otrans.close()

def esdbd():
    """Entry point for esdbd."""
    argv = sys.argv
    oparse = get_opt_parser(default_config_file=get_config_path())
    (opts, args) = oparse.parse_args(args=argv)

    try:
        config = get_config(opts.config_file, opts)
    except ConfigError, e:
        print e
        sys.exit(1)

    esxsnmp.sql.setup_db(config.db_uri)
    init_logging(config.syslog_facility, level=config.syslog_level,
            debug=opts.debug)

    #handler = ESDBHandler(config)
    #processor = ESDB.Processor(handler)
    log = get_logger("esdbd")
    transport = IPACLSocket(9090, [], log=log,
            hints={'family': socket.AF_INET})
    tfactory = TTransport.TBufferedTransportFactory()
    pfactory = TBinaryProtocol.TBinaryProtocolAcceleratedFactory()

    server = HandlerPerThreadThreadedServer(ESDBProcessorFactory(config),
            transport, tfactory, pfactory, config)
    #try_harder(server.serve, exc_handler)
    server.serve()
