#!/usr/bin/env python

"""
esfetch emulates the rrdfetch tool.

the file is a key that can be used to find data in the ESxSNMP datastore.
the file field has the following form:

    device,collection_group,interface

Currently the FastPoll and FastPollHC collection groups are understood.
Currently the only consolidation function understood is AVERAGE
"""

import sys
import time
import optparse
from pprint import pprint

import tsdb
from esxsnmp.util import get_ESDB_client

def output_data(data):
    import pdb
    pdb.set_trace()
    counters = {}
    if data.has_key('ifHCInOctets'):
        counters['in'] = data["ifHCInOctets"].aggregate
        counters['out'] = data["ifHCOutOctets"].aggregate
        print "                   ifHCInOctets       ifHCOutOctets"
    else:
        counters['in'] = data["ifInOctets"].counter32
        counters['out'] = data["ifOutOctets"].counter32
        print "                   ifInOctets         ifOutOctets"
    print 

#    last_good = {}
#    for dir in counters.keys():
#        if counters[dir][0].flags & tsdb.ROW_VALID:
#            last_good[dir] = counters[dir][0]
#        else:
#            last_good[dir] = None
#
    val = {}
    for i in range(1, len(counters['in'])):
        print "%d: %s %s" % (counters['in'][i].timestamp,
                counters['in'][i].average,
                counters['out'][i].average)
#            if counters[dir][i].flags & tsdb.ROW_VALID and \
#                    counters[dir][i-1].flags & tsdb.ROW_VALID:
#                if last_good[dir] is None:
#                    val[dir] = "nan"
#                else:
#                val[dir] = str(8 * (counters[dir][i].value - counters[dir][i-1].value) \
#                        / float(counters[dir][i].timestamp - counters[dir][i-1].timestamp))
#                    val[dir] = str(8 * (counters[dir][i].value - last_good[dir].value) \
#                            / float(counters[dir][i].timestamp - last_good[dir].timestamp))

#                last_good[dir] = counters[dir][i]
#            else:
#                val[dir] = "nan"
#                if not counters[dir][i].flags & tsdb.ROW_VALID:
#                    counters[dir][i].timestamp = counters[dir][i-1].timestamp + 30

#        print "%d: %s %s" % (counters['in'][i].timestamp, val['in'], val['out'])

def fetch_data(device, iface_name, oidset, begin, end, CF, resolution):
    (transport, client) = get_ESDB_client()
    transport.open()

    if oidset == 'FastPollHC':
        oids = ('ifHCInOctets', 'ifHCOutOctets')
    else:
        oids = ('ifInOctets', 'ifOutOctets')

    data = {}
    for oid in oids:
        data[oid] = client.select(device, iface_name, oidset, oid, begin, end,
                None, CF, resolution)

    transport.close()
    return data

def main(argv):
    now = int(time.time())

    oparse = optparse.OptionParser(usage="%prog fetch file CF [options]")
    oparse.add_option("-d", "--debug", dest="debug", action="store_true",
            default=False, help="enable debugging")
    oparse.add_option("-b", "--begin", dest="begin", help="begin time",
            default=str(now-3600))
    oparse.add_option("-e", "--end", dest="end", help="end time",
        default=str(now))
    oparse.add_option("-r", "--resolution", dest="resolution", default=None,
            help="resolution of dataset (default is native resolution)")

    if argv[0] != 'fetch':
        oparse.error("only fetch is implemented")

    if len(argv) < 3:
        oparse.error("must specify file and CF")

    (file, CF) = argv[1:3]
    (opts, args) = oparse.parse_args(args=argv[3:])

    (device, oidset, iface_name) = file.split(',')
   
    output_data(fetch_data(device, iface_name, oidset, opts.begin, opts.end, CF, opts.resolution))

def esfetch():
    """Entry point for the esfetch script."""
    import sys
    main(sys.argv[1:])
