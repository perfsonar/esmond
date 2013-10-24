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

    conn = ApiConnect(options.api_url, filters)

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
class InterfaceWarning(NodeInfoWarning): pass
class EndpointWarning(NodeInfoWarning): pass
class DataPayloadWarning(NodeInfoWarning): pass
class BulkDataPayloadWarning(NodeInfoWarning): pass
class ApiFiltersWarning(Warning): pass
class ApiConnectWarning(Warning): pass

# - Encapsulation classes for nodes (device, interface, etc).

class NodeInfo(object):
    wrn = NodeInfoWarning
    """Base class for encapsulation objects"""
    def __init__(self, data, api_url, filters):
        super(NodeInfo, self).__init__()
        self._data = data
        self.api_url = api_url
        if self.api_url:
            self.api_url = api_url.rstrip("/")
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

    def warn(self, m):
        warnings.warn(m, self.wrn, stacklevel=2)

    def inspect_request(self, r):
        if self.filters.verbose:
            print '[url: {0}]'.format(r.url)


class Device(NodeInfo):
    wrn = DeviceWarning
    """Class to encapsulate device information"""
    def __init__(self, data, api_url, filters):
        super(Device, self).__init__(data, api_url, filters)

    # Property attrs unique to devices
    @property
    def active(self):
        return self._data.get('active', None)

    @property
    def name(self):
        return self._data.get('name', None)

    @property
    def oidsets(self):
        # Return a copy of the internal list so we don't have unintended
        # changes to the internal payload by reference.
        return self._data.get('oidsets', None)[:]

    def get_interfaces(self, **filters):
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
            r = requests.get('{0}{1}'.format(self.api_url, uri),
                params=self.filters.compose_filters(filters))

            self.inspect_request(r)

            if r.status_code == 200 and \
                r.headers['content-type'] == 'application/json':
                data = json.loads(r.text)
                for i in data['children']:
                    yield Interface(i, self.api_url, self.filters)
            else:
                self.http_alert(r)
                return
                yield

    def set_oidsets(self, oidsets):
        if not oidsets or not isinstance(oidsets, list):
            self.warn('oidsets arg must be a non-empty list')
            return

        r = requests.get('{0}/v1/oidset/'.format(self.api_url))
        if r.status_code != 200:
            self.warn('Could not get a list of valid oidsets from {0}/v1/oidset/ - aborting'.format(self.api_url) )
            return
        valid_oidsets = json.loads(r.content)

        for o in oidsets:
            if o not in valid_oidsets:
                self.warn('{0} is not a valid oidset - aborting oidset update.')

        self._data['oidsets'] = oidsets

        headers = {'content-type': 'application/json'}

        p = requests.put('{0}{1}'.format(self.api_url, self.resource_uri), 
            data=json.dumps(self._data), headers=headers)

        if p.status_code != 204:
           self.http_alert(r)



    def __repr__(self):
        return '<Device/{0}: uri:{1}>'.format(self.name, self.resource_uri)

class Interface(NodeInfo):
    wrn = InterfaceWarning
    """Class to encapsulate interface information"""
    def __init__(self, data, api_url, filters):
        super(Interface, self).__init__(data, api_url, filters)

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
            yield Endpoint(i, self.api_url, self.filters)

    def __repr__(self):
        return '<Interface/{0}: uri:{1}>'.format(self.ifDescr, self.resource_uri)

class Endpoint(NodeInfo):
    wrn = EndpointWarning
    """Class to encapsulate endpoint information"""
    def __init__(self, data, api_url, filters):
        super(Endpoint, self).__init__(data, api_url, filters)

    @property
    def name(self):
        return self._data.get('name', None)

    @property
    def uri(self):
        return self._data.get('uri', None)

    def get_data(self, **filters):
        """
        Retrieve the traffic data and return the json response in 
        a DataPayload object.  If there is something wrong with the 
        response (status/content) then issue a warning and return an 
        empty object.
        """

        r = requests.get('{0}{1}'.format(self.api_url, self.uri),
            params=self.filters.compose_filters(filters))

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
        super(DataPayload, self).__init__(data, None, None)

    @property
    def agg(self):
        return self._data.get('agg', None)

    @property
    def cf(self):
        return self._data.get('cf', None)

    @property
    def data(self):
        """Return internal data from payload as list of DataPoint."""
        return [DataPoint(x[0],x[1]) for x in self._data.get('data', [])]

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

class BulkDataPayload(DataPayload):
    wrn = BulkDataPayloadWarning
    """Class to encapsulate bulk data payload"""
    def __init__(self, data={'data':[]}):
        super(BulkDataPayload, self).__init__(data)

    @property
    def data(self):
        return [BulkDataRow(x) for x in self._data.get('data', [])]

    @property
    def device_names(self):
        return self._data.get('device_names', [])

    def __repr__(self):
        return '<BulkDataPayload: len:{0} devs:{1} b:{2} e:{3}>'.format(
            len(self._data.get('data', [])), len(self.device_names), self.begin_time, self.end_time)

class BulkDataRow(object):
    """Class to encapsulate and differentiate data from different devices,
    interfaces and direction/traffic endpoints when getting data back from 
    a bulk request for interface data."""
    def __init__(self, row={}):
        super(BulkDataRow, self).__init__()
        self._info = row.get('path', {})
        self._data = row.get('data', [])

    @property
    def device(self):
        return self._info.get('dev', None)

    @property
    def interface(self):
        return self._info.get('iface', None)

    @property
    def endpoint(self):
        return self._info.get('endpoint', None)

    @property
    def data(self):
        return [DataPoint(x[0],x[1]) for x in self._data]

    def __repr__(self):
        return '<BulkDataRow: dev:{0} iface:{1} endpoint:{2} len:{3}>'.format(
            self.device, self.interface, self.endpoint,len(self._data))

# - Query entry point and filtering.

class ApiFilters(object):
    wrn = ApiFiltersWarning
    """Class to hold filtering/query options.  This will be used by 
    ApiConnect and also passed to all the encapsulation objects."""
    def __init__(self):
        super(ApiFilters, self).__init__()

        self._begin_time = datetime.datetime.utcfromtimestamp(int(time.time() - 3600))
        self._end_time = datetime.datetime.utcfromtimestamp(int(time.time()))

        # Values to use in GET requests - they are combined with a 
        # user defined dict of filtering args (agg, cf) and django
        # filtering options and passed as args to the GET query.
        self._default_filters = {
            'begin': self.ts_epoch('begin_time'),
            'end': self.ts_epoch('end_time'),
            'limit': 0,
        }

        # Values to use in POST requests, verbose flag, etc.
        self.verbose = False
        self.cf = 'average'
        self.agg = None
        # This needs to be checked via property.
        self._endpoint = ['in']

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
            self._default_filters['begin'] = self.ts_epoch('begin_time')
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
            self._default_filters['end'] = self.ts_epoch('end_time')
        def fdel(self):
            pass
        return locals()
    end_time = property(**end_time())

    def limit():
        doc = "The limit property."
        def fget(self):
            return self._limit
        def fset(self, value):
            self._limit = int(value)
            self._default_filters['limit'] = self._limit
        def fdel(self):
            del self._limit
        return locals()
    limit = property(**limit())

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

    def endpoint():
        doc = "The endpoint property."
        def fget(self):
            return self._endpoint
        def fset(self, value):
            if not value or not isinstance(value, list):
                self.warn('The endpoint filter must be set to a non-empty list ("{0}" given), retaining current values {1}'.format(value,self.endpoint))
                return
            self._endpoint = value
        def fdel(self):
            del self._endpoint
        return locals()
    endpoint = property(**endpoint())

    def compose_filters(self, filters):
        """Compose filters using the defaults combined with local filters.

        The defaults will be overwritten by filters with the same name in the
        local filters."""

        return dict(self.default_filters, **filters)

    def warn(self, m):
        warnings.warn(m, self.wrn, stacklevel=2)

class ApiConnect(object):
    wrn = ApiConnectWarning
    """Core class to pull data from the rest api."""
    def __init__(self, api_url, filters=ApiFilters()):
        super(ApiConnect, self).__init__()
        self.api_url = api_url.rstrip("/")
        self.filters = filters
        self._valid_endpoints = []

    def get_devices(self, **filters):
        r = requests.get('{0}/v1/device/'.format(self.api_url),
            params=self.filters.compose_filters(filters))

        self.inspect_request(r)
        
        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            for i in data:
                yield Device(i, self.api_url, self.filters)
        else:
            self.http_alert(r)
            return
            yield

    def get_interfaces(self, **filters):
        r = requests.get('{0}/v1/interface/'.format(self.api_url),
                params=self.filters.compose_filters(filters))

        self.inspect_request(r)

        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            for i in data['children']:
                yield Interface(i, self.api_url, self.filters)
        else:
            self.http_alert(r)
            return
            yield

    def get_interface_bulk_data(self, **filters):
        interfaces = []

        for i in self.get_interfaces(**filters):
            if self.filters.verbose: print i
            interfaces.append({'device': i.device, 'iface': i.ifDescr})
            if self.filters.verbose > 1: print i.dump

        return self._execute_get_interface_bulk_data(interfaces)

    def _execute_get_interface_bulk_data(self, interfaces=[]):

        if not self._check_endpoints():
            return BulkDataPayload()

        payload = { 
            'interfaces': interfaces, 
            'endpoint': self.filters.endpoint,
            'cf': self.filters.cf,
            'begin': self.filters.ts_epoch('begin_time'),
            'end': self.filters.ts_epoch('end_time'),
        }

        if self.filters.agg: payload['agg'] = self.filters.agg

        headers = { 'content-type': 'application/json' }

        r = requests.post('{0}/v1/bulk/'.format(self.api_url), 
            headers=headers, data=json.dumps(payload))

        self.inspect_request(r)
        self.inspect_payload(payload)

        if r.status_code == 201 and \
            r.headers['content-type'] == 'application/json':
            return BulkDataPayload(json.loads(r.text))
        else:
            self.http_alert(r)
            return BulkDataPayload()

    def _check_endpoints(self):
        if not self._valid_endpoints:
            r = requests.get('{0}/v1/oidsetmap/'.format(self.api_url))
            if not r.status_code == 200:
                self.warn('Could not retrieve oid set map from REST api.')
                return False
            data = json.loads(r.content)
            for i in data.keys():
                for ii in data[i].keys():
                    if ii not in self._valid_endpoints:
                        self._valid_endpoints.append(ii)

        for ep in self.filters.endpoint:
            if ep not in self._valid_endpoints:
                self.warn('{0} is not a valid endpoint type - must be of the form {1} - cancelling query'.format(ep, self._valid_endpoints))
                return False

        return True

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
# ----
