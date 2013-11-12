#!/usr/bin/env python

"""
Generate bogus data to put into a memcached persist queue for testing.
"""

import os
import string
import sys

from optparse import OptionParser

from esmond.persist import PollResult
from esmond.api.models import OIDSet

def main():
    usage = '%prog [ -f filename | -r NUM | -i NUM | -v ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-r', '--routers', metavar='NUM_ROUTERS',
            type='int', dest='routers', default=1,
            help='Number of test "routers" to generate.')
    parser.add_option('-i', '--interfaces', metavar='NUM_INTERFACES',
            type='int', dest='interfaces', default=1,
            help='Number of test interfaces to generate on each test router.')
    parser.add_option('-o', '--oidsets', metavar='NUM_OIDSETS',
            type='int', dest='oidsets', default=2,
            help='Number of oidsets to assign to each fake device/router.')
    parser.add_option('-v', '--verbose',
        dest='verbose', action='store_true', default=False,
        help='Verbose output.')
    options, args = parser.parse_args()

    oidset_oid = []

    for oidset in OIDSet.objects.filter(frequency=30)[0:options.oidsets]:
        for oid in oidset.oids.exclude(name='sysUpTime'):
            oidset_oid.append({'oidset': oidset, 'oid': oid})

    if options.verbose:
        print 'Using following oidsets/oids for fake devices:'
        for i in oidset_oid: print i

    for i in string.lowercase[0:options.routers]:
        device_name = 'rtr_{0}'.format(i)
        for ii in xrange(options.interfaces):
            interface_name = 'iface_{0}'.format(ii)
            for os_o in oidset_oid:
                if options.verbose:
                    print device_name, os_o['oidset'], os_o['oid'], interface_name


    pass

if __name__ == '__main__':
    main()