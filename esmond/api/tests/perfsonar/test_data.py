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
        pass

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