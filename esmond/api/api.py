import inspect
import json
import time
import datetime

from django.core.serializers.json import DjangoJSONEncoder
from django.conf.urls.defaults import url
from django.utils.timezone import make_aware, utc
from django.utils.timezone import now as django_now
from django.core.exceptions import ObjectDoesNotExist

from tastypie.resources import ModelResource, Resource, ALL, ALL_WITH_RELATIONS
from tastypie.api import Api
from tastypie.authentication import ApiKeyAuthentication
from tastypie.serializers import Serializer
from tastypie.bundle import Bundle
from tastypie import fields
from tastypie.exceptions import NotFound, BadRequest

from esmond.api.models import Device, IfRef
from esmond.cassandra import CASSANDRA_DB, AGG_TYPES, ConnectionException
from esmond.config import get_config_path, get_config
from esmond.util import remove_metachars

"""
/$DEVICE/
/$DEVICE/interface/
/$DEVICE/interface/$INTERFACE/
/$DEVICE/interface/$INTERFACE/in
/$DEVICE/interface/$INTERFACE/out
"""

try:
    db = CASSANDRA_DB(get_config(get_config_path()))
except ConnectionException, e:
    # Check the stack before raising an error - if test_api is 
    # the calling code, we won't need a running db instance.
    mod = inspect.getmodule(inspect.stack()[1][0])
    if mod.__name__ == 'api.tests.test_api':
        print '\nUnable to connect - presuming stand-alone testing mode...'
        db = None
    else:
        raise ConnectionException(str(e))

OIDSET_INTERFACE_ENDPOINTS = {
    'ALUErrors': {
        'error/in': 'ifInErrors',
        'error/out': 'ifOutErrors',
        'discard/in': 'ifInDiscards',
        'discard/out': 'ifOutDiscards',
    },
    'ALUFastPollHC': {
        'in': 'ifHCInOctets',
        'out': 'ifHCOutOctets',
    },
    'Errors': {
        'error/in': 'ifInErrors',
        'error/out': 'ifOutErrors',
        'discard/in': 'ifInDiscards',
        'discard/out': 'ifOutDiscards',
    },
    'FastPollHC': {
        'in': 'ifHCInOctets',
        'out': 'ifHCOutOctets',
    },
    'InfFastPollHC': {
        'in': 'gigeClientCtpPmRealInOctets',
        'out': 'gigeClientCtpPmRealOutOctets',
    },
}

def check_connection():
    """Called by testing suite to produce consistent errors.  If no 
    cassandra instance is available, test_api might silently hide that 
    fact with mock.patch causing unclear errors in other modules 
    like test_persist."""
    global db
    if not db:
        db = CASSANDRA_DB(get_config(get_config_path()))

def build_time_filters(filters, orm_filters):
    """Build default time filters.

    By default we want only currently active items.  This will inspect
    orm_filters and fill in defaults if they are missing."""

    if 'begin' in filters:
        orm_filters['end_time__gte'] = make_aware(datetime.datetime.utcfromtimestamp(
                float(filters['begin'])), utc)

    if 'end' in filters:
        orm_filters['begin_time__lte'] = make_aware(datetime.datetime.utcfromtimestamp(
                float(filters['end'])), utc)

    filter_keys = map(lambda x: x.split("__")[0], orm_filters.keys())
    now = django_now()

    if 'begin_time' not in filter_keys:
        orm_filters['begin_time__lte'] = now

    if 'end_time' not in filter_keys:
        orm_filters['end_time__gte'] = now

    return orm_filters

class AnonymousGetElseApiAuthentication(ApiKeyAuthentication):
    """Allow GET without authentication, rely on API keys for all else"""
    def is_authenticated(self, request, **kwargs):
        authenticated = super(AnonymousGetElseApiAuthentication, self).is_authenticated(
                request, **kwargs)

        # we always allow GET, but is_authenticated() has side effects which add
        # the user data to the request, which we want if available, so do
        # is_authenticated first then return True for all GETs

        if request.method == 'GET':
            return True

        return authenticated

    def get_identifier(self, request):
        if request.user.is_anonymous():
            return 'AnonymousUser'
        else:
            return super(AnonymousGetElseApiAuthentication,
                    self).get_identifier(request)

class DeviceSerializer(Serializer):
    def to_json(self, data, options=None):
        data = self.to_simple(data, options)
        if data.has_key('objects'):
            d = data['objects']
        else:
            d = data
        return json.dumps(d, cls=DjangoJSONEncoder, sort_keys=True)


class DeviceResource(ModelResource):
    children = fields.ListField()
    leaf = fields.BooleanField()

    class Meta:
        queryset = Device.objects.all()
        resource_name = 'device'
        serializer = DeviceSerializer()
        excludes = ['community', ]
        allowed_methods = ['get']
        detail_uri_name = 'name'
        filtering = {
            'name': ALL,
        }
        authentication = AnonymousGetElseApiAuthentication()

    def dehydrate_begin_time(self, bundle):
        return int(time.mktime(bundle.data['begin_time'].timetuple()))

    def dehydrate_end_time(self, bundle):
        return int(time.mktime(bundle.data['end_time'].timetuple()))

    def alter_detail_data_to_serialize(self, request, data):
        data.data['uri'] = data.data['resource_uri']
        return data

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/$" \
                % self._meta.resource_name, self.wrap_view('dispatch_detail'),
                  name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_interface_list'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/(?P<iface_name>[\w\d_.-]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_interface_detail'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/(?P<iface_name>[\w\d_.-]+)/(?P<iface_dataset>[\w\d_.-/]+)/?$" % (self._meta.resource_name,),
                self.wrap_view('dispatch_interface_data'),
                name="api_get_children"),
                ]

    def build_filters(self,  filters=None):
        if filters is None:
            filters = {}

        orm_filters = super(DeviceResource, self).build_filters(filters)
        orm_filters = build_time_filters(filters, orm_filters)

        return orm_filters

    # XXX(jdugan): next steps
    # data formatting
    # time based limits on view
    # decide to how represent -infinity/infinity timestamps
    # figure out what we need from newdb.py
    # add docs, start with stuff in newdb.py
    #
    # add mapping between oidset and REST API.  Something similar to declarative
    # models/resources ala Django models

    def dispatch_interface_list(self, request, **kwargs):
        return InterfaceResource().dispatch_list(request, device__name=kwargs['name'])

    def dispatch_interface_detail(self, request, **kwargs):
        return InterfaceResource().dispatch_detail(request,
                device__name=kwargs['name'], ifDescr=kwargs['iface_name'] )

    def dispatch_interface_data(self, request, **kwargs):
        return InterfaceDataResource().dispatch_detail(request, **kwargs)

    def dehydrate_children(self, bundle):
        children = ['interface', 'system', 'all']

        base_uri = self.get_resource_uri(bundle)
        return [ dict(leaf=False, uri='%s%s' % (base_uri, x), name=x)
                for x in children ]

    def dehydrate(self, bundle):
        bundle.data['leaf'] = False
        return bundle

class InterfaceResource(ModelResource):
    """An interface on a device.

    Note: this resource is always nested under a DeviceResource and is not bound
    into the normal namespace for the API."""

    device = fields.ToOneField(DeviceResource, 'device')
    children = fields.ListField()
    leaf = fields.BooleanField()
    device_uri = fields.CharField()
    uri = fields.CharField()

    class Meta:
        resource_name = 'interface'
        queryset = IfRef.objects.all()
        allowed_methods = ['get']
        detail_uri_name = 'ifDescr'
        filtering = {
            'device': ALL_WITH_RELATIONS,
        }
        authentication = AnonymousGetElseApiAuthentication()

    def obj_get(self, bundle, **kwargs):
        kwargs['ifDescr'] = kwargs['ifDescr'].replace("_", "/")
        return super(InterfaceResource, self).obj_get(bundle, **kwargs)

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()
        if not request.user.has_perm("api.can_see_hidden_ifref"):
            qs = qs.exclude(ifAlias__contains=":hide:")

        return qs

    def obj_get_list(self, bundle, **kwargs):
        return super(InterfaceResource, self).obj_get_list(bundle, **kwargs)

    def build_filters(self,  filters=None):
        if filters is None:
            filters = {}

        orm_filters = super(InterfaceResource, self).build_filters(filters)
        orm_filters = build_time_filters(filters, orm_filters)

        return orm_filters

    def alter_list_data_to_serialize(self, request, data):
        data['children'] = data['objects']
        del data['objects']
        return data

    def get_resource_uri(self, bundle_or_obj=None):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        if obj:
            uri = "%s%s%s" % (
                DeviceResource().get_resource_uri(obj.device),
                'interface/',
                obj.clean_ifDescr())
        else:
            uri = ''

        return uri

    def dehydrate_children(self, bundle):
        children = []

        for oidset in bundle.obj.device.oidsets.all():
            if oidset.name in OIDSET_INTERFACE_ENDPOINTS:
                children.extend(OIDSET_INTERFACE_ENDPOINTS[oidset.name].keys())

        base_uri = self.get_resource_uri(bundle)
        return [ dict(leaf=True, uri='%s/%s' % (base_uri, x), name=x)
                for x in children ]

    def dehydrate(self, bundle):
        bundle.data['leaf'] = False
        bundle.data['uri'] = bundle.data['resource_uri']
        bundle.data['device_uri'] = bundle.data['device']
        return bundle

class InterfaceDataObject(object):
    def __init__(self, initial=None):
        self.__dict__['_data'] = {}

        if hasattr(initial, 'items'):
            self.__dict__['_data'] = initial

    def __getattr__(self, name):
        return self._data.get(name, None)

    def __setattr__(self, name, value):
        self.__dict__['_data'][name] = value

    def to_dict(self):
        return self._data

class InterfaceDataResource(Resource):
    """Data for interface on a device.

    Note: this resource is always nested under a DeviceResource and is not bound
    into the normal namespace for the API."""

    begin_time = fields.IntegerField(attribute='begin_time')
    end_time = fields.IntegerField(attribute='end_time')
    data = fields.ListField(attribute='data')
    agg = fields.CharField(attribute='agg')
    cf = fields.CharField(attribute='cf')

    class Meta:
        resource_name = 'interface_data'
        allowed_methods = ['get']
        object_class = InterfaceDataObject
        authentication = AnonymousGetElseApiAuthentication()

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()
        n = now()
        return qs.filter(begin_time__gte=n, end_time__lt=n)

    def get_resource_uri(self, bundle_or_obj):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        uri = "%s/%s" % (
                InterfaceResource().get_resource_uri(obj.iface),
                obj.iface_dataset)
        return uri

    def obj_get(self, bundle, **kwargs):
        iface_qs = InterfaceResource().get_object_list(bundle.request)
        try:
            iface = iface_qs.get( device__name=kwargs['name'],
                    ifDescr=kwargs['iface_name'].replace("_", "/"))
        except IfRef.DoesNotExist:
            raise ObjectDoesNotExist("no such device/interface")

        oidsets = iface.device.oidsets.all()
        endpoint_map = {}
        for oidset in oidsets:
            if oidset.name not in OIDSET_INTERFACE_ENDPOINTS:
                continue 

            for endpoint, varname in \
                    OIDSET_INTERFACE_ENDPOINTS[oidset.name].iteritems():
                endpoint_map[endpoint] = [
                    iface.device.name,
                    oidset.name,
                    varname,
                    kwargs['iface_name']
                ]

        iface_dataset = kwargs['iface_dataset'].rstrip("/")

        if iface_dataset not in endpoint_map:
            raise ObjectDoesNotExist("no such dataset: %s" % iface_dataset)

        oidset = iface.device.oidsets.get(name=endpoint_map[iface_dataset][1])

        obj = InterfaceDataObject()
        obj.datapath = endpoint_map[iface_dataset]
        obj.iface_dataset = iface_dataset
        obj.iface = iface

        filters = getattr(bundle.request, 'GET', {})

        # Make sure incoming begin/end timestamps are ints
        if filters.has_key('begin'):
            obj.begin_time = int(float(filters['begin']))
        else:
            obj.begin_time = int(time.time() - 3600)

        if filters.has_key('end'):
            obj.end_time = int(float(filters['end']))
        else:
            obj.end_time = int(time.time())

        if filters.has_key('cf'):
            obj.cf = filters['cf']
        else:
            obj.cf = 'average'

        if filters.has_key('agg'):
            obj.agg = int(filters['agg'])
        else:
            obj.agg = None

        return self._execute_query(oidset, obj)

    def _execute_query(self, oidset, obj):
        # If no aggregate level defined in request, set to the frequency, 
        # otherwise, check if the requested aggregate level is valid.
        if not obj.agg:
            obj.agg = oidset.frequency
        elif obj.agg not in oidset.aggregates:
            raise BadRequest('no aggregation %s for oidset %s' %
                (obj.agg, oidset.name))

        # Make sure we're not exceeding allowable time range.
        if not QueryUtil.valid_timerange(obj):
            raise BadRequest('exceeded valid timerange for agg level: %s' %
                    obj.agg)
        
        # db = CASSANDRA_DB(get_config(get_config_path()))

        if obj.agg == oidset.frequency:
            # Fetch the base rate data.
            data = db.query_baserate_timerange(path=obj.datapath, freq=obj.agg*1000,
                    ts_min=obj.begin_time*1000, ts_max=obj.end_time*1000)
        else:
            # Get the aggregation.
            if obj.cf not in AGG_TYPES:
                raise BadRequest('%s is not a valid consolidation function' %
                        (obj.cf))
            data = db.query_aggregation_timerange(path=obj.datapath, freq=obj.agg*1000,
                    ts_min=obj.begin_time*1000, ts_max=obj.end_time*1000, cf=obj.cf)

        obj.data = QueryUtil.format_data_payload(data)
        return obj

# ---

class TimeseriesDataObject(InterfaceDataObject):
    pass

class TimeseriesResource(Resource):

    begin_time = fields.IntegerField(attribute='begin_time')
    end_time = fields.IntegerField(attribute='end_time')
    data = fields.ListField(attribute='data')
    agg = fields.CharField(attribute='agg')
    cf = fields.CharField(attribute='cf')

    class Meta:
        resource_name = 'timeseries'
        allowed_methods = ['get']
        object_class = TimeseriesDataObject
        serializer = DeviceSerializer()
        authentication = AnonymousGetElseApiAuthentication()

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/$" % \
                self._meta.resource_name, 
                self.wrap_view('dispatch_namespace_root'), 
                name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<r_type>[\w\d_.-]+)/$" % \
                self._meta.resource_name, 
                self.wrap_view('dispatch_data_type'), 
                name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<r_type>[\w\d_.-]+)/(?P<ns>[\w\d_.-]+)/$" % \
                self._meta.resource_name, 
                self.wrap_view('dispatch_data_ns'), 
                name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<r_type>[\w\d_.-]+)/(?P<ns>[\w\d_.-]+)/(?P<path>.+)$" % \
                self._meta.resource_name, 
                self.wrap_view('dispatch_detail'), 
                name="api_dispatch_detail"),
        ]

    def dispatch_namespace_root(self, request, **kwargs):
        raise BadRequest('Must supply data type {0}, namespace and path.'.format(QueryUtil.timeseries_request_types))

    def dispatch_data_type(self, request, **kwargs):
        raise BadRequest('Must supply namespace and path for type {0}.'.format(kwargs.get('r_type')))

    def dispatch_data_ns(self, request, **kwargs):
        raise BadRequest('Must supply path for namespace {0}'.format(kwargs.get('ns')))

    def alter_list_data_to_serialize(self, request, data):
        return data['objects'][0]

    def get_resource_uri(self, bundle_or_obj):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        uri = '/{0}/{1}/{2}/{3}/{4}'.format(self.api_name, self._meta.resource_name, 
            obj.r_type, '/'.join(obj.datapath), obj.agg)

        return uri

    def obj_get(self, bundle, **kwargs):

        # rtr_d:FastPollHC:ifHCInOctets:xe-1_1_0 30000|3600000|86400000

        if kwargs.get('path').endswith('/'):
            raise BadRequest('Path URI segment does not have a trailing slash.')

        obj = InterfaceDataObject()

        obj.r_type = kwargs.get('r_type')
        obj.datapath = [kwargs.get('ns')] + kwargs.get('path').split('/')
        obj.agg = obj.datapath.pop()

        try:
            obj.agg = int(obj.agg)
        except ValueError:
            # Change this to a 404?
            raise BadRequest('Last segment of URI must be frequency integer.')

        if obj.r_type not in QueryUtil.timeseries_request_types:
            raise BadRequest('Request type must be one of {0} - {1} was given.'.format(QueryUtil.timeseries_request_types, obj.r_type))

        filters = getattr(bundle.request, 'GET', {})

        if filters.has_key('begin'):
            obj.begin_time = int(float(filters['begin']))
        else:
            obj.begin_time = int(time.time() - 3600)

        if filters.has_key('end'):
            obj.end_time = int(float(filters['end']))
        else:
            obj.end_time = int(time.time())

        if filters.has_key('cf'):
            obj.cf = filters['cf']
        else:
            obj.cf = 'average'

        obj = self._execute_query(obj)

        if not len(obj.data):
            raise ObjectDoesNotExist('No data found for request {0} with params {1}'.format(obj.pk, filters))

        return obj

    def _execute_query(self, obj):
        # Make sure we're not exceeding allowable time range.
        if not QueryUtil.valid_timerange(obj, in_ms=True):
            raise BadRequest('exceeded valid timerange for agg level: %s' %
                    obj.agg)

        data = []

        if obj.r_type == 'BaseRate':
            data = db.query_baserate_timerange(path=obj.datapath, freq=obj.agg,
                    ts_min=obj.begin_time*1000, ts_max=obj.end_time*1000)
        elif obj.r_type == 'Aggs':
            data = db.query_aggregation_timerange(path=obj.datapath, freq=obj.agg,
                    ts_min=obj.begin_time*1000, ts_max=obj.end_time*1000, cf=obj.cf)
        elif obj.r_type == 'RawData':
            data = db.query_raw_data(path=obj.datapath, freq=obj.agg,
                    ts_min=obj.begin_time*1000, ts_max=obj.end_time*1000)
        else:
            # Input has been checked already
            pass

        obj.data = QueryUtil.format_data_payload(data, in_ms=True)

        return obj

class QueryUtil(object):
    """Class holding common query methods."""
    _timerange_limits = {
        30: datetime.timedelta(days=30),
        300: datetime.timedelta(days=30),
        3600: datetime.timedelta(days=365),
        86400: datetime.timedelta(days=365*10),
    }

    timeseries_request_types = ['RawData', 'BaseRate', 'Aggs']

    @staticmethod
    def valid_timerange(obj, in_ms=False):
        s = datetime.timedelta(seconds=obj.begin_time)
        e = datetime.timedelta(seconds=obj.end_time)

        divs = { False: 1, True: 1000 }

        try:
            if e - s > QueryUtil._timerange_limits[obj.agg/divs[in_ms]]:
                return False
        except KeyError:
            raise BadRequest('invalid aggregation level: %s' %
                    obj.agg)

        return True

    @staticmethod
    def format_data_payload(data, in_ms=False):
        """Massage results from cassandra for json return payload."""

        divs = { False: 1000, True: 1 }

        results = []

        for row in data:
            d = [row['ts']/divs[in_ms], row['val']]
            
            # Further options for different data sets.
            if row.has_key('is_valid'): # Base rates
                if row['is_valid'] == 0: d[1] = None
            elif row.has_key('cf'): # Aggregations
                pass
            else: # Raw Data
                pass
            
            results.append(d)

        return results
        

v1_api = Api(api_name='v1')
v1_api.register(DeviceResource())
v1_api.register(TimeseriesResource())
