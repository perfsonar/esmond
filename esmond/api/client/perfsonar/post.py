import json
import numbers
import pprint
import requests
import warnings

from esmond.api.client.util import add_apikey_header, AlertMixin
from esmond.api.client.perfsonar.query import Metadata, ApiFilters
from esmond.api.perfsonar.types import EVENT_TYPE_CONFIG, INVERSE_SUMMARY_TYPES

class PostException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class MetadataPostException(PostException): pass
class EventTypePostException(PostException): pass
class EventTypeBulkPostException(PostException): pass

class MetadataPostWarning(Warning): pass
class EventTypePostWarning(Warning): pass
class EventTypeBulkPostWarning(Warning): pass


class PostBase(AlertMixin, object):
    """docstring for PostBase"""
    _schema_root = 'perfsonar/archive'
    def __init__(self, api_url, username, api_key):
        super(PostBase, self).__init__()
        self.api_url = api_url
        if self.api_url: self.api_url = api_url.rstrip('/')

        self.username = username
        self.api_key = api_key
        self.headers = { 'content-type': 'application/json' }
        if self.username and self.api_key:
            add_apikey_header(self.username, self.api_key, self.headers)
        else:
            self.warn('username and api_key not set')
        # sublass override
        self._payload = {}

        try:
            getattr(self, 'wrn')
        except AttributeError:
            raise PostException('Do not instantiate base class, use appropriate subclass')

    def _validate(self):
        raise NotImplementedError('Must be implemented in subclass')

    def _check_event_type(self, et):
        if et not in EVENT_TYPE_CONFIG.keys():
            raise MetadataPostException('{0} is not a valid event type'.format(et))

    def _check_summary_type(self, st):
        if st not in INVERSE_SUMMARY_TYPES.keys():
            raise MetadataPostException('{0} is not a valid summary type'.format(st))

    def json_payload(self, pp=False):
        self._validate()
        if pp:
            return json.dumps(self._payload, indent=4)
        else:
            return json.dumps(self._payload)
        
class MetadataPost(PostBase):
    wrn = MetadataPostWarning
    """docstring for MetadataPost"""
    def __init__(self, api_url, username='', api_key='',
            subject_type=None, source=None, destination=None,
            tool_name=None, measurement_agent=None, input_source=None,
            input_destination=None, time_duration=None, 
            ip_transport_protocol=None):
        super(MetadataPost, self).__init__(api_url, username, api_key)
        # required
        self.subject_type = subject_type
        self.source = source
        self.destination = destination
        self.tool_name = tool_name
        self.measurement_agent = measurement_agent
        self.input_source = input_source
        self.input_destination = input_destination
        # optional - if not defined, don't send at all
        self.time_duration = time_duration
        self.ip_transport_protocol = ip_transport_protocol

        self._required_args = (
            'subject_type',
            'source',
            'destination',
            'tool_name',
            'measurement_agent',
            'input_source',
            'input_destination'
        )

        self._optional_args = (
            'time_duration', 
            'ip_transport_protocol'
        )

        self._payload = {
            'subject-type': self.subject_type,
            'source': self.source,
            'destination': self.destination,
            'tool-name': self.tool_name,
            'measurement-agent': self.measurement_agent,
            'input-source': self.input_source,
            'input-destination': self.input_destination,
            'time-duration': self.time_duration,
            'ip-transport-protocol': self.ip_transport_protocol,
            'event-types': []
        }

    def add_event_type(self, et):
        self._check_event_type(et)

        for i in self._payload['event-types']:
            if i.get('event-type', None) == et:
                self.warn('Event type {0} already exists - skipping'.format(et))

        self._payload['event-types'].append({ 'event-type' : et })

    def add_summary_type(self, et, st, windows=[]):
        self._check_event_type(et)
        self._check_summary_type(st)

        if not windows:
            self.warn('No summary windows were defined - skipping')
            return

        for i in windows:
            try:
                int(i)
            except ValueError:
                raise MetadataPostException('Invalid summary window int: {0}'.format(i))

        for i in self._payload['event-types']:
            if i.get('summaries', None) and \
                i.get('event-type', None) == et:
                self.warn('A summary for {0} already exists - skipping'.format(et))
                return

        suminfo = {
            'event-type': et,
            'summaries' : [ 
                { 'summary-type': st, 'summary-window': x } for x in windows
            ]
        }

        self._payload['event-types'].append(suminfo)

    def post_metadata(self):
        url = '{0}/{1}/'.format(self.api_url, self._schema_root)

        r = requests.post(url, data=self.json_payload(), headers=self.headers)

        if not r.status_code == 201:
            # Change this to an exception?
            self.warn('POST error: status_code: {0}, message: {1}'.format(r.status_code, r.content))
            return None

        return Metadata(json.loads(r.content), self.api_url, ApiFilters())

    def _validate(self):
        redash = lambda s: s.replace('_', '-')

        # make sure required args are present
        for arg in self._required_args:
            if not getattr(self, arg):
                raise MetadataPostException('Reqired arg {0} not set'.format(arg))

        # remove any optional args from payload
        for arg in self._optional_args:
            if not getattr(self, arg) and \
                self._payload.has_key(redash(arg)):
                del self._payload[redash(arg)]


class EventTypePost(PostBase):
    wrn = EventTypePostWarning
    """docstring for EventTypePost"""
    def __init__(self, api_url, username='', api_key='', metadata_key=None,
            event_type=None):
        super(EventTypePost, self).__init__(api_url, username, api_key)

        self.metadata_key = metadata_key
        self.event_type = event_type

        if not self.metadata_key or not self.event_type:
            raise EventTypePostException('Must set metadata_key and event_type args')
        self._check_event_type(self.event_type)

        # Slightly different than payload in meta data class.
        # List will hold data points, but whole thing will not
        # be sent to server.
        self._payload = []

    def add_data_point(self, ts, val):
        if not isinstance(ts, int):
            raise EventTypePostException('ts arg must be an integer')
        if not isinstance(val, numbers.Number) and \
            not isinstance(val, dict):
            raise EventTypePostException('val arg must be number or dict for histograms')
        self._payload.append( { 'ts': ts, 'val': val } )

    def post_data(self):
        self._validate()

        url = '{0}/{1}/{2}/{3}/base'.format(self.api_url, self._schema_root,
            self.metadata_key, self.event_type)

        results = []

        for dp in self._payload:
            r = requests.post(url, data=json.dumps(dp), headers=self.headers)

            if not r.status_code == 201:
                self.warn('POST error: status_code: {0}, message: {1}'.format(r.status_code, r.content))

    def _validate(self):
        for i in self._payload:
            if isinstance(i['val'], dict):
                for k,v in i['val'].items():
                    try:
                        int(k), int(v)
                    except ValueError:
                        raise EventTypePostException('Histogram dict items must be integer values - got {0} {1}'.format(k,v))

class EventTypeBulkPost(PostBase):
    wrn = EventTypePostWarning
    """docstring for EventTypePost"""
    def __init__(self, api_url, username='', api_key='', metadata_key=None):
        super(EventTypeBulkPost, self).__init__(api_url, username, api_key)

        self.metadata_key = metadata_key

        if not self.metadata_key:
            raise EventTypeBulkPostException('Must set metadata_key')

        self._payload = { 'data': [] }

    def _get_ts_payload_entry(self, ts):
        entry = False

        for i in self._payload['data']:
            if i['ts'] == ts: entry = i

        if not entry:
            self._payload['data'].append( {'ts': ts, 'val': [] } )
            return self._get_ts_payload_entry(ts)

        return entry

    def add_data_point(self, event_type, ts, val):
        self._check_event_type(event_type)
        if not isinstance(ts, int):
            raise EventTypeBulkPostException('ts arg must be an integer')
        if not isinstance(val, numbers.Number) and \
            not isinstance(val, dict):
            raise EventTypeBulkPostException('val arg must be number or dict for histograms')

        data_entry = self._get_ts_payload_entry(ts)
        data_entry['val'].append({'event-type': event_type, 'val': val})

    def post_data(self):
        self._validate()

        url = '{0}/{1}/{2}/'.format(self.api_url, self._schema_root,
            self.metadata_key)
        
        r = requests.post(url, data=self.json_payload(), headers=self.headers)

        if not r.status_code == 201:
            # Change this to an exception?
            self.warn('POST error: status_code: {0}, message: {1}'.format(r.status_code, r.content))

    def _validate(self):
        for i in self._payload['data']:
            # Validation currently being done on incoming values
            # in add_data_point - leaving this here for the future.
            pass



        

