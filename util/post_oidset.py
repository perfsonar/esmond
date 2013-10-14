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

def get(url):
    r = requests.get(url)
    data = json.loads(r.content)
    return data


def main():
    url = 'http://localhost:8000/v1/device/lbl-mr2/'

    data = get(url)
    beg_o = data['begin_time']
    end_o = data['end_time']

    # add an oidset
    if 'SentryPoll' not in data['oidsets']:
        print 'adding'
        data['oidsets'].append('SentryPoll')
    else:
        print 'removing'
        data['oidsets'].pop()

    print 'sending:', json.dumps(data, indent=4)

    headers = {'content-type': 'application/json'}

    if True:
        p = requests.put(url, data=json.dumps(data), headers=headers)
        if p.status_code != 204:
            print p.content

    res = get(url)

    print 'result:', json.dumps(res, indent=4)

    beg_n = res['begin_time']
    end_n = res['end_time']

    if (beg_o != beg_n) or (end_o != end_n):
        print 'Timestamp mismatch!'
        print 'beg - orig: {0} - new: {1} - delta: {2}'.format(beg_o, beg_n, datetime.timedelta(seconds=beg_n-beg_o))
        print 'end - orig: {0} - new: {1} - delta: {2}'.format(end_o, end_n, datetime.timedelta(seconds=end_n-end_o))


    pass

if __name__ == '__main__':
    main()