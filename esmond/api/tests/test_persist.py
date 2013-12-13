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
     PersistQueueEmpty, TSDBPollPersister, CassandraPollPersister, \
     fit_to_bins
from esmond.config import get_config, get_config_path
from esmond.cassandra import CASSANDRA_DB, SEEK_BACK_THRESHOLD
from esmond.util import max_datetime

from pycassa.columnfamily import ColumnFamily

from esmond.api.tests.example_data import build_rtr_d_metadata, \
     build_metadata_from_test_data, load_test_data
from esmond.api.api import check_connection, SNMP_NAMESPACE, ANON_LIMIT
from esmond.util import atencode

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
                [ "sapDescription.1.270565376.100", "one" ]
            ],
            "sapIngressQosPolicyId": [
                [ "sapIngressQosPolicyId.1.270565376.100", 2 ]
            ],
            "sapEgressQosPolicyId": [
                [ "sapEgressQosPolicyId.1.270565376.100", 2 ]
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
                [ "sapDescription.1.270565376.100", "two" ]
            ],
            "sapIngressQosPolicyId": [
                [ "sapIngressQosPolicyId.1.270565376.100", 2 ]
            ],
            "sapEgressQosPolicyId": [
                [ "sapEgressQosPolicyId.1.270565376.100", 2 ]
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

        ifrefs = ALUSAPRef.objects.filter(device__name="rtr_d", name="1-8/1/1-100")
        ifrefs = ifrefs.order_by("end_time").all()
        self.assertEqual(len(ifrefs), 2)

        self.assertTrue(ifrefs[0].end_time < max_datetime)
        self.assertTrue(ifrefs[1].end_time == max_datetime)
        self.assertTrue(ifrefs[0].sapDescription == "one")
        self.assertTrue(ifrefs[1].sapDescription == "two")

        q = TestPersistQueue(json.loads(empty_alu_sap_test_data))
        p = ALUSAPRefPersister([], "test", persistq=q)
        p.run()

        ifrefs = ALUSAPRef.objects.filter(device__name="rtr_d", name="1-8/1/1-100")
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
                ["ifHCInOctets", "GigabitEthernet0/1"],
                25066556556930
            ],
            [
                ["ifHCInOctets", "GigabitEthernet0/2"],
                126782001836
            ],
            [
                ["ifHCInOctets", "GigabitEthernet0/3"],
                27871397880
            ],
            [
                ["ifHCInOctets", "Loopback0"],
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
                ["ifHCInOctets", "GigabitEthernet0/1"],
                25066575790604
            ],
            [
                ["ifHCInOctets", "GigabitEthernet0/2"],
                126782005062
            ],
            [
                ["ifHCInOctets", "GigabitEthernet0/3"],
                27871411592
            ],
            [
                ["ifHCInOctets", "Loopback0"],
                0
            ]
        ],
        "metadata": {
            "tsdb_flags": 1
        }
    }
]
"""


sys_uptime_test_data = """
[
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1343956800,
        "oid_name": "sysUpTime",
        "data": [
            [
                ["sysUpTime"],
                100
            ]
        ]
    }
]
"""

backwards_counters_test_data = """
[
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1384371885,
        "oid_name": "ifHCOutOctets",
        "data": [
            [
                ["ifHCOutOctets", "GigabitEthernet0/1"],
                3983656138
            ]
        ]
    },
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1384371914,
        "oid_name": "ifHCOutOctets",
        "data": [
            [
                ["ifHCOutOctets", "GigabitEthernet0/1"],
                3984242432
            ]
        ]
    },
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1384371945,
        "oid_name": "ifHCOutOctets",
        "data": [
            [
                ["ifHCOutOctets", "GigabitEthernet0/1"],
                3985220546
            ]
        ]
    },
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1384371974,
        "oid_name": "ifHCOutOctets",
        "data": [
            [
                ["ifHCOutOctets", "GigabitEthernet0/1"],
                3892978381
            ]
        ]
    },
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1384372005,
        "oid_name": "ifHCOutOctets",
        "data": [
            [
                ["ifHCOutOctets", "GigabitEthernet0/1"],
                3893271099
            ]
        ]
    },
    {
        "oidset_name": "FastPollHC",
        "device_name": "rtr_d",
        "timestamp": 1384372034,
        "oid_name": "ifHCOutOctets",
        "data": [
            [
                ["ifHCOutOctets", "GigabitEthernet0/1"],
                3893650623
            ]
        ]
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
    base_rate_val_first = 20.266666666666665
    base_rate_val_last  = 26.566666666666666

    # Values for aggregation tests
    agg_ts = 1343955600
    agg_freq = 3600
    agg_avg = 17
    agg_min = 0
    agg_max = 7500
    agg_raw = 61680

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

    def test_sys_uptime(self):
        config = get_config(get_config_path())
        q = TestPersistQueue(json.loads(sys_uptime_test_data))
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.flush()
        p.db.close()

        db = CASSANDRA_DB(config)
        ret = db.query_raw_data(
            path=[SNMP_NAMESPACE,'rtr_d','FastPollHC', 'sysUpTime'],
            freq=30*1000,
            ts_min=self.ctr.begin*1000,
            ts_max=self.ctr.end*1000)

        ret = ret[0]
        self.assertEqual(ret['ts'], self.ctr.begin * 1000)
        self.assertEqual(ret['val'], 100)

    def test_persister(self):
        """This is a very basic smoke test for a cassandra persister."""
        config = get_config(get_config_path())
        test_data = json.loads(timeseries_test_data)
        #return
        q = TestPersistQueue(test_data)
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.close()
        p.db.stats.report('all')

    def test_persister_backwards_counters(self):
        """Test for counters going backwards.

        Although this isn't supposed to happen, sometimes it does.
        The example data is real data from conf-rtr.sc13.org."""
        
        config = get_config(get_config_path())
        test_data = json.loads(backwards_counters_test_data)

        config.db_clear_on_testing = True
        q = TestPersistQueue(test_data)
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.flush()
        p.db.close()
        p.db.stats.report('all')
        config.db_clear_on_testing = False

        t0 = 1384371885
        t1 = 1384372034
        freq = 30
        b0 = t0 - (t0 % freq)
        b1 = t1 - (t1 % freq)
        b0 *= 1000
        b1 *= 1000

        key = '%s:%s:%s:%s:%s:%s:%s'  % (
                SNMP_NAMESPACE,
                'rtr_d',
                'FastPollHC',
                'ifHCOutOctets',
                'GigabitEthernet0/1',
                freq*1000,
                datetime.datetime.utcfromtimestamp(t0).year
        )

        db = CASSANDRA_DB(config)
        rates = ColumnFamily(db.pool, db.rate_cf)
        data = rates.get(key, column_start=b0, column_finish=b1)

        self.assertEqual(len(data), 6)

        for k,v in data.iteritems():
            # due to the bad data only two datapoints have full data, eg is_valid == 2
            if k in (1384371900000, 1384371990000):
                self.assertEqual(v['is_valid'], 2)
            else:
                self.assertEqual(v['is_valid'], 1)

            #print k,v


    def test_persister_long(self):
        """Make sure the tsdb and cassandra data match"""
        config = get_config(get_config_path())
        test_data = load_test_data("rtr_d_ifhcin_long.json")
        # return
        config.db_clear_on_testing = True
        config.db_profile_on_testing = True

        q = TestPersistQueue(test_data)
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.flush()
        p.db.close()
        p.db.stats.report('all')
        return
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
        
        config.db_clear_on_testing = False
        db = CASSANDRA_DB(config)

        rates = ColumnFamily(db.pool, db.rate_cf)

        count_bad = 0
        tsdb_aggs = 0

        for p in full_paths.keys():
            v = ts_db.get_var(p)
            device,oidset,oid,path,tmp1,tmp2 = p.split('/')
            path = path.replace("_", "/")
            for d in v.select():
                tsdb_aggs += 1
                key = '%s:%s:%s:%s:%s:%s:%s'  % \
                    (SNMP_NAMESPACE, device,oidset,oid,path,int(tmp2)*1000,
                    datetime.datetime.utcfromtimestamp(d.timestamp).year)

                val = rates.get(key, [d.timestamp*1000])[d.timestamp*1000]
                if d.flags != ROW_VALID:
                    self.assertLess(val['is_valid'], 2)
                else:
                    self.assertLessEqual(abs(val['val'] - d.delta), 1.0)
                    self.assertGreater(val['is_valid'], 0)

        db.close()

    def test_persister_heartbeat(self):
        """Test the hearbeat code"""
        # XXX(jdugan): commented out until performance problem from r794 is fixed
        return
        config = get_config(get_config_path())

        freq = 30
        iface = 'GigabitEthernet0/1'
        t0 = 1343953700
        t1 = t0 + (4*freq)
        b0 = t0 - (t0 % freq)
        b1 = t1 - (t1 % freq)
        t2 = t1 + 2*freq + (SEEK_BACK_THRESHOLD/1000)
        b2 = t2 - (t2 % freq)
        b0 *= 1000
        b1 *= 1000
        b2 *= 1000

        data_template = {
            'oidset_name': 'FastPollHC',
            'device_name': 'rtr_d',
            'oid_name': 'ifHCInOctets',
        }

        # with backfill

        test_data = []
        d0 = data_template.copy()
        d0['timestamp'] = t0
        d0['data'] = [[["ifHCInOctets", iface], 0]]
        test_data.append(d0)

        d1 = data_template.copy()
        d1['timestamp'] = t1
        d1['data'] = [[["ifHCInOctets", iface], 1000]]
        test_data.append(d1)

        # no backfill

        d2 = data_template.copy()
        d2['timestamp'] = t2
        d2['data'] = [[["ifHCInOctets", iface], 865000]]
        test_data.append(d2)

        q = TestPersistQueue(test_data)
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.flush()
        p.db.close()
        p.db.stats.report('all')

        key = '%s:%s:%s:%s:%s:%s:%s'  % (
                SNMP_NAMESPACE,
                data_template['device_name'],
                data_template['oidset_name'],
                data_template['oid_name'],
                iface,
                freq*1000,
                datetime.datetime.utcfromtimestamp(t0).year
            )

        db = CASSANDRA_DB(config)
        rates = ColumnFamily(db.pool, db.rate_cf)

        backfill = rates.get(key, column_start=b0, column_finish=b1)

        self.assertEqual(len(backfill), 5)
        last = backfill[b1]
        self.assertEqual(last['val'], 166)
        self.assertEqual(last['is_valid'], 1)

        nobackfill = rates.get(key, column_start=b1, column_finish=b2)

        # test no backfill, make sure we don't insert a month of zeros...

        self.assertEqual(len(nobackfill), 2)
        self.assertEqual(nobackfill[b1]['is_valid'], 1)
        self.assertEqual(nobackfill[b1]['val'], 166)
        self.assertEqual(nobackfill[b2]['is_valid'], 1)
        self.assertEqual(nobackfill[b2]['val'], 6)

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
            path=[SNMP_NAMESPACE,'rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            freq=30*1000,
            ts_min=start_time,
            ts_max=end_time
        )

        self.assertEqual(len(ret), self.ctr.expected_results)
        self.assertEqual(ret[0]['ts'], start_time)
        self.assertEqual(ret[0]['val'], self.ctr.base_rate_val_first)
        self.assertEqual(ret[self.ctr.expected_results-1]['ts'], end_time)
        self.assertEqual(ret[self.ctr.expected_results-1]['val'],
                self.ctr.base_rate_val_last)

        ret = db.query_raw_data(
            path=[SNMP_NAMESPACE,'rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            freq=30*1000,
            ts_min=start_time,
            ts_max=end_time
        )

        self.assertEqual(len(ret), self.ctr.expected_results - 1)
        self.assertEqual(ret[0]['ts'], self.ctr.raw_ts_first*1000)
        self.assertEqual(ret[0]['val'], self.ctr.raw_val_first)
        self.assertEqual(ret[len(ret)-1]['ts'], self.ctr.raw_ts_last*1000)
        self.assertEqual(ret[len(ret)-1]['val'], self.ctr.raw_val_last)

        ret = db.query_aggregation_timerange(
            path=[SNMP_NAMESPACE,'rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            ts_min=start_time - 3600*1000,
            ts_max=end_time,
            freq=self.ctr.agg_freq*1000, # required!
            cf='average',  # min | max | average - also required!
        )
        
        self.assertEqual(ret[0]['cf'], 'average')
        self.assertEqual(ret[0]['val'], self.ctr.agg_avg)
        self.assertEqual(ret[0]['ts'], self.ctr.agg_ts*1000)

        ret = db.query_aggregation_timerange(
            path=[SNMP_NAMESPACE,'rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            ts_min=start_time - 3600*1000,
            ts_max=end_time,
            freq=self.ctr.agg_freq*1000, # required!
            cf='raw',  # raw - rarely used
        )

        self.assertEqual(ret[0]['cf'], 'raw')
        self.assertEqual(ret[0]['val'], self.ctr.agg_raw)
        self.assertEqual(ret[0]['ts'], self.ctr.agg_ts*1000)

        return
        
        ret = db.query_aggregation_timerange(
            path=[SNMP_NAMESPACE,'rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            ts_min=start_time - 3600*1000,
            ts_max=end_time,
            freq=self.ctr.agg_freq*1000, # required!
            cf='min',  # min | max | average - also required!
        )

        self.assertEqual(ret[0]['cf'], 'min')
        self.assertEqual(ret[0]['val'], self.ctr.agg_min)
        self.assertEqual(ret[0]['ts'], self.ctr.agg_ts*1000)

        ret = db.query_aggregation_timerange(
            path=[SNMP_NAMESPACE,'rtr_d','FastPollHC','ifHCInOctets','fxp0.0'],
            ts_min=start_time - 3600*1000,
            ts_max=end_time,
            freq=self.ctr.agg_freq*1000, # required!
            cf='max',  # min | max | average - also required!
        )
        
        self.assertEqual(ret[0]['cf'], 'max')
        self.assertEqual(ret[0]['val'], self.ctr.agg_max)
        self.assertEqual(ret[0]['ts'], self.ctr.agg_ts*1000)

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
        # print json.dumps(data, indent=4)

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
            'begin': self.ctr.begin * 1000,
            'end': self.ctr.end * 1000
        }

        url = '/v1/timeseries/BaseRate/{0}/rtr_d/FastPollHC/ifHCInOctets/fxp0.0/30000'.format(SNMP_NAMESPACE)

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
        self.assertEquals(data['data'][0][0], params['begin'])
        self.assertEquals(data['data'][0][1], self.ctr.base_rate_val_first)
        self.assertEquals(data['data'][self.ctr.expected_results-1][0], params['end'])
        self.assertEquals(data['data'][self.ctr.expected_results-1][1], self.ctr.base_rate_val_last)

    def test_get_timeseries_data_aggs(self):
        """/timeseries rest test for aggs."""
        params = {
            'begin': (self.ctr.begin - 3600) * 1000, # back an hour to get agg bin.
            'end': self.ctr.end * 1000,
        }

        url = '/v1/timeseries/Aggs/{0}/rtr_d/FastPollHC/ifHCInOctets/fxp0.0/{1}'.format(SNMP_NAMESPACE, self.ctr.agg_freq*1000)

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

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
        """/timeseries rest test for raw data - this reads from the canned 
        test data."""
        params = {
            'begin': self.ctr.begin * 1000,
            'end': self.ctr.end * 1000
        }

        url = '/v1/timeseries/RawData/{0}/rtr_d/FastPollHC/ifHCInOctets/fxp0.0/30000'.format(SNMP_NAMESPACE)

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['end_time'], params['end'])
        self.assertEquals(data['begin_time'], params['begin'])
        self.assertEquals(data['agg'], '30000')
        self.assertEquals(len(data['data']), self.ctr.expected_results-1)
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['cf'], 'raw')

    def test_timeseries_post_and_read(self):
        """/timeseries rest test for raw/base rate writes and reads - 
        does not use the canned test data."""

        interface_name = 'interface_test/0/0.0'

        authn = self.create_apikey(self.td.user_admin.username, 
            self.td.user_admin_apikey.key)

        # raw data writes
        url = '/v1/timeseries/RawData/rtr_test/FastPollHC/ifHCInOctets/{0}/30000'.format(atencode(interface_name))

        params = { 
            'ts': int(time.time()) * 1000, 
            'val': 1000 
        }

        # Params sent as json list and not post vars now.
        payload = [ params ]

        response = self.api_client.post(url, data=payload, format='json',
            authentication=authn)
        self.assertEquals(response.status_code, 201) # not 200!

        response = self.client.get(url, authentication=authn)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        
        self.assertEquals(data['agg'], '30000')
        self.assertEquals(data['resource_uri'], url)
        # Check last value in case the db has not been wiped by a
        # full data load.
        self.assertEquals(data['data'][-1][0], params['ts'])
        self.assertEquals(data['data'][-1][1], float(params['val']))
        self.assertEquals(data['cf'], 'raw')

        # base rate write
        url = '/v1/timeseries/BaseRate/rtr_test/FastPollHC/ifHCInOctets/{0}/30000'.format(atencode(interface_name))

        response = self.api_client.post(url, data=payload, format='json',
            authentication=authn)
        self.assertEquals(response.status_code, 201) # not 200!

        response = self.client.get(url, authentication=authn)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['agg'], '30000')
        self.assertEquals(data['resource_uri'], url)
        # Check last value in case the db has not been wiped by a
        # full data load.
        self.assertEquals(data['data'][-1][0], params['ts'])
        # Base rate read will return the delta divided by the frequency,
        # not just the value inserted!
        self.assertEquals(data['data'][-1][1], float(params['val'])/30)
        self.assertEquals(data['cf'], 'average')

    def test_interface_bulk_get(self):
        """Test bulk interface: /bulk/interface/"""

        ifaces = ['xe-7/0/0.0', 'ge-9/1/0']

        devs = []

        for i in ifaces:
            devs.append({'device': 'rtr_d', 'iface': i})

        payload = { 
            'interfaces': devs, 
            'endpoint': ['in'],
            'cf': 'average',
            'begin': self.ctr.begin,
            'end': self.ctr.end
        }

        response = self.api_client.post('/v1/bulk/interface/', data=payload,
            format='json')
        self.assertEquals(response.status_code, 201) # not 200!

        data = json.loads(response.content)
        self.assertEquals(len(data['data']), 2)
        self.assertEquals(data['data'][0]['path']['iface'], ifaces[0])
        self.assertEquals(len(data['data'][0]['data']), 21)
        self.assertEquals(data['end_time'], self.ctr.end)
        self.assertEquals(data['begin_time'], self.ctr.begin)

    def test_timeseries_bulk_get(self):
        """Test bulk interface: /bulk/timeseries/"""
        # Last/frequency element not quoted since json is going to return
        # it as a number in the same list and we want to assess the return
        # values.
        paths = [
            ['snmp','rtr_d','FastPollHC','ifHCInOctets','xe-7/0/0.0', 30000],
            ['snmp','rtr_d','FastPollHC','ifHCInOctets','ge-9/1/0', 30000]
        ]

        payload = {
            'type': 'BaseRate',
            'paths': paths,
            'begin': self.ctr.begin*1000,
            'end': self.ctr.end*1000
        }

        response = self.api_client.post('/v1/bulk/timeseries/', data=payload,
            format='json')
        self.assertEquals(response.status_code, 201) # not 200!

        data = json.loads(response.content)
        self.assertEquals(len(data['data']), 2)
        self.assertEquals(data['data'][0]['path'], paths[0])
        self.assertEquals(data['data'][1]['path'], paths[1])
        self.assertEquals(len(data['data'][0]['data']), 21)
        self.assertEquals(data['end_time'], payload['end'])
        self.assertEquals(data['begin_time'], payload['begin'])

    def test_device_info(self):
        response = self.api_client.get('/v1/device/')
        self.assertEquals(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEquals(len(payload), 1)

        data = payload[0]

        self.assertEquals(data['resource_uri'], '/v1/device/rtr_d/')
        self.assertEquals(data['id'], 1)
        self.assertEquals(data['name'], 'rtr_d')

        ifaces = None

        for c in data['children']:
            if c['name'] == 'interface':
                ifaces = c['uri']

        self.assertTrue(ifaces)

        ifaces += '?limit=0'

        response = self.api_client.get(ifaces)
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(len(data['children']))
        self.assertEquals(len(data['children']), data['meta']['total_count'])

    def test_interface_info(self):
        response = self.api_client.get('/v1/interface/?limit=0&ifDescr__contains=fxp')
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(len(data['children']))
        self.assertEquals(data['children'][0]['ifDescr'], 'fxp0.0')
        self.assertEquals(len(data['children']), data['meta']['total_count'])

    def test_oidset_info(self):
        response = self.api_client.get('/v1/oidset/')
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        
        self.assertEquals(len(data), 16)

    def test_z_throttle(self):
        ifaces = [
            'xe-7/0/0.0',
            'ge-9/1/0',
            'xe-1/3/0.911',
            'ge-9/1/1.337',
            'ge-9/1/2.0',
            'xe-1/1/0.65',
            'ge-9/0/8',
            'xe-0/1/0.0',
            'ge-9/1/0.909',
            'ge-9/0/5',
            'lo0.0',
            'ge-9/1/9',
            'ge-9/0/2.0',
            'ge-9/1/3.0',
            'xe-1/2/0',
            'xe-0/1/0',
            'ge-9/0/2',
            'xe-1/3/0',
            'ge-9/1/5.0',
            'ge-9/1/9.0',
            'irb.0',
            'ge-9/0/9.1116',
            'ge-9/0/7.0',
            'ge-9/0/5.0',
            'ge-9/0/4.0',
            'xe-9/3/0.912',
            'ge-9/0/8.0',
            'ge-9/0/9.1114',
            'xe-0/2/0.16',
            'ge-9/1/6',
            'ge-9/0/1.0',
            'xe-1/1/0',
            'ge-9/0/0.66',
            'ge-9/1/5',
            'ge-9/0/1',
            'xe-7/1/0',
            'ge-9/1/2',
            'xe-0/0/0',
            'ge-9/1/1.3003',
            'fxp0.0',
            'ge-9/0/0',
            'lo0',
            'ge-9/0/0.44',
            'xe-1/2/0.41',
            'ge-9/1/1.332',
            'ge-9/1/8',
            'xe-1/0/0.0',
            'xe-9/3/0.916',
            'ge-9/1/6.0',
            'ge-9/1/4.0',
            'ge-9/0/3',
            'ge-9/1/1.336',
            'ge-9/0/4',
            'ge-9/1/1.333',
            'xe-1/0/0',
            'xe-1/3/0.915',
            'xe-8/0/0',
            'ge-9/1/0.913',
            'ge-9/1/3',
            'ge-9/0/6.0',
            'ge-9/0/3.0',
            'ge-9/1/8.0',
            'xe-0/2/0',
            'xe-8/0/0.0',
            'xe-7/0/0',
            'ge-9/0/9',
            'ge-9/0/6',
            'xe-0/0/0.0',
            'ge-9/0/7',
            'ge-9/1/1',
            'xe-1/1/0.45',
            'xe-9/3/0',
            'ge-9/1/4',
        ]

        devs = []

        for i in ifaces:
            devs.append({'device': 'rtr_d', 'iface': i})

        payload = { 
            'interfaces': devs, 
            'endpoint': ['in', 'out'],
            'cf': 'average',
            'begin': self.ctr.begin,
            'end': self.ctr.end
        }

        config = get_config(get_config_path())
        # This assertion will trigger if the api_anon_limit is set 
        # higher than the number of requests that are about to be
        # generated.  The default is usually around 30 and this will
        # generate somewhere in the neighborhood of 150 different
        # queries and should trigger the throttling.
        self.assertLessEqual(ANON_LIMIT, len(ifaces)*len(payload['endpoint']))

        # Make a request the bulk endpoint will throttle for too many 
        # queries w/out auth.

        response = self.api_client.post('/v1/bulk/interface/', data=payload,
            format='json')
        self.assertEquals(response.status_code, 401)

        # Make the same request with authentication.

        authn = self.create_apikey(self.td.user_admin.username, 
            self.td.user_admin_apikey.key)
        response = self.api_client.post('/v1/bulk/interface/', data=payload,
            format='json', authentication=authn)
        self.assertEquals(response.status_code, 201) # not 200!

        # Make a bunch of requests to make sure that the throttling
        # code kicks in.

        params = {
            'begin': self.ctr.begin-3600, # back an hour to get agg bin.
            'end': self.ctr.end,
            'agg': self.ctr.agg_freq
        }

        url = '/v1/device/rtr_d/interface/fxp0.0/in'

        response = self.client.get(url, params)

        loops = 5 # leave a little overhead

        if not config.api_throttle_at:
            loops += 150 # tastypie default
        else:
            loops += config.api_throttle_at

        # Make looping requests looking for the 429 throttle return code.
        # Leave a couple of extra loops as margin of error, but break
        # out if no 429 received so it doesn't go into the loop of death.

        rcount = 1
        got_429 = False

        while rcount < loops:
            response = self.client.get(url, params)
            if response.status_code == 429:
                got_429 = True
                break
            rcount += 1

        self.assertEqual(got_429, True)

        pass

class TestFitToBins(TestCase):
    def test_fit_to_bins(self):
        # tests from fit_to_bins docstring
        r = fit_to_bins(30, 0, 0, 30, 100)
        self.assertEqual({0: 100, 30: 0}, r)

        r = fit_to_bins(30, 31, 100, 62, 213)
        self.assertEqual({60: 7, 30: 106}, r)

        r = fit_to_bins(30, 90, 100, 121, 200)
        self.assertEqual({120: 3, 90: 97}, r)

        r = fit_to_bins(30, 89, 100, 181, 200)
        self.assertEqual({120: 33, 180: 1, 90: 33, 60: 0, 150: 33}, r)

        # test from real world extreme slowdown
        t0 = time.time()
        r = fit_to_bins(30000, 1386369693000, 141368641534364, 1386369719000, 141368891281597)
        self.assertEqual({1386369690000: 249747233}, r)
        self.assertLess(time.time()-t0, 0.5)
       

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
