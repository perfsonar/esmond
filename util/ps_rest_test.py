#!/usr/bin/env python

"""
Quick tester script to exercise the pS REST client lib
"""

import os
import sys
import time
from optparse import OptionParser

from esmond.api.client.perfsonar.query import ApiConnect, ApiFilters
from esmond.api.client.perfsonar.post import MetadataPost, EventTypePost
from esmond.api.tests.perfsonar.test_data import TestResults

def query():
    tr = TestResults()

    filters = ApiFilters()

    filters.verbose = True
    filters.time_start = tr.q_start / 1000
    filters.time_end = tr.q_end / 1000
    # filters.input_source = 'lbl-pt1.es.net'
    # filters.tool_name = 'bwctl/iperf3'
    # filters.input_destination = 'chic-owamp.es.net'
    # filters.tool_name = 'owamp/powstream'

    conn = ApiConnect('http://localhost:8000/', filters)

    for md in conn.get_metadata():
        print md
        # print md.destination
        # print md.event_types # a list of event type names
        # print md.input_destination
        print md.input_source
        # print md.ip_packet_interval
        # print md.measurement_agent
        # print md.metadata_key
        # print md.sample_bucket_width
        # print md.source
        # print md.subject_type
        # print md.time_duration
        # print md.tool_name
        # print md.uri
        ## Single call
        # et = md.get_event_type('histogram-owdelay')
        # print '  * ', et
        # dpay = et.get_data()
        # print '   * ', dpay
        # print dpay.data[0], dpay.data[0].ts_epoch
        # print dpay.data[-1], dpay.data[-1].ts_epoch
        ## End single call - loop now
        for et in md.get_all_event_types():
            print '  * ', et
            # print et.base_uri
            # print et.event_type
            print et.summaries
            ## Single call
            if et.summaries:
                print '  * found summary - fetching single'
                summ = et.get_summary(et.summaries[0][0], et.summaries[0][1])
                print '    * ', summ
            ## End single call - loop now
            for summ in et.get_all_summaries():
                print '    * ', summ
                # print summ.summary_type
                # print summ.summary_window
                # print summ.uri
                dpay = summ.get_data()
                print dpay, dpay.data_type
                for dp in dpay.data:
                    # print dp, dp.val
                    pass
        print '====='

def main():
    usage = '%prog [ -u username | -a api_key ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-U', '--url', metavar='ESMOND_REST_URL',
            type='string', dest='api_url', 
            help='URL for the REST API (default=%default) - required.',
            default='http://localhost:8000')
    parser.add_option('-u', '--user', metavar='USER',
            type='string', dest='user', default='',
            help='POST interface username.')
    parser.add_option('-k', '--key', metavar='API_KEY',
            type='string', dest='key', default='',
            help='API key for post operation.')
    options, args = parser.parse_args()

    # query()

    args = {
        "subject_type": "point-to-point",
        "source": "10.10.0.1",
        "destination": "10.10.0.2",
        "tool_name": "bwctl/iperf3",
        "measurement_agent": "10.10.0.2",
        "input_source": "host1",
        "input_destination": "host2",
        # "time_duration": 30,
        #"ip_transport_protocol": "tcp"
    }

    mp = MetadataPost(options.api_url, username=options.user, 
        api_key=options.key, **args)
    mp.add_event_type('throughput')
    mp.add_event_type('time-error-estimates')
    mp.add_event_type('histogram-ttl')
    mp.add_summary_type('packet-count-sent', 'aggregation', [3600, 86400])
    
    new_meta = mp.post_metadata()

    print new_meta
    print new_meta.metadata_key

    et = EventTypePost(options.api_url, username=options.user,
        api_key=options.key, metadata_key=new_meta.metadata_key,
        event_type='throughput')

    ts = lambda: int(time.time())
    val = lambda: (int(time.time()) % 5)

    et.add_data_point(ts(), val())
    time.sleep(1)
    et.add_data_point(ts(), val())

    print et.json_payload(True)

    et.post_data()

    events = new_meta.get_event_type('throughput')
    print events
    dps = events.get_data()
    print dps
    for dp in dps.data:
        print dp

    et = EventTypePost(options.api_url, username=options.user,
        api_key=options.key, metadata_key=new_meta.metadata_key,
        event_type='histogram-ttl')

    et.add_data_point(ts(), {val(): val()})
    time.sleep(1)
    et.add_data_point(ts(), {val(): val()})

    print et.json_payload(True)

    et.post_data()

    events = new_meta.get_event_type('histogram-ttl')
    print events
    dps = events.get_data()
    print dps
    for dp in dps.data:
        print dp.ts, dp.val



    
    pass

if __name__ == '__main__':
    main()