#!/usr/bin/env python

"""
Samples for graphing - queries for specific metadata objects, and 
a series of small functions demonstrating how to extract specific
data/information.
"""

from esmond.api.client.perfsonar.query import ApiConnect, ApiFilters

import os
import sys

def throughtput(md):
    """Get throughput data."""
    print('throughput')
    print(md.time_interval)
    print(md.time_duration)
    et = md.get_event_type('throughput')
    payload = et.get_data()
    for dp in payload.data:
        print(dp.ts, dp.val)
    print('+++')

def packet_retransmits(md):
    """Get retransmit data"""
    print('retransmits')
    print(md.time_interval)
    print(md.time_duration)
    et = md.get_event_type('packet-retransmits')
    payload = et.get_data()
    for dp in payload.data:
        print(dp.ts, dp.val)
    print('+++')

def histograms(md):
    """Histograms - base, and hourly/daily summaries"""
    print('histograms')

    # Base
    print('base')
    md.filters.time_range = 600
    
    et = md.get_event_type('histogram-owdelay')
    payload = et.get_data()
    for dp in payload.data:
        print(dp.ts, dp.val)

    del md.filters.time_range

    # Hourly 
    print('hourly')
    summ = et.get_summary('aggregation', 3600)
    payload = summ.get_data()
    print(payload)
    for dp in payload.data:
        pass # etc

    # Daily
    print('daily')
    summ = et.get_summary('aggregation', 86400)
    payload = summ.get_data()
    print(payload)
    for dp in payload.data:
        pass # etc

    print('+++')

def statistics(md):
    """Statistics - base, and hourly/daily summaries"""
    print('statistics')

    # Base
    print('base')
    md.filters.time_range = 600
    
    et = md.get_event_type('histogram-owdelay')

    summ = et.get_summary('statistics', 0)
    payload = summ.get_data()
    for dp in payload.data:
        print(dp.ts, dp.val['standard-deviation'], dp.val['median'], \
            dp.val['variance']) # etc

    del md.filters.time_range

    # Hourly 
    print('hourly')
    summ = et.get_summary('statistics', 3600)
    payload = summ.get_data()
    print(payload)
    for dp in payload.data:
        pass # etc

    # Daily
    print('daily')
    summ = et.get_summary('statistics', 86400)
    payload = summ.get_data()
    print(payload)
    for dp in payload.data:
        pass # etc

    print('+++')

def packet_loss(md):
    """Packet loss rate - base, and hourly/daily summaries"""
    print('packet loss')

    # Base
    print('base')
    md.filters.time_range = 600
    
    et = md.get_event_type('packet-loss-rate')
    payload = et.get_data()
    for dp in payload.data:
        print(dp.ts, dp.val)

    del md.filters.time_range

    # Hourly 
    print('hourly')
    summ = et.get_summary('aggregation', 3600)
    payload = summ.get_data()
    print(payload)
    for dp in payload.data:
        pass

    # Daily
    print('daily')
    summ = et.get_summary('aggregation', 86400)
    payload = summ.get_data()
    print(payload)
    for dp in payload.data:
        pass

    print('+++')

def packet_trace(md):
    """Packet trace data"""
    print('packet trace')
    md.filters.time_range = 600

    et = md.get_event_type('packet-trace')
    payload = et.get_data()
    for dp in payload.data:
        for i in dp.val:
            print(i['ip'], i['rtt']) # etc

    del md.filters.time_range

    print('+++')

def path_mtu(md):
    """Path mtu data"""
    print('path mtu')
    md.filters.time_range = 1800

    et = md.get_event_type('path-mtu')
    payload = et.get_data()
    for dp in payload.data:
        print(dp.ts, dp.val)

    print('+++')

def main():

    filters = ApiFilters()

    # query for key: 89764bfcbc8d4f4bada5b1bfdd451e91 (throughput)
    filters.source = '198.129.254.30'
    filters.destination = '198.129.254.114'
    filters.measurement_agent = '198.129.254.30'
    filters.tool_name = 'bwctl/iperf3'

    conn = ApiConnect('http://lbl-pt1.es.net:9085', filters)

    if len(list(conn.get_metadata())) > 1:
        print('Got more than one md object - fix query')
        return -1

    metadata = list(conn.get_metadata())[0]
    # print metadata

    throughtput(metadata)
    packet_retransmits(metadata)

    # query for key: fce0483e51de49aaa7fcf8884d053134 (histograms/packet loss)
    filters.source = '198.129.254.30'
    filters.destination = '198.124.238.66'
    filters.measurement_agent = '198.129.254.30'
    filters.tool_name = 'powstream'

    metadata = list(conn.get_metadata())[0]
    # print metadata

    histograms(metadata)
    statistics(metadata)
    packet_loss(metadata)

    # query for key: 638e53d546924c58b067f3d6f6926059 (packet trace/path mtu)
    filters.source = '198.129.254.30'
    filters.destination = '198.124.238.66'
    filters.measurement_agent = '198.129.254.30'
    filters.tool_name = 'bwctl/tracepath'

    metadata = list(conn.get_metadata())[0]
    # print metadata

    packet_trace(metadata)
    path_mtu(metadata)

    pass

if __name__ == '__main__':
    main()