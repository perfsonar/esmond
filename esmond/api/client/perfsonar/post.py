import json
import pprint
import requests
import warnings

from esmond.api.client.util import add_apikey_header, AlertMixin
from esmond.api.client.perfsonar.query import Metadata
from esmond.api.perfsonar.types import EVENT_TYPE_CONFIG, INVERSE_SUMMARY_TYPES

class PostException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class MetadataPostException(PostException): pass


class MetadataPostWarning(Warning): pass


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
        add_apikey_header(self.username, self.api_key, self.headers)
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

        self._payload['event-types'].append({ 'event-type' : et })

    def add_summary_type(self, et, st, windows=[]):
        self._check_event_type(et)
        self._check_summary_type(st)

        # XXX(mmg) - just skip an existing summary or do something else?
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

        print r.content

        if not r.status_code == 201:
            # Change this to an exception?
            self.warn('POST error: status_code: {0}, message: {1}'.format(r.status_code, r.content))

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


