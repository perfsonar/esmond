#!/usr/bin/env python

"""
Quick one off to query interface data from API.
"""

import os
import requests
import sys

from optparse import OptionParser

from esmond.api.client.fetch_data import ApiConnect, ApiFilters

def main():    
    usage = '%prog [ -U rest url (required) | -i ifDescr pattern | -a alias pattern ]'
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
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()
    
    filters = ApiFilters()

    filters.verbose = options.verbose

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

    conn = ApiConnect(options.api_url, filters)

    for i in conn.get_interfaces(**interface_filters):
        print i
        for e in i.get_endpoints():
            print '  *', e
        if options.verbose:
            print i.dump

    
    pass

if __name__ == '__main__':
    main()