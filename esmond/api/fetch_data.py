import calendar
import datetime
import json
import pprint
import requests
import time

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

"""

from esmond.util import max_datetime
max_epoch = calendar.timegm(max_datetime.utctimetuple())

class NodeInfoWarning(Warning): pass
class DeviceWarning(NodeInfoWarning): pass
class InterfaceWarning(NodeInfoWarning): pass
class EndpointWarning(NodeInfoWarning): pass
class DataPayloadWarning(NodeInfoWarning): pass
class ApiConnectWarning(Warning): pass

# - Encapsulation classes for nodes (device, interface, etc).

class NodeInfo(object):
    wrn = NodeInfoWarning
    """Base class for encapsulation objects"""
    def __init__(self, data, hostname, filters):
        super(NodeInfo, self).__init__()
        self._data = data
        self.hostname = hostname
        self.filters = filters

        # Default rest parameters for all objects
        if self.filters:
            self._q_params = {
                'begin': self.filters.ts_epoch('begin_time'),
                'end': self.filters.ts_epoch('end_time')
            }

        self.pp = pprint.PrettyPrinter(indent=4)

    def _convert_to_datetime(self, d):
        """API returns both unix timestamps and ISO time so
        normalize to datetime objects transparently"""
        t = None
        
        try:
            i = int(d)
            if i > max_epoch:
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
        warnings.warn('Request for {0} got status: {1}'.format(r.url,r.status_code), self.wrn, stacklevel=2)


class Device(NodeInfo):
    wrn = DeviceWarning
    """Class to encapsulate device information"""
    def __init__(self, data, hostname, filters):
        super(Device, self).__init__(data, hostname, filters)

    # Property attrs unique to devices
    @property
    def active(self):
        return self._data.get('active', None)

    @property
    def name(self):
        return self._data.get('name', None)

    # Fetch and filter data, etc
    def _filter_interfaces(self, interface):
        return interface

    def get_interfaces(self):
        uri = None
        for c in self._data['children']:
            if c['name'] == 'interface':
                uri = c['uri']
                break

        if uri:
            r = requests.get('http://{0}/{1}'.format(self.hostname, uri), 
                params=self._q_params)

            if r.status_code == 200 and \
                r.headers['content-type'] == 'application/json':
                data = json.loads(r.text)
                for i in data['children']:
                    iface = self._filter_interfaces(Interface(i, self.hostname, self.filters))
                    if iface:
                        yield iface
            else:
                self.http_alert(r)
                return
                yield


    def __repr__(self):
        return '<Device/{0}: uri:{1}>'.format(self.name, self.resource_uri)


class Interface(NodeInfo):
    wrn = InterfaceWarning
    """Class to encapsulate interface information"""
    def __init__(self, data, hostname, filters):
        super(Interface, self).__init__(data, hostname, filters)

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

    # Fetch and filter data, etc
    def _filter_endpoints(self, endpoint):
        return endpoint

    def get_endpoints(self):
        for i in self._data['children']:
            e = self._filter_endpoints(Endpoint(i, self.hostname, self.filters))
            if e:
                yield e

    def __repr__(self):
        return '<Interface/{0}: uri:{1}'.format(self.ifDescr, self.resource_uri)

class Endpoint(NodeInfo):
    wrn = EndpointWarning
    """Class to encapsulate endpoint information"""
    def __init__(self, data, hostname, filters):
        super(Endpoint, self).__init__(data, hostname, filters)

    @property
    def name(self):
        return self._data.get('name', None)

    @property
    def uri(self):
        return self._data.get('uri', None)

    def get_data(self):

        r = requests.get('http://{0}/{1}'.format(self.hostname, self.uri),
            params=self._q_params)

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

        self._devices = []

    def ts_epoch(self, time_prop):
        """Convert named property back to epoch.  Generally just for 
        sending cgi params to the api."""
        return int(calendar.timegm(getattr(self, time_prop).utctimetuple()))

    def _convert_ts(self, ts):
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

    def devices():
        doc = "The devices property."
        def fget(self):
            return self._devices
        def fset(self, value):
            if not isinstance(value, list):
                raise TypeError('devices attr must be a list')
            self._devices = value
        def fdel(self):
            pass
        return locals()
    devices = property(**devices())


class ApiConnect(object):
    wrn = ApiConnectWarning
    """Core class to pull data from the rest api."""
    def __init__(self, hostname, filters=ApiFilters()):
        super(ApiConnect, self).__init__()
        self.hostname = hostname
        self.filters = filters

        self._q_params = {
            'begin': self.filters.ts_epoch('begin_time'),
            'end': self.filters.ts_epoch('end_time')
        }

    def _filter_devices(self, device):

        if self.filters.devices and \
            device.name not in self.filters.devices:
            return None

        return device

    def get_devices(self):
        r = requests.get('http://{0}/v1/device/?limit=0'.format(self.hostname), 
            params=self._q_params)
        
        if r.status_code == 200 and \
            r.headers['content-type'] == 'application/json':
            data = json.loads(r.text)
            for i in data:
                d = self._filter_devices(Device(i, self.hostname, self.filters))
                if d: 
                    yield d
        else:
            self.http_alert(r)
            return
            yield
        
    def http_alert(self, r):
        warnings.warn('Request for {0} got status: {1}'.format(r.url,r.status_code), self.wrn, stacklevel=2)
# ----