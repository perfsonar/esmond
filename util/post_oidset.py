#!/usr/bin/env python

"""
Test script to update oidsets with device endpoint.

Just adds and removes a single oidset to a device on subsequent runs.
"""

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

    print 'result:', json.dumps(get(url), indent=4)

    pass

if __name__ == '__main__':
    main()