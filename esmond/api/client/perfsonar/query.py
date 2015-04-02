import calendar
import datetime
import json
import pprint
import requests
import time
import warnings

from ..util import add_apikey_header

MAX_DATETIME = datetime.datetime.max - datetime.timedelta(2)
MAX_EPOCH = calendar.timegm(MAX_DATETIME.utctimetuple())

class NodeInfoWarning(Warning): pass
class MetadataWarning(NodeInfoWarning): pass
class EventTypeWarning(NodeInfoWarning): pass
class SummaryWarning(NodeInfoWarning): pass
class DataPayloadWarning(NodeInfoWarning): pass
class DataPointWarning(NodeInfoWarning): pass
class DataHistogramWarning(NodeInfoWarning): pass
class ApiFiltersWarning(Warning): pass
class ApiConnectWarning(Warning): pass

class NodeInfo(object):
    wrn = NodeInfoWarning
    """Base class for encapsulation objects"""
    def __init__(self, data, api_url, filters):
        super(NodeInfo, self).__init__()
        self._data = data
        self.api_url = api_url
        if self.api_url: self.api_url = api_url.rstrip('/')
        self.filters = filters

        self.request_headers = {}

        self._pp = pprint.PrettyPrinter(indent=4)

    def _convert_to_datetime(self, d):
        if int(d) > MAX_EPOCH:
            return MAX_DATETIME
        else:
            return datetime.datetime.utcfromtimestamp(int(d))

    @property
    def dump(self):
        """Dump the returned/wrapped json as a pretty printed string.
        Just for debugging."""
        return self._pp.pformat(self._data)

    def http_alert(self, r):
        """
        Issue a subclass specific alert in the case that a call to the REST
        api does not return a 200 status code.
        """
        warnings.warn('Request for {0} got status: {1} - response: {2}'.format(r.url,r.status_code,r.content), self.wrn, stacklevel=2)

    def warn(self, m):
        warnings.warn(m, self.wrn, stacklevel=2)

    def inspect_request(self, r):
        if self.filters.verbose:
            print '[url: {0}]'.format(r.url)

class Metadata(NodeInfo):
    wrn = MetadataWarning
    """Class to encapsulate a metadata object.  It exposes the 
    information returned in the metadata json payload from the api 
    as a series of read-only properties.

    Will also return the associated/wrapped event-types as EventType
    objects."""
    def __init__(self, data, api_url, filters):
        super(Metadata, self).__init__(data, api_url, filters)

    @property
    def destination(self):
        return self._data.get('destination', None)

    @property
    def event_types(self):
        """Returns a list of the event-types associated with 
        the returned metadata as a list of strings."""
        e_t = []
        for e in self._data.get('event-types', []):
            e_t.append(e['event-type'])
        return e_t

    @property
    def input_destination(self):
        return self._data.get('input-destination', None)

    @property
    def input_source(self):
        return self._data.get('input-source', None)

    @property
    def ip_packet_interval(self):
        return self._data.get('ip-packet-interval', None)

    @property
    def ip_transport_protocol(self):
        return self._data.get('ip-transport-protocol', None)

    @property
    def measurement_agent(self):
        return self._data.get('measurement-agent', None)

    @property
    def metadata_count_total(self):
        return self._data.get('metadata-count-total', None)

    @property
    def metadata_key(self):
        return self._data.get('metadata-key', None)

    @property
    def sample_bucket_width(self):
        return self._data.get('sample-bucket-width', None)

    @property
    def source(self):
        return self._data.get('source', None)

    @property
    def subject_type(self):
        return self._data.get('subject-type', None)

    @property
    def time_duration(self):
        return self._data.get('time-duration', None)

    @property
    def time_interval(self):
        return self._data.get('time-interval', None)

    @property
    def time_interval_randomization(self):
        return self._data.get('time-interval-randomization', None)

    @property
    def tool_name(self):
        return self._data.get('tool-name', None)

    @property
    def uri(self):
        return self._data.get('uri', None)
    
    @property
    def get_freeform_key_value(self, key):
        return self._data.get(key, None)

    def get_all_event_types(self):
        """Generator returning all the event-types from the metadata
        json payload wrapped in EventType objects."""
        for et in self._data.get('event-types', []):
            yield EventType(et, self.api_url, self.filters)

    def get_event_type(self, event_type):
        """Returns a single named event-type (as specified by the arg
        event_type) from the metadata json payload wrapped in an  
        EventType object."""
        for et in self._data.get('event-types', []):
            if et['event-type'] == event_type:
                return EventType(et, self.api_url, self.filters)
        return None

    def __repr__(self):
        return '<Metadata/{0}: uri:{1}>'.format(self.metadata_key, self.uri)

class EventType(NodeInfo):
    wrn = EventTypeWarning
    """Class to encapsulate a single event-type from the json
    payload returned from a metadata query/Metadata object.
    Exposes the json data as a series of read-only properties.

    Is also used to fetch the data associated with the event-type
    from the API.

    Will also return related summaries as a Summary object."""
    def __init__(self, data, api_url, filters):
        super(EventType, self).__init__(data, api_url, filters)

    @property
    def base_uri(self):
        return self._data.get('base-uri', None)

    @property
    def event_type(self):
        return self._data.get('event-type', None)

    @property
    def data_type(self):
        """Returns whether this data type is a histogram. Decision
        based on event prefix which always indicates histogram type"""
        
        if self.event_type is not None and self.event_type.startswith("histogram-"):
            return "histogram"
        else:
            return "unspecified"

    @property
    def summaries(self):
        """Returns a list of strings of the names of the summaries
        associated with this event-type."""
        s_t = []
        for s in self._data.get('summaries', []):
            s_t.append((s['summary-type'],s['summary-window']))
        return s_t

    def get_all_summaries(self):
        """Generator returning all the summaries from the event-type
        json payload wrapped in Summary objects."""
        for s in self._data.get('summaries', []):
            yield Summary(s, self.api_url, self.filters, self.data_type)

    def get_summary(self, s_type, s_window):
        """Returns a single named summary (as specified by the arg
        pair s_type/s_window) from the event-type json payload wrapped 
        in a Summary object."""
        for s in self._data.get('summaries', []):
            if s['summary-type'] == s_type and \
                s['summary-window'] == str(s_window):
                return Summary(s, self.api_url, self.filters, self.data_type)
        return None

    def get_data(self):
        """Void method to pull the data associated with this event-type
        from the API.  Returns a DataPayload object to calling code."""
        r = requests.get('{0}{1}'.format(self.api_url, self.base_uri),
            params=self.filters.time_filters,
            headers=self.request_headers)

        self.inspect_request(r)

        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            return DataPayload(data, self.data_type)
        else:
            self.http_alert(r)
            return DataPayload([], self.data_type)


    def __repr__(self):
        return '<EventType/{0}: uri:{1}>'.format(self.event_type, self.base_uri)

class Summary(NodeInfo):
    wrn = SummaryWarning
    """Class to encapsulate summary information.  Exposes the summary 
    json payload in the event-type as read-only properties.

    Is also used to fetch the actual summary data from the API."""
    def __init__(self, data, api_url, filters, data_type):
        super(Summary, self).__init__(data, api_url, filters)
        self._data_type = data_type

    @property
    def data_type(self):
        return self._data_type

    @property
    def summary_type(self):
        return self._data.get('summary-type', None)

    @property
    def summary_window(self):
        return self._data.get('summary-window', None)

    @property
    def uri(self):
        return self._data.get('uri', None)

    def get_data(self):
        """Void method to pull the data associated with this event-type
        from the API.  Returns a DataPayload object to calling code."""
        r = requests.get('{0}{1}'.format(self.api_url, self.uri),
            params=self.filters.time_filters,
            headers=self.request_headers)

        self.inspect_request(r)

        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            return DataPayload(data, self.data_type)
        else:
            self.http_alert(r)
            return DataPayload([], self.data_type)

    def __repr__(self):
        return '<Summary/{0}: window:{1}>'.format(self.summary_type, self.summary_window)


class DataPayload(NodeInfo):
    wrn = DataPayloadWarning
    """Class to encapsulate returned data payload.  Holds the json
    payload of timeseries/data points internally and returns the 
    discrete data as a list of DataPoint or DataHistogram objects
    as is appropriate."""
    def __init__(self, data=[], data_type=None):
        super(DataPayload, self).__init__(data, None, None)
        self._data_type = data_type

    @property
    def data_type(self):
        return self._data_type

    @property
    def data(self):
        if self.data_type == 'histogram':
            return [DataHistogram(x) for x in self._data]
        else:
            return [DataPoint(x) for x in self._data]

    @property
    def dump(self):
        return self._pp.pformat(self._data)

    def __repr__(self):
        return '<DataPayload: len:{0} type:{1}>'.format(len(self._data), self.data_type)

class DataPoint(NodeInfo):
    __slots__ = ['ts', 'val']
    wrn = DataPointWarning
    """Class to encapsulate the data points.  Represents a single
    ts/value pair where the value is a simple numeric type."""
    def __init__(self, data={}):
        super(DataPoint, self).__init__(data, None, None)
        self.ts = self._convert_to_datetime(data.get('ts', None))
        self.val = data.get('val', None)

    @property
    def ts_epoch(self):
        return calendar.timegm(self.ts.utctimetuple())

    def __repr__(self):
        return '<DataPoint: ts:{0} val:{1}>'.format(self.ts, self.val)

class DataHistogram(NodeInfo):
    __slots__ = ['ts', 'val']
    wrn = DataHistogramWarning
    """Class to encapsulate the data histograms  Represents a single
    ts/value pair where the value is histogram written as a dict."""
    def __init__(self, data={}):
        super(DataHistogram, self).__init__(data, None, None)
        self.ts = self._convert_to_datetime(data.get('ts', None))
        self.val = data.get('val', {})

    @property
    def ts_epoch(self):
        return calendar.timegm(self.ts.utctimetuple())

    def __repr__(self):
        return '<DataHistogram: ts:{0} len:{1}>'.format(self.ts, len(self.val.keys()))

class ApiFilters(object):
    wrn = ApiFiltersWarning
    """
    Class to hold filtering/query options.

    This is instantiated and the read/write properties that correspond 
    to metadata information and time ranges can be set by the user.  
    The class will then be passed to the ApiConnect class constructor 
    and the values that have been set will be used in the metadata
    query sent to the API.

    In the case where a metadata property has a dash in it (ie: 
    input-destination), the property will be named with an underscore
    (ie: input_destination) instead.

    See the perfsonar_client.rst doc for more usage information.
    """
    def __init__(self):
        super(ApiFilters, self).__init__()
        self.verbose = False

        self._metadata_filters = {}
        self._time_filters = {}

        # Other stuff
        self.auth_username = ''
        self.auth_apikey = ''

    # Metadata level search filters

    @property
    def metadata_filters(self):
        return self._metadata_filters

    def destination():
        doc = "The destination property."
        def fget(self):
            return self._metadata_filters.get('destination', None)
        def fset(self, value):
            self._metadata_filters['destination'] = value
        def fdel(self):
            del self._metadata_filters['destination']
        return locals()
    destination = property(**destination())

    def input_destination():
        doc = "The input_destination property."
        def fget(self):
            return self._metadata_filters.get('input-destination', None)
        def fset(self, value):
            self._metadata_filters['input-destination'] = value
        def fdel(self):
            del self._metadata_filters['input-destination']
        return locals()
    input_destination = property(**input_destination())

    def input_source():
        doc = "The input_source property."
        def fget(self):
            return self._metadata_filters.get('input-source', None)
        def fset(self, value):
            self._metadata_filters['input-source'] = value
        def fdel(self):
            del self._metadata_filters['input-source']
        return locals()
    input_source = property(**input_source())

    def measurement_agent():
        doc = "The measurement_agent property."
        def fget(self):
            return self._metadata_filters.get('measurement-agent', None)
        def fset(self, value):
            self._metadata_filters['measurement-agent'] = value
        def fdel(self):
            del self._metadata_filters['measurement-agent']
        return locals()
    measurement_agent = property(**measurement_agent())

    def source():
        doc = "The source property."
        def fget(self):
            return self._metadata_filters.get('source', None)
        def fset(self, value):
            self._metadata_filters['source'] = value
        def fdel(self):
            del self._metadata_filters['source']
        return locals()
    source = property(**source())

    def tool_name():
        doc = "The tool_name property."
        def fget(self):
            return self._metadata_filters.get('tool-name', None)
        def fset(self, value):
            self._metadata_filters['tool-name'] = value
        def fdel(self):
            del self._metadata_filters['tool-name']
        return locals()
    tool_name = property(**tool_name())

    # Additional metadata search criteria
    # event-type, summary-type, summary-window and subject-type

    def event_type():
        doc = "The event_type property."
        def fget(self):
            return self._metadata_filters.get('event-type', None)
        def fset(self, value):
            self._metadata_filters['event-type'] = value
        def fdel(self):
            del self._metadata_filters['event-type']
        return locals()
    event_type = property(**event_type())

    def subject_type():
        doc = "The subject_type property."
        def fget(self):
            return self._metadata_filters.get('subject-type', None)
        def fset(self, value):
            self._metadata_filters['subject-type'] = value
        def fdel(self):
            del self._metadata_filters['subject-type']
        return locals()
    subject_type = property(**subject_type())

    def summary_type():
        doc = "The summary_type property."
        def fget(self):
            return self._metadata_filters.get('summary-type', None)
        def fset(self, value):
            self._metadata_filters['summary-type'] = value
        def fdel(self):
            del self._metadata_filters['summary-type']
        return locals()
    summary_type = property(**summary_type())

    def summary_window():
        doc = "The summary_window property."
        def fget(self):
            return self._metadata_filters.get('summary-window', None)
        def fset(self, value):
            self._metadata_filters['summary-window'] = value
        def fdel(self):
            del self._metadata_filters['summary-window']
        return locals()
    summary_window = property(**summary_window())

    # Time range search filters

    def _check_time(self, ts):
        try:
            t_s = int(float(ts))
            return t_s
        except ValueError:
            self.warn('The timestamp value {0} is not a valid integer'.format(ts))

    @property
    def time_filters(self):
        return self._time_filters

    def time():
        doc = "The time property."
        def fget(self):
            return self._time_filters.get('time', None)
        def fset(self, value):
            self._time_filters['time'] = self._check_time(value)
        def fdel(self):
            del self._time_filters['time']
        return locals()
    time = property(**time())

    def time_start():
        doc = "The time_start property."
        def fget(self):
            return self._time_filters.get('time-start', None)
        def fset(self, value):
            self._time_filters['time-start'] = self._check_time(value)
        def fdel(self):
            del self._time_filters['time-start']
        return locals()
    time_start = property(**time_start())

    def time_end():
        doc = "The time_end property."
        def fget(self):
            return self._time_filters.get('time-end', None)
        def fset(self, value):
            self._time_filters['time-end'] = self._check_time(value)
        def fdel(self):
            del self._time_filters['time-end']
        return locals()
    time_end = property(**time_end())

    def time_range():
        doc = "The time_range property."
        def fget(self):
            return self._time_filters.get('time-range', None)
        def fset(self, value):
            self._time_filters['time-range'] = self._check_time(value)
        def fdel(self):
            del self._time_filters['time-range']
        return locals()
    time_range = property(**time_range())

    def warn(self, m):
        warnings.warn(m, self.wrn, stacklevel=2)

class ApiConnect(object):
    wrn = ApiConnectWarning
    """
    Core class to pull data from the rest api.

    This is the "top level" class a client program will use to 
    query the perfsonar API.  The args api_url, username and api_key 
    all have their typical usage.  The ApiFilters object will have
    the relevant query criteria assigned to it, and the get_metadata
    method will return the metadata that meet the search criteria 
    as Metadata objects.

    See the perfsonar_client.rst doc for more usage information.
    """
    def __init__(self, api_url, filters=ApiFilters(), username='', api_key='',
            script_alias='esmond'):
        super(ApiConnect, self).__init__()
        self.api_url = api_url.rstrip("/")
        self.filters = filters
        self.filters.auth_username = username
        self.filters.auth_apikey = api_key
        self.script_alias = script_alias

        if self.script_alias: 
            self.script_alias = script_alias.rstrip('/')
            self.script_alias = script_alias.lstrip('/')

        self.request_headers = {}

    def get_metadata(self):
        if self.script_alias:
            archive_url = '{0}/{1}/perfsonar/archive/'.format(self.api_url, self.script_alias)
        else:
            archive_url = '{0}/perfsonar/archive/'.format(self.api_url)

        r = requests.get(archive_url,
            params=dict(self.filters.metadata_filters, **self.filters.time_filters),
            headers = self.request_headers)

        self.inspect_request(r)

        data = list()

        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            
            if data:
                m_total = Metadata(data[0], self.api_url, self.filters).metadata_count_total
            else:
                m_total = 0

            # Check to see if we are geting paginated metadata, tastypie 
            # has a limit to how many results it will return even if 
            # ?limit=0
            if len(data) < m_total:
                # looks like we got paginated content.
                if self.filters.verbose: print 'pagination - metadata_count_total: {0} got: {1}\n'.format(m_total, len(data))
                initial_offset = len(data) # should be the tastypie internal limit of 1000
                offset = initial_offset

                while offset < m_total:
                    if self.filters.verbose:
                        print 'current total results: {0}'.format(len(data))
                        print 'issuing request with offset: {0}'.format(offset)

                    r = requests.get(archive_url,
                        params=dict(self.filters.metadata_filters, offset=offset, **self.filters.time_filters),
                        headers = self.request_headers)
                    self.inspect_request(r)

                    if r.status_code != 200:
                        print 'error fetching paginated content'
                        self.http_alert(r)
                        return
                        yield

                    tmp = json.loads(r.text)

                    if self.filters.verbose: print 'got {0} results\n'.format(len(tmp))

                    data.extend(tmp)
                    offset += initial_offset

            if self.filters.verbose: print 'final result count: {0}\n'.format(len(data))

            for i in data:
                yield Metadata(i, self.api_url, self.filters)
        else:
            self.http_alert(r)
            return
            yield

    def inspect_request(self, r):
        if self.filters.verbose:
            print '[url: {0}]'.format(r.url)

    def inspect_payload(self, p):
        if self.filters.verbose > 1:
            print '[POST payload: {0}]'.format(json.dumps(p, indent=4))

    def http_alert(self, r):
        warnings.warn('Request for {0} got status: {1} - response: {2}'.format(r.url,r.status_code, r.content), self.wrn, stacklevel=2)

    def warn(self, m):
        warnings.warn(m, self.wrn, stacklevel=2)


