#!/usr/bin/env python

"""
Test script to update oidsets with device endpoint.

Just adds and removes a single oidset to a device on subsequent runs.
"""

import datetime
import json
import os
import requests
import sys

from optparse import OptionParser

from esmond.api.client.snmp import ApiConnect

def main():
    usage = '%prog [ -u username | -a api_key ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-u', '--user', metavar='USER',
            type='string', dest='user', default='',
            help='POST interface username.')
    parser.add_option('-k', '--key', metavar='API_KEY',
            type='string', dest='key', default='',
            help='API key for post operation.')
    options, args = parser.parse_args()

    conn = ApiConnect(api_url='http://localhost:8000', 
        username=options.user, api_key=options.key)

    d1 = list(conn.get_devices(**{'name': 'lbl-mr2'}))[0]

    oidsets = d1.oidsets

    if 'SentryPoll' not in oidsets:
        print 'adding SentryPoll'
        oidsets.append('SentryPoll')
    else:
        print 'removing SentryPoll'
        oidsets.pop()

    print 'setting oidsets to:', oidsets

    d1.set_oidsets(oidsets)

    # refresh the result just to make sure.

    d2 = list(conn.get_devices(**{'name': 'lbl-mr2'}))[0]
    print 'Checking result:', d2
    print d2.oidsets

    if (d1.begin_time != d2.begin_time) or \
        (d1.end_time != d2.end_time):
        print 'Timestamp mismatch!'
        print 'orig:', d1.begin_time, d1.end_time
        print 'new :', d2.begin_time, d2.end_time

    pass

if __name__ == '__main__':
    main()