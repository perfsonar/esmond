#!/usr/bin/env python

"""
Code to issue calls to the cassandra MX4J http server and get stats.
"""

import os
import sys

from optparse import OptionParser
from esmond.api.client.jmx import CassandraJMX

def main():
    usage = '%prog [ -U ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-U', '--url', metavar='URL',
            type='string', dest='url', default='http://localhost:8081',
            help='URL:port to cassandra mx4j server (default=%default).')
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()

    cjmx = CassandraJMX(options.url)
    print('Heap mem:', cjmx.get_heap_memory())
    print('Non-heap mem:', cjmx.get_non_heap_memory())
    print('Read latency:', cjmx.get_read_latency())
    print('Write latency:', cjmx.get_write_latency())
    print('Range latency:', cjmx.get_range_latency())
    print('GC count:', cjmx.get_gc_count())
    print('GC time:', cjmx.get_gc_time())
    print('Active read tasks:', cjmx.get_read_active())
    print('Pending read tasks:', cjmx.get_read_pending())
    print('Completed read tasks:', cjmx.get_read_completed())
    print('Active write tasks:', cjmx.get_write_active())
    print('Pending write tasks:', cjmx.get_write_pending())
    print('Completed write tasks:',cjmx.get_write_completed())
    print('Active gossip tasks:', cjmx.get_gossip_active())
    print('Pending gossip tasks:', cjmx.get_gossip_pending())
    print('Completed gossip tasks:',cjmx.get_gossip_completed())
    print('OS load:', cjmx.get_os_load())
    print('OS free mem:', cjmx.get_os_free_memory())
    print('OS free swap:', cjmx.get_os_free_swap())
    print('OS committed virtual mem:', cjmx.get_os_committed_virtual_memory())
    print('Pending compaction', cjmx.get_compaction_pending())
    print('Completed compaction', cjmx.get_compaction_complete())



if __name__ == '__main__':
    main()