#!/usr/bin/env python

"""
Generate bogus data to put into a memcached persist queue for testing.

The approximate math on how many data points will be generated:

options.loop * options.routers * options.interfaces * (options.oidsets * 2)

as most of the oidsets being pulled have 2 oids.
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

class TestQueuesException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class TestQueuesWarning(Warning): pass

class TestQueues(object):
    """Manage the test queues"""
    def __init__(self, config, write, verbose):
        super(TestQueues, self).__init__()
        self.config = config
        self.write = write
        self.verbose = verbose

        self._queues = {}
        self._device_map = {}
        self._next_q = 1

        if not config.persist_queues.has_key('cassandra'):
            raise TestQueuesException('Config does not have cassandra persist_queues defined.')

        self._cassandra_queues = config.persist_queues['cassandra'][1]

        for i in xrange(1,self._cassandra_queues+1):
            qname = 'cassandra_{0}'.format(i)
            self._queues[qname] = MemcachedPersistQueue(qname, config.espersistd_uri)
            print self._queues[qname]

    def _get_device_queue(self, pr):
        if not self._device_map.has_key(pr.device_name):
            self._device_map[pr.device_name] = self._next_q
            if self._next_q < self._cassandra_queues:
                self._next_q += 1
            else:
                self._next_q = 1

        return 'cassandra_{0}'.format(self._device_map[pr.device_name])

    def put(self, pr):
        q = self._get_device_queue(pr)
        if not self.write:
            print 'Noop to: {0}'.format(q)
            if self.verbose > 1: print pr.json()
        else:
            self._queues[q].put(pr)


def main():
    usage = '%prog [ -r NUM | -i NUM | -o NUM | -l NUM | -v ]'
    usage += '\n\tAmount of data generated ~= r * i * (o * 2) * l'
    parser = OptionParser(usage=usage)
    parser.add_option('-r', '--routers', metavar='NUM_ROUTERS',
            type='int', dest='routers', default=1,
            help='Number of test "routers" to generate (default=%default).')
    parser.add_option('-i', '--interfaces', metavar='NUM_INTERFACES',
            type='int', dest='interfaces', default=2,
            help='Number of test interfaces to generate on each test router (default=%default).')
    parser.add_option('-o', '--oidsets', metavar='NUM_OIDSETS',
            type='int', dest='oidsets', default=2,
            help='Number of oidsets to assign to each fake device/router (default=%default).')
    parser.add_option('-l', '--loop', metavar='NUM_LOOPS',
            type='int', dest='loop', default=1,
            help='Number of times to send data for each "device (default=%default)."')
    parser.add_option('-W', '--write',
            dest='write', action='store_true', default=False,
            help='Actually write the data to the memcache queue.')
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()

    if options.routers > 26:
        print 'There is an upper bound of 26 fake routers.'
        return -1

    config = get_config(get_config_path())

    qs = TestQueues(config, options.write, options.verbose)

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
            device_name = 'fake_rtr_{0}'.format(dn)
            for oidset in oidset_oid.keys():
                data = []
                for oid in oidset_oid[oidset]:
                    for i in xrange(options.interfaces):
                        interface_name = 'fake_iface_{0}'.format(i)
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
                if options.verbose > 1: print pr.json()
                qs.put(pr)
        ts += 30
        val += 50
    pass

if __name__ == '__main__':
    main()