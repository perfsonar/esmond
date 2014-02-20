#!/usr/bin/env python

"""
Quick tester script to exercise the pS REST client lib
"""

import os
import sys

from esmond.api.client.perfsonar import ApiConnect, ApiFilters
from esmond.api.tests.perfsonar.test_data import TestResults

def main():

    tr = TestResults()

    filters = ApiFilters()

    filters.verbose = True
    # filters.time_start = tr.q_start / 1000
    # filters.time_end = tr.q_end / 1000
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
        ## Single call
        # et = md.get_event_type('histogram-owdelay')
        # print '  * ', et
        # dpay = et.get_data()
        # print '   * ', dpay
        # print dpay.data[0], dpay.data[0].ts_epoch
        # print dpay.data[-1], dpay.data[-1].ts_epoch
        ## End single call - loop
        for et in md.get_all_event_types():
            print '  * ', et
            # print et.base_uri
            # print et.event_type
            print et.summaries
            for summ in et.get_summaries():
                print '    * ', summ
                print summ.summary_type
                print summ.summary_window
                print summ.uri
                dpay = summ.get_data()
                print dpay, dpay.data_type
                for dp in dpay.data:
                    # print dp, dp.histogram
                    pass

        print '====='
    pass

if __name__ == '__main__':
    main()