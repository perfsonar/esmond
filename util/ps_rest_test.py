#!/usr/bin/env python

"""
Quick tester script to exercise the pS REST client lib
"""

import os
import sys

from esmond.api.client.perfsonar import ApiConnect, ApiFilters

def main():

    filters = ApiFilters()

    filters.verbose = True
    # filters.input_source = 'lbl-pt1.es.net'
    # filters.tool_name = 'bwctl/iperf3'
    filters.input_destination = 'chic-owamp.es.net'
    filters.tool_name = 'owamp/powstream'

    conn = ApiConnect('http://localhost:8000/', filters)

    for md in conn.get_metadata():
        print md
        # print md.destination
        # print md.event_types # a list of event type names
        # print md.input_destination
        # print md.input_source
        # print md.ip_packet_interval
        # print md.measurement_agent
        # print md.metadata_key
        # print md.sample_bucket_width
        # print md.source
        # print md.subject_type
        # print md.time_duration
        # print md.tool_name
        # print md.uri
        for et in md.get_event_types():
            print '  * ', et
            # print et.base_uri
            # print et.event_type
            for summ in et.get_summaries():
                print '    * ', summ
                # print summ.summary_type
                # print summ.summary_window
                # print summ.uri

        print '====='
    pass

if __name__ == '__main__':
    main()