#!/usr/bin/env python

"""
Quick one off to query interface data from API.  Starter sketch for 
summary tools.
"""

import datetime
import os
import os.path
import requests
import sys
import time

from optparse import OptionParser

from esmond.api.client.snmp import ApiConnect, ApiFilters
from esmond.api.client.timeseries import PostRawData, GetRawData
from esmond.api.client.util import MONTHLY_NS, get_summary_name, \
    aggregate_to_ts_and_endpoint

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
            type='int', dest='last', default=1,
            help='Last n months of data to query (default=%default).')
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    parser.add_option('-P', '--post',
            dest='post', action='store_true', default=False,
            help='Switch to actually post data to the backend - otherwise it will just query and give output.')
    parser.add_option('-u', '--user', metavar='USER',
            type='string', dest='user', default='',
            help='POST interface username.')
    parser.add_option('-k', '--key', metavar='API_KEY',
            type='string', dest='key', default='',
            help='API key for POST operation.')
    options, args = parser.parse_args()
    
    filters = ApiFilters()

    filters.verbose = options.verbose
    filters.endpoint = options.endpoint
    filters.agg = 86400
    filters.cf = 'raw'

    filters.begin_time = int(time.time() - datetime.timedelta(days=30*options.last).total_seconds())

    if not options.ifdescr_pattern and not options.alias_pattern:
        # Don't grab *everthing*.
        print 'Specify an ifdescr or alias filter option.'
        parser.print_help()
        return -1
    elif options.ifdescr_pattern and options.alias_pattern:
        print 'Specify only one filter option.'
        parser.print_help()
        return -1
    else:
        if options.ifdescr_pattern:
            interface_filters = { 'ifDescr__contains': options.ifdescr_pattern }
        elif options.alias_pattern:
            interface_filters = { 'ifAlias__contains': options.alias_pattern }

    conn = ApiConnect(options.api_url, filters)

    data = conn.get_interface_bulk_data(**interface_filters)

    print data

    # Aggregate/sum the returned data by timestamp and endpoint alias.
    aggs = aggregate_to_ts_and_endpoint(data, options.verbose)

    return

    # Might be searching over a time period, so re-aggregate based on 
    # path so that we only need to do one API write per endpoint alias, 
    # rather than a write for every data point.

    bin_steps = aggs.keys()[:]
    bin_steps.sort()

    summary_name = get_summary_name(interface_filters)

    path_aggregation = {}

    for bin_ts in bin_steps:
        if options.verbose > 1: print bin_ts
        for endpoint in aggs[bin_ts].keys():
            path = (MONTHLY_NS, summary_name, endpoint)
            if not path_aggregation.has_key(path):
                path_aggregation[path] = []
            if options.verbose > 1: print ' *', endpoint, ':', aggs[bin_ts][endpoint], path
            path_aggregation[path].append({'ts': bin_ts*1000, 'val': aggs[bin_ts][endpoint]})

    if not options.post:
        print 'Not posting (use -P flag to write to backend).'
        return

    if not options.user or not options.key:
        print 'user and key args must be supplied to POST summary data.'
        return

    for k,v in path_aggregation.items():
        args = {
            'api_url': options.api_url, 'path': list(k), 'freq': 30000
        }

        args_and_auth = dict({'username': options.user, 'api_key': options.key}, **args)
        
        p = PostRawData(**args_and_auth)
        p.set_payload(v)
        p.send_data()
        if options.verbose:
            print 'verifying write'
            g = GetRawData(**args)
            payload = g.get_data()
            print payload
            for d in payload.data:
                print '  *', d


    pass

if __name__ == '__main__':
    main()