"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

import os
import os.path
import json
import datetime
import calendar
import shutil
import time

from collections import namedtuple

from django.test import TestCase
from django.conf import settings

from tastypie.test import ResourceTestCase

from esmond.api.models import Device, IfRef, ALUSAPRef, OIDSet, DeviceOIDSetMap

from esmond.persist import IfRefPollPersister, ALUSAPRefPersister, \
     PersistQueueEmpty, TSDBPollPersister, CassandraPollPersister
from esmond.config import get_config, get_config_path
from esmond.cassandra import CASSANDRA_DB
from esmond.util import max_datetime

from pycassa.columnfamily import ColumnFamily

from esmond.api.tests.example_data import build_rtr_d_metadata, \
     build_metadata_from_test_data, load_test_data
from esmond.api.api import check_connection

try:
    import tsdb
    from tsdb.row import ROW_VALID
except ImportError:
    tsdb = None

ifref_test_data = """
[{
    "oidset_name": "IfRefPoll",
    "device_name": "rtr_d",
    "timestamp": 1345125600,
    "oid_name": "",
    "data": {
        "ifSpeed": [ [ "ifSpeed.1", 1000000000 ] ],
        "ifType": [ [ "ifType.1", 53 ] ],
        "ipAdEntIfIndex": [ [ "ipAdEntIfIndex.10.37.37.1", 1 ] ],
        "ifHighSpeed": [ [ "ifHighSpeed.1", 1000 ] ],
        "ifAlias": [ [ "ifAlias.1", "test one" ] ],
        "ifPhysAddress": [ [ "ifPhysAddress.1", "\u0000\u001c\u000fFk@" ] ],
        "ifAdminStatus": [ [ "ifAdminStatus.1", 1 ] ],
        "ifDescr": [ [ "ifDescr.1", "Vlan1" ] ],
        "ifMtu": [ [ "ifMtu.1", 1500 ] ],
        "ifOperStatus": [ [ "ifOperStatus.1", 1 ] ]
    }
},
{
    "oidset_name": "IfRefPoll",
    "device_name": "rtr_d",
    "timestamp": 1345125660,
    "oid_name": "",
    "data": {
        "ifSpeed": [ [ "ifSpeed.1", 1000000000 ] ],
        "ifType": [ [ "ifType.1", 53 ] ],
        "ipAdEntIfIndex": [ [ "ipAdEntIfIndex.10.37.37.1", 1 ] ],
        "ifHighSpeed": [ [ "ifHighSpeed.1", 1000 ] ],
        "ifAlias": [ [ "ifAlias.1", "test two" ] ],
        "ifPhysAddress": [ [ "ifPhysAddress.1", "\u0000\u001c\u000fFk@" ] ],
        "ifAdminStatus": [ [ "ifAdminStatus.1", 1 ] ],
        "ifDescr": [ [ "ifDescr.1", "Vlan1" ] ],
        "ifMtu": [ [ "ifMtu.1", 1500 ] ],
        "ifOperStatus": [ [ "ifOperStatus.1", 1 ] ]
    }
}]
"""

empty_ifref_test_data = """
[{
    "oidset_name": "IfRefPoll",
    "device_name": "rtr_d",
    "timestamp": 1345125720,
    "oid_name": "",
    "data": {
        "ifSpeed": [],
        "ifType": [],
        "ipAdEntIfIndex": [],
        "ifHighSpeed": [],
        "ifAlias": [],
        "ifPhysAddress": [],
        "ifAdminStatus": [],
        "ifDescr": [],
        "ifMtu": [],
        "ifOperStatus": []
    }
}]"""

class TestPollResult(object):
    def __init__(self, d):
        self.__dict__.update(d)

    def __repr__(self):
        s = "TestPollResult("
        for k,v in self.__dict__.iteritems():
            s += "%s: %s, " % (k,v)
        s = s[:-2] + ")"

        return s

class TestPersistQueue(object):
    """Data is a list of dicts, representing the objects"""
    def __init__(self, data):
        self.data = data

    def get(self):
        try:
            return TestPollResult(self.data.pop(0))
        except IndexError:
            raise PersistQueueEmpty()

class SimpleTest(TestCase):
    def test_basic_addition(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        self.assertEqual(1 + 1, 2)

class TestIfRefPersister(TestCase):
    def setUp(self):
        self.td = build_rtr_d_metadata()

    def test_test(self):
        d = Device.objects.get(name="rtr_d")
        self.assertEqual(d.name, "rtr_d")

    def test_persister(self):
        ifrefs = IfRef.objects.filter(device__name="rtr_d", ifDescr="Vlan1")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 0)

        q = TestPersistQueue(json.loads(ifref_test_data))
        p = IfRefPollPersister([], "test", persistq=q)
        p.run()

        ifrefs = IfRef.objects.filter(device__name="rtr_d", ifDescr="Vlan1")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 2)

        self.assertEqual(ifrefs[0].ifIndex, ifrefs[1].ifIndex)
        self.assertTrue(ifrefs[0].end_time < max_datetime)
        self.assertTrue(ifrefs[1].end_time == max_datetime)
        self.assertTrue(ifrefs[0].ifAlias == "test one")
        self.assertTrue(ifrefs[1].ifAlias == "test two")

        q = TestPersistQueue(json.loads(empty_ifref_test_data))
        p = IfRefPollPersister([], "test", persistq=q)
        p.run()

        ifrefs = IfRef.objects.filter(device__name="rtr_d", ifDescr="Vlan1")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 2)

        self.assertTrue(ifrefs[1].end_time < max_datetime)

alu_sap_test_data = """
[
    {
        "oidset_name": "ALUSAPRefPoll",
        "device_name": "rtr_d",
        "timestamp": 1345125600,
        "oid_name": "",
        "data": {
            "sapDescription": [
                [ "sapDescription.1.1342177281.100", "one" ]
            ],
            "sapIngressQosPolicyId": [
                [ "sapIngressQosPolicyId.1.1342177281.100", 2 ]
            ],
            "sapEgressQosPolicyId": [
                [ "sapEgressQosPolicyId.1.1342177281.100", 2 ]
            ]
        },
        "metadata": {}
    },
    {
        "oidset_name": "ALUSAPRefPoll",
        "device_name": "rtr_d",
        "timestamp": 1345125660,
        "oid_name": "",
        "data": {
            "sapDescription": [
                [ "sapDescription.1.1342177281.100", "two" ]
            ],
            "sapIngressQosPolicyId": [
                [ "sapIngressQosPolicyId.1.1342177281.100", 2 ]
            ],
            "sapEgressQosPolicyId": [
                [ "sapEgressQosPolicyId.1.1342177281.100", 2 ]
            ]
        },
        "metadata": {}
    }
]
"""
empty_alu_sap_test_data = """
[
    {
        "oidset_name": "ALUSAPRefPoll",
        "device_name": "rtr_d",
        "timestamp": 1345125720,
        "oid_name": "",
        "data": {
            "sapDescription": [],
            "sapIngressQosPolicyId": [],
            "sapEgressQosPolicyId": []
        },
        "metadata": {}
    }
]"""
class TestALUSAPRefPersister(TestCase):
    def setUp(self):
        self.td = build_rtr_d_metadata()

    def test_persister(self):
        ifrefs = IfRef.objects.filter(device__name="rtr_d")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 0)

        q = TestPersistQueue(json.loads(alu_sap_test_data))
        p = ALUSAPRefPersister([], "test", persistq=q)
        p.run()

        ifrefs = ALUSAPRef.objects.filter(device__name="rtr_d", name="1-8_0_0-100")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 2)

        self.assertTrue(ifrefs[0].end_time < max_datetime)
        self.assertTrue(ifrefs[1].end_time == max_datetime)
        self.assertTrue(ifrefs[0].sapDescription == "one")
        self.assertTrue(ifrefs[1].sapDescription == "two")

        q = TestPersistQueue(json.loads(empty_alu_sap_test_data))
        p = ALUSAPRefPersister([], "test", persistq=q)
        p.run()

        ifrefs = ALUSAPRef.objects.filter(device__name="rtr_d", name="1-8_0_0-100")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertTrue(len(ifrefs) == 2)

        self.assertTrue(ifrefs[1].end_time < max_datetime)

# XXX(jdugan): it would probably be better and easier in the long run to keep
# these JSON blobs in files and define a small class to load them
timeseries_test_data = """
[
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1343953700,
        "oid_name": "ifHCInOctets",
        "data": [
            [
                "ifHCInOctets/GigabitEthernet0_1",
                25066556556930
            ],
            [
                "ifHCInOctets/GigabitEthernet0_2",
                126782001836
            ],
            [
                "ifHCInOctets/GigabitEthernet0_3",
                27871397880
            ],
            [
                "ifHCInOctets/Loopback0",
                0
            ]
        ],
        "metadata": {
            "tsdb_flags": 1
        }
    },
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1343953730,
        "oid_name": "ifHCInOctets",
        "data": [
            [
                "ifHCInOctets/GigabitEthernet0_1",
                25066575790604
            ],
            [
                "ifHCInOctets/GigabitEthernet0_2",
                126782005062
            ],
            [
                "ifHCInOctets/GigabitEthernet0_3",
                27871411592
            ],
            [
                "ifHCInOctets/Loopback0",
                0
            ]
        ],
        "metadata": {
            "tsdb_flags": 1
        }
    }
]
"""

class CassandraTestResults(object):
    """
    Container to hold timestamps and return values common to 
    both sets of cassandra data queries (raw and rest apis).
    """
    # Common values
    begin = 1343956800
    end   = 1343957400

    expected_results = 21

    # Values for base rate tests
    base_rate_val_first = 0.020266666666666665
    base_rate_val_last  = 0.026533333333333332

    # Values for aggregation tests
    agg_ts = 1343955600
    agg_freq = 3600
    agg_avg = 17
    agg_min = 0
    agg_max = 7500

    # Values from raw data tests
    raw_ts_first = 1343956814
    raw_val_first = 281577000
    raw_ts_last = 1343957394
    raw_val_last = 281585760


class TestCassandraPollPersister(TestCase):
    fixtures = ['oidsets.json']

    def setUp(self):
        """make sure we have a clean rtr_d directory to start with."""
        self.td = build_rtr_d_metadata()
        rtr_d_path = os.path.join(settings.ESMOND_ROOT, "tsdb-data", "rtr_d")
        if os.path.exists(rtr_d_path):
            shutil.rmtree(rtr_d_path, ignore_errors=True)

        self.ctr = CassandraTestResults()


    def test_build_metadata_from_test_data(self):
        rtr_d = Device.objects.get(name="rtr_d")
        self.assertEqual(rtr_d.oidsets.all().count(), 0)

        test_data = json.loads(timeseries_test_data)
        build_metadata_from_test_data(test_data)

        self.assertEqual(rtr_d.oidsets.all().count(), 1)
        self.assertEqual(IfRef.objects.filter(device=rtr_d).count(), 4)

    def test_persister(self):
        """This is a very basic smoke test for a cassandra persister."""
        config = get_config(get_config_path())
        test_data = json.loads(timeseries_test_data)
        return
        q = TestPersistQueue(test_data)
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.close()
        p.db.stats.report('all')

    def test_persister_long(self):
        """Make sure the tsdb and cassandra data match"""
        config = get_config(get_config_path())
        test_data = load_test_data("rtr_d_ifhcin_long.json")
        #return
        config.db_clear_on_testing = True
        config.db_profile_on_testing = True

        q = TestPersistQueue(test_data)
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.flush()
        p.db.close()
        p.db.stats.report('all')
        
        test_data = load_test_data("rtr_d_ifhcin_long.json")
        q = TestPersistQueue(test_data)
        p = TSDBPollPersister(config, "test", persistq=q)
        p.run()

        path_levels = []

        rtr_d_path = os.path.join(settings.ESMOND_ROOT, "tsdb-data", "rtr_d")
        for (path, dirs, files) in os.walk(rtr_d_path):
            if dirs[0] == 'TSDBAggregates':
                break
            path_levels.append(dirs)

        oidsets = path_levels[0]
        oids    = path_levels[1]
        paths   = path_levels[2]

        full_paths = {}

        for oidset in oidsets:
            for oid in oids:
                for path in paths:
                    full_path = 'rtr_d/%s/%s/%s/TSDBAggregates/30'  % \
                        (oidset, oid, path)
                    if not full_paths.has_key(full_path):
                        full_paths[full_path] = 1

        ts_db = tsdb.TSDB(config.tsdb_root)
        db = CASSANDRA_DB(config)

        rates = ColumnFamily(db.pool, db.rate_cf)

        count_bad = 0
        tsdb_aggs = 0

        for p in full_paths.keys():
            v = ts_db.get_var(p)
            device,oidset,oid,path,tmp1,tmp2 = p.split('/')
            for d in v.select():
                tsdb_aggs += 1
                key = '%s:%s:%s:%s:%s:%s'  % \
                    (device,oidset,oid,path,int(tmp2)*1000,
                    datetime.datetime.utcfromtimestamp(d.timestamp).year)

                val = rates.get(key, [d.timestamp*1000])[d.timestamp*1000]
                if d.flags != ROW_VALID:
                    assert val['is_valid'] == 0
                else:
                    assert val['val'] == d.delta
                    assert val['is_valid'] > 0

        db.close()

    def test_range_baserate_query(self):
        """
        Presumed using test data loaded in previous test method.

        Shows the three query methods that return json formatted data.
        """
        config = get_config(get_config_path())
        db = CASSANDRA_DB(config)
        
        start_time = self.ctr.begin*1000
        end_time = self.ctr.end*1000

        ret = db.query_baserate_timerange(
            path=['rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            freq=30*1000,
            ts_min=start_time,
            ts_max=end_time
        )

        assert len(ret) == self.ctr.expected_results
        assert ret[0]['ts'] == start_time
        assert ret[0]['val'] == self.ctr.base_rate_val_first
        assert ret[self.ctr.expected_results-1]['ts'] == end_time
        assert ret[self.ctr.expected_results-1]['val'] == self.ctr.base_rate_val_last

        ret = db.query_raw_data(
            path=['rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            freq=30*1000,
            ts_min=start_time,
            ts_max=end_time
        )

        assert len(ret) == self.ctr.expected_results - 1
        assert ret[0]['ts'] == self.ctr.raw_ts_first*1000
        assert ret[0]['val'] == self.ctr.raw_val_first
        assert ret[len(ret)-1]['ts'] == self.ctr.raw_ts_last*1000
        assert ret[len(ret)-1]['val'] == self.ctr.raw_val_last

        ret = db.query_aggregation_timerange(
            path=['rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            ts_min=start_time - 3600*1000,
            ts_max=end_time,
            freq=self.ctr.agg_freq*1000, # required!
            cf='average',  # min | max | average - also required!
        )
        
        assert ret[0]['cf'] == 'average'
        assert ret[0]['val'] == self.ctr.agg_avg
        assert ret[0]['ts'] == self.ctr.agg_ts*1000
        
        ret = db.query_aggregation_timerange(
            path=['rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            ts_min=start_time - 3600*1000,
            ts_max=end_time,
            freq=self.ctr.agg_freq*1000, # required!
            cf='min',  # min | max | average - also required!
        )

        assert ret[0]['cf'] == 'min'
        assert ret[0]['val'] == self.ctr.agg_min
        assert ret[0]['ts'] == self.ctr.agg_ts*1000

        ret = db.query_aggregation_timerange(
            path=['rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            ts_min=start_time - 3600*1000,
            ts_max=end_time,
            freq=self.ctr.agg_freq*1000, # required!
            cf='max',  # min | max | average - also required!
        )
        
        assert ret[0]['cf'] == 'max'
        assert ret[0]['val'] == self.ctr.agg_max
        assert ret[0]['ts'] == self.ctr.agg_ts*1000

        db.close()

class TestCassandraApiQueries(ResourceTestCase):
    fixtures = ['oidsets.json']

    def setUp(self):
        super(TestCassandraApiQueries, self).setUp()

        self.td = build_rtr_d_metadata()

        test_data = load_test_data("rtr_d_ifhcin_long.json")
        build_metadata_from_test_data(test_data)

        self.ctr = CassandraTestResults()

        # Check connection in case the test_api module was unable
        # to connect but we've not seen an error yet.  This way
        # we'll see an explicit error that makes sense.
        check_connection()

    def test_a_load_data(self):
        config = get_config(get_config_path())
        config.db_clear_on_testing = True
        # return
        test_data = load_test_data("rtr_d_ifhcin_long.json")
        q = TestPersistQueue(test_data)
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.flush()
        p.db.close()

    def test_get_device_list(self):
        url = '/v1/device/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEquals(data[0]['resource_uri'], '/v1/device/rtr_d/')

    def test_get_device_interface_list(self):
        url = '/v1/device/rtr_d/interface/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEquals(data['children'][0]['resource_uri'], 
            '/v1/device/rtr_d/interface/fxp0.0')

    def test_get_device_interface_data_detail(self):
        params = {
            'begin': self.ctr.begin,
            'end': self.ctr.end
        }

        url = '/v1/device/rtr_d/interface/fxp0.0/in'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], '30')
        self.assertEquals(data['cf'], 'average')
        self.assertEquals(data['resource_uri'], url)

        self.assertEquals(len(data['data']), self.ctr.expected_results)
        self.assertEquals(data['data'][0][0], params['begin'])
        self.assertEquals(data['data'][0][1], self.ctr.base_rate_val_first)
        self.assertEquals(data['data'][self.ctr.expected_results-1][0], params['end'])
        self.assertEquals(data['data'][self.ctr.expected_results-1][1], self.ctr.base_rate_val_last)

    def test_get_device_interface_data_aggs(self):
        params = {
            'begin': self.ctr.begin-3600, # back an hour to get agg bin.
            'end': self.ctr.end,
            'agg': self.ctr.agg_freq
        }

        url = '/v1/device/rtr_d/interface/fxp0.0/in'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], str(params['agg']))
        self.assertEquals(data['cf'], 'average')
        self.assertEquals(data['resource_uri'], url)

        self.assertEquals(len(data['data']), 1)
        self.assertEquals(data['data'][0][0], self.ctr.agg_ts)
        self.assertEquals(data['data'][0][1], self.ctr.agg_avg)

        params['cf'] = 'min'

        url = '/v1/device/rtr_d/interface/fxp0.0/in'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], str(params['agg']))
        self.assertEquals(data['cf'], params['cf'])
        self.assertEquals(data['resource_uri'], url)

        self.assertEquals(len(data['data']), 1)
        self.assertEquals(data['data'][0][0], self.ctr.agg_ts)
        self.assertEquals(data['data'][0][1], self.ctr.agg_min)

        params['cf'] = 'max'

        url = '/v1/device/rtr_d/interface/fxp0.0/in'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], str(params['agg']))
        self.assertEquals(data['cf'], params['cf'])
        self.assertEquals(data['resource_uri'], url)

        self.assertEquals(len(data['data']), 1)
        self.assertEquals(data['data'][0][0], self.ctr.agg_ts)
        self.assertEquals(data['data'][0][1], self.ctr.agg_max)

        # make sure that an invalid aggregation raises an error
        params['agg'] = params['agg'] * 3
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 400)

    def test_get_timeseries_data_detail(self):
        """/timeseries rest test for base rates."""
        # rtr_d:FastPollHC:ifHCInOctets:xe-1_1_0 30000|3600000|86400000
        params = {
            'begin': self.ctr.begin,
            'end': self.ctr.end
        }

        url = '/v1/timeseries/BaseRate/rtr_d/FastPollHC/ifHCInOctets/fxp0.0/30000'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], '30000')
        self.assertEquals(data['cf'], 'average')
        self.assertEquals(data['resource_uri'], url)

        self.assertEquals(len(data['data']), self.ctr.expected_results)
        self.assertEquals(data['data'][0][0], params['begin']*1000)
        self.assertEquals(data['data'][0][1], self.ctr.base_rate_val_first)
        self.assertEquals(data['data'][self.ctr.expected_results-1][0], params['end']*1000)
        self.assertEquals(data['data'][self.ctr.expected_results-1][1], self.ctr.base_rate_val_last)

    def test_get_timeseries_data_aggs(self):
        """/timeseries rest test for aggs."""
        params = {
            'begin': self.ctr.begin-3600, # back an hour to get agg bin.
            'end': self.ctr.end,
        }

        url = '/v1/timeseries/Aggs/rtr_d/FastPollHC/ifHCInOctets/fxp0.0/{0}'.format(self.ctr.agg_freq*1000)

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], str(self.ctr.agg_freq*1000))
        self.assertEquals(data['cf'], 'average')
        self.assertEquals(data['resource_uri'], url)

        self.assertEquals(len(data['data']), 1)
        self.assertEquals(data['data'][0][0], self.ctr.agg_ts*1000)
        self.assertEquals(data['data'][0][1], self.ctr.agg_avg)

        params['cf'] = 'min'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], str(self.ctr.agg_freq*1000))
        self.assertEquals(data['cf'], params['cf'])

        self.assertEquals(len(data['data']), 1)
        self.assertEquals(data['data'][0][0], self.ctr.agg_ts*1000)
        self.assertEquals(data['data'][0][1], self.ctr.agg_min)

        params['cf'] = 'max'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], str(self.ctr.agg_freq*1000))
        self.assertEquals(data['cf'], params['cf'])

        self.assertEquals(len(data['data']), 1)
        self.assertEquals(data['data'][0][0], self.ctr.agg_ts*1000)
        self.assertEquals(data['data'][0][1], self.ctr.agg_max)

        # print json.dumps(data, indent=4)

    def test_get_timeseries_raw_data(self):
        """/timeseries rest test for raw data."""
        # rtr_d:FastPollHC:ifHCInOctets:xe-1_1_0 30000|3600000|86400000
        params = {
            'begin': self.ctr.begin,
            'end': self.ctr.end
        }

        url = '/v1/timeseries/RawData/rtr_d/FastPollHC/ifHCInOctets/fxp0.0/30000'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], '30000')
        self.assertEquals(len(data['data']), self.ctr.expected_results-1)
        self.assertEquals(data['resource_uri'], url)

if False:
    class TestTSDBPollPersister(TestCase):
        fixtures = ['oidsets.json']

        def setUp(self):
            """make sure we have a clean rtr_d directory to start with."""
            self.td = build_rtr_d_metadata()
            rtr_d_path = os.path.join(settings.ESMOND_ROOT, "tsdb-data", "rtr_d")
            if os.path.exists(rtr_d_path):
                shutil.rmtree(rtr_d_path)


        def test_persister(self):
            """This is a very basic smoke test for a TSDB persister."""
            config = get_config(get_config_path())

            test_data = json.loads(timeseries_test_data)
            q = TestPersistQueue(test_data)
            p = TSDBPollPersister(config, "test", persistq=q)
            p.run()

            test_data = json.loads(timeseries_test_data)
            db = tsdb.TSDB(config.tsdb_root)
            for pr in test_data:
                for oid, val in pr['data']:
                    iface = oid.split('/')[-1]
                    path = "%s/%s/%s/%s/" % (pr['device_name'],
                            pr['oidset_name'], pr['oid_name'], iface)
                    v = db.get_var(path)
                    d = v.get(pr['timestamp'])
                    self.assertEqual(val, d.value)

        def test_persister_long(self):
            """Use actual data to test persister"""
            config = get_config(get_config_path())

            # load example data

            test_data = load_test_data("rtr_d_ifhcin_long.json")
            q = TestPersistQueue(test_data)
            p = TSDBPollPersister(config, "test", persistq=q)
            p.run()

            test_data = load_test_data("rtr_d_ifhcin_long.json")
            ts0 = test_data[0]['timestamp']
            tsn = test_data[-1]['timestamp']

            # make sure it got written to disk as expected

            db = tsdb.TSDB(config.tsdb_root)
            paths = []
            for pr in test_data:
                for oid, val in pr['data']:
                    iface = oid.split('/')[-1]
                    path = "%s/%s/%s/%s/" % (pr['device_name'],
                            pr['oidset_name'], pr['oid_name'], iface)
                    if path not in paths:
                        paths.append(path)
                    v = db.get_var(path)
                    d = v.get(pr['timestamp'])
                    self.assertEqual(val, d.value)

            # check that aggregates were calculated as expected

            db = tsdb.TSDB(config.tsdb_root)
            aggs = load_test_data("rtr_d_ifhcin_long_agg.json")
            for path in paths:
                p = path + "TSDBAggregates/30"
                v = db.get_var(p)
                for d in v.select(begin=ts0, end=tsn):
                    average, delta = aggs[p][str(d.timestamp)]
                    self.assertEqual(d.average, average)
                    self.assertEqual(d.delta, delta)
                v.close()
