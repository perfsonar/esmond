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
    interface_list='/{0}/device/rtr_a/interface',
    interface_data='/{0}/device/rtr_a/interface/xe-0@2F0@2F0/discard/in',
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
    parser.add_option('-i', '--interface-data',
            dest='interface_data', action='store_true', default=False,
            help='Make call to interface endpoint.')
    parser.add_option('-I', '--interface-list',
            dest='interface_list', action='store_true', default=False,
            help='List of interfaces on a router.')
    parser.add_option('-R', '--interface-root',
            dest='interface_root', action='store_true', default=False,
            help='Root level list of interfaces.')
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

    r = requests.get(options.url + uri_map.get(selection).format('v2'))
    if options.verbose or r.status_code != 200:
        print r.content
    print pp.pprint(json.loads(r.content))

    pass

if __name__ == '__main__':
    main()