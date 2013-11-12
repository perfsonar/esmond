#!/usr/bin/env python

"""
Generate bogus data to put into a memcached persist queue for testing.
"""

import json
import os
import pprint
import string
import sys
import time

from optparse import OptionParser

from esmond.api.models import OIDSet
from esmond.config import get_config, get_config_path
from esmond.persist import PollResult, MemcachedPersistQueue

pp = pprint.PrettyPrinter(indent=2)

def main():
    usage = '%prog [ -f filename | -r NUM | -i NUM | -v ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-r', '--routers', metavar='NUM_ROUTERS',
            type='int', dest='routers', default=1,
            help='Number of test "routers" to generate.')
    parser.add_option('-i', '--interfaces', metavar='NUM_INTERFACES',
            type='int', dest='interfaces', default=2,
            help='Number of test interfaces to generate on each test router.')
    parser.add_option('-o', '--oidsets', metavar='NUM_OIDSETS',
            type='int', dest='oidsets', default=2,
            help='Number of oidsets to assign to each fake device/router.')
    parser.add_option('-l', '--loop', metavar='NUM_LOOPS',
            type='int', dest='loop', default=1,
            help='Number of times to send data for each "device."')
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()

    config = get_config(get_config_path())

    persistq = MemcachedPersistQueue('test_data', config.espersistd_uri)

    oidset_oid = {}
    oid_count = 0

    for oidset in OIDSet.objects.filter(frequency=30)[0:options.oidsets]:
        if not oidset_oid.has_key(oidset.name): oidset_oid[oidset.name] = []
        for oid in oidset.oids.exclude(name='sysUpTime'):
            oidset_oid[oidset.name].append(oid.name)
            oid_count += 1
    
    if options.verbose:
        print 'Using following oidsets/oids for fake devices:'
        pp.pprint(oidset_oid)
    
    ts = int(time.time())
    val = 100

    print 'Generating {0} data points.'.format(
        options.loop*options.routers*options.interfaces*oid_count)

    for iteration in xrange(options.loop):
        for dn in string.lowercase[0:options.routers]:
            device_name = 'test_rtr_{0}'.format(dn)
            for oidset in oidset_oid.keys():
                data = []
                for oid in oidset_oid[oidset]:
                    for i in xrange(options.interfaces):
                        interface_name = 'iface_{0}'.format(i)
                        datum = [[oid, interface_name], val]
                        data.append(datum)
                pr = PollResult(
                        oidset_name=oidset,
                        device_name=device_name,
                        oid_name=oid,
                        timestamp=ts,
                        data=data,
                        metadata={'tsdb_flags': 1}
                        )
                if options.verbose == 1: print pr.json()
                elif options.verbose > 1: print json.dumps(json.loads(pr.json()), indent=4)
        ts += 30
        val += 50


    pass

if __name__ == '__main__':
    main()