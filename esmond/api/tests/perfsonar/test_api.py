import json
import os

# This MUST be here in any testing modules that use cassandra!
os.environ['ESMOND_UNIT_TESTS'] = 'True'

from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now
from tastypie.exceptions import BadRequest
from tastypie.models import ApiKey
from tastypie.test import ResourceTestCase
from esmond.api.models import PSEventTypes
from esmond.api.perfsonar.types import *
from esmond.cassandra import CASSANDRA_DB
from esmond.config import get_config, get_config_path
from esmond.api.perfsonar.validators import *
import time

class PSAPIBaseTest(ResourceTestCase):
    fixtures = ['perfsonar_api_metadata.json']
    
    def setUp(self):
        super(PSAPIBaseTest, self).setUp()
                                
        #create user credentials
        self.noperms_user = User(username="no_perms", is_staff=True)
        self.noperms_user.save()
        self.noperms_apikey = ApiKey(user=self.noperms_user)
        self.noperms_apikey.key = self.noperms_apikey.generate_key()
        self.noperms_apikey.save()
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
        self.admin_apikey = ApiKey(user=self.admin_user)
        self.admin_apikey.key = self.admin_apikey.generate_key()
        self.admin_apikey.save()
        
    def create_noperms_credentials(self):
        return self.create_apikey(self.noperms_user.username, self.noperms_apikey.key)
        
    def create_admin_credentials(self):
        return self.create_apikey(self.admin_user.username, self.admin_apikey.key)
    
    def assertExpectedResponse(self, expected, url, get_params={}):
        response = self.client.get(url, get_params)
        self.assertHttpOK(response)
        data = json.loads(response.content)
        self.assertEquals(expected, data)
        
class PSArchiveResourceTest(PSAPIBaseTest):
    """
    Tests to validate the JSON API properly stores and retrieves metadata
    in the relational database.
    """    
    
    def setUp(self):
        super(PSArchiveResourceTest, self).setUp()
        
        #Set DNS Names used in tests
        self.v4_ip = '198.129.254.30'
        self.v4_name = 'lbl-pt1.es.net'
        self.v6_ip = '2001:400:201:1150::3'
        self.v6_name = 'lbl-pt1-v6.es.net'
        self.v4v6_ipv4 = '198.129.254.187'
        self.v4v6_ipv6 = '2001:400:201:11ff::87'
        self.v4v6_name = 'ps-lat.es.net'
        self.dest = 'bost-pt1.es.net'
        
        #metadata detail test object
        self.md_detail = {
           "metadata-key":"e99bbc44b7b041c7ad9e51dc6a053b8c",
           "time-duration":"20",
           "subject-type":"point-to-point",
           "ip-tos":"32",
           "measurement-agent":"198.129.254.30",
           "input-destination":"lbl-pt1.es.net",
           "destination":"198.129.254.30",
           "uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c",
           "event-types":[
              {
                 "time-updated":1398785370,
                 "summaries":[

                 ],
                 "base-uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/streams-throughput/base",
                 "event-type":"streams-throughput"
              },
              {
                 "time-updated":1398785370,
                 "summaries":[

                 ],
                 "base-uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/streams-throughput-subintervals/base",
                 "event-type":"streams-throughput-subintervals"
              },
              {
                 "time-updated":1398785369,
                 "summaries":[

                 ],
                 "base-uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/packet-retransmits/base",
                 "event-type":"packet-retransmits"
              },
              {
                 "time-updated":1398785370,
                 "summaries":[

                 ],
                 "base-uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/streams-retransmits/base",
                 "event-type":"streams-retransmits"
              },
              {
                 "time-updated":1398785369,
                 "summaries":[
                    {
                       "summary-type":"average",
                       "summary-window":"3600",
                       "time-updated":1398785369,
                       "uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/throughput/averages/3600"
                    }
                 ],
                 "base-uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/throughput/base",
                 "event-type":"throughput"
              },
              {
                 "time-updated":None,
                 "summaries":[

                 ],
                 "base-uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/failures/base",
                 "event-type":"failures"
              },
              {
                 "time-updated":1398785370,
                 "summaries":[

                 ],
                 "base-uri":"/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/throughput-subintervals/base",
                 "event-type":"throughput-subintervals"
              }
           ],
           "source":"198.124.238.66",
           "ip-transport-protocol":"tcp",
           "input-source":"bost-pt1.es.net",
           "bw-parallel-streams":"2",
           "tool-name":"bwctl/iperf3"
        }
        
        #event type detail test object
        self.et_detail = [
           {
              'time-updated':1398785369,
              'summaries':[
                 {
                    'summary-type':'average',
                    'summary-window':'3600',
                    'time-updated':1398785369,
                    'uri':'/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/throughput/averages/3600'
                 }
              ],
              'base-uri':'/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/throughput/base',
              'event-type':'throughput'
           }
        ]
        
        #summary detail test object
        self.summ_detail = [
           {
              'summary-type':'average',
              'summary-window':'3600',
              'time-updated':1398785369,
              'uri':'/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/throughput/averages/3600'
           }
        ]
        
        #data to post
        self.post_data = {
           "source":"10.1.1.1",
           "destination":"10.1.1.2",
           "subject-type":"point-to-point",
           "tool-name":"bwctl/iperf3",
           "input-destination":"10.1.1.1",
           "input-source":"10.1.1.2",
           "measurement-agent":"10.1.1.1",
           "time-interval": 7200,
           "time-duration": 20,
           "event-types":[
              {
                 "event-type":"packet-retransmits",
              },
              {
                 "event-type":"throughput",
                 "summaries":[
                    {
                       "summary-type":"average",
                       "summary-window":"86400",
                    }
                 ],
              }
           ],
        }
        
        #set last updated time to current time so we can test time-range in API
        PSEventTypes.objects.filter(pk=220).update(time_updated=now().replace(microsecond=0))
        
    def assertMetadataCount(self, count, url, get_params={}):
        response = self.client.get(url, get_params)
        self.assertHttpOK(response)
        data = json.loads(response.content)
        self.assertEquals(len(data), count)
        
    def test_get_metadata_list(self):
        url = '/perfsonar/archive/'
            
        #test getting full list
        self.assertMetadataCount(16, url)
        
        #test query using event type
        self.assertMetadataCount(4, url, {EVENT_TYPE_FILTER: 'packet-trace'})
        
        #test query using event type and summary type. Test this because uses custom Q filters
        self.assertMetadataCount(5, url, {EVENT_TYPE_FILTER: 'throughput', SUMMARY_TYPE_FILTER: 'average' })
        
        #test query using event type, summary type and summary window. Test this because uses custom Q filters
        self.assertMetadataCount(4, url, {EVENT_TYPE_FILTER: 'throughput', SUMMARY_TYPE_FILTER: 'average', SUMMARY_WINDOW_FILTER: 86400 })
        
        #test query using IPv4 address
        response = self.client.get(url, {'source': self.v4_ip})
        self.assertHttpOK(response)
        ipv4_data = json.loads(response.content)
        self.assertEquals(len(ipv4_data), 4)
        
        #test query using DNS name with only A record
        self.assertExpectedResponse(ipv4_data, url, {'source': self.v4_name})
        
        #test query using DNS name with only A record but telling it to return all v4 and v6 results
        self.assertExpectedResponse(ipv4_data, url, {'source': self.v4_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_V4_V6})
        
        #test query using DNS name that only does v4 lookups on name with only A record
        self.assertExpectedResponse(ipv4_data, url, {'source': self.v4_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_ONLY_V4})
        
        #test query using DNS name that only does v6 lookups on name with only A record (should fail)
        response = self.client.get(url, {'source': self.v4_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_ONLY_V6})
        self.assertHttpBadRequest(response)
        
        #test query using DNS name that prefers v4 on name with only A record
        self.assertExpectedResponse(ipv4_data, url, {'source': self.v4_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_PREFER_V4})
        
        #test query using DNS name that prefers v6 on name with only A record
        self.assertExpectedResponse(ipv4_data, url, {'source': self.v4_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_PREFER_V6})
 
        #test query using IPv6 address
        response = self.client.get(url, {'source': self.v6_ip})
        self.assertHttpOK(response)
        ipv6_data = json.loads(response.content)
        self.assertEquals(len(ipv6_data), 2)
        
        #test query using DNS name with only AAAA record
        self.assertExpectedResponse(ipv6_data, url, {'source': self.v6_name})
        
        #test query using DNS name on name with only AAAA record but telling it to return all v4 and v6 results
        self.assertExpectedResponse(ipv6_data, url, {'source': self.v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_V4_V6})
         
        #test query using DNS name that only does v4 lookups on name with only AAAA record (should fail)
        response = self.client.get(url, {'source': self.v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_ONLY_V4})
        self.assertHttpBadRequest(response)
        
        #test query using DNS name that only does v6 lookups on name with only AAAA record 
        self.assertExpectedResponse(ipv6_data, url, {'source': self.v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_ONLY_V6})
         
        #test query using DNS name that prefers v4 on name with only AAAA record
        self.assertExpectedResponse(ipv6_data, url, {'source': self.v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_PREFER_V4})
         
        #test query using DNS name that prefers v6 on name with only AAAA record
        self.assertExpectedResponse(ipv6_data, url, {'source': self.v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_PREFER_V6})
        
        #test query using DNS name on name with both A and AAAA records
        response = self.client.get(url, {'source': self.v4v6_ipv4})
        self.assertHttpOK(response)
        ipv4_data = json.loads(response.content)
        self.assertEquals(len(ipv4_data), 1)
        response = self.client.get(url, {'source': self.v4v6_ipv6})
        self.assertHttpOK(response)
        ipv6_data = json.loads(response.content)
        self.assertEquals(len(ipv6_data), 1)
               
        #test query using DNS name that only does v4 lookups on name both A and AAAA records
        self.assertExpectedResponse(ipv4_data, url, {'source': self.v4v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_ONLY_V4})
        
        #test query using DNS name that only does v6 lookups on name both A and AAAA records
        self.assertExpectedResponse(ipv6_data, url, {'source': self.v4v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_ONLY_V6})
        
        #test query using DNS name that prefers v4 on name with both A and AAAA records
        self.assertExpectedResponse(ipv4_data, url, {'source': self.v4v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_PREFER_V4})
        
        #test query using DNS name that prefers v6 on name with both A and AAAA records
        self.assertExpectedResponse(ipv6_data, url, {'source': self.v4v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_PREFER_V6})
        
        #test query using DNS name on name with both A and AAAA records
        ipv4_data[0]['metadata-count-total'] = 2
        del ipv6_data[0]['metadata-count-total']
        self.assertExpectedResponse(ipv4_data + ipv6_data, url, {'source': self.v4v6_name})
        
        #test query using DNS name on name with both A and AAAA records and telling it to return all v4 and v6 results
        self.assertExpectedResponse(ipv4_data + ipv6_data, url, {'source': self.v4v6_name, DNS_MATCH_RULE_FILTER: DNS_MATCH_V4_V6})


        #test query using time-range
        self.assertMetadataCount(1, url, {TIME_RANGE_FILTER: 600})
        
        #test query using time-start
        self.assertMetadataCount(4, url, {TIME_START_FILTER: 1398798900})
        
        #test query using time-end
        self.assertMetadataCount(12, url, {TIME_END_FILTER: 1398798900})
        
        #test query using time
        self.assertMetadataCount(1, url, {TIME_FILTER: 1398798965})
        
        #test query using time-start and time-range
        self.assertMetadataCount(1, url, {TIME_START_FILTER: 1398798900, TIME_RANGE_FILTER: 60})
        
        #test query using time-end and time-range
        self.assertMetadataCount(1, url, {TIME_END_FILTER: 1398798900, TIME_RANGE_FILTER: 60})
        
        #test query using time-start and time-end
        self.assertMetadataCount(2, url, {TIME_START_FILTER: 1398798840, TIME_END_FILTER: 1398798960})
        
        #test query using source, dest, and event-type. Added because common query.
        self.assertMetadataCount(1, url, {'source': self.v4_ip, 'destination': self.dest,  'event-type': 'throughput'})
        
        #test limit keyword
        self.assertMetadataCount(1, url, {LIMIT_FILTER: 1})
        self.assertMetadataCount(2, url, {LIMIT_FILTER: 2})
        
        #test offset keyword
        self.assertMetadataCount(15, url, {OFFSET_FILTER: 1})
        self.assertMetadataCount(5, url, {OFFSET_FILTER: 0, LIMIT_FILTER: 5})
        self.assertMetadataCount(5, url, {OFFSET_FILTER: 5, LIMIT_FILTER: 5})
        self.assertMetadataCount(6, url, {OFFSET_FILTER: 10, LIMIT_FILTER: 10})
        
    def test_get_metadata_detail(self):
        url = '/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/'
        response = self.client.get(url)
        self.assertHttpOK(response)
        data = json.loads(response.content)
        self.assertEquals(self.md_detail, data)
    
    def test_get_event_type_detail(self):
        url = '/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/throughput/'
        response = self.client.get(url)
        self.assertHttpOK(response)
        self.assertEquals(self.et_detail, json.loads(response.content))

    
    def test_get_summary_detail(self):
        url = '/perfsonar/archive/e99bbc44b7b041c7ad9e51dc6a053b8c/throughput/averages/'
        response = self.client.get(url)
        self.assertHttpOK(response)
        self.assertEquals(self.summ_detail, json.loads(response.content))
    
    
    def test_post_metadata_list(self):
        url = '/perfsonar/archive/'
        
        #test with no credentials
        self.assertHttpUnauthorized(self.api_client.post(url, format='json', data=self.post_data))
        
        #test with credentials with no permissions
        self.assertHttpUnauthorized(self.api_client.post(url, format='json', data=self.post_data, authentication=self.create_noperms_credentials()))
        
        #test with credentials with permissions
        response = self.api_client.post(url, format='json', data=self.post_data, authentication=self.create_admin_credentials())
        self.assertHttpCreated(response)
        data = json.loads(response.content)
        #verify the server generated he uri and metadata keys
        self.assertIsNotNone(data['uri'])
        self.assertIsNotNone(data['metadata-key'])
        #verify the fields registered match the fields returned
        for post_field in self.post_data:
            if post_field != 'event-types':
                self.assertEquals(str(self.post_data[post_field]), str(data[post_field]))
        #verify the event types
        self.assertIsNotNone(data['event-types'])
        self.assertEquals(len(data['event-types']), len(self.post_data['event-types']))
        
        #test creating existing object returns same object
        existing_uri = data['uri']
        existing_mdkey = data['metadata-key']
        response = self.api_client.post(url, format='json', data=self.post_data, authentication=self.create_admin_credentials())
        self.assertHttpCreated(response)
        new_data = json.loads(response.content)
        self.assertEquals(new_data['uri'], existing_uri )
        self.assertEquals(new_data['metadata-key'], existing_mdkey )
        
class PSArchiveResourceDataTest(PSAPIBaseTest):
    '''
    Test querying data from API. Since we want to test that the server calculates
    summaries correctly, we create the data in each test and then query that everything
    got generated correctly
    '''
    
    def setUp(self):
        super(PSArchiveResourceDataTest, self).setUp()
        self.int_data = [5978580000, 5413040000, 7964590000, 6946810000]
        self.float_data = [0.001, 0.003, 0.002, 0.003, 0.001]
        self.json_data = map(lambda x: {'error': x }, ["error1", "error2", "error3", "error4"])
        self.perc_post_data = map(lambda x: {'numerator': x[0], 'denominator': x[1] }, [(4, 100), (50, 200), (1, 10), (15, 40)])
        self.perc_expected_data = map(lambda x: x['numerator']/float(x['denominator']), self.perc_post_data)
        self.subint_data = [
            [
                 {
                    "duration":"1.000080",
                    "start":"0.000000",
                    "val":"1331580000"
                 },
                 {
                    "duration":"1.000000",
                    "start":"1.000080",
                    "val":"1069540000"
                 },
                 {
                    "duration":"0.999994",
                    "start":"2.000090",
                    "val":"4886390000"
                 },
                 {
                    "duration":"1.000010",
                    "start":"3.000080",
                    "val":"9615340000"
                 },
                 {
                    "duration":"1.000130",
                    "start":"4.000090",
                    "val":"9540780000"
                 },
                 {
                    "duration":"0.999856",
                    "start":"5.000220",
                    "val":"7257190000"
                 },
            ],
            [
                 {
                    "duration":"1.000090",
                    "start":"0.000000",
                    "val":"1331570000"
                 },
                 {
                    "duration":"1.000290",
                    "start":"1.000090",
                    "val":"1163590000"
                 },
                 {
                    "duration":"0.999730",
                    "start":"2.000370",
                    "val":"5202340000"
                 },
                 {
                    "duration":"0.999990",
                    "start":"3.000100",
                    "val":"9741370000"
                 },
                 {
                    "duration":"1.000580",
                    "start":"4.000090",
                    "val":"9599430000"
                 },
                 {
                    "duration":"0.999767",
                    "start":"5.000670",
                    "val":"9754030000"
                 }
            ],
            [
                 {
                    "duration":"1.000090",
                    "start":"0.000000",
                    "val":"1331570000"
                 },
                 {
                    "duration":"1.000290",
                    "start":"1.000090",
                    "val":"1163590000"
                 },
                 {
                    "duration":"0.999730",
                    "start":"2.000370",
                    "val":"7849890000"
                 },
                 {
                    "duration":"0.999990",
                    "start":"3.000100",
                    "val":"7330050000"
                 },
                 {
                    "duration":"1.000580",
                    "start":"4.000090",
                    "val":"9599430000"
                 },
                 {
                    "duration":"0.999767",
                    "start":"5.000670",
                    "val":"9754030000"
                 }
           ]
        ]
        
        self.hist_data = [
            {
                "41.00":98,
                "41.10":2
            },
            {
                "41.00":98,
                "41.10":2
            },
            {
                "41.10":96,
                "41.20":3,
                "50.0": 1
            }
        ]

    def assertSinglePostSuccess(self, url, ts, val, test_equals=True):
        post_data = {'ts': ts, 'val': val}
        response = self.api_client.post(url, format='json', data=post_data, authentication=self.create_admin_credentials())
        self.assertHttpCreated(response)
        response = self.client.get(url, {'time': ts})
        self.assertHttpOK(response)
        response_data = json.loads(response.content)
        self.assertEquals(len(response_data), 1)
        if(test_equals):
            self.assertEquals(post_data, response_data[0])
    
    def assertSinglePostFailure(self, url, ts, val):
        post_data = {'ts': ts, 'val': val}
        response = self.api_client.post(url, format='json', data=post_data, authentication=self.create_admin_credentials())
        self.assertHttpBadRequest(response)
    
    def assertSinglePostConflict(self, url, ts, val):
        post_data = {'ts': ts, 'val': val}
        response = self.api_client.post(url, format='json', data=post_data, authentication=self.create_admin_credentials())
        self.assertHttpConflict(response)
        
    def assertBulkTSPostSuccess(self, bulk_url, base_url, start, interval, data, event_type):
        end=0
        bulk_data = { 'data': []}
        for i in range(1, len(data)):
            end = start + i*interval
            bulk_data['data'].append({'ts': end, 'val':  [{'event-type': event_type, 'val': data[i]}]})
        response = self.api_client.post(bulk_url, format='json', data=bulk_data, authentication=self.create_admin_credentials())
        self.assertHttpCreated(response)
        response = self.client.get(base_url, {'time-start': start, 'time-end': end})
        self.assertHttpOK(response)
        response_data = json.loads(response.content)
        self.assertEquals(len(response_data), len(data))
    
    def assertAuthFailure(self, url, ts, val, credentials):
        post_data = {'ts': ts, 'val': val}
        response = self.api_client.post(url, format='json', data=post_data, authentication=credentials)
        self.assertHttpUnauthorized(response)
        
    def test_a_config_cassandra(self):
        '''
        Clear database before starting a test. Takes too long to do before an individual test
        '''
        config = get_config(get_config_path())
        config.db_clear_on_testing = True
        db = CASSANDRA_DB(config)
        
    def test_integer_data(self): 
        base_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base/'
        start = 1398965989
        interval = 7200
        
        #test invalid integer
        self.assertSinglePostFailure(base_url, start, 'bad input')
        
        #single post
        self.assertSinglePostSuccess(base_url, start, self.int_data[0])
        
        #duplicate last request which should give a conflict
        self.assertSinglePostConflict(base_url, start, self.int_data[0])
        
        #bulk post
        bulk_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/'
        self.assertBulkTSPostSuccess(bulk_url, base_url, start, interval, self.int_data, 'throughput')
        
        #query average summary
        expected = [{"ts": 1398902400, "val": 6575755000.0}]
        avg_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/averages/86400/'
        self.assertExpectedResponse(expected, avg_url)
        
        #query aggregation summary
        expected = [{"ts": 1398902400, "val": 26303020000}]
        agg_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/aggregations/86400/'
        self.assertExpectedResponse(expected, agg_url)
    
    def test_float_data(self):
        base_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/time-error-estimates/base/'
        start = 1398965989
        interval = 60
        
        #test invalid float
        self.assertSinglePostFailure(base_url, start, 'bad input')
        
        #single post
        self.assertSinglePostSuccess(base_url, start, self.float_data[0])
        
        #duplicate last request which should give a conflict
        self.assertSinglePostConflict(base_url, start, self.float_data[0])
        
        #bulk post
        bulk_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/'
        self.assertBulkTSPostSuccess(bulk_url, base_url, start, interval, self.float_data, 'time-error-estimates')
        
        #query average summary
        expected = [{"ts": 1398902400, "val": .002}]
        avg_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/time-error-estimates/averages/86400/'
        self.assertExpectedResponse(expected, avg_url)
        
        #query aggregation summary
        expected = [{"ts": 1398902400, "val": .01}]
        agg_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/time-error-estimates/aggregations/86400/'
        self.assertExpectedResponse(expected, agg_url)
    
    def test_json_data(self):
        base_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/failures/base/'
        start = 1398965989
        interval = 7200
        
        #single post
        self.assertSinglePostSuccess(base_url, start, self.json_data[0])
        
        #duplicate last request which should give a conflict
        self.assertSinglePostConflict(base_url, start, self.json_data[0])
        
        #bulk post
        bulk_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/'
        self.assertBulkTSPostSuccess(bulk_url, base_url, start, interval, self.json_data, 'failures')
    
    def test_percentage_data(self):
        base_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/packet-loss-rate/base/'
        start = 1398965989
        interval = 60
        
        #test invalid percentage
        self.assertSinglePostFailure(base_url, start, 'bad input')
        self.assertSinglePostFailure(base_url, start, {})
        self.assertSinglePostFailure(base_url, start, {'numerator': 10})
        self.assertSinglePostFailure(base_url, start, {'denominator': 10})
        self.assertSinglePostFailure(base_url, start, {'numerator': 'bad', 'denominator': 'bad'})
        self.assertSinglePostFailure(base_url, start, {'numerator': 10, 'denominator': 'bad'})
        self.assertSinglePostFailure(base_url, start, {'numerator': 10, 'denominator': 0})
        self.assertSinglePostFailure(base_url, start, {'numerator': -1, 'denominator': 10})
        self.assertSinglePostFailure(base_url, start, {'numerator': 'bad', 'denominator': 10})
        
        #single post
        self.assertSinglePostSuccess(base_url, start, self.perc_post_data[0], False)
        
        #duplicate last request which should give a conflict
        self.assertSinglePostConflict(base_url, start, self.perc_post_data[0])
        
        #bulk post
        bulk_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/'
        self.assertBulkTSPostSuccess(bulk_url, base_url, start, interval, self.perc_post_data, 'packet-loss-rate')
        expected_data = []
        for i in range(0, len(self.perc_expected_data)):
            ts = start + i*interval
            expected_data.append({'ts': ts, 'val': self.perc_expected_data[i]})
        self.assertExpectedResponse(expected_data, base_url)
        
    def test_subinterval_data(self):
        base_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput-subintervals/base/'
        start = 1398965989
        interval = 7200
        
        #test invalid float
        self.assertSinglePostFailure(base_url, start, 'bad input')
        self.assertSinglePostFailure(base_url, start, {})
        self.assertSinglePostFailure(base_url, start, [{}])
        self.assertSinglePostFailure(base_url, start, [{'duration': 1, 'val': 1}])
        self.assertSinglePostFailure(base_url, start, [{'start': 1, 'val': 1}])
        self.assertSinglePostFailure(base_url, start, [{'duration': 1, 'start': 1}])
        self.assertSinglePostFailure(base_url, start, [{'duration': 'bad', 'start': 1, 'val': 1}])
        self.assertSinglePostFailure(base_url, start, [{'duration': 1, 'start': 'bad', 'val': 1}])
        
        #single post
        self.assertSinglePostSuccess(base_url, start, self.subint_data[0])
        
        #duplicate last request which should give a conflict
        self.assertSinglePostConflict(base_url, start, self.subint_data[0])
        
        #bulk post
        bulk_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/'
        self.assertBulkTSPostSuccess(bulk_url, base_url, start, interval, self.subint_data, 'throughput-subintervals')
    
    def test_post_histogram_data(self):
        base_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/histogram-rtt/base/'
        start = 1398965989
        interval = 600
        
        #test invalid histogram
        self.assertSinglePostFailure(base_url, start, {'41.0': 'bad', '42.2': 20})
        
        #single post
        self.assertSinglePostSuccess(base_url, start, self.hist_data[0])
        
        #duplicate last post - should fail
        self.assertSinglePostConflict(base_url, start, self.hist_data[0])
        
        #bulk post
        bulk_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/'
        self.assertBulkTSPostSuccess(bulk_url, base_url, start, interval, self.hist_data, 'histogram-rtt')
        
        #query aggregation summary
        expected = [{u'ts': 1398902400, u'val': {u'41.10': 98, u'41.00': 98, u'50.0': 1, u'41.20': 3}}]
        agg_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/histogram-rtt/aggregations/86400/'
        self.assertExpectedResponse(expected, agg_url)
        
        #query stats summary
        expected =[{u'ts': 1398902400, u'val': {u'standard-deviation': 0.6333174559413313, u'median': 41.1, u'maximum': 50.0, u'minimum': 41.0, u'mode': [41.1, 41.0], u'percentile-75': 41.1, u'percentile-25': 41.0, u'percentile-95': 41.1, u'variance': 0.40109100000000003, u'mean': 41.097}}]
        stat_url = '/perfsonar/archive/67a3c298de0b4237abee56b879e03587/histogram-rtt/statistics/86400/'
        self.assertExpectedResponse(expected, stat_url)
        
        #test non-numeric key(should work) and re-check stats
        self.assertSinglePostSuccess(base_url, start+1000, {'test': 100})
        self.assertExpectedResponse([{u'ts': 1398902400, u'val': {}}], stat_url)
        
    def test_authentication_failures(self):
        base_url = '/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base/'
        self.assertAuthFailure(base_url, 1398965989, self.int_data[0], None)
        self.assertAuthFailure(base_url, 1398965989, self.int_data[0], self.create_noperms_credentials())
    
    def test_validator_edge_cases(self):
        '''
        A few cases are hard to test via the API but should be handled in case something
        changes going forward.
        '''
        #test invalid json
        self.assertRaises(BadRequest, JSONValidator().validate, ({'value': '{invalidjson'}))
        self.assertRaises(BadRequest, HistogramValidator().validate, ({'value': '{invalidjson'}))
        
        #test percentile calculations when only one element
        p = Percentile(40, 1)
        p.findvalue(1, 100)
        self.assertEquals(p.value, 100)
        
        #test where count equals sample size but > 1
        p = Percentile(95, 9)
        p.findvalue(9, 101)
        self.assertEquals(p.value, 101)
        
        #test percentile that as sample spread across multiple values
        p = Percentile(95, 10)
        p.findvalue(4, 100)
        p.findvalue(6, 101)
        self.assertEquals(p.value, 100.45)