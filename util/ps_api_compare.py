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
    archive_root='/{0}/archive/',
    metadata_root='/{0}/archive/0CB19291FB6D40EAA1955376772BF5D2/'
)

def main():

    import os.path
    from optparse import OptionParser
    usage = '%prog [ -v ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-a', '--archive-root',
            dest='archive_root', action='store_true', default=False,
            help='Simple get to archive root.')
    parser.add_option('-m', '--metadata-root',
            dest='metadata_root', action='store_true', default=False,
            help='Metadata root.')
    parser.add_option('-u', '--url', metavar='URL',
            type='string', dest='url', default='http://localhost:8000',
            help='Url where API is running (default: %default).')
    parser.add_option('-l', '--legacy',
            dest='legacy', action='store_true', default=False,
            help='Only call v1 endpoint.')
    parser.add_option('-p', '--post-back',
            dest='post_back', action='store_true', default=False,
            help='Verbose output.')
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

    r = requests.get(options.url + uri_map.get(selection).format('perfsonar'))
    print pp.pprint(json.loads(r.content))

    print '=+=+=+='
    if options.legacy: return

    r = requests.get(options.url + uri_map.get(selection).format('perfsonar2'))
    if options.verbose or r.status_code != 200:
        print r.content
    print pp.pprint(json.loads(r.content))

    if options.post_back:
        got = json.loads(r.content)
        if isinstance(got, list):
            send = got[0]
            method = 'post'
        elif isinstance(got, dict):
            send = got
            method = 'put'

        p = getattr(requests, method)(options.url + uri_map.get(selection).format('perfsonar2'),
            data=json.dumps(send), headers={ 'content-type': 'application/json' })
        print p.content

if __name__ == '__main__':
    main()