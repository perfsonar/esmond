#!/usr/bin/env python

"""
Quick one off to query interface data from API.  Starter sketch for 
summary tools.
"""

import datetime
import os
import requests
import sys
import time

from optparse import OptionParser

from esmond.api.api import OIDSET_INTERFACE_ENDPOINTS
from esmond.api.client.snmp import ApiConnect, ApiFilters, BulkDataPayload

SUMMARY_NS = 'summary'

def main():    
    usage = '%prog [ -U rest url (required) | -i ifDescr pattern | -a alias pattern | -e endpoint -e endpoint (multiple ok) ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-U', '--url', metavar='ESMOND_REST_URL',
            type='string', dest='api_url', 
            help='URL for the REST API (default=%default) - required.',
            default='http://localhost')
    parser.add_option('-i', '--ifdescr', metavar='IFDESCR',
            type='string', dest='ifdescr_pattern', 
            help='Pattern to apply to interface ifdescr search.')
    parser.add_option('-a', '--alias', metavar='ALIAS',
            type='string', dest='alias_pattern', 
            help='Pattern to apply to interface alias search.')
    parser.add_option('-e', '--endpoint', metavar='ENDPOINT',
            dest='endpoint', action='append', default=[],
            help='Endpoint type to query (required) - can specify more than one.')
    parser.add_option('-l', '--last', metavar='LAST',
            type='int', dest='last', default=0,
            help='Last n minutes of data to query - api defaults to 60 if not given.')
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()
    
    filters = ApiFilters()

    filters.verbose = options.verbose

    if options.last:
        filters.begin_time = int(time.time() - (options.last*60))
    else:
        # Default to one minute ago, then rounded to the nearest 30 
        # second bin.
        time_point = int(time.time() - 60)
        bin_point = time_point - (time_point % 30)
        filters.begin_time = filters.end_time = bin_point

    valid_endpoints = []

    for i in OIDSET_INTERFACE_ENDPOINTS.keys():
        for ii in OIDSET_INTERFACE_ENDPOINTS[i].keys():
            if ii not in valid_endpoints:
                valid_endpoints.append(ii)

    if not options.ifdescr_pattern and not options.alias_pattern:
        # Don't grab *everthing*.
        print 'Specify an ifdescr or alias filter option.'
        parser.print_help()
        return -1
    elif options.ifdescr_pattern and options.alias_pattern:
        # Keep it simple for now, flesh this out later.
        print 'Specify only one filter option.'
        parser.print_help()
        return -1
    else:
        if options.ifdescr_pattern:
            interface_filters = { 'ifDescr__contains': options.ifdescr_pattern }
        elif options.alias_pattern:
            interface_filters = { 'ifAlias__contains': options.alias_pattern }

    if not options.endpoint:
        print 'No endpoints specified: {0}'.format(valid_endpoints)
        parser.print_help()
        return -1
    else:
        for ep in options.endpoint:
            if ep not in valid_endpoints:
                print 'Specify a valid endpoint of the form: {0}'.format(valid_endpoints)
                parser.print_help()
                return -1
        filters.endpoint = options.endpoint
        pass

    conn = ApiConnect(options.api_url, filters)

    data = conn.get_interface_bulk_data(**interface_filters)

    print data

    aggs = {}

    for row in data.data:
        # do something....
        if options.verbose: print ' *', row
        for data in row.data:
            if options.verbose > 1: print '  *', data
            if not aggs.has_key(data.ts_epoch): aggs[data.ts_epoch] = {}
            if not aggs[data.ts_epoch].has_key(row.endpoint): 
                aggs[data.ts_epoch][row.endpoint] = 0
            if data.val != None:
                aggs[data.ts_epoch][row.endpoint] += data.val
        pass

    bin_steps = aggs.keys()[:]
    bin_steps.sort()

    for bin_ts in bin_steps:
        print bin_ts
        for endpoint in aggs[bin_ts].keys():
            path = [ SUMMARY_NS, 'TotalTraffic' ] + endpoint.split('/')
            print ' *', endpoint, ':', aggs[bin_ts][endpoint], path

    pass

if __name__ == '__main__':
    main()