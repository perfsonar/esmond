#!/usr/bin/env python

"""
Quick one off to query interface data from API.  Starter sketch for 
summary tools.
"""

import os
import requests
import sys

from optparse import OptionParser

from esmond.api.api import OIDSET_INTERFACE_ENDPOINTS
from esmond.api.client.fetch_data import ApiConnect, ApiFilters, BulkDataPayload

def main():    
    usage = '%prog [ -U rest url (required) | -i ifDescr pattern | -a alias pattern | -e endpoint ]'
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
            type='string', dest='endpoint', 
            help='Endpoint type to query (required).')
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()
    
    filters = ApiFilters()

    filters.verbose = options.verbose

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

    if not options.endpoint or options.endpoint not in valid_endpoints:
        print 'Specify a valid endpoint of the form: {0}'.format(valid_endpoints)
        parser.print_help()
        return -1

    conn = ApiConnect(options.api_url, filters)

    interfaces = []

    for i in conn.get_interfaces(**interface_filters):
        if options.verbose: print i
        interfaces.append({'device': i.device, 'iface': i.ifDescr})
        if options.verbose > 1: print i.dump

    data = conn.get_interface_bulk_data(interfaces, options.endpoint)
    print data

    for datum in data.data:
        # do something....
        # print datum
        pass

    pass

if __name__ == '__main__':
    main()