#!/data/esxsnmp/esxsnmp/bin/python
# 
"""template python command with command line parsing"""

import os
import sys
import json
import time
import optparse

import requests

from esxsnmp.api.models import *

VERSION = "0"

OLD_REST_API = "http://snmp-west.es.net:8001/snmp"

IFACE_IGNORE = ["lo0"]

small_dev_set = ['lbl-mr2', 'anl-mr2']

class DataBundle(object):
    """bundle together data for comparison"""
    def __init__(self, oid, frequency, device, interface, direction, begin, end, data):
        self.oidset = oid
        self.frequency = frequency
        self.device = device
        self.interface = interface
        self.direction = direction
        self.begin = begin
        self.end = end
        self.data = data


def old_iface_list(dev):
    url = "%s/%s/interface/" % (OLD_REST_API, dev.name)
    r = requests.get(url)
    data = r.json()
    l = [ (x['name'], x['uri'], x['ifAlias']) for x in data['children'] ]
    ifaces = []

    for iface in l:
        if not iface[2]:
            continue
        ignore = False
        for ig in IFACE_IGNORE:
            if iface[0].startswith(ig):
                ignore = True
                break
        if not ignore:
            ifaces.append(iface[1].split("/")[-1])

    return ifaces

def compare_data(bundle):
    print bundle.device, bundle.interface, bundle.direction, len(bundle.data['data'])
    # XXX lookup cassandra data here
    #print bundle.data['data']

def old_fetch_data(oidset, dev, iface, begin, end):
    params = dict(begin=begin, end=end)
    for d in ("in", "out"):
        url = "%s/%s/interface/%s/%s" % (OLD_REST_API, dev, iface, d)
        r = requests.get(url, params=params)

        if r.status_code == 404:
            print "got 404, skipping %s %s" % (dev, iface)
            return
        data = r.json()

        if d == 'in':
            oid = 'ifHCInOctets'
        else:
            oid = 'ifHCOutOctets'

        bundle = DataBundle(oid, oidset.frequency, dev, iface, d,
                begin, end, data)
        compare_data(bundle)

def process_devices(opts, devs):
    for d in devs:
        try:
            dev = Device.objects.get(name=d)
        except Device.DoesNotExist:
            print "skipping unknown device: %s" % d
            continue

        ifaces = old_iface_list(dev)

        oidset = dev.oidsets.get(name="FastPollHC")

        for iface in ifaces:
            data = old_fetch_data(oidset, dev.name, iface,  opts.begin,
                    opts.end)

def main(argv=sys.argv):
    """Parse options, output config"""
    global OPTS

    prog = os.path.basename(argv[0])
    usage = 'usage: %prog device [device]'

    parser = optparse.OptionParser(usage=usage, version=VERSION)

    parser.add_option('-D', None,
        action='store_true', dest='Debug', default=False,
        help='interactive debugging')
    parser.add_option('-n', None,
        action='store_true', dest='dry_run', default=False,
        help='''dry run: don't do anything just print what would be done''')
    parser.add_option('-b', '--begin',
        action='store', type='int', default=None, dest='begin',
        help="begin time (seconds since the epoch)")
    parser.add_option('-e', '--end',
        action='store', type='int', default=None, dest='end',
        help="end time (seconds since the epoch)")
    parser.add_option('-l', '--last', dest='last',
        action='store', type='int', default=3600,
        help="set time range to last n seconds")


    (opts, args) = parser.parse_args(args=argv[1:])

    if (opts.begin and not opts.end) or (not opts.begin and opts.end):
        print "must specify both -b and -e"
        return 1
    
    if not opts.begin and not opts.end:
        opts.end = int(time.time())
        opts.begin = opts.end - opts.last

    # Interactive debugging
    if opts.Debug:
        import pdb
        pdb.set_trace()

    return process_devices(opts, args)

if __name__ == '__main__':
    sys.exit(main())
