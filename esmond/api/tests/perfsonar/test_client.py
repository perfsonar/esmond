"""
Tests for the client libraries.

Presumes access to Cassandra backend.
"""

import os
import os.path
import json

# This MUST be here in any testing modules that use cassandra!
os.environ['ESMOND_UNIT_TESTS'] = 'True'

from django.test import LiveServerTestCase
from django.contrib.auth.models import User, Permission

from esmond.config import get_config, get_config_path
from esmond.cassandra import CASSANDRA_DB, RawRateData, BaseRateBin
from esmond_client.perfsonar.query import ApiConnect, ApiFilters
from esmond.api.tests.example_data import load_test_data
from esmond.api.tests.perfsonar.test_data import TestResults, hist_data, rate_data
from esmond_client.perfsonar.post import (
    EventTypeBulkPost, 
    EventTypeBulkPostException,
    EventTypePost,
    EventTypePostException,
    MetadataPost, 
)

from rest_framework.authtoken.models import Token

class TestClientLibs(LiveServerTestCase):
    """
    Tests to validate that the apprpriate known data points from the 
    test_data module matche the corresponding points returned from the
    client libraries.
    """
    fixtures = ['perfsonar_client_metadata.json']

    def setUp(self):
        self.tr = TestResults()
        self.filters = ApiFilters()
        self.filters.time_start = self.tr.q_start / 1000
        self.filters.time_end = self.tr.q_end / 1000

        #create user credentials
        self.admin_user = User(username="admin", is_staff=True)
        self.admin_user.save()

        for model_name in ['psmetadata', 'pspointtopointsubject', 'pseventtypes', 'psmetadataparameters']:
            for perm_name in ['add', 'change', 'delete']:
                perm = Permission.objects.get(codename='{0}_{1}'.format(perm_name, model_name))
                self.admin_user.user_permissions.add(perm)
        #Add timeseries permissions
        for perm_name in ['add', 'change', 'delete']:
            perm = Permission.objects.get(codename='esmond_api.{0}_timeseries'.format(perm_name))
            self.admin_user.user_permissions.add(perm)
        self.admin_user.save()

        self.admin_apikey = Token.objects.create(user=self.admin_user)

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
        conn = ApiConnect('http://localhost:8081', self.filters,
                script_alias=None)
        self.filters.input_source = 'lbl-owamp.es.net'

        md = list(conn.get_metadata())[0]
        et = md.get_event_type('histogram-ttl')
        
        first_dp = et.get_data().data[0]
        final_dp = et.get_data().data[-1]

        self.assertEqual(len(et.get_data().data), self.tr.h_ttl_len)
        self.assertEqual(first_dp.val, self.tr.h_ttl_start_val)
        self.assertEqual(first_dp.ts_epoch, self.tr.h_ttl_start_ts/1000)
        self.assertEqual(final_dp.val, self.tr.h_ttl_end_val)
        self.assertEqual(final_dp.ts_epoch, self.tr.h_ttl_end_ts/1000)

        et = md.get_event_type('histogram-owdelay')
        
        first_dp = et.get_data().data[0]
        final_dp = et.get_data().data[-1]

        self.assertEqual(len(et.get_data().data), self.tr.h_owd_min_len)
        self.assertEqual(first_dp.val, self.tr.h_owd_min_start_val)
        self.assertEqual(first_dp.ts_epoch, self.tr.h_owd_min_start_ts/1000)
        self.assertEqual(final_dp.val, self.tr.h_owd_min_end_val)
        self.assertEqual(final_dp.ts_epoch, self.tr.h_owd_min_end_ts/1000)


    def test_values(self):
        conn = ApiConnect('http://localhost:8081', self.filters,
                script_alias=None)
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
        conn = ApiConnect('http://localhost:8081', self.filters,
                script_alias=None)
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
        self.assertEqual(first_dp.val, self.tr.h_owd_day_start_val)
        self.assertEqual(first_dp.ts_epoch, self.tr.h_owd_day_start_ts/1000)
        self.assertEqual(final_dp.val, self.tr.h_owd_day_end_val)
        self.assertEqual(final_dp.ts_epoch, self.tr.h_owd_day_end_ts/1000)

        # Same test but pull specific summary

        summ = et.get_summary(test_summary[0], test_summary[1])

        first_dp = summ.get_data().data[0]
        final_dp = summ.get_data().data[-1]

        self.assertEqual(len(summ.get_data().data), self.tr.h_owd_day_len)
        self.assertEqual(first_dp.val, self.tr.h_owd_day_start_val)
        self.assertEqual(first_dp.ts_epoch, self.tr.h_owd_day_start_ts/1000)
        self.assertEqual(final_dp.val, self.tr.h_owd_day_end_val)
        self.assertEqual(final_dp.ts_epoch, self.tr.h_owd_day_end_ts/1000)


    def test_client_post(self):
        
        # make the metadata
        md_args = {
            'subject_type': 'point-to-point',
            'source': '10.0.0.1',
            'destination': '10.0.0.2',
            'tool_name': 'bwctl/iperf3',
            'measurement_agent': '10.0.0.3',
            'input_source': 'host1.example.net',
            'input_destination': 'host2.example.net',
        }

        mp = MetadataPost('http://localhost:8081', username=self.admin_user.username,
            api_key=self.admin_apikey.key, script_alias=None, **md_args)

        mp.add_event_type('throughput')
        mp.add_event_type('streams-packet-retransmits')

        metadata = mp.post_metadata()
        self.assertIsNotNone(metadata)

        # post a single event type data point
        et = EventTypePost('http://localhost:8081', username=self.admin_user.username,
            api_key=self.admin_apikey.key, script_alias=None, event_type='throughput',
            metadata_key=metadata.metadata_key)
        et.add_data_point(60, 6000)
        et.post_data()

        # did it take?
        self.assertEqual(len(metadata.get_event_type('throughput').get_data().data), 1)
        data_point = metadata.get_event_type('throughput').get_data().data[0]

        self.assertEqual(data_point.ts_epoch, 60)
        self.assertEqual(data_point.val, 6000)

        # now add a duplicate point to raise an exception.
        et = EventTypePost('http://localhost:8081', username=self.admin_user.username,
            api_key=self.admin_apikey.key, script_alias=None, event_type='throughput',
            metadata_key=metadata.metadata_key)
        et.add_data_point(60, 6000)

        with self.assertRaises(EventTypePostException):
            et.post_data()

        # bulk data now
        etb = EventTypeBulkPost('http://localhost:8081', username=self.admin_user.username,
            api_key=self.admin_apikey.key, script_alias=None, 
            metadata_key=metadata.metadata_key)

        etb.add_data_point('throughput', 90, 9000)
        etb.add_data_point('throughput', 120, 12000)

        etb.add_data_point('streams-packet-retransmits', 60, 4)
        etb.add_data_point('streams-packet-retransmits', 90, 0)

        etb.post_data()

        # did it take?
        self.assertEqual(len(metadata.get_event_type('throughput').get_data().data), 3)
        self.assertEqual(len(metadata.get_event_type('streams-packet-retransmits').get_data().data), 2)

        data_point = metadata.get_event_type('throughput').get_data().data[-1]

        self.assertEqual(data_point.ts_epoch, 120)
        self.assertEqual(data_point.val, 12000)

        data_point = metadata.get_event_type('streams-packet-retransmits').get_data().data[-1]

        self.assertEqual(data_point.ts_epoch, 90)
        self.assertEqual(data_point.val, 0)

        # do it again to raise a different exception
        etb = EventTypeBulkPost('http://localhost:8081', username=self.admin_user.username,
            api_key=self.admin_apikey.key, script_alias=None, 
            metadata_key=metadata.metadata_key)

        etb.add_data_point('throughput', 90, 9000)

        with self.assertRaises(EventTypeBulkPostException):
            etb.post_data()
