import json
import time
import calendar
import datetime

import mock 

from django.core.urlresolvers import reverse
from tastypie.test import ResourceTestCase

from esmond.api.models import *
from esmond.api.api import OIDSET_INTERFACE_ENDPOINTS
from esmond.api.tests.example_data import build_default_metadata
from esmond.cassandra import AGG_TYPES

def datetime_to_timestamp(dt):
    return calendar.timegm(dt.timetuple())

from django.test import TestCase

class DeviceAPITestsBase(ResourceTestCase):
    fixtures = ["oidsets.json"]
    def setUp(self):
        super(DeviceAPITestsBase, self).setUp()

        self.td = build_default_metadata()


class DeviceAPITests(DeviceAPITestsBase):
    def test_get_device_list(self):
        url = '/v1/device/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        # by default only currently active devices are returned
        data = json.loads(response.content)
        self.assertEquals(len(data), 3)

        # get all three devices, with date filters
        begin = datetime_to_timestamp(self.td.rtr_b.begin_time)
        response = self.client.get(url, dict(begin=begin))
        data = json.loads(response.content)
        self.assertEquals(len(data), 4)

        # exclude rtr_b by date

        begin = datetime_to_timestamp(self.td.rtr_a.begin_time)
        response = self.client.get(url, dict(begin=begin))
        data = json.loads(response.content)
        self.assertEquals(len(data), 3)
        for d in data:
            self.assertNotEqual(d['name'], 'rtr_b')

        # exclude all routers with very old end date
        response = self.client.get(url, dict(end=0))
        data = json.loads(response.content)
        self.assertEquals(len(data), 0)

        # test for equal (gte/lte)
        begin = datetime_to_timestamp(self.td.rtr_b.begin_time)
        response = self.client.get(url, dict(begin=0, end=begin))
        data = json.loads(response.content)
        self.assertEquals(len(data), 1)
        self.assertEquals(data[0]['name'], 'rtr_b')

        end = datetime_to_timestamp(self.td.rtr_b.end_time)
        response = self.client.get(url, dict(begin=0, end=end))
        data = json.loads(response.content)
        self.assertEquals(len(data), 1)
        self.assertEquals(data[0]['name'], 'rtr_b')

    def test_get_device_detail(self):
        url = '/v1/device/rtr_a/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        #print json.dumps(data, indent=4)
        for field in [
            'active',
            'begin_time',
            'end_time',
            'id',
            'leaf',
            'name',
            'resource_uri',
            'uri',
            ]:
            self.assertIn(field,data)

        children = {}
        for child in data['children']:
            children[child['name']] = child
            for field in ['leaf','name','uri']:
                self.assertIn(field, child)

        for child_name in ['all', 'interface', 'system']:
            self.assertIn(child_name, children)
            child = children[child_name]
            self.assertEqual(child['uri'], url + child_name)

    def test_post_device_list_unauthenticated(self):
        # We don't allow POSTs at this time.  Once that capability is added
        # these tests will need to be expanded.

        self.assertHttpMethodNotAllowed(
                self.client.post('/v1/device/entries/', format='json',
                    data=self.td.rtr_z_post_data))

    def test_get_device_interface_list(self):
        url = '/v1/device/rtr_a/interface/'

        # single interface at current time
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEquals(len(data['children']), 1)

        # no interfaces if we are looking in the distant past
        response = self.client.get(url, dict(end=0))
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEquals(len(data['children']), 0)

        url = '/v1/device/rtr_b/interface/'

        begin = datetime_to_timestamp(self.td.rtr_b.begin_time)
        end = datetime_to_timestamp(self.td.rtr_b.end_time)

        # rtr_b has two interfaces over it's existence
        response = self.client.get(url, dict(begin=begin, end=end))
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEquals(len(data['children']), 2)

        # rtr_b has only one interface during the last part of it's existence
        begin = datetime_to_timestamp(self.td.rtr_b.begin_time +
                datetime.timedelta(days=8))
        response = self.client.get(url, dict(begin=begin, end=end))
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEquals(len(data['children']), 1)
        self.assertEquals(data['children'][0]['ifDescr'], 'xe-1/0/0')

        url = '/v1/device/rtr_alu/interface/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(len(data['children']), 1)
        self.assertEquals(data['children'][0]['ifDescr'], '3/1/1')

    def test_get_device_interface_detail(self):
        for device, iface in (
                ('rtr_a', 'xe-0_0_0'),
                ('rtr_alu', '3_1_1'),
                ('rtr_inf', 'xe-3_0_0'),
            ):

            url = '/v1/device/{0}/interface/{1}/'.format(device, iface)

            response = self.client.get(url)
            self.assertEquals(response.status_code, 200)

            data = json.loads(response.content)
            self.assertEquals(data['ifDescr'], iface.replace("_", "/"))

            for field in [
                    'begin_time',
                    'children',
                    'device_uri',
                    'end_time',
                    'ifAlias',
                    'ifDescr',
                    'ifHighSpeed',
                    'ifIndex',
                    'ifSpeed',
                    'ipAddr',
                    'leaf',
                    'uri',
                ]:
                self.assertIn(field, data)

            self.assertNotEqual(len(data['children']), 0)

            children = {}
            for child in data['children']:
                children[child['name']] = child
                for field in ['leaf','name','uri']:
                    self.assertIn(field, child)

            for oidset in Device.objects.get(name=device).oidsets.all():
                if oidset.name not in OIDSET_INTERFACE_ENDPOINTS:
                    continue

                for child_name in OIDSET_INTERFACE_ENDPOINTS[oidset.name].keys():
                    self.assertIn(child_name , children)
                    child = children[child_name]
                    self.assertEqual(child['uri'], url + child_name)
                    self.assertTrue(child['leaf'])

    def test_get_device_interface_list_hidden(self):
        url = '/v1/device/rtr_a/interface/'

        response = self.client.get(url)
        data = json.loads(response.content)

        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(data['children']), 1)
        for child in data['children']:
            self.assertTrue(":hide:" not in child['ifAlias'])

        authn = self.create_apikey(self.td.user_seeall.username,
                self.td.user_seeall_apikey.key)

        response = self.api_client.get(url, authentication=authn)
        data = json.loads(response.content)
        self.assertEquals(len(data['children']), 2)

    def test_get_device_interface_detail_hidden(self):
        url = '/v1/device/rtr_a/interface/xe-1_0_0/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 404)

        authn = self.create_apikey(self.td.user_seeall.username,
                self.td.user_seeall_apikey.key)

        response = self.api_client.get(url, authentication=authn)
        data = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertTrue(":hide:" in data['ifAlias'])


class MockCASSANDRA_DB(object):
    def __init__(self, config):
        pass

    def query_baserate_timerange(self, path=None, freq=None, ts_min=None, ts_max=None):
        # Mimic returned data, format elsehwere
        self._test_incoming_args(path, freq, ts_min, ts_max)
        return [
            {'is_valid': 2, 'ts': 0*1000, 'val': 10},
            {'is_valid': 2, 'ts': 30*1000, 'val': 20},
            {'is_valid': 2, 'ts': 60*1000, 'val': 40},
            {'is_valid': 0, 'ts': 90*1000, 'val': 80}
        ]

    def query_aggregation_timerange(self, path=None, freq=None, ts_min=None, ts_max=None, cf=None):
        self._test_incoming_args(path, freq, ts_min, ts_max, cf)
        if cf == 'average':
            return [
                {'ts': 0, 'val': 60, 'cf': 'average'},
                {'ts': freq, 'val': 120, 'cf': 'average'},
                {'ts': freq*2, 'val': 240, 'cf': 'average'},
            ]
        elif cf == 'min':
            return [
                {'ts': 0, 'val': 0, 'cf': 'min'},
                {'ts': freq, 'val': 10, 'cf': 'min'},
                {'ts': freq*2,'val': 20, 'cf': 'min'},
            ]
        elif cf == 'max':
            return [
                {'ts': 0, 'val': 75, 'cf': 'max'},
                {'ts': freq, 'val': 150, 'cf': 'max'},
                {'ts': freq*2, 'val': 300, 'cf': 'max'},
            ]
        else:
            pass

    def _test_incoming_args(self, path, freq, ts_min, ts_max, cf=None):
        assert isinstance(path, list)
        assert isinstance(freq, int)
        assert isinstance(ts_min, int)
        assert isinstance(ts_max, int)
        if cf:
            assert isinstance(cf, str) or isinstance(cf, unicode)
            assert cf in AGG_TYPES


class DeviceAPIDataTests(DeviceAPITestsBase):
    def setUp(self):
        super(DeviceAPIDataTests, self).setUp()
        # mock patches names where used/imported, not where defined
        # This form will patch a class when it is instantiated by the executed code:
        # self.patcher = mock.patch("esmond.api.api.CASSANDRA_DB", MockCASSANDRA_DB)
        # This form will patch a module-level class instance:
        self.patcher = mock.patch("esmond.api.api.db", MockCASSANDRA_DB(None))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_bad_endpoints(self):
        # there is no router called nonexistent
        url = '/v1/device/nonexistent/interface/xe-0_0_0/in'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 404)

        # rtr_a does not have an nonexistent interface
        url = '/v1/device/rtr_a/interface/nonexistent/in'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 404)

        # there is no nonexistent sub collection in traffic
        url = '/v1/device/rtr_a/interface/xe-0_0_0/nonexistent'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 404)

        # there is no nonexistent collection 
        url = '/v1/device/rtr_a/interface/xe-0_0_0/nonexistent/in'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 404)

        # rtr_b has no traffic oidsets defined
        url = '/v1/device/rtr_a/interface/xe-0_0_0/nonexistent/in'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 404)


    def test_get_device_interface_data_detail(self):
        url = '/v1/device/rtr_a/interface/xe-0_0_0/in'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(int(data['agg']), 30)
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][1][0], 30)
        self.assertEquals(data['data'][1][1], 20)

        url = '/v1/device/rtr_inf/interface/xe-3_0_0/out'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(int(data['agg']), 30)
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][2][0], 60)
        self.assertEquals(data['data'][2][1], 40)

        # make sure it works with a trailing slash too
        url = '/v1/device/rtr_inf/interface/xe-3_0_0/out/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(int(data['agg']), 30)
        self.assertEquals(data['resource_uri'], url.rstrip("/"))
        self.assertEquals(data['data'][2][0], 60)
        self.assertEquals(data['data'][2][1], 40)


    def test_get_device_interface_data_detail_hidden(self):
        url = '/v1/device/rtr_a/interface/xe-1_0_0/in'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        authn = self.create_apikey(self.td.user_seeall.username,
                self.td.user_seeall_apikey.key)

        response = self.api_client.get(url, authentication=authn)

        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(len(data['data']) > 0)

    def test_bad_aggregations(self):
        url = '/v1/device/rtr_a/interface/xe-0_0_0/in'

        params = {'agg': '3601'} # this agg does not exist

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

        params = {'agg': '3600', 'cf': 'bad'} # this cf does not exist

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)


    def test_get_device_interface_data_aggs(self):
        url = '/v1/device/rtr_a/interface/xe-0_0_0/in'

        params = {'agg': '3600'}

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(data['agg'], params['agg'])
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][2][0], int(params['agg'])*2)
        self.assertEquals(data['data'][2][1], 240)

        # try the same agg, different cf
        params['cf'] = 'min'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['cf'], 'min')
        self.assertEquals(data['agg'], params['agg'])
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][2][0], int(params['agg'])*2)
        self.assertEquals(data['data'][2][1], 20)

        # and the last cf
        params['cf'] = 'max'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['cf'], 'max')
        self.assertEquals(data['agg'], params['agg'])
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][2][0], int(params['agg'])*2)
        self.assertEquals(data['data'][2][1], 300)

    def test_get_device_errors(self):
        url = '/v1/device/rtr_a/interface/xe-0_0_0/error/in'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(data['resource_uri'], url)

        # print json.dumps(data, indent=4)

        url = '/v1/device/rtr_a/interface/xe-0_0_0/discard/out'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(data['resource_uri'], url)

    def test_timerange_limiter(self):
        url = '/v1/device/rtr_a/interface/xe-0_0_0/in'

        params = { 
            'begin': int(time.time() - datetime.timedelta(days=31).total_seconds())
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

        url = '/v1/device/rtr_a/interface/xe-0_0_0/out'

        params = {
            'agg': '3600',
            'begin': int(time.time() - datetime.timedelta(days=366).total_seconds())
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

        url = '/v1/device/rtr_a/interface/xe-0_0_0/in'

        params = {
            'agg': '86400',
            'begin': int(time.time() - datetime.timedelta(days=366*10).total_seconds())
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

    def test_float_timestamp_input(self):
        url = '/v1/device/rtr_a/interface/xe-0_0_0/in'

        # pass in floats
        params = { 
            'begin': time.time() - 3600,
            'end': time.time()
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['begin_time'], int(params['begin']))
        self.assertEquals(data['end_time'], int(params['end']))

        # print json.dumps(data, indent=4)

    #
    # The following tests are for the /timeseries rest namespace.
    #

    def test_bad_timeseries_endpoints(self):
        # url = '/v1/timeseries/BaseRate/rtr_d/FastPollHC/ifHCInOctets/fxp0.0/30000'

        # all of these endpoints are incomplete
        url = '/v1/timeseries/'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 400)

        url = '/v1/timeseries/BaseRate/'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 400)

        url = '/v1/timeseries/BaseRate/rtr_a/'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 400)

        # This does not end in a parsable frequency
        url = '/v1/timeseries/BaseRate/rtr_a/FastPollHC/ifHCInOctets/fxp0.0'
        response = self.client.get(url)
        self.assertEquals(response.status_code, 400)

    def test_timeseries_data_detail(self):
        agg = 30000

        url = '/v1/timeseries/BaseRate/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/{0}'.format(agg)

        response = self.client.get(url)
        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(int(data['agg']), agg)
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][1][0], agg)
        self.assertEquals(data['data'][1][1], 20)

        # make sure it works with a trailing slash too
        url = '/v1/timeseries/BaseRate/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/{0}/'.format(agg)

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(int(data['agg']), agg)
        self.assertEquals(data['resource_uri'], url.rstrip("/"))
        self.assertEquals(data['data'][2][0], agg*2)
        self.assertEquals(data['data'][2][1], 40)

    def test_timeseries_data_aggs(self):
        agg = 3600000

        url = '/v1/timeseries/Aggs/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/{0}'.format(agg)

        response = self.client.get(url)
        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(data['agg'], str(agg))
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][2][0], agg*2)
        self.assertEquals(data['data'][2][1], 240)

        params = { 'cf': 'min' }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['cf'], 'min')
        self.assertEquals(data['agg'], str(agg))
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][2][0], agg*2)
        self.assertEquals(data['data'][2][1], 20)

        params['cf'] = 'max'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['cf'], 'max')
        self.assertEquals(data['agg'], str(agg))
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][2][0], agg*2)
        self.assertEquals(data['data'][2][1], 300)

    def test_timeseries_bad_aggregations(self):
        url = '/v1/timeseries/Aggs/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/3600000'

        params = {'cf': 'bad'} # this cf does not exist

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

    def test_timeseries_timerange_limiter(self):
        url = '/v1/timeseries/BaseRate/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/30000'
        params = { 
            'begin': int(time.time() - datetime.timedelta(days=31).total_seconds())
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

        url = '/v1/timeseries/Aggs/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/3600000'

        params = {
            'begin': int(time.time() - datetime.timedelta(days=366).total_seconds())
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

        params = {
            'begin': int(time.time() - datetime.timedelta(days=366*10).total_seconds())
        }

        url = '/v1/timeseries/Aggs/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/86400000'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

        # This is an invalid aggregation/frequency
        url = '/v1/timeseries/BaseRate/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/31000'

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 400)

    def test_timeseries_float_timestamp_input(self):
        url = '/v1/timeseries/BaseRate/rtr_a/FastPollHC/ifHCInOctets/fxp0.0/30000'

        # pass in floats
        params = { 
            'begin': time.time() - 3600,
            'end': time.time()
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEquals(data['begin_time'], int(params['begin']))
        self.assertEquals(data['end_time'], int(params['end']))











