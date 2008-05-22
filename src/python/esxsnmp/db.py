#!/usr/bin/env python

import threading
import time
import traceback
from calendar import timegm

from thrift.transport import TSocket, TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer

import tsdb

from esxsnmp.sql import *
from esxsnmp.rpc import ESDB
from esxsnmp.ipaclsocket import IPACLSocket
import esxsnmp.rpc.ttypes
from esxsnmp.util import run_server, remove_metachars

class ESDBHandler(object):
    def __init__(self):
        self.session = create_session(esxsnmp.sql.vars['db'])
        self.tsdb = tsdb.TSDB("/data/esxsnmp/data")
        self.device_threads = {}

    def list_devices(self, active):
        limit = ""
        if active:
            limit = "device.end_time > 'NOW' AND device.begin_time < 'NOW'"

        return [d.name for d in self.session.query(Device).select(limit)]

    def get_device(self,name):
        return self.session.query(Device).select_by(name=name)[0]

    def get_all_devices(self, active):
        d = {}
        for device in self.list_devices(active):
            d[device] = self.get_device(device)

        return d

    def add_device(self, device):
        self.session.save(device)
        self.session.flush()

    def list_oids(self):
        return [o.name for o in self.session.query(OID).select()]

    def get_oid(self,name):
        return self.session.query(OID).select_by(name=name)[0]

    def list_oidsets(self):
        return [s.name for s in self.session.query(OIDSet).select()]

    def get_oidset(self,name):
        return self.session.query(OIDSet).select_by(name=name)[0]

    def select(self, device, iface_name, oidset, oid, begin_time, end_time,
            flags, cf, resolution):
        """
        Returns raw data.

        If resolution is None, return the native resolution of the variable.
        """
        begin = time.time()

        print "Q:", device, iface_name, oidset, oid, begin_time, end_time, flags, cf, resolution

        if cf != "AVERAGE":
            raise esxsnmp.rpc.ttypes.ESDBError(
                    dict(what="unsupported consolidation function: %s" % cf))

        iface_name = remove_metachars(iface_name)

        var = self.tsdb.get_var("/".join((device, oidset, oid, iface_name)))
        aggs = var.list_aggregates()
        resolution = str(resolution)
        if resolution in aggs:
            var = var.get_aggregate(resolution)
            print "AGG", var

        data = var.select(int(begin_time), int(end_time))

        l = []

        for datum in data:
            l.append(datum)
       
        result = esxsnmp.rpc.ttypes.VarList()

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
                    dict(what="unknown return type from TSDB select"))

        print "select took: %fs returned %d items" % (time.time() - begin, len(l))
        return result

    def get_active_devices(self):
        return self.session.query(Device).select("end_time > 'NOW' and begin_time < 'NOW'")

    def get_interfaces(self, device, all_interfaces):
        """
        Return a list of the most recent IfRef entry for each interface on
        each active device.
        """
        # XXX might be faster to do a join, but need to read up on SQLAlchemy
        # to do that...

        d = self.session.query(Device).select_by(name=device)[0]
        q = """ifref.deviceid = %d
                AND ifref.end_time > 'NOW'
                AND ifref.begin_time < 'NOW'""" % d.id

        if not all_interfaces:
            q += """ AND ifref.ifalias ~* 'show:'"""
        print q

        l = self.session.query(IfRef).select(q)
        print len(l)
        return l

#
# Make tsdb types Thrifty
#
tsdb.Counter32.__bases__ += (esxsnmp.rpc.ttypes.Counter32, )
tsdb.Counter64.__bases__ += (esxsnmp.rpc.ttypes.Counter64, )
tsdb.Gauge32.__bases__ += (esxsnmp.rpc.ttypes.Gauge32, )
tsdb.Aggregate.__bases__ += (esxsnmp.rpc.ttypes.Aggregate, )

class ESDBProcessorFactory(object):
    """Factory for ESDBHandlers."""

    def __init__(self):
        pass 

    def getProcessor(self):
        return ESDB.Processor(ESDBHandler())

class HandlerPerThreadThreadedServer(TServer.TServer):
    def __init__(self, processorFactory, transport, transportFactory,
            protocolFactory):

        self.processorFactory = processorFactory

        TServer.TServer.__initArgs__(self, None, transport, transportFactory,
                transportFactory, protocolFactory, protocolFactory)
        
    def serve(self):
        self.serverTransport.listen()
        while True:
            try:
                client = self.serverTransport.accept()
                t = threading.Thread(target = self.handle, args=(client,))
                t.start()
            except Exception, x:
                print '%s, %s, %s,' % (type(x), x, traceback.format_exc())
    
    def handle(self, client):
        itrans = self.inputTransportFactory.getTransport(client)
        otrans = self.outputTransportFactory.getTransport(client)
        iprot = self.inputProtocolFactory.getProtocol(itrans)
        oprot = self.outputProtocolFactory.getProtocol(otrans)
        proc = self.processorFactory.getProcessor()
        print itrans, otrans, iprot, oprot, proc
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
    esxsnmp.sql.setup_db("postgres:///esxsnmp")
    handler = ESDBHandler()
    processor = ESDB.Processor(handler)
    transport = IPACLSocket(9090, []) #TSocket.TServerSocket(9090)
    tfactory = TTransport.TBufferedTransportFactory()
    pfactory = TBinaryProtocol.TBinaryProtocolAcceleratedFactory()

    server = HandlerPerThreadThreadedServer(ESDBProcessorFactory(), transport, tfactory, pfactory)
    try_harder(server.serve, exc_handler)
