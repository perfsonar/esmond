import json
import time
import datetime

import mock 

from django.core.urlresolvers import reverse
from tastypie.test import ResourceTestCase

from esmond.api.models import *
from esmond.api.api import OIDSET_INTERFACE_ENDPOINTS

def datetime_to_timestamp(dt):
    return time.mktime(dt.timetuple())

from django.test import TestCase

class DeviceAPITestsBase(ResourceTestCase):
    fixtures = ["oidsets.json"]
    def setUp(self):
        super(DeviceAPITestsBase, self).setUp()

        self.rtr_a, _ = Device.objects.get_or_create(
                name="rtr_a",
                community="public")

        DeviceOIDSetMap(device=self.rtr_a,
                oid_set=OIDSet.objects.get(name="FastPollHC")).save()
        DeviceOIDSetMap(device=self.rtr_a,
                oid_set=OIDSet.objects.get(name="Errors")).save()

        rtr_b_begin = datetime.datetime(2013,6,1)
        rtr_b_end = datetime.datetime(2013,6,15)
        self.rtr_b, _ = Device.objects.get_or_create(
                name="rtr_b",
                community="public",
                begin_time = rtr_b_begin,
                end_time = rtr_b_end)

        self.rtr_c, _ = Device.objects.get_or_create(
                name="rtr_c",
                community="public")

        DeviceOIDSetMap(device=self.rtr_c,
                oid_set=OIDSet.objects.get(name="InfFastPollHC")).save()

        self.rtr_z_post_data = {
            "name": "rtr_z",
            "community": "private",
        }

        IfRef.objects.get_or_create(
                device=self.rtr_a,
                ifIndex=1,
                ifDescr="xe-0/0/0",
                ifAlias="test interface",
                ipAddr="10.0.0.1",
                ifSpeed=0,
                ifHighSpeed=10000,
                ifMtu=9000,
                ifOperStatus=1,
                ifAdminStatus=1,
                ifPhysAddress="00:00:00:00:00:00")

        IfRef.objects.get_or_create(
                device=self.rtr_b,
                ifIndex=1,
                ifDescr="xe-1/0/0",
                ifAlias="test interface",
                ipAddr="10.0.0.2",
                ifSpeed=0,
                ifHighSpeed=10000,
                ifMtu=9000,
                ifOperStatus=1,
                ifAdminStatus=1,
                ifPhysAddress="00:00:00:00:00:00",
                begin_time=rtr_b_begin,
                end_time=rtr_b_end)

        IfRef.objects.get_or_create(
                device=self.rtr_b,
                ifIndex=1,
                ifDescr="xe-2/0/0",
                ifAlias="test interface",
                ipAddr="10.0.0.2",
                ifSpeed=0,
                ifHighSpeed=10000,
                ifMtu=9000,
                ifOperStatus=1,
                ifAdminStatus=1,
                ifPhysAddress="00:00:00:00:00:00",
                begin_time=rtr_b_begin,
                end_time=rtr_b_begin + datetime.timedelta(days=7))

        IfRef.objects.get_or_create(
                device=self.rtr_c,
                ifIndex=1,
                ifDescr="xe-3/0/0",
                ifAlias="test interface",
                ipAddr="10.0.0.3",
                ifSpeed=0,
                ifHighSpeed=10000,
                ifMtu=9000,
                ifOperStatus=1,
                ifAdminStatus=1,
                ifPhysAddress="00:00:00:00:00:00")


class DeviceAPITests(DeviceAPITestsBase):
    def test_get_device_list(self):
        url = '/v1/device/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        # by default only currently active devices are returned
        data = json.loads(response.content)
        self.assertEquals(len(data), 1)

        # get both devices, with date filters
        begin = datetime_to_timestamp(self.rtr_b.begin_time)
        response = self.client.get(url, dict(begin=begin))
        data = json.loads(response.content)
        self.assertEquals(len(data), 2)

        # exclude rtr_b by date

        begin = datetime_to_timestamp(self.rtr_a.begin_time)
        response = self.client.get(url, dict(begin=begin))
        data = json.loads(response.content)
        self.assertEquals(len(data), 1)
        self.assertEquals(data[0]['name'], 'rtr_a')

        # exclude all routers with very old end date
        response = self.client.get(url, dict(end=0))
        data = json.loads(response.content)
        self.assertEquals(len(data), 0)

        # test for equal (gte/lte)
        begin = datetime_to_timestamp(self.rtr_b.begin_time)
        response = self.client.get(url, dict(begin=0, end=begin))
        data = json.loads(response.content)
        self.assertEquals(len(data), 1)
        self.assertEquals(data[0]['name'], 'rtr_b')

        end = datetime_to_timestamp(self.rtr_b.end_time)
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
                    data=self.rtr_z_post_data))

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

        begin = datetime_to_timestamp(self.rtr_b.begin_time)
        end = datetime_to_timestamp(self.rtr_b.end_time)

        # rtr_b has two interfaces over it's existence
        response = self.client.get(url, dict(begin=begin, end=end))
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEquals(len(data['children']), 2)

        # rtr_b has only one interface during the last part of it's existence
        begin = datetime_to_timestamp(self.rtr_b.begin_time +
                datetime.timedelta(days=8))
        response = self.client.get(url, dict(begin=begin, end=end))
        self.assertEquals(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEquals(len(data['children']), 1)
        self.assertEquals(data['children'][0]['ifDescr'], 'xe-1/0/0')

    def test_get_device_interface_detail(self):
        url = '/v1/device/rtr_a/interface/xe-0_0_0/'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEquals(data['ifDescr'], 'xe-0/0/0')

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

        children = {}
        for child in data['children']:
            children[child['name']] = child
            for field in ['leaf','name','uri']:
                self.assertIn(field, child)

        for oidset in Device.objects.get(name='rtr_a').oidsets.all():
            for child_name in OIDSET_INTERFACE_ENDPOINTS[oidset.name].keys():
                self.assertIn(child_name , children)
                child = children[child_name]
                self.assertEqual(child['uri'], url + child_name)
                self.assertTrue(child['leaf'])

class MockCASSANDRA_DB(object):
    def __init__(self, config):
        pass

    def query_baserate_timerange(self, path=None, freq=None, ts_min=None, ts_max=None):
        return [[0,10], [30,20], [60, 40]]

    def query_aggregation_timerange(self, path=None, freq=None, ts_min=None, ts_max=None, cf=None):
        if cf == 'average':
            return [[0, 60], [freq, 120], [freq*2, 240]]
        elif cf == 'min':
            return [[0, 0], [freq, 10], [freq*2, 20]]
        elif cf == 'max':
            return [[0, 75], [freq, 150], [freq*2, 300]]
        else:
            pass

class DeviceAPIDataTests(DeviceAPITestsBase):
    def setUp(self):
        super(DeviceAPIDataTests, self).setUp()
        # mock patches names where used/imported, not where defined
        mock.patch("esmond.api.api.CASSANDRA_DB", MockCASSANDRA_DB).start()

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

        url = '/v1/device/rtr_c/interface/xe-3_0_0/out'

        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

        data = json.loads(response.content)

        # print json.dumps(data, indent=4)

        self.assertEquals(data['cf'], 'average')
        self.assertEquals(int(data['agg']), 30)
        self.assertEquals(data['resource_uri'], url)
        self.assertEquals(data['data'][2][0], 60)
        self.assertEquals(data['data'][2][1], 40)

    def test_bad_aggregations(self):
        url = '/v1/device/rtr_a/interface/xe-0_0_0/in'

        params = {'agg': '3601'} # this agg does not exist

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 404)

        params = {'agg': '3600', 'cf': 'bad'} # this cf does not exist

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 404)


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
            'begin': time.time() - datetime.timedelta(days=31).total_seconds()
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 404)

        url = '/v1/device/rtr_a/interface/xe-0_0_0/out'

        params = {
            'agg': '3600',
            'begin': time.time() - datetime.timedelta(days=366).total_seconds()
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 404)

        url = '/v1/device/rtr_a/interface/xe-0_0_0/in'

        params = {
            'agg': '86400',
            'begin': time.time() - datetime.timedelta(days=366*10).total_seconds()
        }

        response = self.client.get(url, params)
        self.assertEquals(response.status_code, 404)

        





