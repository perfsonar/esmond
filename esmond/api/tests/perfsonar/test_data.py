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

These can be used as search boundries to bookend the data set.

lower bound: 1376087220000
upper bound: 1391639280000

These can be used to grab a 4 day subset of data over the year turn.

12/30/2013:  1388361600000
01/03/2014:  1388707200000

raw_data column family:

hist_ttl (ps:histogram_ttl:0CB19291FB6D40EAA1955376772BF5D2:2013): 
start: 1376087276000 '2013-08-09 22:27:56'
end: 1391639216000 '2014-02-05 22:26:56'

hist_owdelay (minute - ps:histogram_owdelay:0CB19291FB6D40EAA1955376772BF5D2:2013):
start: 1376087247000 '2013-08-09 22:27:27'
end: 1391639187000 '2014-02-05 22:26:27'

hist_owdelay (daily - ps:histogram_owdelay:0CB19291FB6D40EAA1955376772BF5D2:aggregation:86400:2013):
start: 1376087275000 '2013-08-09 22:27:55'
end: 1391552875000 '2014-02-04 22:27:55'

---

base_rates column family:

throughput (ps:throughput:EC7E5AF67F8746C8AEF41E60288F3F59:2013):
start: 1376087247000 '2013-08-09 22:27:27'
end: 1391624847000 '2014-02-05 18:27:27'

packet_duplicates (ps:packet_duplicates:0CB19291FB6D40EAA1955376772BF5D2:2013):
start: 1376087349000 '2013-08-09 22:29:09'
end: 1391639289000 '2014-02-05 22:28:09'

packet_count_sent (ps:packet_count_sent:0CB19291FB6D40EAA1955376772BF5D2:2013):
start: 1376087326000 '2013-08-09 22:28:46'
end: 1391639266000 '2014-02-05 22:27:46'

packet_count_lost_data (ps:packet_count_lost:0CB19291FB6D40EAA1955376772BF5D2:2013)
start: 1376087304000 '2013-08-09 22:28:24'
end: 1391639244000 '2014-02-05 22:27:24'
"""

class TestResults(object):
    # test query start/end times
    q_start = 1388361600000
    q_end   = 1388707200000

    # hist paths
    h_ttl_path = ['ps','histogram_ttl','0CB19291FB6D40EAA1955376772BF5D2']
    h_ttl_len = 5760
    h_ttl_start_ts = 1388361656000
    h_ttl_start_val = u'{"9": 253, "10": 347}'
    h_ttl_end_ts = 1388707196000
    h_ttl_end_val = u'{"9": 214, "10": 386}'

    h_owd_min_path = ['ps','histogram_owdelay','0CB19291FB6D40EAA1955376772BF5D2']
    h_owd_min_len = 5760
    h_owd_min_start_ts = 1388361627000
    h_owd_min_start_val = u'{"720": 1, "712": 5, "179": 4, "93": 229, "282": 6, "173": 310, "87": 45}'
    h_owd_min_end_ts = 1388707167000
    h_owd_min_end_val = u'{"628": 21, "696": 331, "842": 2, "896": 244, "96": 2}'

    h_owd_day_path = ['ps','histogram_owdelay','0CB19291FB6D40EAA1955376772BF5D2','aggregation','86400']
    h_owd_day_len = 4
    h_owd_day_start_ts = 1388442475000
    h_owd_day_start_val = u'{"623": 104154, "606": 309, "310": 8, "333": 16, "395": 8195, "493": 20719, "189": 13374, "348": 139554, "409": 1608, "501": 110346, "754": 34602, "564": 7, "76": 166, "72": 1, "485": 3129, "92": 780, "11": 414275, "782": 14, "946": 6945, "37": 129, "53": 5336, "352": 324, "293": 9}'
    h_owd_day_end_ts = 1388701675000
    h_owd_day_end_val = u'{"607": 2699, "791": 31, "78": 1472, "560": 57862, "639": 271, "45": 14, "609": 5072, "550": 86517, "218": 3, "241": 3896, "721": 3, "504": 63813, "431": 553856, "233": 88491}'

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
            ts_min=self.tr.q_start, ts_max=self.tr.q_end
        )

        self.assertEqual(len(ret), self.tr.h_owd_day_len)
        self.assertEqual(ret[0]['ts'], self.tr.h_owd_day_start_ts)
        self.assertEqual(ret[0]['val'], self.tr.h_owd_day_start_val)
        self.assertEqual(ret[-1]['ts'], self.tr.h_owd_day_end_ts)
        self.assertEqual(ret[-1]['val'], self.tr.h_owd_day_end_val)

    def test_values(self):
        config = get_config(get_config_path())
        db = CASSANDRA_DB(config)
        return


