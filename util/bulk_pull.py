#!/usr/bin/env python

"""
Example one off to play with/give example of bulk retrieval interface.
"""

import os
import sys
import time
from optparse import OptionParser

from esmond.api.client.timeseries import GetBulkRawData, GetBulkBaseRate

# The final frequency element can be a string or a numeric value.
# Class will cast/sanity check it internally.
PATHS = [
    ['snmp','anl-mr2','FastPollHC','ifHCOutOctets','xe-1/3/0','30000'],
    ['snmp','anl-mr2','FastPollHC','ifHCInOctets','xe-1/0/0','30000']
]

def main():
    usage = '%prog [ -U api_url ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-U', '--url', metavar='ESMOND_REST_URL',
            type='string', dest='url', 
            help='URL for the REST API (default=%default) - required.',
            default='http://localhost')
    parser.add_option('-b', '--baserate',
            dest='baserate', action='store_true', default=False,
            help='Query base rates rather than raw data.')
    parser.add_option('-l', '--last', metavar='LAST_MINS',
            type='int', dest='last', default=10,
            help='Last n minutes of data to query.')
    parser.add_option('-u', '--user', metavar='USER',
            type='string', dest='user', default='',
            help='POST interface username.')
    parser.add_option('-k', '--key', metavar='API_KEY',
            type='string', dest='key', default='',
            help='API key for post operation.')
    options, args = parser.parse_args()

    params = { 
        'begin': (time.time()-(options.last*60))*1000, 
        #'end': time.time()*1000 # end is optional - api will set to now.
    }
    
    if options.baserate:
        print 'Querying base rates'
        klass = GetBulkBaseRate
    else:
        print 'Querying raw data'
        klass = GetBulkRawData

    bulk = klass(options.url, username=options.user, api_key=options.key)
    payload = bulk.get_data(PATHS, **params)
    print payload

    for row in payload.data:
        print ' *', row
        for dp in row.data:
            print '  +', dp
    pass

if __name__ == '__main__':
    main()