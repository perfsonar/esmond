"""Implement a RESTish API to Esmond data.


"""

import sys
import time
import os
import crypt
import base64

import web
from web.webapi import HTTPError
try:
    import json
except ImportError:
    import simplejson as json
try: 
    import cmemcache as memcache
except ImportError:
    import memcache

import urllib
from fpconst import isNaN
import logging

import tsdb
from tsdb.error import *
from esmond.util import get_logger, remove_metachars, datetime_to_unixtime
from esmond.error import *
from esmond.config import get_opt_parser, get_config, get_config_path

from esmond.api.models import Device, IfRef, ALUSAPRef
import datetime

import pprint

#
# XXX this whole thing should be refactored to break each individual part of
# the request tree into it's own self contained class and called directly from
# the url pattern matching below.
#

"""
The URL structure of the REST service is as follows:

    /snmp/  
        returns a list of available devices

    /snmp/DEVICE_NAME/ 
        returns the avaiable sets for devices

    /snmp/DEVICE_NAME/interface/  
        returns a list of interfaces and interface details for a specific device

    /snmp/DEVICE_NAME/interface/INTERFACE_NAME/
        returns details for a specific interface

    /snmp/DEVICE_NAME/interface/INTERFACE_NAME/in
    /snmp/DEVICE_NAME/interface/INTERFACE_NAME/out
    /snmp/DEVICE_NAME/interface/INTERFACE_NAME/error/in
    /snmp/DEVICE_NAME/interface/INTERFACE_NAME/error/out
    /snmp/DEVICE_NAME/interface/INTERFACE_NAME/discard/in
    /snmp/DEVICE_NAME/interface/INTERFACE_NAME/discard/out
        returns counter data for a specific interface

"""

urls = (
        '/snmp/.*', 'SNMPHandler',
        '/bulk/?', 'BulkHandler',
        '/topN/?', 'TopNHandler',
        '/power/.*', 'PowerHandler',
        '/sap/', 'ALUSAPRefHandler',
        )

POWER_DEVICES = ['student10']
POWER_DATA_SET_TO_OID = {
        'load': 'outletLoadValue',
        'temp': 'tempHumidSensorTempValue',
        'humidity': 'tempHumidSensorHumidValue',
        }
class PowerHandler(object):
    """A quick hack to support power monitoring demo."""
    def __init__(self):
        self.db = tsdb.TSDB(CONFIG.tsdb_root, mode="r")

        self.log = get_logger("newdb.power")

        self.begin = None
        self.end = None

    def GET(self):
        print "power"
        uri = web.ctx.environ.get('REQUEST_URI', 
                    web.ctx.environ.get('PATH_INFO', None))

        try:
            uri, args = uri.split('?')
        except ValueError:
            pass

        args = parse_query_string()

        if args.has_key('begin'):
            self.begin = int(args['begin'])

        if args.has_key('end'):
            self.end = int(args['end'])

        if not self.end:
            self.end = int(time.time())

        if not self.begin:
            self.begin = self.end - 3600

        if self.end < self.begin:
            print "begin (%d) is greater than end (%d)" % (self.begin, self.end)
            return web.notfound()

        parts = uri.split('/')[2:]
        if parts[-1] == '':
            parts = parts[:-1]

        if len(parts) == 0:
            return json.dumps(dict(children=POWER_DEVICES))

        device = parts[0]
        if device not in POWER_DEVICES:
            print "ERR> unknown device: %s" % device
            return web.notfound() # unknown dataset

        if len(parts) == 1:
            r = {}
            for dataset in POWER_DATA_SET_TO_OID.keys():
                r.update(self.get_data(device, dataset))

            return json.dumps(r)

        dataset = parts[1]
        if not POWER_DATA_SET_TO_OID.has_key(dataset):
            print "ERR> unknown dataset: %s" % dataset
            return web.notfound() # unknown dataset

        if len(parts) == 2:
            return json.dumps(self.get_data(device, dataset))

        port = parts[2]

        return json.dumps(self.get_data(device, dataset, port))

    def get_data(self, device, dataset, port=None):
        path = "/".join((device, 'SentryPoll', POWER_DATA_SET_TO_OID[dataset]))
        ds = self.db.get_set(path)
        r = {}
        r[dataset] = {}
        if port:
            ports = [port]
        else:
            ports = ds.list_vars()

        for port in ports:
            v = ds.get_var(port)
            r[dataset][port] = [(d.timestamp, d.value) for d in
                    v.select(begin=self.begin, end=self.end)]

        return r

SNMP_URI = '/snmp'
DATASET_INFINERA_MAP = {'in': 'Rx', 'out': 'Tx'}

class UserDB(object):
    def __init__(self):
        self.userpasswdmap = {}

    def read_htpassd(self, htpasswd_file):
        try:
            f = open(htpasswd_file, "r")
            for line in f:
                line = line.strip()
                user, pwhash = line.split(':')
                self.userpasswdmap[user] = pwhash
        except Exception, e:
            print >>sys.stderr, e

    def check_password(self, user, passwd):
        pwhash = self.userpasswdmap.get(user)
        if pwhash:
            salt = pwhash[:2]
            return crypt.crypt(passwd, salt) == pwhash

        return False

    def get_groups(self, user):
        return []


def check_basic_auth():
    """Check HTTP BASIC Authentication.

    userdb is an object with the same interface as UserDB.

    """
    if not web.ctx.environ.has_key('HTTP_AUTHORIZATION') or \
            not web.ctx.environ['HTTP_AUTHORIZATION'].startswith('Basic '):
        return False

    print >>sys.stderr, ">>AUTH", web.ctx.environ['HTTP_AUTHORIZATION']
    
    hash = web.ctx.environ['HTTP_AUTHORIZATION'][6:]
    remote_user, remote_passwd = base64.b64decode(hash).split(':')

    if USER_DB.check_password(remote_user, remote_passwd):
        return True

    return False

def remove_metachars(name):
    """remove troublesome metacharacters from ifDescr"""
    for (char,repl) in (("/", "_"), (" ", "_")):
        name = name.replace(char, repl)
    return name

def split_url(rest):
    parts = rest.split('/', 1)
    if len(parts) == 1:
        return parts[0], ''
    else:
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

def get_time_range_django(args):
    if args.has_key('begin'):
        begin = datetime.datetime.fromtimestamp(int(args['begin']))
    else:
        begin = None

    if args.has_key('end'):
        end = datetime.datetime.fromtimestamp(int(args['end']))
    else:
        end = None

    if not args.has_key('begin') and not args.has_key('end'):
        begin = end = datetime.datetime.now()

    return begin, end

# XXX this should be reworked, can we do it with metadata alone?  probably
# once TSDB uses SQLite for metadata
device_oidset = {}
def get_traffic_oidset(device_name):
    db = tsdb.TSDB(CONFIG.tsdb_root, mode="r")

    try:
        db.get_set('/%s/SuperFastPollHC' % (device_name))
        r = ('SuperFastPollHC', 'HC')
    except:
        try:
            db.get_set('/%s/FastPollHC' % (device_name))
            r = ('FastPollHC', 'HC')
        except:
            try:
                db.get_set('/%s/InfFastPollHC' % (device_name))
                r = ('InfFastPollHC', 'HC')
            except:
                try:
                    db.get_set('/%s/ALUFastPollHC' % (device_name))
                    r = ('ALUFastPollHC', 'HC')
                except:
                    r = ('FastPoll', '')

    return r

def encode_device(dev, uri, children=[]):
    d = dev.to_dict()
    d['children'] = children
    d['uri'] = uri
    d['leaf'] =False

    return d

def encode_ifref(ifref, uri, children=[]):
    d = ifref.to_dict()
    d['uri'] = uri
    d['device_uri'] = '%s/%s' % (SNMP_URI, ifref.device.name)
    d['children'] = children
    d['leaf'] = False
    return d

def make_children(uri_prefix, children, leaf=False):
    return [ dict(name=child, uri="%s/%s" % (uri_prefix, child), leaf=leaf) for child in
            children ]

class BulkHandler:
    def __init__(self):
        self.uris = []
        self.snmp_handler = SNMPHandler()

    def GET(self):
        print "ERR> GET not allowed for bulk"
        return web.notfound() # GET not supported

    def POST(self):
        t0 = time.time()
        data = web.input()
        if data.has_key('uris'):
            return self.OLDPOST()

        if data.has_key('calcq'):
            return self.calcq(data['calcq'])

        if not data.has_key('q'):
            print "ERR> No q argument:", ",".join(data.keys())
            return web.webapi.BadRequest()

        #print ">>> Q ", data['q']

        try:
            self.queries = json.loads(data['q'])
        except ValueError, e:
            print "ERR> BAD JSON:", data['q'], str(e)
            return web.webapi.BadRequest()

        r = {}

        for q in self.queries:
            try:
                id, uri = self.uri_from_json(q)
            except BadQuery, e:
                r[q['id']] = dict(result=None, error=str(e))
                continue

            out = self.snmp_handler.GET(uri=uri, raw=True)

            if isinstance(out, HTTPError):
                r[id] = dict(result=None, error=str(out))
            else:
                r[id] = dict(result=out, error=None)

        web.ctx.status = "200 OK"
        print "grabbed %d vars in %f sec" % (len(r), time.time()-t0)

        return json.dumps(r)

    def uri_from_json(self, q):
        try:
            uri = q['uri']
        except KeyError:
            raise BadQuery("query does not contain a uri")

        try:
            id = q['id']
        except KeyError:
            raise BadQuery("query does not contain an id")

        del q['uri']
        del q['id']

        args = ["%s=%s" % (k, v) for k,v in q.iteritems()]

        return id, uri + '?' + '&'.join(args)

    def calcq(self, q):
        try:
            queries = json.loads(q)
        except ValueError, e:
            print "ERR> BAD JSON:", q, str(e)
            return web.webapi.BadRequest()

        i = 0
        results = {}
        for query in queries:
            r = dict(error=None, result=None)

            if not query.has_key('id'):
                query['id'] = 'anon%d' % i
                i += 1

            if not query.has_key('func'):
                r.error = "func not defined"
                results[query['id']] = r
                continue

            if query['func'] not in ['sum']:
                r.error = "unknown function: %s" % query['func']
                results[query['id']] = r
                continue

            calcf = getattr(self, 'calcf_' + query['func'])
    
            if not query.has_key('uris'):
                r.error = "uris not defined"
                results[query['id']] = r
                continue

            if not query.has_key('args'):
                r.error = "args not defined"
                results[query['id']] = r
                continue

            args = [ "%s=%s" % (k,v) for k,v in query['args'].iteritems() ]
            args = "&".join(args)

            data = []
            for uri in query['uris']:
                uri += '?' + args
                d = self.snmp_handler.GET(uri=uri, raw=True)
                print ">>> d = >", str(d), "<", type(d), d == "404 Not Found"
                if type(d) == dict:
                    data.append(d['data'])

            r['result'] = calcf(data)
            results[query['id']] = r

        return json.dumps(results)

    def calcf_sum(self, data):
        r = []
        for i in range(len(data[0])):
            x = 0
            for j in range(len(data)):
                x += data[j][i][1]
            r.append([data[0][i][0], x])

        return r

    def OLDPOST(self):
        data = web.input()
        if not data.has_key('uris'):
            print "ERR> no uris in POST"
            return web.webapi.BadRequest()

        try:
            self.uris = json.loads(data['uris'])
        except ValueError, e:
            print ">>> BAD JSON:", data['uris'], str(e)
            return web.webapi.BadRequest()

        r = {}

        for uri in self.uris:
            #print ">>> grabbing ", uri
            out = self.snmp_handler.GET(uri=uri, raw=True)
            if isinstance(out, HTTPError):
                r[uri] = dict(result=None, error=str(out))
            else:
                r[uri] = dict(result=out, error=None)

        return json.dumps(r)

class ALUSAPRefHandler:
    def __init__(self):
        self.log = get_logger("newdb.alusapref")

    def GET(self):
        print "SAPPY"
        saps = []

        args = parse_query_string()
        begin, end = get_time_range_django(args)
        saprefs = ALUSAPRef.objects.filter(end_time__gt=begin, begin_time__lt=end)

        for sap in saprefs:
            print sap
            saps.append(sap.to_dict())

        return json.dumps(saps)

class SNMPHandler:
    def __init__(self):
        self.db = tsdb.TSDB(CONFIG.tsdb_root, mode="r")
        if CONFIG.agg_tsdb_root:
            self.agg_db = tsdb.TSDB(CONFIG.agg_tsdb_root, mode="r")
        else:
            self.agg_db = None

        self.log = get_logger("newdb")

    def GET(self, uri=None, raw=False, args=None):
        # XXX hack because Apache performs a URL decode on PATH_INFO
        # we need /'s encoded as %2F
        # also apache config option: AllowEncodedSlashes On
        # see http://wsgi.org/wsgi/WSGI_2.0

        if not uri:
            uri = web.ctx.environ.get('REQUEST_URI', 
                    web.ctx.environ.get('PATH_INFO', None))

        try:
            uri, args = uri.split('?')
        except ValueError:
            pass


        if args:
            web.ctx.query = "?" + args

        print ">>> ", uri, web.ctx.query

        parts = uri.split('/')
        device_name = parts[2]
        rest = '/'.join(parts[3:])

        self.log.debug( "QQQ: " + " ". join((str(device_name), str(rest),
            str(web.ctx.query))))

        if not device_name:
            args = parse_query_string()
            print args
            if args.has_key('interface_descr'):
                r = self.get_interfaces_by_descr(args['interface_descr'])
            else:
                r = self.list_devices()
                # XXX hack to support aggs.  ugh!
                r['children'].append(dict(
                    name='Aggregates',
                    uri="%s/Aggregates" % (SNMP_URI, ),
                    leaf=False))
        elif device_name == 'Aggregates':
            if self.agg_db:
                r = self.handle_aggregates(parts[3:])
            else:
                print "ERR> agg_db not defined"
                return web.notfound()
        elif len(parts) > 5 and parts[3] == 'interface' and parts[5]:
            r = self.get_interface_data(device_name, parts[4], parts[5],
                    '/'.join(parts[6:]))
        else:
            try:
                device = Device.objects.get(name=device_name,
                        end_time__gt=datetime.datetime.now())
            except Device.DoesNotExist:
                print "ERR> device %s does not exist" % device_name
                return web.notfound()
            except Device.MultipleObjectsReturned:
                print "ERR> got more than one device %s" % device_name
                return web.notfound()

            if not rest:
                r = self.get_device(device)
            else:
                next, rest = split_url(rest)
                if next == 'interface':
                    r = self.get_interface_set(device, rest)
                elif next == 'system':
                    r = self.get_system(device, rest)
                elif next == 'all':
                    r = self.get_all(device, rest)
                elif next == 'firewall':
                    r = self.get_firewall(device, rest)
                elif next == 'sap':
                    r = self.get_sap(device, rest)
                else:
                    r = web.notfound()

        if raw or isinstance(r, HTTPError):
            return r
        else:
            return json.dumps(r)

    def handle_aggregates(self, parts):
        if len(parts) > 0 and parts[-1] == '':
            parts = parts[:-1]
        if len(parts) == 0:
            r = [dict(name=s, uri="%s/%s" % (SNMP_URI, s), leaf=False)
                    for s in self.agg_db.list_sets()]
        elif len(parts) == 1:
            r = [dict(name=v, uri="%s/%s/%s" % (SNMP_URI, parts[0], v), leaf=True)
                    for v in self.agg_db.get_set(parts[0]).list_vars()]
        elif len(parts) == 2:
            args = parse_query_string()

            if args.has_key('begin'):
                begin = args['begin']
            else:
                begin = int(time.time() - 3600)

            if args.has_key('end'):
                end = args['end']
            else:
                end = int(time.time())

            path = "/".join(parts)

            try:
                v = self.agg_db.get_var(path)
            except TSDBVarDoesNotExistError:
                print "ERR> var doesn't exist: %s" % path
                return web.notfound()  # Requested variable does not exist
            except InvalidMetaData:
                print "ERR> invalid metadata: %s" % path
                return web.notfound()

            print v

            data = v.select(begin=begin, end=end)
            data = [d for d in data]
            r = []

            for datum in data:
                d = [datum.timestamp, datum.value]

                if isNaN(d[1]):
                    d[1] = None

                r.append(d)

            result = dict(data=r, begin_time=begin, end_time=end, agg="30")
            return result
        else:
            print "ERR> too many parts in handle_aggregates"
            return web.notfound()

        return dict(children=r)

    def list_devices(self, active=True):
        """Returns a JSON array of objests representing device names and URIs.

        This is obtained by doing a GET on /snmp/.

        Example:

        [ {'name': 'router1', 'uri': 'http://example.com/snmp/router1/' },
          {'name': 'router2', 'uri': 'http://example.com/snmp/router2/' } ]
        
        """

        active=True

        args = parse_query_string()
        begin, end = get_time_range_django(args)

        active = bool(args.get('active', True))

        devices = Device.objects.filter(active=active)

        if end:
            devices = devices.filter(begin_time__lt=end)
        if begin:
            devices = devices.filter(end_time__gt=begin)

        r = [dict(name=d.name, uri="%s/%s" % (SNMP_URI, d.name), leaf=False)
                for d in devices.all()]

        return dict(children=r)

    def get_device(self, device):
        """Returns a JSON object representing a device.

        This is obtained by doing a GET of /DEVICE_NAME/.

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
        subsets=['interface', 'system','all']
        r = make_children('%s/%s' % (SNMP_URI, device.name), subsets)
        return encode_device(device, '%s/%s' % (SNMP_URI, device.name),
            children=r)

    def get_interface_set(self, device, rest):
        """Returns a list of JSON objects representing the interfaces for a device.

        This is obtained by doing a GET of /DEVICE_NAME/interface.

        The fields for each object are the same as the get_interface() method.

        Example:

        """

        args = parse_query_string()
        begin, end = get_time_range_django(args)

        ifaces = IfRef.objects.filter(device=device)
        ifaces = ifaces.filter(end_time__gt=begin, begin_time__lt=end)
        if not check_basic_auth():
            ifaces = ifaces.exclude(ifAlias__contains=':hide:')

        ifset = map(lambda x: x.ifDescr, ifaces)

        if not rest:
            def build_iface(iface):
                uri = "%s/%s/interface/%s" % (SNMP_URI, device.name,
                        remove_metachars(iface.ifDescr))

                return encode_ifref(iface, uri)

            l = map(build_iface, ifaces.all())
            return dict(children=l, leaf=False)
        else:
            next, rest = split_url(rest)
            next = urllib.unquote(next)
#            print ">>>>", next, rest
            return self.get_interface(device, ifaces, next, rest)

    def get_interfaces_by_descr(self, descr_pattern):
        # XXX quick hack to test search idea, totally needs to be written like
        # this whole module.... *sigh*
        args = parse_query_string()
        begin, end = get_time_range(args)

        limit = """
            ifref.end_time > %(begin)s
            AND ifref.begin_time < %(end)s""" % locals()

        begin, end = get_time_range_django(args)

        ifrefs = IfRef.objects.filter(ifAlias__contains=descr_pattern)
        ifrefs = ifrefs.filter(end_time__gt=begin, begin_time__lt=end)

        if not check_basic_auth():
            ifrefs = ifrefs.exclude(ifAlias__contains=':hide:')

        print "Q=",ifrefs.query
        print ifrefs.count()
        

        children = ['in', 'out', 'error/in', 'error/out', 'discard/in',
                'discard/out']
        l = []
        for ifref in ifrefs:
            uri = '%s/%s/interface/%s' % (SNMP_URI, ifref.device.name,
                    ifref.ifDescr.replace('/','_'))
            kids = make_children(uri, children)
            l.append(encode_ifref(ifref, uri, children=kids))

        return l

    def get_interface(self, device, ifaces, iface, rest):
        """Returns a JSON object representing an interface.

        This obtained by doing a GET of /DEVICE_NAME/interface/INTERFACE_NAME/.

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

             [{ 'ifIndex': 1,
               'ifDescr': 'xe-2/0/0',
               'ifAlias': '10Gig to Timbuktu',
               'ipAddr': '10.255.255.1',
               'ifSpeed': 0,
               'ifHighSpeed': 10000,
               'begin_time': 0,
               'end_time': 2147483647,
               'subsets': ['in', 'out'],
               'uri': 'http://example.com/snmp/router1/interface/xe-2_0_0', }
               'device_uri': 'http://example.com/snmp/router1/' }]
        """

        # XXX fill in ifref info
        children = ['in', 'out', 'error/in', 'error/out', 'discard/in',
                'discard/out']

        iface = iface.replace('_', '/')
        # XXX hack workaround for ALU
        iface = iface.replace(',/', ', ').replace('Gig/', 'Gig ')
        if not rest:
            t0 = time.time()
            ifrefs = ifaces.filter(ifDescr=iface).order_by("end_time")
#            print ifrefs.all()
            if ifrefs.count() == 0:
                iface = iface.replace('/', '_')
                ifrefs = ifaces.filter(ifDescr=iface).order_by("end_time")
                print ">>hack>> trying %s, %s" % (iface, ifrefs)
            l = []
            t1 = time.time()
            print "t>> iface select %f" % (t1 - t0)
            t0 = t1
            for ifref in ifrefs:
                if not check_basic_auth() and ':hide:' in ifref.ifAlias:
                    continue
                uri = '%s/%s/interface/%s' % (SNMP_URI, device.name,
                        iface.replace('/','_'))
                kids = make_children(uri, children, leaf=True)
                l.append(encode_ifref(ifref, uri, children=kids))

            t1 = time.time()
            print "t>> iface process %f" % (t1 - t0)

            if l:
                return l
            else:
                return web.notfound()
        else:
            next, rest = split_url(rest)
            if next in children:
                return self.get_interface_data(device.name, iface, next, rest)
            else:
                return web.notfound()

    def get_interface_data(self, devicename, iface, dataset, rest):
        """Returns a JSON object representing counter data for an interface.

        This is obtained by doing a GET of one of the follwing URIs:

            /snmp/DEVICE_NAME/interface/INTERFACE_NAME/in
            /snmp/DEVICE_NAME/interface/INTERFACE_NAME/out
            /snmp/DEVICE_NAME/interface/INTERFACE_NAME/error/in
            /snmp/DEVICE_NAME/interface/INTERFACE_NAME/error/out
            /snmp/DEVICE_NAME/interface/INTERFACE_NAME/discard/in
            /snmp/DEVICE_NAME/interface/INTERFACE_NAME/discard/out

        For in and out 

        get_interface_data accepts several query parameters:

            begin --  expressed a seconds since the epoch
            end --  expressed a seconds since the epoch
            agg -- use a precomputed aggregate for data, defaults to highest available resolution
            cf -- consolidation function. defaults to average
            calc -- calculate an aggregate, see below for more details
            calc_func --
            oidset -- specifically specify an oidset, see below

        agg specifies which precomputed aggregate to use.  Aggregates are
        represented as rates (eg. bytes/sec) and are calculated for the base
        rate at the time the data is persisted to disk.   This is specified as
        the number of seconds in the aggregation period or as 'raw'.  'raw'
        returns the counter data as collected from the device without any
        processing.  Currently there is only the aggreagate for the base polling
        interval and as a result this is rarely used.  cf determines how
        datapoints are agreggated into a single datapoint.  By default the
        datapoints are averaged but the maximum and minimum can also be used.
        valid options for this parameter are 'min', 'max' and 'average'.  This
        applies to precomputed aggregates that are greater than the base polling
        frequency.

        calc requests that the database dynamically generate an aggregate from
        the base aggregate for this counter.  The parameter is set to the
        numberof seconds to be used in the aggregation period.  The function
        used to consolidate each group of data points into a single data in the
        aggregate is controlled by the calc_func parameter.

        calc_func specifies the function to use when calculating an aggregate.
        It may be one of 'average', 'min',  or 'max' and defaults to 'average'.

        oidset allows the query to specify a specific oidset to get the data
        from rather than using the usual method for locating the oidset.  This
        is very rarely used.

        An interface data JSON object has the following fields:

            :param data: a list of tuples.  each tuple is [timestamp, value]
            :param begin_time: the requested begin_time
            :param end_time: the requested end_time
            :param agg: the requested aggregation period
            :param cf: the requestion consolidation function

        Example:

            {"agg": "30",
             "end_time": 1254350090,
             "data": [[1254349980, 163.0],
                      [1254350010, 28.133333333333333],
                      [1254350040, 96.966666666666669],
                      [1254350070, 110.03333333333333]],
             "cf": "average",
             "begin_time": 1254350000}
        """

        next = None
        if rest:
            next, rest = split_url(rest)
            if next == 'aggs':
                # XXX list actual aggs
                return dict(aggregates=[30], cf=['average'])
            elif dataset not in ['error', 'discard'] and next not in ['in', 'out']:
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

        if args.has_key('oidset'):
            traffic_oidset = args['oidset']
            if traffic_oidset == 'FastPoll':
                traffic_mod = ''
            else:
                traffic_mod = 'HC'
        else:
            traffic_oidset, traffic_mod = get_traffic_oidset(devicename)

        if args.has_key('agg'):
            agg = args['agg']
            suffix = 'TSDBAggregates/%s/' % (args['agg'], )
        else:
            if cf == 'raw':
                suffix = ''
                agg = ''
            else:
                if traffic_oidset != 'SuperFastPollHC':
                    suffix = 'TSDBAggregates/30/'
                    agg = '30'
                else:
                    suffix = 'TSDBAggregates/10/'
                    agg = '10'

        if dataset in ['in', 'out']: # traffic
            begin, end = int(begin), int(end)

            if traffic_oidset == 'InfFastPollHC':
                path = '%s/%s/gigeClientCtpPmReal%sOctets/%s/%s' % (devicename,
                        traffic_oidset, DATASET_INFINERA_MAP[dataset],
                        remove_metachars(iface), suffix)
            else:
                path = '%s/%s/if%s%sOctets/%s/%s' % (devicename, traffic_oidset,
                    traffic_mod, dataset.capitalize(),
                    remove_metachars(iface), suffix)
        elif dataset in ['error', 'discard']:
            # XXX set agg to delta rather than average
            path = '%s/Errors/if%s%ss/%s' % (devicename, next.capitalize(),
                    dataset.capitalize(), remove_metachars(iface))
            path += '/TSDBAggregates/300/'
            agg = '300'
        else:
            print "ERR> can't resolve path"
            return web.notfound()  # Requested variable does not exist
            
        try:
            v = self.db.get_var(path)
        except TSDBVarDoesNotExistError:
            print "ERR> var doesn't exist: %s" % path
            return web.notfound()  # Requested variable does not exist
        except InvalidMetaData:
            print "ERR> invalid metadata: %s" % path
            return web.notfound()

        try:
            data = v.select(begin=begin, end=end)
        except TSDBVarEmpty:
            print "ERR> var has no data: %s" % path
            return web.notfound()

        data = [d for d in data]
        r = []

        for datum in data:
            if cf != 'raw':
                d = [datum.timestamp, getattr(datum, cf)]
            else:
                d = [datum.timestamp, datum.value]

            if isNaN(d[1]):
                d[1] = None

            r.append(d)

        result = dict(data=r, begin_time=begin, end_time=end, cf=cf, agg=agg)

        if args.has_key('calc'):
            if args.has_key('calc_func'):
                calc_func = args['calc_func']
            else:
                calc_func = 'average'

            r = self.calculate(args['calc'], agg, calc_func, r)
            if isinstance(r, HTTPError):
                return r

            result['data'] = r
            result['calc'] = args['calc']
            result['calc_func'] = calc_func

            # these don't make sense if we're using calc
            del result['agg']
            del result['cf']

        return result
            

    def calculate(self, period, base_period, cf, data):
        points_per_step = int(period)/int(base_period)

        try:
            f = getattr(self, "calculate_%s" % cf)
        except AttributeError:
            print "ERR> unknown calc function: %s" % cf
            return web.webapi.BadRequest() # invalid consolidation function

        r = []
        for i in range(0, len(data), points_per_step):
            r.append(f(data[i:i+points_per_step]))

        return r

    def calculate_average(self, data):
        total = 0
        for d in data:
            if d[1]:
                total += d[1]

        return (data[0][0], total/len(data))

    def calculate_max(self, data):
        max = data[0][1]
        for d in data[1:]:
            if d[1] > max:
                max = d[1]

        return [data[0][0], max]

    def calculate_min(self, data):
        min = data[0][1]
        for d in data[1:]:
            if d[1] < min:
                min = d[1]

        return (data[0][0], min)

    def get_system(self, device, rest):
        pass
    def get_all(self, device, rest):
        """
        This attempts to simply return the tree of sets and vars in
        our TSDB with minimal interpretation.
        """
        print "Device: %s Rest: %s"%(device,rest)
        path = os.path.join(device.name,rest)
        if tsdb.TSDBSet.is_tsdb_set(self.db.fs,path):
            result = dict(children=[],leaf=False)
            sets = self.db.get_set(path).list_sets()
            for s in sets:
                result['children'].append(dict(
                    leaf=False,
                    speed=0,
                    uri="%s/%s/all/%s" % (SNMP_URI, device.name,rest),
                    name = s,
                    descr = ''))
            vars = self.db.get_set(path).list_vars()
            for v in vars:
                result['children'].append(dict(
                    leaf=True,
                    speed=0,
                    uri="%s/%s/all/%s" % (SNMP_URI, device.name,rest),
                    name = v,
                    descr = ''))
        elif tsdb.TSDBVar.is_tsdb_var(self.db.fs,path):
            result = {}
            args = parse_query_string()
            result = self.get_all_data(path, args)
        else:
            return web.notfound()  # Requested variable does not exist
        return result
    def get_all_data(self, path, args):
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
            cf = 'raw'
        print "DBG> path is %s" % path
        if 'ALUSAPPoll' in path:
            path += "/TSDBAggregates/11/"
            if args.has_key('cf'):
                cf = args['cf']
            else:
                cf = 'average'

        try:
            v = self.db.get_var(path)
        except TSDBVarDoesNotExistError:
            print "ERR> var doesn't exist: %s" % path
            return web.notfound()  # Requested variable does not exist
        except InvalidMetaData:
            print "ERR> invalid metadata: %s" % path
            return web.notfound()
        print "MIN: %d MAX %d"%(v.min_timestamp(recalculate=True),v.max_timestamp(recalculate=True))
        data = v.select(begin=begin, end=end)
        data = [d for d in data]
        r = []
        for datum in data:
            if cf != 'raw':
                d = [datum.timestamp, getattr(datum, cf)]
            else:
                d = [datum.timestamp, datum.value]
            if isNaN(d[1]) or datum.flags != tsdb.row.ROW_VALID:
                d[1] = None
            r.append(d)
        if len(r):
            agg = r[1][0]-r[0][0] # not really the best way to guess the agg.
            result = dict(data=r[:-1], begin_time=begin, end_time=end,agg=agg,scale=0)
        else:
            result = dict(data=[], begin_time=begin, end_time=end,agg=agg,scale=0)

        return result

    def get_firewall(self, device, rest):
        path = "/%s/JnxFirewall/counter/%s" % (device.name, rest)
        print ">>", path
        try:
            v = self.db.get_var(path)
        except TSDBVarDoesNotExistError:
            self.log.error("not found: %s" % path)
            return web.notfound()

        args = parse_query_string()

        if args.has_key('begin'):
            begin = args['begin']
        else:
            begin = int(time.time() - 3600)

        if args.has_key('end'):
            end = args['end']
        else:
            end = int(time.time())

        data = v.select(begin=begin, end=end)
        data = [d for d in data]
        r = []

        for datum in data:
            d = [datum.timestamp, datum.value]

            if isNaN(d[1]):
                d[1] = None

            r.append(d)

        result = dict(data=r, begin_time=begin, end_time=end)

        return result

    def get_sap(self, device, rest):
        if not rest:
            result = dict(children=[],leaf=False)
            path = '/%s/ALUSAPPoll' % device.name
            for v in self.db.get_set(path).list_vars():
                result['children'].append(dict(
                    leaf=False,
                    speed=0,
                    uri="%s/%s/sap/" % (SNMP_URI, device.name, rest),
                    name = s,
                    descr = ''))
            return result
        path = "/%s/ALUSAPPoll/%s" % (device.name, rest)
        print ">>", path
        try:
            v = self.db.get_var(path)
        except TSDBVarDoesNotExistError:
            self.log.error("not found: %s" % path)
            return web.notfound()

        args = parse_query_string()

        if args.has_key('begin'):
            begin = args['begin']
        else:
            begin = int(time.time() - 3600)

        if args.has_key('end'):
            end = args['end']
        else:
            end = int(time.time())

        data = v.select(begin=begin, end=end)
        data = [d for d in data]
        r = []

        for datum in data:
            d = [datum.timestamp, datum.value]

            if isNaN(d[1]):
                d[1] = None

            r.append(d)

        result = dict(data=r, begin_time=begin, end_time=end)

        return result

class TopNHandler:
    def __init__(self):
        self.memcache = memcache.Client([CONFIG.espersistd_uri])

    def GET(self, uri=None, raw=False, rawargs=None):
        t0 = time.time()
        if not uri:
            uri = web.ctx.environ.get('REQUEST_URI', 
                    web.ctx.environ.get('PATH_INFO', None))
        try:
            uri, rawargs = uri.split('?')
        except ValueError:
            pass

        if rawargs:
            web.ctx.query = "?" + rawargs

        args = parse_query_string()
        data = self.memcache.get("summary")

        aggfunc = args.get('aggfunc', 'max')
        agg = int(args.get("agg", 30))
        if agg > 30 and agg % 30 == 0:
            f = getattr(self, aggfunc)
            d = json.loads(data)
            tin = d['traffic']
            tout = []
            span = agg/30
            for i in range(len(tin) / span):
                tout.append(tin[i*span])
                for j in range(1,4):
                    tout[i][j] = f(map(lambda x: x[j], tin[i*span:(i+1)*span]))
            d['traffic'] = tout
            d['agg'] = agg
            d['aggfunc'] = aggfunc
            data = json.dumps(d)

        if args.has_key("callback"):
            data = "%s(%s)" % (args['callback'], data)

        print >>sys.stderr, ">> topn took %f seconds" % (time.time() - t0,) 

        return data

    def max(self, data):
        return max(data)

    def avg(self, data):
        return sum(data) / len(data)

class LoggingMiddleware:

    def __init__(self, application):
        self.__application = application

    def __call__(self, environ, start_response):
        errors = environ['wsgi.errors']
        pprint.pprint(('REQUEST', environ), stream=errors)

        def _start_response(status, headers):
            pprint.pprint(('RESPONSE', status, headers), stream=errors)
            return start_response(status, headers)

        return self.__application(environ, _start_response)

def setup(inargs, config_file=None):
    oparse = get_opt_parser(default_config_file=get_config_path())
    (opts, args) = oparse.parse_args(args=inargs)
    if config_file:
        opts.config_file = config_file

    try:
        config = get_config(opts.config_file, opts)
    except ConfigError, e:
        print e
        sys.exit(1)

    # XXX(jdugan): is there a way to pass this into the web.py code so that each
    # handler has it?
    global CONFIG
    CONFIG = config

    # XXX(jdugan): ditto on this one, globals are icky
    global USER_DB
    USER_DB = UserDB()
    if config.htpasswd_file:
        USER_DB.read_htpassd(config.htpasswd_file)

def esdb_wsgi(config_file):
    sys.stdout = sys.stderr
    setup([], config_file=config_file)

    application = web.application(urls, globals()).wsgifunc()
    #application = LoggingMiddleware(application)
    #application = web.profiler(application)
    return application

def esdb_standalone():
    setup(sys.argv)
    application = web.application(urls, globals())
    application.run()

if __name__ == '__main__':
    esdb_standalone()
