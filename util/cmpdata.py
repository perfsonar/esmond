#!/usr/bin/env python
# 
"""template python command with command line parsing"""

import os
import sys
import json
import time
import optparse
import datetime

import requests

from esmond.api.models import *
from esmond.cassandra import CASSANDRA_DB
from esmond.config import get_config, get_config_path

VERSION = "0"

OLD_REST_API = "http://snmp-west.es.net:8001/snmp"

IFACE_IGNORE = ["lo0"]

small_dev_set = ['lbl-mr2', 'anl-mr2']

class DataBundle(object):
    """bundle together data for comparison"""
    def __init__(self, oidset, oid, frequency, device, interface, direction, begin, end, data, url):
        self.oid = oid
        self.oidset = str(oidset)
        self.frequency = frequency
        self.device = device
        self.interface = interface
        self.direction = direction
        self.begin = begin
        self.end = end
        self.data = data
        self.url = url


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

def compare_data(bundle, db):
    # print bundle.device, bundle.interface, bundle.oid, bundle.frequency
    # print bundle.direction, len(bundle.data['data'])
    path = [bundle.device, bundle.oidset, bundle.oid, bundle.interface]

    # print path
    url = 'http://localhost/v1/device' + bundle.url.replace(OLD_REST_API, '')

    params = {
        'begin': bundle.begin,
        'end': bundle.end,
    }

    response = requests.get(url, params=params)

    print '**', ':'.join(path)
    
    
    if response.status_code == 200:
        data_n = json.loads(response.content)
    else:
        print 'Got:', response.status_code
        print response.url
        return

    val_new = {}

    for i in data_n['data']:
        val_new[i[0]] = i[1]


    period = 600 # avg bin period in sec
    av_div = period/(30)

    orig_avg = {}
    new_avg = {}
    ordered_bins = []

    for i in bundle.data['data']:
        # print i[0]*1000, ':' ,
        if val_new.has_key(i[0]):
            orig_val = i[1]
            new_val = val_new.get(i[0])
            if orig_val is None or new_val is None:
                if orig_val is None: orig_val = 0.0
                if new_val is None: new_val = 0.0
            else:
                new_val = new_val*1000
                avg_bin = ((i[0])/period)*period
                if not orig_avg.has_key(avg_bin):
                    ordered_bins.append(avg_bin)
                    orig_avg[avg_bin] = new_avg[avg_bin] = 0
                orig_avg[avg_bin] += orig_val
                new_avg[avg_bin] += new_val
        else:
            print 'no match found - orig val:', i[1], datetime.datetime.utcfromtimestamp(i[0]), i[0]

    for i in ordered_bins:
        row = [str(datetime.datetime.utcfromtimestamp(i)),
                orig_avg[i], new_avg[i]]
        if orig_avg[i] != 0:
            row.append(new_avg[i]/orig_avg[i]*100)
        else:
            row.append('no data')
        print '{: >20} {: >15} {: >15} {: <15} '.format(*row)

    return

    # period = 600*1000 # avg bin period in ms
    # av_div = period/(30*1000)

    # orig_avg = {}
    # new_avg = {}
    # ordered_bins = []

    # for i in bundle.data['data']:
    #     # print i[0]*1000, ':' ,
    #     if val_new.has_key(i[0]*1000):
    #         orig_val = i[1]
    #         new_val = val_new.get(i[0]*1000)
    #         if orig_val is None or new_val is None:
    #             if orig_val is None: orig_val = 0.0
    #             if new_val is None: new_val = 0.0
    #         else:
    #             new_val = new_val*1000
    #             avg_bin = ((i[0]*1000)/period)*period
    #             if not orig_avg.has_key(avg_bin):
    #                 ordered_bins.append(avg_bin)
    #                 orig_avg[avg_bin] = new_avg[avg_bin] = 0
    #             orig_avg[avg_bin] += orig_val
    #             new_avg[avg_bin] += new_val
    #     else:
    #         print 'no match found - orig val:', i[1], datetime.datetime.utcfromtimestamp(i[0]), i[0]*1000

    # for i in ordered_bins:
    #     row = [str(datetime.datetime.utcfromtimestamp(i/1000)),
    #             orig_avg[i], new_avg[i]]
    #     if orig_avg[i] != 0:
    #         row.append(new_avg[i]/orig_avg[i]*100)
    #     else:
    #         row.append('no data')
    #     print '{: >20} {: >15} {: >15} {: <15} '.format(*row)

def old_fetch_data(oidset, dev, iface, begin, end, db):
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
        bundle = DataBundle(oidset, oid, oidset.frequency, dev, iface, d,
                begin, end, data, url)
        compare_data(bundle, db)
        # break

def process_devices(opts, devs, db):
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
                    opts.end, db)
            # break

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
        
    config = get_config(get_config_path())
    # db = CASSANDRA_DB(config)
    db = None

    return process_devices(opts, args, db)

if __name__ == '__main__':
    sys.exit(main())
