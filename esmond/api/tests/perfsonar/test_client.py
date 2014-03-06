"""
Tests for the client libraries.

Presumes access to Cassandra backend.
"""

import os
import os.path
import json

from django.test import LiveServerTestCase

from esmond.config import get_config, get_config_path
from esmond.cassandra import CASSANDRA_DB, RawRateData, BaseRateBin
from esmond.api.client.perfsonar import ApiConnect, ApiFilters
from esmond.api.tests.example_data import load_test_data
from esmond.api.tests.perfsonar.test_data import TestResults, hist_data, rate_data

class TestClientLibs(LiveServerTestCase):
    """
    Tests to validate that the apprpriate known data points from the 
    test_data module matche the corresponding points returned from the
    client libraries.
    """
    fixtures = ['perfsonar_metadata.json']

    def setUp(self):
        self.tr = TestResults()
        self.filters = ApiFilters()
        self.filters.time_start = self.tr.q_start / 1000
        self.filters.time_end = self.tr.q_end / 1000

    def test_a_load_data(self):
        config = get_config(get_config_path())
        config.db_clear_on_testing = True

        db = CASSANDRA_DB(config)

        for dat in hist_data:
            for row in load_test_data(dat):
                db.set_raw_data(RawRateData(**row))

        for dat in rate_data:
            for row in load_test_data(dat):
                db.update_rate_bin(BaseRateBin(**row))

        db.flush()

    def test_histograms(self):
        conn = ApiConnect('http://localhost:8081', self.filters)
        self.filters.input_source = 'lbl-owamp.es.net'

        md = list(conn.get_metadata())[0]
        et = md.get_event_type('histogram-ttl')
        
        first_dp = et.get_data().data[0]
        final_dp = et.get_data().data[-1]

        self.assertEqual(len(et.get_data().data), self.tr.h_ttl_len)
        self.assertEqual(first_dp.val, json.loads(self.tr.h_ttl_start_val))
        self.assertEqual(first_dp.ts_epoch, self.tr.h_ttl_start_ts/1000)
        self.assertEqual(final_dp.val, json.loads(self.tr.h_ttl_end_val))
        self.assertEqual(final_dp.ts_epoch, self.tr.h_ttl_end_ts/1000)

        et = md.get_event_type('histogram-owdelay')
        
        first_dp = et.get_data().data[0]
        final_dp = et.get_data().data[-1]

        self.assertEqual(len(et.get_data().data), self.tr.h_owd_min_len)
        self.assertEqual(first_dp.val, json.loads(self.tr.h_owd_min_start_val))
        self.assertEqual(first_dp.ts_epoch, self.tr.h_owd_min_start_ts/1000)
        self.assertEqual(final_dp.val, json.loads(self.tr.h_owd_min_end_val))
        self.assertEqual(final_dp.ts_epoch, self.tr.h_owd_min_end_ts/1000)


    def test_values(self):
        conn = ApiConnect('http://localhost:8081', self.filters)
        self.filters.input_source = 'lbl-pt1.es.net'

        md = list(conn.get_metadata())[0]
        et = md.get_event_type('throughput')

        first_dp = et.get_data().data[0]
        final_dp = et.get_data().data[-1]

        self.assertEqual(len(et.get_data().data), self.tr.throughput_len)
        self.assertEqual(first_dp.val, self.tr.throughput_start_val)
        self.assertEqual(first_dp.ts_epoch, self.tr.throughput_start_ts/1000)
        self.assertEqual(final_dp.val, self.tr.throughput_end_val)
        self.assertEqual(final_dp.ts_epoch, self.tr.throughput_end_ts/1000)

        self.filters.input_source = 'lbl-owamp.es.net'
        md = list(conn.get_metadata())[0]
        
        et = md.get_event_type('packet-duplicates')
        
        first_dp = et.get_data().data[0]
        final_dp = et.get_data().data[-1]

        self.assertEqual(len(et.get_data().data), self.tr.packet_dup_len)
        self.assertEqual(first_dp.val, self.tr.packet_dup_start_val)
        self.assertEqual(first_dp.ts_epoch, self.tr.packet_dup_start_ts/1000)
        self.assertEqual(final_dp.val, self.tr.packet_dup_end_val)
        self.assertEqual(final_dp.ts_epoch, self.tr.packet_dup_end_ts/1000)


        et = md.get_event_type('packet-count-sent')

        first_dp = et.get_data().data[0]
        final_dp = et.get_data().data[-1]

        self.assertEqual(len(et.get_data().data), self.tr.packet_sent_len)
        self.assertEqual(first_dp.val, self.tr.packet_sent_start_val)
        self.assertEqual(first_dp.ts_epoch, self.tr.packet_sent_start_ts/1000)
        self.assertEqual(final_dp.val, self.tr.packet_sent_end_val)
        self.assertEqual(final_dp.ts_epoch, self.tr.packet_sent_end_ts/1000)

        et = md.get_event_type('packet-count-lost')
        
        first_dp = et.get_data().data[0]
        final_dp = et.get_data().data[-1]

        self.assertEqual(len(et.get_data().data), self.tr.packet_lost_len)
        self.assertEqual(first_dp.val, self.tr.packet_lost_start_val)
        self.assertEqual(first_dp.ts_epoch, self.tr.packet_lost_start_ts/1000)
        self.assertEqual(final_dp.val, self.tr.packet_lost_end_val)
        self.assertEqual(final_dp.ts_epoch, self.tr.packet_lost_end_ts/1000)

    def test_summaries(self):
        conn = ApiConnect('http://localhost:8081', self.filters)
        self.filters.input_source = 'lbl-owamp.es.net'

        md = list(conn.get_metadata())[0]
        et = md.get_event_type('histogram-owdelay')

        test_summary = (u'aggregation', u'86400')

        self.assertEqual(len(et.summaries), 1)
        self.assertEqual(et.summaries[0], test_summary)

        # Grab from generator first
        
        summ = list(et.get_all_summaries())[0]
        
        first_dp = summ.get_data().data[0]
        final_dp = summ.get_data().data[-1]

        self.assertEqual(len(summ.get_data().data), self.tr.h_owd_day_len)
        self.assertEqual(first_dp.val, json.loads(self.tr.h_owd_day_start_val))
        self.assertEqual(first_dp.ts_epoch, self.tr.h_owd_day_start_ts/1000)
        self.assertEqual(final_dp.val, json.loads(self.tr.h_owd_day_end_val))
        self.assertEqual(final_dp.ts_epoch, self.tr.h_owd_day_end_ts/1000)

        # Same test but pull specific summary

        summ = et.get_summary(test_summary[0], test_summary[1])

        first_dp = summ.get_data().data[0]
        final_dp = summ.get_data().data[-1]

        self.assertEqual(len(summ.get_data().data), self.tr.h_owd_day_len)
        self.assertEqual(first_dp.val, json.loads(self.tr.h_owd_day_start_val))
        self.assertEqual(first_dp.ts_epoch, self.tr.h_owd_day_start_ts/1000)
        self.assertEqual(final_dp.val, json.loads(self.tr.h_owd_day_end_val))
        self.assertEqual(final_dp.ts_epoch, self.tr.h_owd_day_end_ts/1000)







