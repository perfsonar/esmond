import calendar
import datetime
import json
import pprint
import requests
import time
import warnings

"""
Library to fetch data from 'simplified' API /v1/snmp/ namespace.

The class ApiConnect is the 'entry point' that the client uses, and 
the ApiFilters class is used to set time/device/etc filters, and is 
passed to the ApiConnect class as an argument.

Example:

    filters = ApiFilters()

    if options.last:
        filters.begin_time = int(time.time() - (options.last*60))

    if options.devices:
        filters.devices = options.devices

    conn = ApiConnect(options.hostname, filters)

After the entry point is set up, it returns device objects, which in 
turn return associated interface objects, endpoint objects and data 
point objects.  

Traversing down through hierarchy of objects:

    for d in conn.get_devices():
        for i in d.get_interfaces():
            for e in i.get_endpoints():
                payload_object = e.get_data()
                    list_of_data_point_objects = payload_object.data
                        for i in list_of_data_point_objects:
                            print i.ts, i.val

Where timestamp values are returned, they are python datetime objects.

NOTE: actually executing that example w/out filtering/limiting the 
devices being polled will grab a lot of data from the API so proceed 
with caution!

The objects that encapsulate the device/interface/etc data that are
returned from the api follow the general pattern where information in 
a given object are accessed by properties, and when acutal 'work' is 
being done (hitting the api), that is done by a method prefixed with
get_ (ex: get_interfaces()).
"""

from esmond.util import max_datetime
MAX_EPOCH = calendar.timegm(max_datetime.utctimetuple())

class NodeInfoWarning(Warning): pass
class DeviceWarning(NodeInfoWarning): pass
class OidsetWarning(NodeInfoWarning): pass
class InterfaceWarning(NodeInfoWarning): pass
class EndpointWarning(NodeInfoWarning): pass
class DataPayloadWarning(NodeInfoWarning): pass
class ApiConnectWarning(Warning): pass

# - Encapsulation classes for nodes (device, interface, etc).

class NodeInfo(object):
    wrn = NodeInfoWarning
    """Base class for encapsulation objects"""
    def __init__(self, data, hostname, port, filters):
        super(NodeInfo, self).__init__()
        self._data = data
        self.hostname = hostname
        self.port = port
        self.filters = filters

        # Default rest parameters for all objects
        if self.filters:
            self._default_filters = self.filters.default_filters

        self.pp = pprint.PrettyPrinter(indent=4)

    def _convert_to_datetime(self, d):
        """API returns both unix timestamps and ISO time so
        normalize to datetime objects transparently"""
        t = None
        
        try:
            i = int(d)
            if i > MAX_EPOCH:
                # bullet proof against out of range datetime errors
                t = max_datetime
            else:
                t = datetime.datetime.utcfromtimestamp(i)
        except ValueError:
            # Not an epoch timestamp
            pass

        if not t:
            # Presume this is ISO time
            t = datetime.datetime.strptime(d, "%Y-%m-%dT%H:%M:%S.%f")

        return t

    # Properties for most subclasses
    @property
    def begin_time(self):
        if self._data.get('begin_time', None):
            return self._convert_to_datetime(self._data.get('begin_time'))
        else:
            return None

    @property
    def end_time(self):
        if self._data.get('end_time', None):
            return self._convert_to_datetime(self._data.get('end_time'))
        else:
            return None

    @property
    def id(self):
        return self._data.get('id', None)

    @property
    def leaf(self):
        return self._data.get('leaf', None)

    @property
    def resource_uri(self):
        return self._data.get('resource_uri', None)

    # Utility properties
    @property
    def dump(self):
        return self.pp.pformat(self._data)

    def http_alert(self, r):
        """
        Issue a subclass specific alert in the case that a call to the REST
        api does not return a 200 status code.
        """
        warnings.warn('Request for {0} got status: {1} - response: {2}'.format(r.url,r.status_code,r.content), self.wrn, stacklevel=2)

    def inspect_request(self, r):
        if self.filters.verbose:
            print '[url: {0}]'.format(r.url)


class Device(NodeInfo):
    wrn = DeviceWarning
    """Class to encapsulate device information"""
    def __init__(self, data, hostname, port, filters):
        super(Device, self).__init__(data, hostname, port, filters)

    # Property attrs unique to devices
    @property
    def active(self):
        return self._data.get('active', None)

    @property
    def name(self):
        return self._data.get('name', None)

    def get_interfaces(self):
        """
        Issue a call to the API to get a list of interfaces (via a 
        generator) associated with the device this object refers to.
        """
        uri = None
        for c in self._data['children']:
            if c['name'] == 'interface':
                uri = c['uri']
                break

        if uri:
            r = requests.get('http://{0}:{1}{2}'.format(self.hostname, self.port, uri), 
                params=dict(self.filters.default_filters, **self.filters.filter_interfaces()))

            self.inspect_request(r)

            if r.status_code == 200 and \
                r.headers['content-type'] == 'application/json':
                data = json.loads(r.text)
                for i in data['children']:
                    yield Interface(i, self.hostname, self.port, self.filters)
            else:
                self.http_alert(r)
                return
                yield

    def get_oidsets(self):

        uri = self._data['resource_uri'] + 'oidset/'

        # Don't need extra query params for this becasue the device
        # object was already filtered.
        r = requests.get('http://{0}:{1}{2}'.format(self.hostname, self.port, uri))

        self.inspect_request(r)

        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            return Oidset(data, self.hostname, self.port, self.filters)
        else:
            self.http_alert(r)
            return Oidset(None, self.hostname, self.port, self.filters)


    def __repr__(self):
        return '<Device/{0}: uri:{1}>'.format(self.name, self.resource_uri)

class Oidset(NodeInfo):
    wrn = OidsetWarning
    """Class to encapsulate device information"""
    def __init__(self, data, hostname, port, filters):
        super(Oidset, self).__init__(data, hostname, port, filters)

        self._oidsets = []
        self._resource_uri = None

        if self._data:
            for d in self._data:
                self._oidsets.append(d['oidset'])
                self._resource_uri = d['resource_uri']

    # Property attrs unique to oidset
    @property
    def oidsets(self):
        return self._oidsets

    def __repr__(self):
        return '<Oidset: {0}: uri:{1}>'.format(self.oidsets, self._resource_uri)

class Interface(NodeInfo):
    wrn = InterfaceWarning
    """Class to encapsulate interface information"""
    def __init__(self, data, hostname, port, filters):
        super(Interface, self).__init__(data, hostname, port, filters)

    # Property attrs unique to interfaces
    @property
    def device(self):
        return self._data.get('device', None)

    @property
    def ifAdminStatus(self):
        return self._data.get('ifAdminStatus', None)

    @property
    def ifAlias(self):
        return self._data.get('ifAlias', None)

    @property
    def ifDescr(self):
        return self._data.get('ifDescr', None)

    @property
    def ifHighSpeed(self):
        return self._data.get('ifHighSpeed', None)

    @property
    def ifIndex(self):
        return self._data.get('ifIndex', None)

    @property
    def ifMtu(self):
        return self._data.get('ifMtu', None)

    @property
    def ifOperStatus(self):
        return self._data.get('ifOperStatus', None)

    @property
    def ifPhysAddress(self):
        return self._data.get('ifPhysAddress', None)

    @property
    def ifSpeed(self):
        return self._data.get('ifSpeed', None)

    @property
    def ifType(self):
        return self._data.get('ifType', None)

    @property
    def ipAddr(self):
        return self._data.get('ipAddr', None)

    @property
    def uri(self):
        return self._data.get('uri', None)

    def get_endpoints(self):
        """
        Generate and return a list of endpoints (via a generator) associated
        with this interface.  Even though this does not 'do work' by issuing
        a call to the API, it is a get_ method just for consistency.
        """
        for i in self._data['children']:
            e = self.filters.filter_endpoints(Endpoint(i, self.hostname, self.port, self.filters))
            if e:
                yield e

    def __repr__(self):
        return '<Interface/{0}: uri:{1}>'.format(self.ifDescr, self.resource_uri)

class Endpoint(NodeInfo):
    wrn = EndpointWarning
    """Class to encapsulate endpoint information"""
    def __init__(self, data, hostname, port, filters):
        super(Endpoint, self).__init__(data, hostname, port, filters)

    @property
    def name(self):
        return self._data.get('name', None)

    @property
    def uri(self):
        return self._data.get('uri', None)

    def get_data(self):
        """
        Retrieve the traffic data and return the json response in 
        a DataPayload object.  If there is something wrong with the 
        response (status/content) then issue a warning and return an 
        empty object.
        """

        r = requests.get('http://{0}:{1}{2}'.format(self.hostname, self.port, self.uri),
            params=dict(self.filters.default_filters, **self.filters.filter_data()))

        self.inspect_request(r)

        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            return DataPayload(data)
        else:
            self.http_alert(r)
            return DataPayload()
        
    def __repr__(self):
        return '<Endpoint/{0}: uri:{1}>'.format(self.name, self.uri)

class DataPayload(NodeInfo):
    wrn = DataPayloadWarning
    """Class to encapsulate data payload"""
    def __init__(self, data={'data':[]}):
        super(DataPayload, self).__init__(data, None, None, None)

    @property
    def agg(self):
        return self._data.get('agg', None)

    @property
    def cf(self):
        return self._data.get('cf', None)

    @property
    def data(self):
        """Return internal data from payload as list of DataPoint."""
        return [DataPoint(x[0],x[1]) for x in self._data.get('data', None)]

    @property
    def dump(self):
        return self.pp.pformat(self.data)

    def __repr__(self):
        return '<DataPayload: len:{0} b:{1} e:{2}>'.format(
            len(self.data), self.begin_time, self.end_time)

class DataPoint(object):
    """Class to encapsulate the returned data points."""
    def __init__(self, ts, val):
        super(DataPoint, self).__init__()
        self.ts = datetime.datetime.utcfromtimestamp(ts)
        self.val = val

    @property
    def ts_epoch(self):
        return calendar.timegm(self.ts.utctimetuple())

    def __repr__(self):
        return '<DataPoint: ts:{0} val:{1}>'.format(self.ts, self.val)
        
        
# - Query entry point and filtering.

class ApiFilters(object):
    """Class to hold filtering/query options.  This will be used by 
    ApiConnect and also passed to all the encapsulation objects."""
    def __init__(self):
        super(ApiFilters, self).__init__()

        self._begin_time = datetime.datetime.utcfromtimestamp(int(time.time() - 3600))
        self._end_time = datetime.datetime.utcfromtimestamp(int(time.time()))

        self._default_filters = {
            'begin': self.ts_epoch('begin_time'),
            'end': self.ts_epoch('end_time'),
            'limit': 0,
        }

        self.verbose = False

        # Attrs for specific object filtering.
        self._device = None
        self._interface = None

    def ts_epoch(self, time_prop):
        """Convert named property back to epoch.  Generally just for 
        sending cgi params to the api."""
        return int(calendar.timegm(getattr(self, time_prop).utctimetuple()))

    def _convert_ts(self, ts):
        """
        Massage the timestamp to datetime if need be.
        """
        if isinstance(ts, type(self._begin_time)):
            return ts
        else:
            return datetime.datetime.utcfromtimestamp(int(ts))

    def begin_time():
        doc = "The begin_time property."
        def fget(self):
            return self._begin_time
        def fset(self, value):
            self._begin_time = self._convert_ts(value)
        def fdel(self):
            pass
        return locals()
    begin_time = property(**begin_time())

    def end_time():
        doc = "The end_time property."
        def fget(self):
            return self._end_time
        def fset(self, value):
            self._end_time = self._convert_ts(value)
        def fdel(self):
            pass
        return locals()
    end_time = property(**end_time())

    def device():
        doc = "The device property."
        def fget(self):
            return self._device
        def fset(self, value):
            self._device = str(value)
        def fdel(self):
            del self._device
        return locals()
    device = property(**device())

    def interface():
        doc = "The interface property."
        def fget(self):
            return self._interface
        def fset(self, value):
            self._interface = str(value)
        def fdel(self):
            del self._interface
        return locals()
    interface = property(**interface())

    def default_filters():
        doc = "The default_filters property."
        def fget(self):
            return self._default_filters
        def fset(self, value):
            self._default_filters = value
        def fdel(self):
            del self._default_filters
        return locals()
    default_filters = property(**default_filters())

    def filter_devices(self):
        """Build queryset filters for device queries."""

        filters = {}

        if self.device:
            filters['name__contains'] = self.device

        return filters

    def filter_interfaces(self):
        """Build queryset filters for interface queries."""
        # Nothing implemented yet
        filters = {}

        if self.interface:
            filters['ifDescr__contains'] = self.interface

        return filters

    def filter_endpoints(self, endpoint):
        """
        Filter endpoints.

        Since this is not a call to the api, we are not generating queryset
        filters.  Rather we would need to filter by looking at the payload 
        and exclude results we don't want.

        Return the object if it meets criteria, otherwise, return None.
        """
        # Nothing implemented yet.
        return endpoint

    def filter_data(self):
        """Build queryset filters for data retrieval."""
        # Nothing implemented yet
        filters = {}

        return filters

class ApiConnect(object):
    wrn = ApiConnectWarning
    """Core class to pull data from the rest api."""
    def __init__(self, hostname='localhost', port=80, filters=ApiFilters()):
        super(ApiConnect, self).__init__()
        self.hostname = hostname
        self.filters = filters
        self.port = port

    def get_devices(self):
        r = requests.get('http://{0}:{1}/v1/device/'.format(self.hostname, self.port), 
            params=dict(self.filters.default_filters, **self.filters.filter_devices()))

        self.inspect_request(r)
        
        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            for i in data:
                yield Device(i, self.hostname, self.port, self.filters)
        else:
            self.http_alert(r)
            return
            yield

    def inspect_request(self, r):
        if self.filters.verbose:
            print '[url: {0}]'.format(r.url)
        
    def http_alert(self, r):
        warnings.warn('Request for {0} got status: {1}'.format(r.url,r.status_code), self.wrn, stacklevel=2)
# ----
