#!/usr/bin/env python

"""
A sketch script with bin filling logic.  Based on api.tests test data. 
Should most likely be removed when logic implemented.
"""
import datetime
import json
import os
import sys

import requests

from collections import OrderedDict
from optparse import OptionParser

from esmond.api.client.timeseries import GetBaseRate
from esmond.util import atencode
from esmond.api.client.snmp import ApiConnect, ApiFilters



def expected_bin_count(start_bin, end_bin, freq):
    """Get expected number of bins in a given range of bins."""
    # XXX(mmg): optmize this
    # Should be ((end_bin - start_bin) / freq) + 1  ??
    return ((end_bin - start_bin) / freq) + 1
    # s = start_bin + 0 # making a copy
    # bincount = 0
    # while s <= end_bin:
    #     bincount += 1
    #     s += freq
    # return bincount

def get_expected_first_bin(begin, freq):
    """Get the first bin of a given frequency based on the begin ts
    of a timeseries query."""
    # Determine the first bin in the series based on the begin
    # timestamp in the timeseries request.
    #
    # Bin count math will round down to last bin but timerange queries will
    # return the next bin.  That is, given a 30 second bin, a begin
    # timestamp of 15 seconds past the minute will yield a bin calc
    # of on the minute, but but the time range query will return 
    # 30 seconds past the minute as the first result.
    #
    # A begin timestamp falling directly on a bin will return 
    # that bin.
    bin = (begin/freq)*freq
    if bin < begin:
        return bin+freq
    elif bin == begin:
        return bin
    else:
        # Shouldn't happen
        raise RuntimeError

def get_bin_alignment(begin, end, freq):
    """Generate a few values needed for checking and filling a series if 
    need be."""
    start_bin = get_expected_first_bin(begin,freq)
    end_bin = (end/freq)*freq
    expected_bins = expected_bin_count(start_bin, end_bin, freq)
    
    return start_bin, end_bin, expected_bins

def generate_filled_series(start_bin, end_bin, freq, data):
    """Genrate a new 'filled' series if the returned series has unexpected
    gaps.  Initialize a new range based in the requested time range as
    an OrderedDict, then iterate through original series to retain original
    values.
    """
    # Generate the empty "proper" timerange
    filled_range = []
    s = start_bin + 0 # copy it
    while s <= end_bin:
        filled_range.append((s,None))
        s += freq

    # Make it a ordered dict
    fill = OrderedDict(filled_range)

    # Go through the original data and plug in 
    # good values

    for dp in data:
        fill[dp[0]] = dp[1]

    for i in fill.items():
        yield list(i)

def verify_fill(begin, end, freq, data):
    """Top-level function to inspect a returned series for gaps.
    Returns the original series of the count is correct, else will
    return a new filled series."""
    begin, end, freq = int(begin), int(end), int(freq)
    start_bin,end_bin,expected_bins = get_bin_alignment(begin, end, freq)
    print 'got :', len(data)
    print 'need:', expected_bin_count(start_bin,end_bin,freq)
    if len(data) == expected_bin_count(start_bin,end_bin,freq):
        print 'verify: not filling'
        return data
    else:
        print 'verify: filling'
        return list(generate_filled_series(start_bin,end_bin,freq,data))



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
    parser.add_option('-g', '--gap',
            dest='gap', action='store_true', default=False,
            help='Force gaps.')
    parser.add_option('-e', '--empty',
            dest='empty', action='store_true', default=False,
            help='Force query to miss data range.')
    parser.add_option('-b', '--bogus',
            dest='bogus', action='store_true', default=False,
            help='Force bogus path.')
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()

    if False:
        path=['snmp','rtr_d','FastPollHC','ifHCInOctets','fxp0.0']
        begin = 1343955600000-10 # real start
        # begin = 1343955540000-10 # backtrack to make leading gap
        end   = 1343957400000+10
    else:
        path = ['snmp','fake_rtr_a','FastPoll','ifInOctets','fake_iface_1']
        # key = 'snmp:fake_rtr_a:FastPoll:ifInOctets:fake_iface_1:30000:2013'
        begin = 1384369830000
        end = 1384377810000


    if options.gap:
        # Mess with timestamp and force a leading gap
        begin = begin - 60000

    if options.empty:
        # Mess with timestamp to force missing the data in a valid row.
        begin += 60000000
        end += 60000000
        # print datetime.datetime.utcfromtimestamp(begin/1000)

    if options.bogus:
        path.append('bogus')

    params = {
        'begin': begin, 'end': end
    }

    args = {
        'api_url': options.api_url, 
        'path': path, 
        'freq': 30000,
        'params': params,
        'username': options.user,
        'api_key': options.key
    }

    if True:
        get = GetBaseRate(**args)

        payload = get.get_data()
        data_pack = json.dumps(payload._data)

        # print payload
        for d in payload.data:
            if options.verbose > 1:
                print '  *', d
    else:
        data_pack = """
    {"agg": "30000", "cf": "average", "end_time": 1343957400000, "begin_time": 1343955540000, "data": [[1343955600000, 4.0], [1343955630000, 22.4], [1343955660000, 27.533333333333335], [1343955690000, 11.4], [1343955720000, 21.5], [1343955750000, 28.0], [1343955780000, 20.366666666666667], [1343955810000, 10.8], [1343955840000, 1.3333333333333333], [1343955870000, 19.033333333333335], [1343955900000, 6.166666666666667], [1343955930000, 15.8], [1343955960000, 9.666666666666666], [1343955990000, null], [1343956020000, 1.9333333333333333], [1343956050000, 9.1], [1343956080000, 10.266666666666667], [1343956110000, 17.666666666666668], [1343956140000, 13.733333333333333], [1343956170000, 10.8], [1343956200000, 19.533333333333335], [1343956230000, 10.6], [1343956260000, 3.966666666666667], [1343956290000, 7.966666666666667], [1343956320000, 10.266666666666667], [1343956350000, 2.1666666666666665], [1343956380000, 9.1], [1343956410000, 10.066666666666666], [1343956440000, 2.8333333333333335], [1343956470000, 6.866666666666666], [1343956500000, 4.5], [1343956530000, 13.733333333333333], [1343956560000, 13.433333333333334], [1343956590000, 3.466666666666667], [1343956620000, 6.333333333333333], [1343956650000, 22.033333333333335], [1343956680000, 24.833333333333332], [1343956710000, 20.4], [1343956740000, 8.4], [1343956770000, 12.033333333333333], [1343956800000, 20.266666666666666], [1343956830000, 29.033333333333335], [1343956860000, 20.666666666666668], [1343956890000, 5.6], [1343956920000, 11.8], [1343956950000, 6.6], [1343956980000, 21.8], [1343957010000, 40.6], [1343957040000, 23.333333333333332], [1343957070000, 18.4], [1343957100000, 13.4], [1343957130000, 13.8], [1343957160000, 15.933333333333334], [1343957190000, 7.533333333333333], [1343957220000, 11.2], [1343957250000, 5.8], [1343957280000, 14.7], [1343957310000, 1.5], [1343957340000, 4.5], [1343957370000, 20.3], [1343957400000, 26.533333333333335]], "resource_uri": "/v1/timeseries/BaseRate/snmp/rtr_d/FastPollHC/ifHCInOctets/fxp0.0/30000"}
    """
    freq = args['freq']

    d = json.loads(data_pack)

    start_bin,end_bin,expected_bins = get_bin_alignment(begin, end, freq)

    print 'begin tsp', begin
    
    print 'start bin', start_bin
    
    print 'finis bin', end_bin
    if len(d['data']):
        print 'first val', d['data'][0][0]
        print 'finis val', d['data'][-1][0]
    else:
        print 'no data'
    print 'number of vals', len(d['data'])
    print 'expected  vals', expected_bins

    d['data'] = verify_fill(begin, end, freq, d['data'])

    # count = 1
    # for dp in d['data']:
    #     if options.verbose:
    #         #print count, dp
    #         pass
    #     #count += 1
    #     pass
    # pass

    return

    filters = ApiFilters()

    filters.verbose = options.verbose

    conn = ApiConnect(options.api_url, filters, username=options.user,
        api_key=options.key)

    for d in conn.get_devices(name='lbl-mr2'):
        print d
        for i in d.get_interfaces(ifDescr='ge-9/0/0'):
            print i, i.ifDescr
            for e in i.get_endpoints():
                if e.name != 'out':
                    continue
                print '   *', e
                # print e.get_data()._data
                payload = e.get_data()._data
                # print payload
                if options.gap:
                    del payload['data'][-6]
                    del payload['data'][-7]
                dt = verify_fill(payload['begin_time'], payload['end_time'],
                    payload['agg'], payload['data'])
                for dp in dt:
                    print dp
                # print '     +', e.get_data().dump



if __name__ == '__main__':
    main()