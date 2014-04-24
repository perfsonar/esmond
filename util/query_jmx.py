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

    qjmx = CassandraJMX(options.url)
    print 'Heap mem:', qjmx.get_heap_memory()
    print 'Non-heap mem:', qjmx.get_non_heap_memory()
    print 'Read latency:', qjmx.get_read_latency()
    print 'Write latency:', qjmx.get_write_latency()
    print 'Range latency:', qjmx.get_range_latency()
    print 'GC count:', qjmx.get_gc_count()
    print 'GC time:', qjmx.get_gc_time()
    print 'Active read tasks:', qjmx.get_read_active()
    print 'Pending read tasks:', qjmx.get_read_pending()
    print 'Completed read tasks:', qjmx.get_read_completed()
    print 'Active write tasks:', qjmx.get_write_active()
    print 'Pending write tasks:', qjmx.get_write_pending()
    print 'Completed write tasks:',qjmx.get_write_completed()
    print 'Active gossip tasks:', qjmx.get_gossip_active()
    print 'Pending gossip tasks:', qjmx.get_gossip_pending()
    print 'Completed gossip tasks:',qjmx.get_gossip_completed()
    print 'OS load:', qjmx.get_os_load()
    print 'OS free mem:', qjmx.get_os_free_memory()
    print 'OS free swap:', qjmx.get_os_free_swap()
    print 'OS committed virtual mem:', qjmx.get_os_committed_virtual_memory()
    print 'Pending compaction', qjmx.get_compaction_pending()
    print 'Completed compaction', qjmx.get_compaction_complete()



if __name__ == '__main__':
    main()