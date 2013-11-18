#!/usr/bin/env python

"""
Small example/test script to post some data to locally running rest 
interface (django runserver) and cassandra instance.
"""

import json
import os
import requests
import sys
import time

from optparse import OptionParser

from esmond.api.client.timeseries import PostRawData, PostBaseRate, GetRawData, GetBaseRate
from esmond.util import atencode

def read_insert(api_url, ts, p_type, path):
    params = {
        'begin': ts-90000, 'end': ts+1000
    }

    get = None

    args = {
        'api_url': api_url, 
        'path': path, 
        'freq': 30000,
        'params': params,
    }

    if p_type == 'RawData':
        get = GetRawData(**args)
    elif p_type == 'BaseRate':
        get = GetBaseRate(**args)

    payload = get.get_data()

    print payload
    for d in payload.data:
        print '  *', d

def main():
    usage = '%prog [ -u username | -a api_key ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-U', '--url', metavar='ESMOND_REST_URL',
            type='string', dest='api_url', 
            help='URL for the REST API (default=%default) - required.',
            default='http://localhost')
    parser.add_option('-u', '--user', metavar='USER',
            type='string', dest='user', default='',
            help='POST interface username.')
    parser.add_option('-k', '--key', metavar='API_KEY',
            type='string', dest='key', default='',
            help='API key for post operation.')
    options, args = parser.parse_args()

    ts = int(time.time()) * 1000

    payload = [
        { 'ts': ts-90000, 'val': 1000 },
        { 'ts': ts-60000, 'val': 2000 },
        { 'ts': ts-30000, 'val': 3000 },
        { 'ts': ts, 'val': 4000 },
    ]

    path = ['rtr_test_post', 'FastPollHC', 'ifHCInOctets', 'interface_test/0/0.0']

    p = PostRawData(api_url=options.api_url, path=path, freq=30000,
        username=options.user, api_key=options.key)
    # set_payload will completely replace the internal payload of the object.
    p.set_payload(payload)
    # add_to_payload will just add new items to internal payload.
    p.add_to_payload({'ts': ts+1000, 'val': 5000})
    # send the request and clear the internal payload list.
    p.send_data()
    # Second call will generate a warning since the first will
    # clear the internal payload.
    p.send_data()

    read_insert(options.api_url, ts, 'RawData', path)

    p = PostBaseRate(api_url=options.api_url, path=path, freq=30000,
        username=options.user, api_key=options.key)
    p.set_payload(payload)
    p.send_data()

    read_insert(options.api_url, ts, 'BaseRate', path)



if __name__ == '__main__':
    main()