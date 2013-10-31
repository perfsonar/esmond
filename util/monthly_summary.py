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
    aggregate_to_device_interface_endpoint, lastmonth, \
    get_month_start_and_end, iterate_device_interface_endpoint

# Chosen because there isn't a seconds value for a month, so using
# the aggregation value for a day because the monthly summaries
# are derived from daily rollups.
AGG_FREQUENCY = 86400

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
    parser.add_option('-m', '--month', metavar='MONTH',
            type='string', dest='month', default='',
            help='Specify month in YYYY-MM format.')
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

    if not options.month:
        print 'No -m arg, defaulting to last month'
        now = datetime.datetime.utcnow()
        start_year, start_month = lastmonth((now.year,now.month))
        start_point = datetime.datetime.strptime('{0}-{1}'.format(start_year, start_month),
            '%Y-%m')
    else:
        print 'Parsing -m input {0}'.format(options.month)
        try:
            start_point = datetime.datetime.strptime(options.month, '%Y-%m')
        except ValueError:
            print 'Unable to parse -m arg {0} - expecting YYYY-MM format'.format(options.month)
            return -1

    print 'Generating monthly summary starting on: {0}'.format(start_point)

    start, end = get_month_start_and_end(start_point)

    if options.verbose: print 'Scanning from {0} to {1}'.format(
        datetime.datetime.utcfromtimestamp(start), 
        datetime.datetime.utcfromtimestamp(end)
    )
    
    filters = ApiFilters()

    filters.verbose = options.verbose
    filters.endpoint = options.endpoint
    filters.agg = AGG_FREQUENCY
    filters.cf = 'raw'

    filters.begin_time = start
    filters.end_time = end

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

    aggs = aggregate_to_device_interface_endpoint(data, options.verbose)

    # Generate the grand total
    total_aggs = {}

    for d, i, endpoint, val in iterate_device_interface_endpoint(aggs):
        if not total_aggs.has_key(endpoint): total_aggs[endpoint] = 0
        total_aggs[endpoint] += val

    if options.verbose: print 'Grand total:', total_aggs

    # Roll everything up before posting
    summary_name = get_summary_name(interface_filters)

    post_data = {}

    for device, interface, endpoint, val in iterate_device_interface_endpoint(aggs):
        path = (MONTHLY_NS, summary_name, device, interface, endpoint)
        payload = { 'ts': start*1000, 'val': val }
        if options.verbose > 1: print path, '\n\t', payload
        post_data[path] = payload                

    for endpoint, val in total_aggs.items():
        path = (MONTHLY_NS, summary_name, endpoint)
        payload = { 'ts': start*1000, 'val': val }
        if options.verbose > 1: print path, '\n\t', payload
        post_data[path] = payload

    if not options.post:
        print 'Not posting (use -P flag to write to backend).'
        return

    if not options.user or not options.key:
        print 'user and key args must be supplied to POST summary data.'
        return

    for path, payload in post_data.items():
        args = {
            'api_url': options.api_url, 
            'path': list(path), 
            'freq': AGG_FREQUENCY*1000
        }
        
        p = PostRawData(username=options.user, api_key=options.key, **args)
        p.add_to_payload(payload)
        p.send_data()

        if options.verbose:
            print 'verifying write for', path
            p = { 'begin': start*1000, 'end': start*1000 }
            g = GetRawData(params=p, **args)
            result = g.get_data()
            print result, '\n\t', result.data[0]

    return

if __name__ == '__main__':
    main()
