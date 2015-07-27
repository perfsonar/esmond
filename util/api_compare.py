#!/usr/bin/env python

"""
Utility script to call v1 and v2 apis for comparison during development.
"""

import requests

import json
import os
import sys

import pprint

pp = pprint.PrettyPrinter(indent=4)

uri_map = dict(
    device_root='/{0}/device/',
    interface_root='/{0}/interface/',
    device_detail='/{0}/device/rtr_a/',
    interface_list='/{0}/device/rtr_a/interface/',
    interface_error='/{0}/device/rtr_a/interface/xe-0@2F0@2F0/discard/in',
    interface_traffic='/{0}/device/rtr_a/interface/xe-0@2F0@2F0/out',
    pdu_list='/{0}/pdu/',
    pdu_detail='/{0}/pdu/sentry_pdu/',
    pdu_outlet_list='/{0}/pdu/sentry_pdu/outlet/',
    outlet_list='/{0}/outlet/',
    outlet_list_search='/{0}/outlet/?outletName__contains=rtr_a',
    oid_set_map='/{0}/oidsetmap/',
)

def main():

    import os.path
    from optparse import OptionParser
    usage = '%prog [ -f filename | -n NUM | -v ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-d', '--device-detail',
            dest='device_detail', action='store_true', default=False,
            help='Device detail.')
    parser.add_option('-D', '--device-list',
            dest='device_root', action='store_true', default=False,
            help='List of devices.')
    parser.add_option('-e', '--interface-error',
            dest='interface_error', action='store_true', default=False,
            help='Interface endpoint for error data (discard/in).')
    parser.add_option('-t', '--interface-traffic',
            dest='interface_traffic', action='store_true', default=False,
            help='Interface endpoint for traffic data (out).')
    parser.add_option('-I', '--interface-list', # meta
            dest='interface_list', action='store_true', default=False,
            help='List of interfaces on a router (paginated).')
    parser.add_option('-R', '--interface-root', # meta
            dest='interface_root', action='store_true', default=False,
            help='Root level list of interfaces (paginated).')
    parser.add_option('-p', '--pdu-list',
            dest='pdu_list', action='store_true', default=False,
            help='PDU list.')
    parser.add_option('-P', '--pdu-detail',
            dest='pdu_detail', action='store_true', default=False,
            help='PDU detail.')
    parser.add_option('-U', '--pdu-outlet-list',
            dest='pdu_outlet_list', action='store_true', default=False,
            help='PDU Outlet list.')
    parser.add_option('-o', '--outlet-list',
            dest='outlet_list', action='store_true', default=False,
            help='Outlet List.')
    parser.add_option('-s', '--outlet-list-search',
            dest='outlet_list_search', action='store_true', default=False,
            help='Outlet list search.')
    parser.add_option('-M', '--oid-set-map',
            dest='oid_set_map', action='store_true', default=False,
            help='Oidset map.')
    parser.add_option('-u', '--url', metavar='URL',
            type='string', dest='url', default='http://localhost:8000',
            help='Url where API is running (default: %default).')
    parser.add_option('-v', '--verbose',
        dest='verbose', action='store_true', default=False,
        help='Verbose output.')
    options, args = parser.parse_args()

    selected = 0
    selection = None

    for i in uri_map.keys():
        if getattr(options, i): 
            selected += 1
            selection = i

    if selected == 0:
        print 'no option selected'
        parser.print_help()
        return -1
    elif selected > 1:
        print 'select only one option'
        parser.print_help()
        return -1

    print 'calling:', uri_map.get(selection)

    r = requests.get(options.url + uri_map.get(selection).format('v1'))
    print pp.pprint(json.loads(r.content))

    print '=+=+=+='
    # return

    r = requests.get(options.url + uri_map.get(selection).format('v2'))
    if options.verbose or r.status_code != 200:
        print r.content
    print pp.pprint(json.loads(r.content))

    pass

if __name__ == '__main__':
    main()