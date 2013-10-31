#!/usr/bin/env python

"""
Quick one off to dump keys from a column family in an esmond 
cassandra instance.  Use optional -c (contains) flag to limit 
the output.

Generally used for debugging.
"""

import os
import sys

from optparse import OptionParser

from esmond.config import get_config, get_config_path
from esmond.cassandra import CASSANDRA_DB

def main():
    usage = '%prog [ -c col_family | -p pattern_to_find (optional) ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--column', metavar='COLUMN_FAMILY',
            type='string', dest='column_family',  default='raw',
            help='Column family to dump [raw|rate|aggs|stat] (default=%default).')
    parser.add_option('-p', '--pattern', metavar='PATTERN',
            type='string', dest='pattern', 
            help='Optional pattern to look for in keys (uses python string.find()).')
    parser.add_option('-l', '--limit', metavar='LIMIT',
            type='int', dest='limit', default=25,
            help='Limit number of keys dumped since a few generally makes the point (default=%default).')
    options, args = parser.parse_args()

    config = get_config(get_config_path())

    db = CASSANDRA_DB(config, clear_on_test=False)

    col_fams = {
        'raw': db.raw_data,
        'rate': db.rates,
        'aggs': db.aggs,
        'stat': db.stat_agg
    }

    if options.column_family not in col_fams.keys():
        print '{0} is not a valid column family selection'.format(options.column_family)
        parser.print_help()
        return -1

    count = 0

    for k in col_fams[options.column_family]._column_family.get_range(
        column_count=0, filter_empty=False):
        if count >= options.limit:
            break
        if k[0].find(options.pattern) == -1:
            continue
        print k[0]
        count += 1

    return

if __name__ == '__main__':
    main()