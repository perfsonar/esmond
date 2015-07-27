"""
Tests for the client libraries.
"""

import os
import os.path
import json

# import encodings.idna

# This MUST be here in any testing modules that use cassandra!
os.environ['ESMOND_UNIT_TESTS'] = 'True'

from django.test import LiveServerTestCase

from esmond.config import get_config, get_config_path
from esmond.persist import CassandraPollPersister
from esmond.api import SNMP_NAMESPACE

from esmond_client.snmp import ApiConnect, ApiFilters, API_VERSION_PREFIX 
from esmond_client.timeseries import GetRawData, GetBaseRate, \
    GetBulkRawData, GetBulkBaseRate
from esmond.api.tests.example_data import build_rtr_d_metadata, \
     build_metadata_from_test_data, load_test_data
from esmond.api.tests.test_persist import CassandraTestResults, TestPersistQueue


class TestClientLibs(LiveServerTestCase):
    fixtures = ['oidsets.json']

    def setUp(self):
        self.td = build_rtr_d_metadata()
        test_data = load_test_data("rtr_d_ifhcin_long.json")
        build_metadata_from_test_data(test_data)

        # print self.td.user_admin.username, self.td.user_admin_apikey.key

        self.ctr = CassandraTestResults()

    def test_a_load_data(self):
        config = get_config(get_config_path())
        config.db_clear_on_testing = True
        
        test_data = load_test_data("rtr_d_ifhcin_long.json")
        q = TestPersistQueue(test_data)
        p = CassandraPollPersister(config, "test", persistq=q)
        p.run()
        p.db.flush()
        p.db.close()

    def test_snmp_device_hierarchy(self):
        filters = ApiFilters()

        filters.begin_time = self.ctr.begin
        filters.end_time = self.ctr.end

        conn = ApiConnect('http://localhost:8081', filters,
            username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)
        d = list(conn.get_devices())
        self.assertEquals(len(d), 1)
        device = d[0]
        self.assertEquals(device.name, 'rtr_d')

        self.assertTrue(device.begin_time)
        self.assertTrue(device.end_time)
        self.assertTrue(device.id)
        self.assertFalse(device.leaf)
        self.assertTrue(device.resource_uri)
        self.assertTrue(device.children)
        self.assertTrue(device.active)
        self.assertTrue(device.oidsets)

        ifaces = list(device.get_interfaces())

        interface = ifaces[0]

        self.assertEquals(interface.device_uri, '/{0}/device/rtr_d/'.format(API_VERSION_PREFIX))
        self.assertEquals(interface.device, 'rtr_d')
        self.assertEquals(interface.ifName, 'fxp0.0')

        endpoints = list(interface.get_endpoints())
        self.assertEquals(len(endpoints), 2)
        # sort into dict since banking on array ordering is madness.
        e_map = dict()
        for e in endpoints:
            e_map[e.name] = e
        # make sure we have the right ones
        self.assertEqual(set(e_map.keys()), set(['in', 'out']))

        # test fetching a single endpoint
        ep = interface.get_endpoint('out')
        self.assertEquals(ep.name, 'out')

        # check the data
        payload = e_map.get('in').get_data()
        self.assertTrue(payload.agg)
        self.assertTrue(payload.cf)

        datapoints = payload.data

        self.assertEquals(datapoints[0].val, self.ctr.base_rate_val_first)
        self.assertEquals(datapoints[-1].val, self.ctr.base_rate_val_last)

    def test_snmp_interfaces(self):
        filters = ApiFilters()

        filters.begin_time = self.ctr.begin
        filters.end_time = self.ctr.end

        conn = ApiConnect('http://localhost:8081', filters,
            username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)

        iface_filt = {'ifName__contains': 'fxp0.0'}

        i = list(conn.get_interfaces(**iface_filt))
        self.assertEquals(len(i), 1)

        interface = i[0]

        self.assertEquals(interface.device_uri, '/{0}/device/rtr_d/'.format(API_VERSION_PREFIX))
        self.assertEquals(interface.device, 'rtr_d')
        self.assertEquals(interface.ifName, 'fxp0.0')

        self.assertTrue(interface.device)
        self.assertTrue(interface.ifAdminStatus)
        self.assertTrue(interface.ifAlias)
        self.assertTrue(interface.ifName)
        self.assertTrue(interface.ifHighSpeed)
        self.assertTrue(interface.ifIndex)
        self.assertTrue(interface.ifMtu)
        self.assertTrue(interface.ifOperStatus)
        self.assertTrue(interface.ifPhysAddress)
        self.assertTrue(isinstance(interface.ifSpeed, int))
        self.assertFalse(interface.ifType)
        self.assertTrue(interface.ipAddr)
        self.assertTrue(interface.uri)

    def test_snmp_rate_get(self):
        filters = ApiFilters()

        filters.begin_time = self.ctr.begin
        filters.end_time = self.ctr.end
        filters.endpoint = ['in']

        conn = ApiConnect('http://localhost:8081', filters,
            username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)

        i = list(conn.get_interfaces(**{'ifName': 'fxp0.0'})).pop()

        e = i.get_endpoint('in')

        payload = e.get_data()

        data = payload.data

        self.assertEquals(len(data), self.ctr.expected_results)
        self.assertEquals(data[0].ts_epoch, self.ctr.begin)
        self.assertEquals(data[0].val, self.ctr.base_rate_val_first)
        self.assertEquals(data[0].m_ts, None)
        self.assertEquals(data[self.ctr.expected_results-1].ts_epoch, self.ctr.end)
        self.assertEquals(data[self.ctr.expected_results-1].val, self.ctr.base_rate_val_last)

    def test_snmp_agg_get(self):

        filters = ApiFilters()

        filters.begin_time = self.ctr.begin-3600
        filters.end_time = self.ctr.end
        filters.endpoint = ['in']
        filters.cf = 'min'
        filters.agg = self.ctr.agg_freq

        conn = ApiConnect('http://localhost:8081', filters,
            username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)

        payload = conn.get_interface_bulk_data(**{'ifName': 'fxp0.0'})
        
        row = payload.data.pop()

        dp = row.data.pop()

        self.assertEquals(len(row.data), 1)
        self.assertEquals(dp.ts_epoch, self.ctr.agg_ts)
        self.assertEquals(dp.val, self.ctr.agg_min)
        self.assertEquals(dp.m_ts, self.ctr.agg_min_ts)

        filters.cf = 'max'

        payload = conn.get_interface_bulk_data(**{'ifName': 'fxp0.0'})
        
        row = payload.data.pop()

        dp = row.data.pop()

        self.assertEquals(len(row.data), 1)
        self.assertEquals(dp.ts_epoch, self.ctr.agg_ts)
        self.assertEquals(dp.val, self.ctr.agg_max)
        self.assertEquals(dp.m_ts, self.ctr.agg_max_ts)

    def test_snmp_bulk_get(self):
        filters = ApiFilters()

        filters.begin_time = self.ctr.begin
        filters.end_time = self.ctr.end

        conn = ApiConnect('http://localhost:8081', filters,
            username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)

        iface_filt = {'ifName__contains': 'xe-'}

        data = conn.get_interface_bulk_data(**iface_filt)
        self.assertEquals(len(data.data), 24)

        for d in data.data:
            self.assertEquals(d.interface[0:3], 'xe-')
            self.assertEquals(len(d.data), 21)
            for dd in d.data:
                self.assertNotEquals(dd.val, None)

    def test_timeseries_get(self):
        params = {
            'begin': self.ctr.begin*1000,
            'end': self.ctr.end*1000,
        }

        path = [SNMP_NAMESPACE,'rtr_d','FastPollHC','ifHCInOctets','fxp0.0']

        g = GetRawData(api_url='http://localhost:8081', path=path, freq=30000,
            params=params,username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)

        payload = g.get_data()

        self.assertEquals(payload.cf, 'raw')
        self.assertEquals(int(payload.agg), 30000)
        self.assertEquals(len(payload.data), self.ctr.expected_results-1)

        data = list(payload.data)
        self.assertEquals(data[0].val, self.ctr.raw_val_first)
        self.assertEquals(data[-1].val, self.ctr.raw_val_last)

        g = GetBaseRate(api_url='http://localhost:8081', path=path, freq=30000,
            params=params,username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)

        payload = g.get_data()

        self.assertEquals(payload.cf, 'average')
        self.assertEquals(int(payload.agg), 30000)
        self.assertEquals(len(payload.data), self.ctr.expected_results)

        data = list(payload.data)
        self.assertEquals(data[0].val, self.ctr.base_rate_val_first)
        self.assertEquals(data[-1].val, self.ctr.base_rate_val_last)

    def test_timeseries_bulk_get(self):

        params = {
            'begin': self.ctr.begin*1000,
            'end': self.ctr.end*1000,
        }

        paths = [
            ['snmp','rtr_d','FastPollHC','ifHCInOctets','xe-7/0/0.0', 30000],
            ['snmp','rtr_d','FastPollHC','ifHCInOctets','ge-9/1/0', 30000]
        ]

        g = GetBulkRawData('http://localhost:8081',username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)
        payload = g.get_data(paths, **params)

        data = list(payload.data)

        self.assertEquals(len(data), 2)
        self.assertEquals(data[0].path, paths[0])
        self.assertEquals(data[1].path, paths[1])
        self.assertEquals(len(list(data[1].data)), 20)

        g = GetBulkBaseRate('http://localhost:8081',username=self.td.user_admin.username, 
            api_key=self.td.user_admin_apikey.key)
        payload = g.get_data(paths, **params)

        data = list(payload.data)

        self.assertEquals(len(data), 2)
        self.assertEquals(data[0].path, paths[0])
        self.assertEquals(data[1].path, paths[1])
        self.assertEquals(len(list(data[1].data)), 21)

        pass
