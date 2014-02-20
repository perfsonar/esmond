"""
Tests for PS cassandra/data handling.

"""

import json
import os
import sys

from django.test import TestCase
from django.conf import settings

from esmond.config import get_config, get_config_path
from esmond.cassandra import CASSANDRA_DB, RawRateData, BaseRateBin

from esmond.api.tests.example_data import load_test_data

"""
Notes on fixture test data (all kinds have a :2014 key as well):

These can be used to grab a subset from the middle of the dataset

2014-02-05 00:00:00 1391558400000
2014-02-05 16:00:00 1391616000000

raw_data column family:

hist_ttl (ps:histogram_ttl:0CB19291FB6D40EAA1955376772BF5D2:2014): 
start: 1391548899000 '2014-02-04 21:21:39'
end: 1391635239000 '2014-02-05 21:20:39'

hist_owdelay (minute - ps:histogram_owdelay:0CB19291FB6D40EAA1955376772BF5D2:2014):
start: 1391548750000 '2014-02-04 21:19:10'
end: 1391635090000 '2014-02-05 21:18:10'

hist_owdelay (daily - ps:histogram_owdelay:0CB19291FB6D40EAA1955376772BF5D2:aggregation:86400:2013):
start: 1382995231000 '2013-10-28 21:20:31'
end: 1391721631000 '2014-02-06 21:20:31'

---

base_rates column family:

throughput (ps:throughput:EC7E5AF67F8746C8AEF41E60288F3F59:2013):
start: 1382995070000 '2013-10-28 21:17:50'
end: 1391620670000 '2014-02-05 17:17:50'

packet_duplicates (ps:packet_duplicates:0CB19291FB6D40EAA1955376772BF5D2:2014):
start: 1391549053000 '2014-02-04 21:24:13'
end: 1391635393000 '2014-02-05 21:23:13'

packet_count_sent (ps:packet_count_sent:0CB19291FB6D40EAA1955376772BF5D2:2014):
start: 1391549015000 '2014-02-04 21:23:35'
end: 1391635355000 '2014-02-05 21:22:35'

packet_count_lost_data (ps:packet_count_lost:0CB19291FB6D40EAA1955376772BF5D2:2014)
start: 1391548990000 '2014-02-04 21:23:10'
end: 1391635330000 '2014-02-05 21:22:10'
"""

class TestResults(object):
    # test query start/end times
    q_start = 1391558400000
    q_end   = 1391616000000

    # hist paths
    h_ttl_path = ['ps','histogram_ttl','0CB19291FB6D40EAA1955376772BF5D2']
    h_ttl_len = 960
    h_ttl_start_ts = 1391558439000
    h_ttl_start_val = u'{"10": 600}'
    h_ttl_end_ts = 1391615979000
    h_ttl_end_val = u'{"9": 114, "10": 486}'

    h_owd_min_path = ['ps','histogram_owdelay','0CB19291FB6D40EAA1955376772BF5D2']
    h_owd_min_len = 960
    h_owd_min_start_ts = 1391558410000
    h_owd_min_start_val = u'{"472": 3, "800": 41, "15": 5, "263": 281, "241": 49, "505": 30, "232": 191}'
    h_owd_min_end_ts = 1391615950000
    h_owd_min_end_val = u'{"309": 1, "763": 1, "45": 11, "182": 3, "473": 3, "427": 1, "362": 99, "424": 9, "430": 472}'

    h_owd_day_path = ['ps','histogram_owdelay','0CB19291FB6D40EAA1955376772BF5D2','aggregation']
    h_owd_day_freq = 86400
    h_owd_day_len = 1
    h_owd_day_start_ts = 1391613631000
    h_owd_day_start_val = u'{"623": 206173, "203": 54590, "833": 175, "203": 330, "863": 6, "193": 5, "713": 85, "928": 575408, "341": 1402, "265": 93, "224": 25810, "544": 1}'
    h_owd_day_end_ts = h_owd_day_start_ts
    h_owd_day_end_val = h_owd_day_start_val

    # value paths
    throughput_path = ['ps','throughput','EC7E5AF67F8746C8AEF41E60288F3F59']
    throughput_len = 4
    throughput_start_ts =  1391563070000
    throughput_start_val = 5524593445.0
    throughput_end_ts = 1391606270000
    throughput_end_val =  7549113664.0

    packet_dup_path = ['ps','packet_duplicates','0CB19291FB6D40EAA1955376772BF5D2']
    packet_dup_len = 960
    packet_dup_start_ts = 1391558413000
    packet_dup_start_val = 281.0
    packet_dup_end_ts = 1391615953000
    packet_dup_end_val = 379.0

    packet_sent_path = ['ps','packet_count_sent','0CB19291FB6D40EAA1955376772BF5D2']
    packet_sent_len = 960
    packet_sent_start_ts = 1391558435000
    packet_sent_start_val = 431.0
    packet_sent_end_ts = 1391615975000
    packet_sent_end_val = 505.0

    packet_lost_path = ['ps','packet_count_lost','0CB19291FB6D40EAA1955376772BF5D2']
    packet_lost_len = 960
    packet_lost_start_ts = 1391558410000
    packet_lost_start_val = 95.0
    packet_lost_end_ts = 1391615950000
    packet_lost_end_val = 312.0

class DataTest(TestCase):
    fixtures = ['perfsonar_metadata.json']

    hist_data = [
        'histogram_owdelay_daily_data.json',
        'histogram_owdelay_minute_data.json',
        'histogram_ttl_data.json'
    ]

    rate_data = [
        'packet_count_lost_data.json',
        'packet_count_sent_data.json',
        'packet_duplicates_data.json',
        'throughput_data.json'
    ]

    def setUp(self):
        self.tr = TestResults()

    def test_a_load_data(self):
        config = get_config(get_config_path())
        config.db_clear_on_testing = True

        db = CASSANDRA_DB(config)

        for dat in self.hist_data:
            for row in load_test_data(dat):
                db.set_raw_data(RawRateData(**row))

        for dat in self.rate_data:
            for row in load_test_data(dat):
                db.update_rate_bin(BaseRateBin(**row))

        db.flush()

    def test_histograms(self):
        config = get_config(get_config_path())
        db = CASSANDRA_DB(config)

        ret = db.query_raw_data( path=self.tr.h_ttl_path,
            ts_min=self.tr.q_start, ts_max=self.tr.q_end
        )

        self.assertEqual(len(ret), self.tr.h_ttl_len)
        self.assertEqual(ret[0]['ts'], self.tr.h_ttl_start_ts)
        self.assertEqual(ret[0]['val'], self.tr.h_ttl_start_val)
        self.assertEqual(ret[-1]['ts'], self.tr.h_ttl_end_ts)
        self.assertEqual(ret[-1]['val'], self.tr.h_ttl_end_val)

        ret = db.query_raw_data( path=self.tr.h_owd_min_path,
            ts_min=self.tr.q_start, ts_max=self.tr.q_end
        )

        self.assertEqual(len(ret), self.tr.h_owd_min_len)
        self.assertEqual(ret[0]['ts'], self.tr.h_owd_min_start_ts)
        self.assertEqual(ret[0]['val'], self.tr.h_owd_min_start_val)
        self.assertEqual(ret[-1]['ts'], self.tr.h_owd_min_end_ts)
        self.assertEqual(ret[-1]['val'], self.tr.h_owd_min_end_val)

        ret = db.query_raw_data( path=self.tr.h_owd_day_path,
            ts_min=self.tr.q_start, ts_max=self.tr.q_end,
            freq=self.tr.h_owd_day_freq
        )

        self.assertEqual(len(ret), self.tr.h_owd_day_len)
        self.assertEqual(ret[0]['ts'], self.tr.h_owd_day_start_ts)
        self.assertEqual(ret[0]['val'], self.tr.h_owd_day_start_val)
        self.assertEqual(ret[-1]['ts'], self.tr.h_owd_day_end_ts)
        self.assertEqual(ret[-1]['val'], self.tr.h_owd_day_end_val)

    def test_values(self):
        config = get_config(get_config_path())
        db = CASSANDRA_DB(config)
        
        ret = db.query_baserate_timerange( path=self.tr.throughput_path,
            ts_min=self.tr.q_start, ts_max=self.tr.q_end
        )

        self.assertEqual(len(ret), self.tr.throughput_len)
        self.assertEqual(ret[0]['ts'], self.tr.throughput_start_ts)
        self.assertEqual(ret[0]['val'], self.tr.throughput_start_val)
        self.assertEqual(ret[-1]['ts'], self.tr.throughput_end_ts)
        self.assertEqual(ret[-1]['val'], self.tr.throughput_end_val)

        ret = db.query_baserate_timerange( path=self.tr.packet_dup_path,
            ts_min=self.tr.q_start, ts_max=self.tr.q_end
        )

        self.assertEqual(len(ret), self.tr.packet_dup_len)
        self.assertEqual(ret[0]['ts'], self.tr.packet_dup_start_ts)
        self.assertEqual(ret[0]['val'], self.tr.packet_dup_start_val)
        self.assertEqual(ret[-1]['ts'], self.tr.packet_dup_end_ts)
        self.assertEqual(ret[-1]['val'], self.tr.packet_dup_end_val)

        ret = db.query_baserate_timerange( path=self.tr.packet_sent_path,
            ts_min=self.tr.q_start, ts_max=self.tr.q_end
        )

        self.assertEqual(len(ret), self.tr.packet_sent_len)
        self.assertEqual(ret[0]['ts'], self.tr.packet_sent_start_ts)
        self.assertEqual(ret[0]['val'], self.tr.packet_sent_start_val)
        self.assertEqual(ret[-1]['ts'], self.tr.packet_sent_end_ts)
        self.assertEqual(ret[-1]['val'], self.tr.packet_sent_end_val)

        ret = db.query_baserate_timerange( path=self.tr.packet_lost_path,
            ts_min=self.tr.q_start, ts_max=self.tr.q_end
        )

        self.assertEqual(len(ret), self.tr.packet_lost_len)
        self.assertEqual(ret[0]['ts'], self.tr.packet_lost_start_ts)
        self.assertEqual(ret[0]['val'], self.tr.packet_lost_start_val)
        self.assertEqual(ret[-1]['ts'], self.tr.packet_lost_end_ts)
        self.assertEqual(ret[-1]['val'], self.tr.packet_lost_end_val)


