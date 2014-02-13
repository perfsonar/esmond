import calendar
import datetime
import json
import pprint
import requests
import time
import warnings

from esmond.api.client.util import add_apikey_header

MAX_DATETIME = datetime.datetime.max - datetime.timedelta(2)
MAX_EPOCH = calendar.timegm(MAX_DATETIME.utctimetuple())

class NodeInfoWarning(Warning): pass
class MetadataWarning(NodeInfoWarning): pass
class EventTypeWarning(NodeInfoWarning): pass
class DataPayloadWarning(NodeInfoWarning): pass
class DataPointWarning(NodeInfoWarning): pass
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

        self._pp = pprint.PrettyPrinter(indent=4)

    def _convert_to_datetime(self, d):
        if int(d) > MAX_EPOCH:
            return MAX_DATETIME
        else:
            return datetime.datetime.utcfromtimestamp(i)

    @property
    def dump(self):
        return self._pp.pformat('something TBA')

    def http_alert(self, r):
        """
        Issue a subclass specific alert in the case that a call to the REST
        api does not return a 200 status code.
        """
        warnings.warn('Request for {0} got status: {1} - response: {2}'.format(r.url,r.status_code,r.content), self.wrn, stacklevel=2)

    def warn(self, m):
        warnings.warn(m, self.wrn, stacklevel=2)

class Metadata(NodeInfo):
    wrn = MetadataWarning
    """Class to encapsulate a metadata object"""
    def __init__(self, data, api_url, filters):
        super(Metadata, self).__init__(data, api_url, filters)

    def __repr__(self):
        return '<Metadata/{0}: uri:{1}>'.format('mdkey', 'resource url')

class EventType(NodeInfo):
    wrn = EventTypeWarning
    """Class to encapsulate event-types"""
    def __init__(self, data, api_url, filters):
        super(EventType, self).__init__(data, api_url, filters)

    def __repr__(self):
        return '<EventType/{0}: uri:{1}>'.format('e-t', 'base uri')

class DataPayload(NodeInfo):
    wrn = DataPayloadWarning
    """Class to encapsulate returned data payload"""
    def __init__(self, data={'data': []}): # XXX(mmg) most likely change data arg default
        super(EventType, self).__init__(data, None, None)

    def __repr__(self):
        return '<DataPayload: len:{0} b:{1} e:{2}>'.format(
            len(self.data), 'self.begin_time', 'self.end_time')

class DataPoint(object):
    wrn = DataPointWarning
    """Class to encapsulate the data points"""
    def __init__(self, ts, val): # XXX(mmg) change args when see data
        self.ts = datetime.datetime.utcfromtimestamp(ts)
        self.val = val

    def __repr__(self):
        return '<DataPoint: ts:{0} val:{1}>'.format(self.ts, self.val)

class ApiFilters(object):
    wrn = ApiFiltersWarning
    """Class to hold filtering/query options."""
    def __init__(self):
        super(ApiFilters, self).__init__()

        # Other stuff
        self.auth_username = ''
        self.auth_apikey = ''

    def warn(self, m):
        warnings.warn(m, self.wrn, stacklevel=2)

class ApiConnect(object):
    wrn = ApiConnectWarning
    """Core class to pull data from the rest api"""
    def __init__(self, api_url, filters=ApiFilters(), username='', api_key=''):
        super(ApiConnect, self).__init__()
        self.api_url = api_url.rstrip("/")
        self.filters = filters
        self.filters.auth_username = username
        self.filters.auth_apikey = api_key

    def http_alert(self, r):
        warnings.warn('Request for {0} got status: {1} - response: {2}'.format(r.url,r.status_code, r.content), self.wrn, stacklevel=2)

    def warn(self, m):
        warnings.warn(m, self.wrn, stacklevel=2)


