#!/usr/bin/env python

"""
Query gap inventory and get data from alternate server.
"""

import calendar
import datetime
import os
import sys

from optparse import OptionParser

from esmond.cassandra import _split_rowkey
from esmond.api.models import GapInventory
from esmond.api.client.timeseries import GetBaseRate, PostBaseRate

def ts_epoch(ts):
    return calendar.timegm(ts.utctimetuple())


def process_gaps(source_api_url, destination_api_url, username='', key='', 
            limit=0, verbose=False):

    if limit:
        gaps = GapInventory.objects.filter(processed=False)[:limit]
    else:
        gaps = GapInventory.objects.filter(processed=False)

    for gap in gaps:

        if verbose:
            print gap.row.row_key
            print ' *', gap.start_time, ts_epoch(gap.start_time)
            print ' *', gap.end_time, ts_epoch(gap.end_time)

        path = _split_rowkey(gap.row.row_key)[:-1]
        freq = int(path.pop())

        params = {
            'begin': ts_epoch(gap.start_time)*1000, 
            'end': ts_epoch(gap.end_time)*1000
        }

        args = {
            'api_url': source_api_url, 
            'path': path, 
            'freq': freq,
            'params': params,
            'username': username,
            'api_key': key
        }

        get = GetBaseRate(**args)

        payload = get.get_data()

        if verbose:
            print '  *', payload

        post_payload = []

        for d in payload.data:
            if verbose:
                print '   *', d, datetime.datetime.utcfromtimestamp(d.ts/1000)

            # Only transfer valid data points
            if d.val is not None:
                post_payload.append( { 'ts': d.ts, 'val': d.val } )

        if post_payload:
            print gap.row.row_key
            print ' *', gap.start_time, ts_epoch(gap.start_time)
            print ' *', gap.end_time, ts_epoch(gap.end_time)
            # post = PostBaseRate(api_url=destination_api_url, path=path,
            #             freq=freq, username=username, api_key=key)

            # post.set_payload(post_payload)
            # post.send_data()
            pass


        

def main():
    usage = '%prog [ options | -v ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-S', '--source_url', metavar='SOURCE_ESMOND_REST_URL',
        type='string', dest='source_api_url', 
        help='URL for the source REST API (default=%default) - required.',
        default='http://localhost')
    parser.add_option('-D', '--destination_url', metavar='DESTINATION_ESMOND_REST_URL',
        type='string', dest='destination_api_url', 
        help='URL for the destination REST API (default=%default) - required.',
        default='http://localhost')
    parser.add_option('-l', '--limit', metavar='LIMIT',
        type='int', dest='limit', default=0,
        help='Limit query loops for development (default=No Limit).')
    parser.add_option('-u', '--user', metavar='USER',
        type='string', dest='user', default='',
        help='POST interface username.')
    parser.add_option('-k', '--key', metavar='API_KEY',
        type='string', dest='key', default='',
        help='API key for post operation.')
    parser.add_option('-v', '--verbose',
        dest='verbose', action='store_true', default=False,
        help='Verbose output.')
    options, args = parser.parse_args()

    if options.source_api_url == options.destination_api_url:
        print 'Source and destination REST API URLs must be different'
        parser.print_help()
        return -1

    process_gaps(options.source_api_url, options.destination_api_url,
                options.user, options.key, options.limit, options.verbose)
    
    pass

if __name__ == '__main__':
    main()