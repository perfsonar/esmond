"""Implement a RESTish API to ESxSNMP data.


"""

import sys
import time

sys.path.extend([
    '/data/esxsnmp/esxsnmp/src/python',
    '/data/esxsnmp/esxsnmp/eggs/web.py-0.32-py2.5.egg',
    '/data/esxsnmp/esxsnmp/eggs/simplejson-2.0.9-py2.5-freebsd-7.1-RELEASE-amd64.egg',
    '/data/esxsnmp/esxsnmp/parts/tsdb-svn/tsdb',
    '/data/esxsnmp/esxsnmp/eggs/fs-0.1.0-py2.5.egg'
])

import web
import simplejson
import urllib

import tsdb
from tsdb.error import *
import esxsnmp.sql
from esxsnmp.sql import Device, OID, OIDSet, IfRef

urls = ('/snmp/([\-a-zA-Z0-9]+)?/?(.+)?/?', 'SNMPHandler')

ROOT_URI = 'http://snmp-west.es.net:8001/snmp'

def remove_metachars(name):
    """remove troublesome metacharacters from ifDescr"""
    for (char,repl) in (("/", "_"), (" ", "_")):
        name = name.replace(char, repl)
    return name

def split_url(rest):
    parts = rest.split('/', 1)
    return parts[0], parts[1]

def parse_query_string():
    d = {}

    if web.ctx.query:
        kvpairs = web.ctx.query[1:].split('&')
        for kvp in kvpairs:
            k,v = kvp.split('=')
            d[k] = v

    return d

def get_time_range(args):
    begin="'-infinity'"
    end="'infinity'"

    if args.has_key('begin'):
        begin = "TIMESTAMP 'epoch' + %s * INTERVAL '1 second'" % args['begin']
    if args.has_key('end'):
        end = "TIMESTAMP 'epoch' + %s * INTERVAL '1 second'" % args['end']
    if not args.has_key('begin') and not args.has_key('end'):
        begin = end = "'NOW'"

    return begin, end

def get_traffic_oidset(device):
    if 'FastPollHC' in [x.name for x in device.oidsets]:
        return 'FastPollHC', 'HC'
    else:
        return 'FastPoll', ''

def encode_device(dev, uri, children=[]):
    return dict(begin_time=dev.begin_time, end_time=dev.end_time,
            name=dev.name, active=dev.active, children=children, uri=uri)

def encode_ifref(ifref, uri, children=[]):
    return dict(
            begin_time=ifref.begin_time,
            end_time=ifref.end_time,
            ifIndex=ifref.ifIndex,
            ifDescr=ifref.ifDescr,
            ifAlias=ifref.ifAlias,
            ifSpeed=ifref.ifSpeed,
            ifHighSpeed=ifref.ifHighSpeed,
            ipAddr=ifref.ipAddr,
            uri=ifref.uri,
            device_uri=ifref.device_uri)

def make_children(uri_prefix, children):
    return [ dict(name=child, uri="%s/%s" % (uri_prefix, child)) for child in
            children ]

class SNMPHandler:
    def __init__(self):
        self.db = tsdb.TSDB("/ssd/esxsnmp/data", mode="r")
        self.session = esxsnmp.sql.Session()

    def GET(self, device_name, rest):
        print "QQQ", device_name, rest, web.ctx.query
        if not device_name:
            return self.list_devices()

        device = self.session.query(Device).filter_by(name=device_name).one()

        if not rest:
            return self.get_device(device)
        else:
            next, rest = split_url(rest)
            if next == 'interface':
                return self.get_interface_set(device, rest)
            elif next == 'system':
                return self.get_system(device, rest)
            else:
                return web.notfound()

    def list_devices(self, active=True):
        """Returns a JSON array of objests representing device names and URIs.

        Example:

        [ {'name': 'router1', 'uri': 'http://example.com/snmp/router1/' },
          {'name': 'router2', 'uri': 'http://example.com/snmp/router2/' } ]
        
        """

        active='t'

        args = parse_query_string()
        begin, end = get_time_range(args)

        if args.has_key('active'):
            active = bool(args['active'])

        limit = """
            device.end_time > %(begin)s
            AND device.begin_time < %(end)s
            AND active = '%(active)s'""" % locals()

        print ">>>",limit
        devices = self.session.query(esxsnmp.sql.Device).filter(limit)
        r = [dict(name=d.name, uri="%s/%s" % (ROOT_URI, d.name))
                for d in devices]
        return simplejson.dumps(dict(children=r))

    def get_device(self, device):
        """Returns a JSON object representing a device.

        A device JSON object has the following fields:

            :param name: the name of the device
            :param begin_time: start time in seconds since the epoch
            :param end_time: start time in seconds since the epoch
            :param active: should the device be polled, boolean
            :param subsets: an array of available subsets
            :param uri: URI for this device

        For ``begin_time`` and ``end_time`` the values 0 and 2147483647 have
        special significance.  0 represents -infinity and 2147483647
        represents infinity.  This should be fixed.

        Example:

             { 'name': 'router1',
               'begin_time': 0,
               'end_time': 2147483647,
               'active': true,
               'subsets': ['system', 'interface'],
               'uri': 'http://example.com/snmp/router1/' }

        """

        # XXX once database is rearranged this will be dynamic
        subsets=['interface', 'system']
        r = make_children('%s/%s' % (ROOT_URI, device.name), subsets)
        return simplejson.dumps(encode_device(device,
            '%s/%s' % (ROOT_URI, device.name),
            children=r))

    def get_interface_set(self, device, rest):
        active='t'

        print ">>> XXQ", web.ctx.query, rest
        args = parse_query_string()
        begin, end = get_time_range(args)
        deviceid = device.id

        limit = """
            ifref.end_time > %(begin)s
            AND ifref.begin_time < %(end)s
            AND ifref.deviceid = %(deviceid)s""" % locals()

        print ">>>",limit

        ifaces = self.session.query(IfRef).filter(limit).all()
        ifset = map(lambda x: x.ifdescr, ifaces)

        if not rest:
            l = map(lambda iface: 
                dict(name=iface.ifdescr,
                    uri="%s/%s/interface/%s/" % (ROOT_URI, device.name,
                        urllib.quote(iface.ifdescr, safe='')),
                    descr=iface.ifalias),
                ifaces)
            return simplejson.dumps(dict(children=l))
        else:
            next, rest = split_url(rest)
            next = urllib.unquote(next)
            print ">>>>", next, rest
            try:
                ifref = ifaces.filter_by(name=device_name).one()
                return self.get_interface(device, next, rest)
            except NOTFOUND: # XXX check this
                return web.notfound()

    def get_interface(self, device, iface, rest):
        """Returns a JSON object representing an interface.

        An interface JSON object has the following fields:

            :param ifIndex: SNMP ifIndex
            :param ifDescr: SNMP ifDescr, the interface name
            :param ifAlias: SNMP ifAlias, the interface description
            :param ipAddr: SNMP ipAddr, IP address of interface
            :param ifSpeed: SNMP ifSpeed, interface speed in bit/sec
            :param ifHighSpeed: SNMP ifHighSpeed, interface speed in Mbit/sec
            :param begin_time: start time in seconds since the epoch
            :param end_time: start time in seconds since the epoch
            :param subsets: an array of available subsets
            :param uri: URI for this interface
            :param device_uri: URI for the device this interface belongs to

        For ``begin_time`` and ``end_time`` the values 0 and 2147483647 have
        special significance.  0 represents -infinity and 2147483647
        represents infinity.  This should be fixed.

        Example:

             { 'ifIndex': 1,
               'ifDescr': 'xe-2/0/0',
               'ifAlias': '10Gig to Timbuktu',
               'ipAddr': '10.255.255.1',
               'ifSpeed': 0,
               'ifHighSpeed': 10000,
               'begin_time': 0,
               'end_time': 2147483647,
               'subsets': ['in', 'out'],
               'uri': 'http://example.com/snmp/router1/interface/xe-2%2F0%2F0', }
               'device_uri': 'http://example.com/snmp/router1/' }
        """

        # XXX fill in ifref info
        children = ['in', 'out']


        if not rest:
            uri = '%s/%s/interface/%s' % (ROOT_URI, device.name,
                    urllib.quote(iface.ifDescr, safe=''))
            kids = make_children(uri, children)
            return simplejson.dumps(encode_ifref(iface, uri, children=kids))
        else:
            next, rest = split_url(rest)
            if next in children:
                return self.get_interface_data(device, iface, next, rest)
            else:
                return web.notfound()

    def get_interface_data(self, device, iface, dataset, rest):
        if rest:
            if rest == 'aggs' or rest == 'aggs/':
                # XXX list actual aggs
                return simplejson.dumps(dict(aggregates=[30], cf=['average']))
            else:
                return web.notfound("nope")

        args = parse_query_string()

        if args.has_key('begin'):
            begin = args['begin']
        else:
            begin = int(time.time() - 3600)

        if args.has_key('end'):
            end = args['end']
        else:
            end = int(time.time())

        if args.has_key('cf'):
            cf = args['cf']
        else:
            cf = 'average'

        if args.has_key('agg'):
            suffix = 'TSDBAggregates/%s/' % (args['agg'], )
        else:
            if cf == 'raw':
                suffix = ''
            else:
                suffix = 'TSDBAggregates/30/'

        traffic_oidset, traffic_mod = get_traffic_oidset(device)
        begin, end = int(begin), int(end)
        print ">>> B:", time.ctime(begin), "E:", time.ctime(end)

        path = '%s/%s/if%s%sOctets/%s/%s' % (device.name, traffic_oidset,
                traffic_mod, dataset.capitalize(),
                remove_metachars(iface.ifDescr), suffix)

        v = self.db.get_var(path)
        data = v.select(begin=begin, end=end)
        r = []
        for datum in data:
            if cf != 'raw':
                r.append((datum.timestamp, getattr(datum, cf)))
            else:
                r.append((datum.timestamp, datum.value))

        return simplejson.dumps(dict(data=r))

    def get_system(self, device, rest):
        pass

if __name__ == '__main__':
    from esxsnmp.config import get_opt_parser, get_config, get_config_path
    from esxsnmp.error import ConfigError
    """
    argv = sys.argv
    oparse = get_opt_parser(default_config_file=get_config_path())
    (opts, args) = oparse.parse_args(args=argv)

    try:
        config = get_config(opts.config_file, opts)
    except ConfigError, e:
        print e
        sys.exit(1)
    """

    esxsnmp.sql.setup_db('postgres://snmp:ed1nCit0@localhost/esxsnmp')
    app = web.application(urls, globals())
    app.run()
