#!/usr/bin/env python

"""
Query gap inventory and get data from alternate server.
"""

import calendar
import datetime
import os
import sys

from optparse import OptionParser

from django.core.paginator import Paginator
from django import db as django_db

from esmond.cassandra import _split_rowkey
from esmond.api.models import GapInventory
from esmond.api.client.timeseries import GetBaseRate, PostBaseRate

def ts_epoch(ts):
    return calendar.timegm(ts.utctimetuple())

def fix_string_for_db(s):
    if len(s) > 128:
        return '{0}...{1}'.format(s[:60], s[-60:])
    return s

def process_gaps(source_api_url, destination_api_url, username='', key='', 
            limit=0, verbose=False, dry=False):

    # Would normaly limit django set with a [slice] but 
    # need to handle the iteration artfully for handling
    # large querysets.
    count = 0

    paginator = Paginator(GapInventory.objects.filter(processed=False).order_by('id'), 1000)
    for page in range(1, paginator.num_pages):
        print 'page', count # XXX(mmg): remove this
        if limit and count >= limit: break
        for gap in paginator.page(page):
            if limit and count >= limit: break
            count += 1

            # XXX(mmg) remove this after first QA pass
            if gap.row.row_key.find('albq-cr5') > -1:
                django_db.reset_queries()
                continue

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

            if get.get_error:
                if verbose:
                    print '  xx', get.get_error
                gap.issues = fix_string_for_db(get.get_error)
                # XXX(mmg): remove this
                print 'xxx', fix_string_for_db(get.get_error)

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
                # XXX(mmg): remove this after first QA pass
                gap.issues = 'Data found in gap'
                print gap.row.row_key
                print ' *', gap.start_time, ts_epoch(gap.start_time)
                print ' *', gap.end_time, ts_epoch(gap.end_time)
                # post = PostBaseRate(api_url=destination_api_url, path=path,
                #             freq=freq, username=username, api_key=key)

                # post.set_payload(post_payload)
                # post.send_data()
                # if post.get_error:
                #     # do something
                #     pass
                pass

            gap.processed = True
            if not dry:
                gap.save()
            django_db.reset_queries()


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
    parser.add_option('-d', '--dry',
            dest='dry', action='store_true', default=False,
            help='Dry run - do not commit saves to gap inventory.')
    parser.add_option('-v', '--verbose',
        dest='verbose', action='store_true', default=False,
        help='Verbose output.')
    options, args = parser.parse_args()

    if options.source_api_url == options.destination_api_url:
        print 'Source and destination REST API URLs must be different'
        parser.print_help()
        return -1

    process_gaps(options.source_api_url, options.destination_api_url,
                options.user, options.key, options.limit, options.verbose,
                options.dry)
    
    pass

if __name__ == '__main__':
    main()