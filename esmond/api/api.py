import inspect
import json
import time
import datetime
import calendar

from collections import OrderedDict

from django.core.serializers.json import DjangoJSONEncoder
from django.conf.urls.defaults import url
from django.utils.timezone import make_aware, utc
from django.utils.timezone import now as django_now
from django.core.exceptions import ObjectDoesNotExist

from tastypie.resources import ModelResource, Resource, ALL, ALL_WITH_RELATIONS
from tastypie.api import Api
from tastypie.authentication import ApiKeyAuthentication
from tastypie.authorization import Authorization, DjangoAuthorization
from tastypie.serializers import Serializer
from tastypie.bundle import Bundle
from tastypie import fields
from tastypie.exceptions import NotFound, BadRequest, Unauthorized
from tastypie.http import HttpCreated
from tastypie.throttle import CacheDBThrottle

from esmond.api import SNMP_NAMESPACE, ANON_LIMIT, OIDSET_INTERFACE_ENDPOINTS
from esmond.api.auth import EsmondAuthorization, AnonymousGetElseApiAuthentication, \
    AnonymousBulkLimitElseApiAuthentication, AnonymousTimeseriesBulkLimitElseApiAuthentication, \
    AnonymousThrottle
from esmond.api.dataseries import QueryUtil, Fill
from esmond.api.models import Device, IfRef, DeviceOIDSetMap, OIDSet, OID, OutletRef
from esmond.cassandra import CASSANDRA_DB, AGG_TYPES, ConnectionException, RawRateData, BaseRateBin
from esmond.config import get_config_path, get_config
from esmond.util import atdecode, atencode

try:
    db = CASSANDRA_DB(get_config(get_config_path()))
except ConnectionException, e:
    # Check the stack before raising an error - if test_api is 
    # the calling code, we won't need a running db instance.
    mod = inspect.getmodule(inspect.stack()[1][0])
    if mod and mod.__name__ == 'api.tests.test_api' or 'sphinx.ext.autodoc':
        print '\nUnable to connect - presuming stand-alone testing mode...'
        db = None
    else:
        raise ConnectionException(str(e))

snmp_ns_doc = """
REST namespace documentation:

**/v1/device/** - Namespace to retrieve traffic data with a simplfied helper syntax.

/v1/device/
/v1/device/$DEVICE/
/v1/device/$DEVICE/interface/
/v1/device/$DEVICE/interface/$INTERFACE/
/v1/device/$DEVICE/interface/$INTERFACE/in
/v1/device/$DEVICE/interface/$INTERFACE/out

Params for GET: begin, end, agg (and cf where appropriate).

If none are supplied, sane defaults will be set by the interface and the 
last hour of base rates will be returned.  The begin/end params are 
timestamps in seconds, the agg param is the frequency of the aggregation 
that the client is requesting, and the cf is one of average/min/max.

This namespace is 'browsable' - /v1/device/ will return a list of devices, 
/v1/device/$DEVICE/interface/ will return the interfaces on a device, etc. 
A full 'detail' URI with a defined endpoing data set (as outlined in the 
OIDSET_INTERFACE_ENDPOINTS just below) will return the data.

**/v1/oidset/** - Namespace to retrive a list of valid oidsets.

This endpoint is not 'browsable' and it takes no GET arguments.  It merely 
return a list of valid oidsets from the metadata database for user 
reference.

**/v1/interface/** - Namespace to retrieve information about discrete interfaces 
without having to "go through" information about a specific device.

This endpoint is not 'browsable.'  It takes common GET arguments that 
would apply like begin and end to filter active interfaces.  Additionally, 
standard django filtering arguments can be applied to the ifDesc and 
ifAlias fields (ex: &ifAlias__contains=intercloud) to get information 
about specifc subsets of interfaces.

"""

def get_throttle_args(config):
    args = {
        'throttle_at': config.api_throttle_at,
        'timeframe': config.api_throttle_timeframe,
        'expiration': config.api_throttle_expiration
    }
    return args

THROTTLE_ARGS = get_throttle_args(get_config(get_config_path()))

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


class DeviceSerializer(Serializer):
    def to_json(self, data, options=None):
        data = self.to_simple(data, options)
        if data.has_key('objects'):
            d = data['objects']
        else:
            d = data
        return json.dumps(d, cls=DjangoJSONEncoder, sort_keys=True)


class DeviceResource(ModelResource):
    """
    Root resource of this REST schema.  This will return device information 
    form using the ORM and dispatch requests for interface and endpoint 
    information to the appropriate InterfaceResource.
    """
    children = fields.ListField()
    leaf = fields.BooleanField()
    oidsets = fields.ToManyField('esmond.api.api.OidsetResource', 'oidsets', full=True)

    class Meta:
        queryset = Device.objects.all()
        resource_name = 'device'
        serializer = DeviceSerializer()
        excludes = ['community',]
        allowed_methods = ['get', 'put']
        detail_uri_name = 'name'
        filtering = {
            'name': ALL,
        }
        authentication = AnonymousGetElseApiAuthentication()
        authorization = DjangoAuthorization()
        throttle = AnonymousThrottle(**THROTTLE_ARGS)

    def dehydrate_begin_time(self, bundle):
        # return int(time.mktime(bundle.data['begin_time'].timetuple()))
        return int(calendar.timegm(bundle.data['begin_time'].utctimetuple()))

    def dehydrate_end_time(self, bundle):
        # return int(time.mktime(bundle.data['end_time'].timetuple()))
        return int(calendar.timegm(bundle.data['end_time'].utctimetuple()))

    def hydrate_end_time(self, bundle):
        # The integer timestamp as previously dehydrated needs to 
        # be coerced back to a date string or the dateutil parser will
        # barf.
        if bundle.request.META['REQUEST_METHOD'] == 'PUT' and isinstance(bundle.data['end_time'], int):
            bundle.data['end_time'] = make_aware(datetime.datetime.utcfromtimestamp(
                bundle.data['end_time']), utc)
        return bundle

    def hydrate_begin_time(self, bundle):
        # See hydrate_end_time comment.
        if bundle.request.META['REQUEST_METHOD'] == 'PUT' and isinstance(bundle.data['begin_time'], int):
            bundle.data['begin_time'] = make_aware(datetime.datetime.utcfromtimestamp(
                bundle.data['begin_time']), utc)
        return bundle

    def hydrate_oidsets(self, bundle):
        if bundle.data['oidsets'] and not isinstance(bundle.data['oidsets'][0], unicode):
            return bundle
        bundle.data['oidsets'] = OIDSet.objects.filter(name__in=bundle.data.get('oidsets', []))
        return bundle

    def save_m2m(self, bundle):

        device = Device.objects.get(id=bundle.data['id'])
        device.oidsets.clear()

        for o in bundle.data['oidsets']:
            omap = DeviceOIDSetMap(device=device, oid_set=o)
            omap.save()

        return bundle

    def alter_detail_data_to_serialize(self, request, data):
        data.data['uri'] = data.data['resource_uri']
        return data

    def prepend_urls(self):
        """
        URL regex parsing for this REST schema.  The call to dispatch_detail 
        returns Device information the ORM, the other calls are dispatched to 
        the methods below.  

        This is connected to the django url schema by the call:

        v1_api = Api(api_name='v1')
        v1_api.register(DeviceResource())

        at the bottom of the module.
        """
        return [
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/$" \
                % self._meta.resource_name, self.wrap_view('dispatch_detail'),
                  name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_interface_list'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/(?P<iface_name>[\w\d_.\-@]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_interface_detail'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/(?P<iface_name>[\w\d_.\-@]+)/(?P<iface_dataset>[\w\d_.-/]+)/?$" % (self._meta.resource_name,),
                self.wrap_view('dispatch_interface_data'),
                name="api_get_children"),
                ]

    def build_filters(self,  filters=None):
        if filters is None:
            filters = {}

        orm_filters = super(DeviceResource, self).build_filters(filters)
        orm_filters = build_time_filters(filters, orm_filters)

        return orm_filters

    """
    The three following methods are invoked by the prepend_urls regex parsing. 
    They invoke and return an the appropriate method call on an instance of 
    one of the Interface* resorces below.
    """

    def dispatch_interface_list(self, request, **kwargs):
        return InterfaceResource().dispatch_list(request,
                device__name=kwargs['name'])

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


class OidsetResource(ModelResource):
    class Meta:
        resource_name = 'oidset'
        allowed_methods = ['get']
        queryset = OIDSet.objects.all()
        authentication = AnonymousGetElseApiAuthentication()
        excludes = ['id', 'poller_args', 'frequency']
        # This one doesn't really need to be throttled.

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()
        return qs

    def obj_get_list(self, bundle, **kwargs):
        return super(OidsetResource, self).obj_get_list(bundle, **kwargs)

    def alter_list_data_to_serialize(self, request, data):
        return data['objects']

    def dehydrate(self, bundle):
        return bundle.data['name']

class OidsetEndpointResource(ModelResource):
    oids = fields.ToManyField('esmond.api.api.OidResource', 'oids', full=True)
    class Meta:
        resource_name = 'oidsetmap'
        allowed_methods = ['get']
        queryset = OIDSet.objects.all()
        authentication = AnonymousGetElseApiAuthentication()
        excludes = ['id', 'poller_args', 'frequency']
        include_resource_uri = False

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()
        return qs

    def obj_get_list(self, bundle, **kwargs):
        return super(OidsetEndpointResource, self).obj_get_list(bundle, **kwargs)

    def alter_list_data_to_serialize(self, request, data):
        payload = {}
        for oidset in data['objects']:
            for oid in oidset.data['oids']:
                if oid.data['endpoint_alias']:
                    if not payload.has_key(oidset.obj.name):
                        payload[oidset.obj.name] = {}
                    payload[oidset.obj.name][oid.data['endpoint_alias']] = oid.data['name']
        return payload

    def dehydrate(self, bundle):
        for oid in bundle.data['oids']:
            del oid.data['aggregate']
            del oid.data['id']
            del oid.data['resource_uri']
        return bundle

class OidResource(ModelResource):
    class Meta:
        resource_name = 'oid'
        queryset = OID.objects.all()

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()
        return qs

    def obj_get_list(self, bundle, **kwargs):
        return super(OidResource, self).obj_get_list(bundle, **kwargs)


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
            'ifDescr': ALL,
            'ifAlias': ALL,
        }
        authentication = AnonymousGetElseApiAuthentication()
        throttle = AnonymousThrottle(**THROTTLE_ARGS)

    def obj_get(self, bundle, **kwargs):
        """
        The standard time range filtering is applied to obj_get since there may
        actually be more than one underlying IfRef for this interface. If there
        is more than one IfRef during the selected time period the IfRef with
        the greatest end_time is returned.

        This also massages the incoming URL fragment to restore characters in 
        ifDescr which were encoded to avoid URL metacharacters back to
        their original state.
        """
        kwargs['ifDescr'] = atdecode(kwargs['ifDescr'])
        kwargs = build_time_filters(bundle.request.GET, kwargs)

        object_list = self.get_object_list(bundle.request).filter(**kwargs)
        if len(object_list) > 1:
            kwargs['pk'] = object_list.order_by("-end_time")[0].pk

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
        """
        Modify resource object default format before this is returned 
        and serialized as json.
        """
        data['children'] = data['objects']
        del data['objects']
        return data

    def get_resource_uri(self, bundle_or_obj=None):
        """Generates the resource uri element that is returned in json payload."""
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        if obj:
            uri = "%s%s%s" % (
                DeviceResource().get_resource_uri(obj.device),
                'interface/',
                obj.encoded_ifDescr())
        else:
            uri = ''

        return uri

    def dehydrate_children(self, bundle):
        children = []

        for oidset in bundle.obj.device.oidsets.all():
            if oidset.name in OIDSET_INTERFACE_ENDPOINTS.endpoints:
                children.extend(OIDSET_INTERFACE_ENDPOINTS.endpoints[oidset.name].keys())

        base_uri = self.get_resource_uri(bundle)
        return [ dict(leaf=True, uri='%s/%s' % (base_uri, x), name=x)
                for x in children ]

    def dehydrate(self, bundle):
        bundle.data['leaf'] = False
        bundle.data['uri'] = bundle.data['resource_uri']
        bundle.data['device_uri'] = bundle.data['device']
        return bundle

class DataObject(object):
    """Encapsulation object to assign values to during processing."""
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

class InterfaceDataObject(DataObject):
    """Encapsulation object to assign values to during processing."""
    pass

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
        throttle = AnonymousThrottle(**THROTTLE_ARGS)

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()
        n = now()
        return qs.filter(begin_time__gte=n, end_time__lt=n)

    def get_resource_uri(self, bundle_or_obj):
        """Generate resource uri"""
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        uri = "%s/%s" % (
                InterfaceResource().get_resource_uri(obj.iface),
                obj.iface_dataset)
        return uri

    def obj_get(self, bundle, **kwargs):
        """
        Invoked when the actual data detail is requested.  Checks the 
        interface name, and generates the endpoint mapping which contains 
        the array 'path' that is used to request the data from the backend.

        If that is all good, then query args are parsed, defaults are set if 
        none were supplied and then the query is executed.
        """

        kwargs['iface_name'] = atdecode(kwargs['iface_name'])

        try:
            iface = InterfaceResource().obj_get(bundle,
                    device__name=kwargs['name'],
                    ifDescr=kwargs['iface_name'])
        except IfRef.DoesNotExist:
            raise BadRequest("no such device/interface: dev: {0} int: {1}".format(kwargs['name'], kwargs['iface_name']))

        oidsets = iface.device.oidsets.all()
        endpoint_map = {}
        for oidset in oidsets:
            if oidset.name not in OIDSET_INTERFACE_ENDPOINTS.endpoints:
                continue

            for endpoint, varname in \
                    OIDSET_INTERFACE_ENDPOINTS.endpoints[oidset.name].iteritems():
                endpoint_map[endpoint] = [
                    SNMP_NAMESPACE,
                    iface.device.name,
                    oidset.name,
                    varname,
                    kwargs['iface_name']
                ]

        iface_dataset = kwargs['iface_dataset'].rstrip("/")

        if iface_dataset not in endpoint_map:
            raise BadRequest("no such dataset: %s" % iface_dataset)

        oidset = iface.device.oidsets.get(name=endpoint_map[iface_dataset][2])

        obj = InterfaceDataObject()
        obj.datapath = endpoint_map[iface_dataset]
        obj.datapath[2] = oidset.set_name  # set_name defaults to oidset.name, but can be overidden in poller_args
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
        """
        Executes a couple of reality checks (making sure that a valid 
        aggregation was requested and checks/limits the time range), and
        then make calls to cassandra backend.
        """

        # If no aggregate level defined in request, set to the frequency, 
        # otherwise, check if the requested aggregate level is valid.
        if not obj.agg:
            obj.agg = oidset.frequency
        elif obj.agg and not oidset.aggregates:
            raise BadRequest('there are no aggregations for oidset {0} - {1} was requested'.format(oidset.name, obj.agg))
        elif obj.agg not in oidset.aggregates:
            raise BadRequest('no valid aggregation %s in oidset %s' %
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
        obj.data = Fill.verify_fill(obj.begin_time, obj.end_time,
                obj.agg, obj.data)

        return obj

# ---

bulk_ns_doc = """
**/v1/bulk/** - Not a true namespace.  The /bulk/ ns node will dispatch URIs
like /bulk/interface/ or /bulk/timeseries/ to the appropriate classes.
"""

class BulkDispatch(Resource):
    """
    Class to dispatch the /v1/bulk namespace to other bulk resources.
    """
    class Meta:
        resource_name = 'bulk'
        serializer = DeviceSerializer()
        allowed_methods = ['get', 'post']
        # This just dispatches, so let the actual resources work it out.
        # authentication = AnonymousGetElseApiAuthentication()

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/$" % \
                self._meta.resource_name, 
                self.wrap_view('dispatch_namespace_root'), 
                name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<r_type>[\w\d_.-]+)/$" % \
                self._meta.resource_name, 
                self.wrap_view('dispatch_query_type'), 
                name="api_dispatch_detail"),
        ]

    def dispatch_namespace_root(self, request, **kwargs):
        """Incomplete path: /v1/bulk/"""
        raise BadRequest('Must supply bulk node: /v1/bulk/{0}'.format('|'.join(QueryUtil.bulk_request_types)))

    def dispatch_query_type(self, request, **kwargs):
        r_type = kwargs.get('r_type')

        if r_type == 'timeseries':
            return TimeseriesBulkRequestResource().dispatch_list(request, **kwargs)
        elif r_type == 'interface':
            return InterfaceBulkRequestResource().dispatch_list(request, **kwargs)
        else:
            raise BadRequest('Bulk node must be one of the following: /v1/bulk/{0}'.format('|'.join(QueryUtil.bulk_request_types)))

bulk_interface_ns_doc = """
**/v1/bulk/interface/** - Namespace to retrive bulk traffic data from 
multiple interfaces without needing to make multiple round trip http 
requests via the main device/interface/endpoint namespace documented 
at the top of the module.

This namespace is not 'browsable,' and while it runs counter to typical 
REST semantics/verbs, it implements the POST verb.  This is to get around 
potential limitations in how many arguments/length of said that can be 
sent in a GET request.  The request information is sent as a json blob:

{ 
    'interfaces': [{'interface': me0.0, 'device': albq-asw1}, ...], 
    'endpoint': ['in', 'out'],
    'cf': 'average',
    'begin': 1382459647,
    'end': 1382463247,
}

Interfaces are requestes as a list of dicts containing iface and device 
information.  Different kinds of endpoints (in, out, error/in, 
discard/out, etc) are passed in as a list and data for each sort of 
endpoint will be returned for each interface.
"""

class InterfaceBulkRequestDataObject(DataObject):
    """Data encapsulation."""
    pass

class InterfaceBulkRequestResource(Resource):
    """
    Resource to make a series of requests to the cassandra backend
    to avoid a bunch of round trip http requests to the REST interface.
    Takes a POST verb to get around around limitations in passing 
    lots of args to GET requests.  Incoming payload looks like this:

    {
        'interfaces': [{'interface': me0.0, 'device': albq-asw1}, ...],
        'endpoint': 'in',
        other usual args (begin/end/cf...)
    }
    
    """

    class Meta:
        resource_name = 'bulkinterface' # handled by BulkDispatch.
        allowed_methods = ['post']
        always_return_data = True
        object_class = InterfaceBulkRequestDataObject
        serializer = DeviceSerializer()
        authentication = AnonymousBulkLimitElseApiAuthentication()
        throttle = AnonymousThrottle(**THROTTLE_ARGS)

    def obj_create(self, bundle, **kwargs):
        if bundle.request.META.get('CONTENT_TYPE') != 'application/json':
            raise BadRequest('Must post content-type: application/json header and json-formatted payload.')

        if not bundle.data:
            raise BadRequest('No data payload POSTed.')

        if not bundle.data.has_key('interfaces') or not \
            bundle.data.has_key('endpoint'):
            raise BadRequest('Payload must contain keys interfaces and endpoint.')

        ret_obj = InterfaceBulkRequestDataObject()
        ret_obj.iface_dataset = bundle.data['endpoint']
        ret_obj.data = []
        ret_obj.device_names = []

        # Set up filtering and return values

        if bundle.data.has_key('begin'):
            ret_obj.begin_time = int(float(bundle.data['begin']))
        else:
            ret_obj.begin_time = int(time.time() - 3600)

        if bundle.data.has_key('end'):
            ret_obj.end_time = int(float(bundle.data['end']))
        else:
            ret_obj.end_time = int(time.time())

        if bundle.data.has_key('cf'):
            ret_obj.cf = bundle.data['cf']
        else:
            ret_obj.cf = 'average'

        if bundle.data.has_key('agg'):
            ret_obj.agg = int(bundle.data['agg'])
        else:
            ret_obj.agg = None

        for i in bundle.data['interfaces']:
            device_name = i['device'].rstrip('/').split('/')[-1]
            iface_name = i['iface']

            ret_obj.device_names.append(device_name)

            for end_point in bundle.data['endpoint']:
                # print device_name, iface_name, end_point
                endpoint_map = {}
                device = Device.objects.get(name=device_name)
                for oidset in device.oidsets.all():
                    if oidset.name not in OIDSET_INTERFACE_ENDPOINTS.endpoints:
                        continue
                    for endpoint, varname in \
                        OIDSET_INTERFACE_ENDPOINTS.endpoints[oidset.name].iteritems():
                        endpoint_map[endpoint] = [
                            SNMP_NAMESPACE,
                            device_name,
                            oidset.name,
                            varname,
                            iface_name
                        ]

                if end_point not in endpoint_map:
                    raise BadRequest("no such dataset: %s" % end_point)

                oidset = device.oidsets.get(name=endpoint_map[end_point][2])

                obj = InterfaceBulkRequestDataObject()
                obj.datapath = endpoint_map[end_point]
                obj.iface_dataset = end_point
                obj.iface = iface_name

                obj.begin_time = ret_obj.begin_time
                obj.end_time = ret_obj.end_time
                obj.cf = ret_obj.cf
                obj.agg = ret_obj.agg

                data = InterfaceDataResource()._execute_query(oidset, obj)

                row = {
                    'data': data.data,
                    'path': {'dev': device_name,'iface': iface_name,'endpoint': end_point},
                }

                ret_obj.data.append(row)

        bundle.obj = ret_obj
        return bundle

    def alter_detail_data_to_serialize(self, request, data):
        return data.obj.to_dict()

    def detail_uri_kwargs(self, bundle_or_obj):
        kwargs = {}
        if isinstance(bundle_or_obj, Bundle):
            pass
        else:
            pass
        return kwargs

# ---

ts_ns_doc = """
**/v1/timeseries/** - Namespace to retrive data with explicit Cassandra 
schema-like syntax.

/v1/timeseries/
/v1/timeseries/$TYPE/
/v1/timeseries/$TYPE/$NS/
/v1/timeseries/$TYPE/$NS/$DEVICE/
/v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/
/v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/$OID/
/v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/$OID/$INTERFACE/
/v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/$OID/$INTERFACE/$FREQUENCY

$TYPE: is RawData, BaseRate or Aggs
$NS: is just a prefix/key construct

Params for get: begin, end, and cf where appropriate.
Params for put: JSON list of dicts with keys 'val' and 'ts' sent as POST 
data payload.

GET: The begin/end params are timestamps in milliseconds, and the cf is 
one of average/min/max.  If none are given, begin/end will default to the 
last hour.

In short: everything after the /v1/timeseries/$TYPE/ segment of the URI is 
joined together to create a cassandra row key.  The path must end with a 
valid numeric frequency.  The URIs could potentailly be longer or shorter 
depending on the composition of the row keys of the data being retrieved 
or written - this is just based on the composition of the snmp data keys.

The $NS element is just a construct of how we are storing the data.  It is 
just a prefix - the esmond data is being stored with the previx snmp for 
example.  Ultimately it is still just part of the generated path.

This namespace is not 'browsable' - GET and POST requests expect expect a 
full 'detail' URI.  Entering an incomplete URI (ex: /v1/timeseries/, etc) 
will result in a 400 error being returned.
"""

class TimeseriesDataObject(DataObject):
    """Data encapsulation."""
    pass

class TimeseriesResource(Resource):
    """
    This is a non-ORM resource.  The fields defined right below 
    are just the return values from ths resource, not connected to 
    a database backend.

    This accepts both GET and POST requests.  The POST is dispatched 
    to post_detail and not create_obj since this is using the full 
    'detail' level URI during the request to define the complete cassandra
    key.
    """

    begin_time = fields.IntegerField(attribute='begin_time')
    end_time = fields.IntegerField(attribute='end_time')
    data = fields.ListField(attribute='data')
    agg = fields.CharField(attribute='agg')
    cf = fields.CharField(attribute='cf')

    class Meta:
        resource_name = 'timeseries'
        allowed_methods = ['get', 'post'] # see post_detail comment
        object_class = TimeseriesDataObject
        serializer = DeviceSerializer()
        authentication = AnonymousGetElseApiAuthentication()
        authorization = EsmondAuthorization('timeseries')
        throttle = AnonymousThrottle(**THROTTLE_ARGS)

    def prepend_urls(self):
        """
        URL parsing - most of these patterns just match an imcomplete 
        URL and dispatch them to methods that return an appropriate
        error message.  The final pattern passes a request to an actual 
        processing method.
        """
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
        """Incomplete path: /v1/timeseries/"""
        raise BadRequest('Must supply data type {0}, namespace and path.'.format(QueryUtil.timeseries_request_types))

    def dispatch_data_type(self, request, **kwargs):
        """Incomplete path: /v1/timeseries/$TYPE/"""
        raise BadRequest('Must supply namespace and path for type {0}.'.format(kwargs.get('r_type')))

    def dispatch_data_ns(self, request, **kwargs):
        """Incomplete path: /v1/timeseries/$TYPE/$NS/ """
        raise BadRequest('Must supply path for namespace {0}'.format(kwargs.get('ns')))

    def alter_list_data_to_serialize(self, request, data):
        return data['objects'][0]

    def get_resource_uri(self, bundle_or_obj):
        """Generate resource_uri for json payload."""
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
            obj.datapath = QueryUtil.encode_datapath(obj.datapath)
        else:
            obj = bundle_or_obj

        uri = '/{0}/{1}/{2}/{3}/{4}'.format(self.api_name, self._meta.resource_name, 
            obj.r_type, '/'.join(obj.datapath), obj.agg)

        return uri

    def obj_get(self, bundle, **kwargs):
        """
        Invoked when a GET request hits this namespace.  Sanity check incoming
        URI segment/args, sets defaults if need be and executes the query.
        """
        obj = TimeseriesDataObject()

        obj.r_type = kwargs.get('r_type')
        obj.datapath = [kwargs.get('ns')] + kwargs.get('path').rstrip('/').split('/')
        obj.agg = obj.datapath.pop()
        obj.datapath = QueryUtil.decode_datapath(obj.datapath)

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
            obj.begin_time = int(time.time() - 3600) * 1000

        if filters.has_key('end'):
            obj.end_time = int(float(filters['end']))
        else:
            obj.end_time = int(time.time()) * 1000

        if filters.has_key('cf'):
            obj.cf = filters['cf']
        else:
            if obj.r_type == 'RawData':
                obj.cf = 'raw'
            else:
                obj.cf = 'average'

        obj = self._execute_query(obj)

        return obj

    def _check_post_detail_auth(self, request):
        o = TimeseriesDataObject()
        o.request = request
        try:
            EsmondAuthorization('timeseries').create_detail([], o)
        except Unauthorized as e:
            self.unauthorized_result(e)

    def post_detail(self, request, **kwargs):
        """
        Invoked when a POST request is issued.  Rather than CGI-style 
        http parameters, a JSON blob (a list of dicts) is passed in as 
        the the body of the request.

        This performs some rather granular sanity checks on the incoming 
        request/JSON payload.  If that passes, then a list of data objects 
        is generated from the payload and passed to the method that 
        executes the inserts.

        When debating the PUT/POST issue on how to handle this,
        I read a comment about the issue that theoretically a 
        PUT command should be idempotent and not all of our
        cassandra writes are (base rates for example) so post 
        was chosen. -MMG
        """
        # Check auth
        self._check_post_detail_auth(request)

        # Validate incoming POST/JSON payload:
        if request.META.get('CONTENT_TYPE') != 'application/json':
            raise BadRequest('Must post content-type: application/json header and json-formatted payload.')

        if not request.body:
            raise BadRequest('No data payload POSTed.')

        try:
            input_payload = json.loads(request.body)
        except ValueError:
            raise BadRequest('POST data payload could not be decoded to a JSON object - given: {0}'.format(bundle.body))

        if not isinstance(input_payload, list):
            raise BadRequest('Successfully decoded JSON, but expecting a list - got: {0} from input: {1}'.format(type(input_payload), input_payload))

        for i in input_payload:
            if not isinstance(i, dict):
                raise BadRequest('Expecting a JSON formtted list of dicts - contained {0} as an array element.'.format(type(i)))
            if not i.has_key('ts') or not i.has_key('val'):
                raise BadRequest('Expecting list of dicts with keys \'val\' and \'ts\' - got: {0}'.format(i))
            try:
                int(float(i.get('ts')))
                float(i.get('val'))
            except ValueError:
                raise BadRequest('Must supply valid numeric args for ts and val dict attributes - got: {0}'.format(i))


        objs = []

        for i in input_payload:

            obj = TimeseriesDataObject()

            obj.r_type = kwargs.get('r_type')
            obj.datapath = [kwargs.get('ns')] + kwargs.get('path').rstrip('/').split('/')
            obj.agg = obj.datapath.pop()
            obj.ts = i.get('ts')
            obj.val = i.get('val')

            obj.datapath = QueryUtil.decode_datapath(obj.datapath)

            if obj.r_type not in QueryUtil.timeseries_request_types:
                raise BadRequest('Request type must be one of {0} - {1} was given.'.format(QueryUtil.timeseries_request_types, obj.r_type))

            # Currently only doing raw and base.
            if obj.r_type not in [ 'RawData', 'BaseRate' ]:
                raise BadRequest('Only POSTing RawData or BaseRate currently supported.')

            objs.append(obj)

        if self._execute_inserts(objs):
            return HttpCreated()
        else:
            # Error TBA
            pass

    def _execute_query(self, obj):
        """
        Sanity check the requested timerange, and then make the appropriate
        method call to the cassandra backend.
        """
        # Make sure we're not exceeding allowable time range.
        if not QueryUtil.valid_timerange(obj, in_ms=True):
            raise BadRequest('exceeded valid timerange for agg level: %s' %
                    obj.agg)
        
        data = []

        if obj.r_type == 'BaseRate':
            data = db.query_baserate_timerange(path=obj.datapath, freq=obj.agg,
                    ts_min=obj.begin_time, ts_max=obj.end_time)
        elif obj.r_type == 'Aggs':
            if obj.cf not in AGG_TYPES:
                raise BadRequest('%s is not a valid consolidation function' %
                        (obj.cf))
            data = db.query_aggregation_timerange(path=obj.datapath, freq=obj.agg,
                    ts_min=obj.begin_time, ts_max=obj.end_time, cf=obj.cf)
        elif obj.r_type == 'RawData':
            data = db.query_raw_data(path=obj.datapath, freq=obj.agg,
                    ts_min=obj.begin_time, ts_max=obj.end_time)
        else:
            # Input has been checked already
            pass

        obj.data = QueryUtil.format_data_payload(data, in_ms=True)
        if not len(obj.data):
            # If no data is returned, sanity check that there is a 
            # corresponding key in the database.
            v = db.check_for_valid_keys(path=obj.datapath, freq=obj.agg, 
                ts_min=obj.begin_time, ts_max=obj.end_time)
            if not v:
                raise BadRequest('The request path {0} has no corresponding keys.'.format([obj.r_type] + obj.datapath + [obj.agg]))

        if obj.r_type != 'RawData':
            obj.data = Fill.verify_fill(obj.begin_time, obj.end_time,
                    obj.agg, obj.data)

        return obj

    def _execute_inserts(self, objs):
        """
        Iterate through a list of TimeseriesDataObject, execute the 
        appropriate inserts, and then explicitly flush the db so the 
        inserts don't sit in the batch wating for more data to auto-flush.
        """
        for obj in objs:
            if obj.r_type == 'BaseRate':
                rate_bin = BaseRateBin(path=obj.datapath, ts=obj.ts, 
                    val=obj.val, freq=obj.agg)
                db.update_rate_bin(rate_bin)
            elif obj.r_type == 'Aggs':
                pass
            elif obj.r_type == 'RawData':
                raw_data = RawRateData(path=obj.datapath, ts=obj.ts, 
                    val=obj.val, freq=obj.agg)
                db.set_raw_data(raw_data)
            else:
                # Input has been checked already
                pass
        
        db.flush()

        return True

# ---

bulk_namespace_ns_doc = """
**/v1/bulk/timeseries/** - Namespace to retrive bulk traffic data from 
multiple paths without needing to make multiple round trip http 
requests via the /timeseries/ namespace.

This namespace is not 'browsable,' and while it runs counter to typical 
REST semantics/verbs, it implements the POST verb.  This is to get around 
potential limitations in how many arguments/length of said that can be 
sent in a GET request.  The request information is sent as a json blob:

{
    'paths': [
        ['snmp', 'lbl-mr2', 'FastPollHC', 'ifHCInOctets', 'xe-9/3/0.202', '30000'], 
        ['snmp', 'anl-mr2', 'FastPollHC', 'ifHCOutOctets', 'xe-7/0/0.1808', '30000']
    ], 
    'begin': 1384976511773, 
    'end': 1384980111773, 
    'type': 'RawData'
}

Data are requested as a list of paths per the /timeseries namespace with
the addition of a frequency (in ms) at the end of the path dict mimicing
the cassandra row keys.
"""

class TimeseriesBulkRequestDataObject(DataObject):
    """Data encapsulation."""
    pass

class TimeseriesBulkRequestResource(Resource):
    """
    Resource to make a series of requests to the cassandra backend
    to avoid a bunch of round trip http requests to the REST interface.
    Takes a POST verb to get around around limitations in passing 
    lots of args to GET requests.  Incoming payload looks like this:

    {
    'paths': [
        ['snmp', 'lbl-mr2', 'FastPollHC', 'ifHCInOctets', 'xe-9/3/0.202', '30000'], 
        ['snmp', 'anl-mr2', 'FastPollHC', 'ifHCOutOctets', 'xe-7/0/0.1808', '30000']
    ], 
    'begin': 1384976511773, 
    'end': 1384980111773, 
    'type': 'RawData'
    }
    
    """

    class Meta:
        resource_name = 'timeseriesbulk' # handled by BulkDispatch
        allowed_methods = ['post']
        always_return_data = True
        object_class = TimeseriesBulkRequestDataObject
        serializer = DeviceSerializer()
        authentication = AnonymousTimeseriesBulkLimitElseApiAuthentication()
        throttle = AnonymousThrottle(**THROTTLE_ARGS)

    def obj_create(self, bundle, **kwargs):

        if bundle.request.META.get('CONTENT_TYPE') != 'application/json':
            raise BadRequest('Must post content-type: application/json header and json-formatted payload.')

        if not bundle.data:
            raise BadRequest('No data payload POSTed.')

        if not bundle.data.has_key('paths') or not \
            bundle.data.has_key('type'):
            raise BadRequest('Payload must contain keys paths and type.')

        if not isinstance(bundle.data['paths'], list):
            raise BadRequest('Payload paths element must be a list - got: {0}'.format(bundle.data['lists']))

        ret_obj = TimeseriesBulkRequestDataObject()

        if bundle.data['type'] == 'RawData':
            ret_obj.cf = 'raw'
        else:
            ret_obj.cf = 'average'

        ret_obj.data = []

        if bundle.data.has_key('begin'):
            ret_obj.begin_time = int(float(bundle.data['begin']))
        else:
            ret_obj.begin_time = int(time.time() - 3600) * 1000

        if bundle.data.has_key('end'):
            ret_obj.end_time = int(float(bundle.data['end']))
        else:
            ret_obj.end_time = int(time.time()) * 1000

        for p in bundle.data['paths']:
            obj = TimeseriesBulkRequestDataObject()
            obj.r_type = bundle.data['type']
            obj.cf = ret_obj.cf
            obj.begin_time = ret_obj.begin_time
            obj.end_time = ret_obj.end_time
            obj.datapath = p
            obj.agg = int(obj.datapath.pop())

            obj = TimeseriesResource()._execute_query(obj)

            row = {
                'data': obj.data,
                'path': obj.datapath + [obj.agg]
            }

            ret_obj.data.append(row)

        bundle.obj = ret_obj
        return bundle

    def alter_detail_data_to_serialize(self, request, data):
        return data.obj.to_dict()

    def detail_uri_kwargs(self, bundle_or_obj):
        kwargs = {}
        if isinstance(bundle_or_obj, Bundle):
            pass
        else:
            pass
        return kwargs

# ---

# class QueryUtil(object):
#     """Class holding common query methods used by multiple resources 
#     and data structures to validate incoming request elements."""

#     _timerange_limits = {
#         30: datetime.timedelta(days=30),
#         60: datetime.timedelta(days=30),
#         300: datetime.timedelta(days=30),
#         3600: datetime.timedelta(days=365),
#         86400: datetime.timedelta(days=365*10),
#     }

#     timeseries_request_types = ['RawData', 'BaseRate', 'Aggs']
#     bulk_request_types = ['timeseries', 'interface']

#     @staticmethod
#     def decode_datapath(datapath):
#         return [ atdecode(step) for step in datapath ]

#     @staticmethod
#     def encode_datapath(datapath):
#         return [ atencode(step) for step in datapath ]

#     @staticmethod
#     def valid_timerange(obj, in_ms=False):
#         """Check the requested time range against the requested aggregation 
#         level and limit if too much data was requested.

#         The in_ms flag is set to true if a given resource (like the 
#         /timeseries/ namespace) is doing business in milliseconds rather 
#         than seconds."""
#         if in_ms:
#             s = datetime.timedelta(milliseconds=obj.begin_time)
#             e = datetime.timedelta(milliseconds=obj.end_time)
#         else:
#             s = datetime.timedelta(seconds=obj.begin_time)
#             e = datetime.timedelta(seconds=obj.end_time)
        
#         divs = { False: 1, True: 1000 }

#         try:
#             if e - s > QueryUtil._timerange_limits[obj.agg/divs[in_ms]]:
#                 return False
#         except KeyError:
#             raise BadRequest('invalid aggregation level: %s' %
#                     obj.agg)

#         return True

#     @staticmethod
#     def format_data_payload(data, in_ms=False, coerce_to_bins=None):
#         """Massage results from cassandra for json return payload.

#         The in_ms flag is set to true if a given resource (like the 
#         /timeseries/ namespace) is doing business in milliseconds rather 
#         than seconds.

#         If coerce_to_bins is not None, truncate the timestamp to the
#         the bins spaced coerce_to_bins ms apart. This is useful for 
#         fitting raw data to bin boundaries."""

#         divs = { False: 1000, True: 1 }

#         results = []

#         for row in data:
#             ts = row['ts']

#             if coerce_to_bins:
#                 ts -= ts % coerce_to_bins

#             d = [ts/divs[in_ms], row['val']]
            
#             # Further options for different data sets.
#             if row.has_key('is_valid'): # Base rates
#                 if row['is_valid'] == 0: d[1] = None
#             elif row.has_key('cf'): # Aggregations
#                 pass
#             else: # Raw Data
#                 pass
            
#             results.append(d)

#         return results

# class Fill(object):
#     """Set of methods to verify that a series of binned data contains
#     the correct number of datapoints over a given time range, and if 
#     not, fill the missing bins with an invalid value before returning
#     the data to the client.

#     Normally persister will backfill gaps in the data in the DB but gaps
#     could be returned under the following circumstances:

#     1 - The most common scenario is when requesting up to the minute 
#     binned data where the most recent value might not have been written 
#     yet.

#     2 - The query might span when a new device started having data 
#     recorded.

#     3 - A gap (like if a device was offline for a period of time) might 
#     exceed the "heartbeat limit" and generate a span too long to reasonably
#     fill with invalid data points.
#     """
#     @staticmethod
#     def expected_bin_count(start_bin, end_bin, freq):
#         """Get expected number of bins in a given range of bins."""
#         return ((end_bin - start_bin) / freq) + 1

#     @staticmethod
#     def get_expected_first_bin(begin, freq):
#         """Get the first bin of a given frequency based on the begin ts
#         of a timeseries query."""
#         # Determine the first bin in the series based on the begin
#         # timestamp in the timeseries request.
#         #
#         # Bin math will round down to last bin but timerange queries will
#         # return the next bin.  That is, given a 30 second bin, a begin
#         # timestamp of 15 seconds past the minute will yield a bin calc
#         # of on the minute, but but the time range query will return 
#         # 30 seconds past the minute as the first result.
#         #
#         # A begin timestamp falling directly on a bin will return 
#         # that bin.
#         bin = (begin/freq)*freq
#         if bin < begin:
#             return bin+freq
#         elif bin == begin:
#             return bin
#         else:
#             # Shouldn't happen
#             raise RuntimeError

#     @staticmethod
#     def get_bin_alignment(begin, end, freq):
#         """Generate a few values needed for checking and filling a series if 
#         need be."""
#         start_bin = Fill.get_expected_first_bin(begin,freq)
#         end_bin = (end/freq)*freq
#         expected_bins = Fill.expected_bin_count(start_bin, end_bin, freq)
        
#         return start_bin, end_bin, expected_bins

#     @staticmethod
#     def generate_filled_series(start_bin, end_bin, freq, data):
#         """Genrate a new 'filled' series if the returned series has unexpected
#         gaps.  Initialize a new range based in the requested time range as
#         an OrderedDict, then iterate through original series to retain original
#         values.
#         """
#         # Generate the empty "proper" timerange
#         filled_range = []
#         s = start_bin + 0 # copy it
#         while s <= end_bin:
#             filled_range.append((s,None))
#             s += freq

#         # Make it a ordered dict
#         fill = OrderedDict(filled_range)

#         # Go through the original data and plug in 
#         # good values

#         for dp in data:
#             fill[dp[0]] = dp[1]

#         for i in fill.items():
#             yield list(i)

#     @staticmethod
#     def verify_fill(begin, end, freq, data):
#         """Top-level function to inspect a returned series for gaps.
#         Returns the original series of the count is correct, else will
#         return a new filled series."""
#         begin, end, freq = int(begin), int(end), int(freq)
#         start_bin,end_bin,expected_bins = Fill.get_bin_alignment(begin, end, freq)
#         #print 'got :', len(data)
#         #print 'need:', Fill.expected_bin_count(start_bin,end_bin,freq)
#         if len(data) == Fill.expected_bin_count(start_bin,end_bin,freq):
#             #print 'verify: not filling'
#             return data
#         else:
#             #print 'verify: filling'
#             return list(Fill.generate_filled_series(start_bin,end_bin,freq,data))

class PDUResource(DeviceResource):
    class Meta:
        queryset = Device.objects.filter(pk__in=OutletRef.objects.values_list("device__pk")).distinct()
        resource_name = 'pdu'
        serializer = DeviceSerializer()
        excludes = ['community',]
        allowed_methods = ['get']
        detail_uri_name = 'name'
        filtering = {
            'name': ALL,
        }

    def dehydrate_children(self, bundle):
        children = ['outlet', ]

        base_uri = self.get_resource_uri(bundle)
        return [ dict(leaf=False, uri='%s%s' % (base_uri, x), name=x)
                for x in children ]


    def prepend_urls(self):
        """
        URL regex parsing for this REST schema.  The call to dispatch_detail
        returns Device information the ORM, the other calls are dispatched to
        the methods below.

        This is connected to the django url schema by the call:

        v1_api = Api(api_name='v1')
        v1_api.register(DeviceResource())

        at the bottom of the module.
        """
        return [
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/$" \
                % self._meta.resource_name, self.wrap_view('dispatch_detail'),
                  name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/outlet/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_outlet_list'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/outlet/(?P<outlet_id>[\w\d_.\-@]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_outlet_detail'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/outlet/(?P<outlet_id>[\w\d_.\-@]+)/(?P<outlet_dataset>[\w\d_.-/]+)/?$" % (self._meta.resource_name,),
                self.wrap_view('dispatch_outlet_data'),
                name="api_get_children"),
                ]

    """
    The three following methods are invoked by the prepend_urls regex parsing. 
    They invoke and return an the appropriate method call on an instance of 
    one of the Interface* resorces below.
    """

    def dispatch_outlet_list(self, request, **kwargs):
        return OutletResource().dispatch_list(request,
                device__name=kwargs['name'])

    def dispatch_outlet_detail(self, request, **kwargs):
        return OutletResource().dispatch_detail(request,
                device__name=kwargs['name'], outletID=kwargs['outlet_id'] )

    def dispatch_outlet_data(self, request, **kwargs):
        return OutletDataResource().dispatch_detail(request, **kwargs)

class OutletResource(ModelResource):
    """An outlet on a PDU.

    Note: this resource is always nested under a PDUResource and is not bound
    into the normal namespace for the API."""

    pdu = fields.ToOneField(PDUResource, 'device')
    children = fields.ListField()
    leaf = fields.BooleanField()
    device_uri = fields.CharField()

    class Meta:
        resource_name = 'outlet'
        queryset = OutletRef.objects.all()
        allowed_methods = ['get']
        detail_uri_name = 'outletID'
        filtering = {
            'pdu': ALL_WITH_RELATIONS,
            'outletID': ALL,
            'outletName': ALL,
        }
        authentication = AnonymousGetElseApiAuthentication()
        throttle = AnonymousThrottle(**THROTTLE_ARGS)

    def obj_get(self, bundle, **kwargs):
        kwargs['outletID'] = atdecode(kwargs['outletID'])
        kwargs = build_time_filters(bundle.request.GET, kwargs)
        
        object_list = self.get_object_list(bundle.request).filter(**kwargs)
        if len(object_list) > 1:
            kwargs['pk'] = object_list.order_by("-end_time")[0].pk

        return super(OutletResource, self).obj_get(bundle, **kwargs)

    def build_filters(self, filters=None):
        if filters is None:
            filters = {}
        orm_filters = super(OutletResource, self).build_filters(filters)
        orm_filters = build_time_filters(filters, orm_filters)

        return orm_filters

    def alter_list_data_to_serialize(self, request, data):
        """
        Modify resource object default format before this is returned 
        and serialized as json.
        """
        data['children'] = data['objects']
        del data['objects']
        return data

    def get_resource_uri(self, bundle_or_obj=None):
        """Generates the resource uri element that is returned in json payload."""
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        if obj:
            uri = "%s%s%s" % (
                PDUResource().get_resource_uri(obj.device),
                'outlet/',
                obj.outletID)
        else:
            uri = ''

        return uri

    def dehydrate_children(self, bundle):
        children = ['load', ]

        base_uri = self.get_resource_uri(bundle)
        return [ dict(leaf=False, uri='%s%s' % (base_uri, x), name=x)
                for x in children ]


class OutletDataObject(DataObject):
    """Encapsulation for outlet data."""
    pass

class OutletDataResource(Resource):
    """Data for an outlet on a PDU.

    Note: this resource is always nested under a PDURessource and is not bound
    into the normal namespace for the API."""

    begin_time = fields.IntegerField(attribute="begin_time")
    end_time = fields.IntegerField(attribute="end_time")
    data = fields.ListField(attribute='data')

    class Meta:
        resource_name = 'outlet_data'
        allowed_methods = ['get']
        object_class = OutletDataObject
        authentication = AnonymousGetElseApiAuthentication()
        throttle = AnonymousThrottle(**THROTTLE_ARGS)

    def get_resource_uri(self, bundle_or_obj):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj


        uri = "%s/%s/" % (
            OutletResource().get_resource_uri(obj.outlet),
            obj.outlet_dataset)

        return uri

    def obj_get(self, bundle, **kwargs):
        outlet_id = atdecode(kwargs['outlet_id'])
        outlet_dataset = kwargs['outlet_dataset'].rstrip("/")

        try:
            outlet = OutletResource().obj_get(bundle,
                device__name=kwargs['name'],
                outletID=outlet_id)
        except OutletRef.DoesNotExist:
            raise BadRequest("no such device/oulet: dev: {0} outlet: {1}".format(kwargs['name'], outlet_id))

        if outlet_dataset != 'load':
            raise BadRequest("no such dataset: {0}".format(outlet_dataset))

        oidset_name = 'SentryPoll'
        datapath = [SNMP_NAMESPACE, outlet.device.name, oidset_name, 'outletLoadValue', outlet_id]

        obj = OutletDataObject()
        obj.outlet = outlet
        obj.datapath = datapath
        obj.outlet_dataset = outlet_dataset

        oidset = outlet.device.oidsets.get(name=oidset_name)

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

        return self._execute_query(oidset, obj)

    def _execute_query(self, oidset, obj):
        data = db.query_raw_data(obj.datapath, oidset.frequency*1000,
                                 obj.begin_time*1000, obj.end_time*1000)

        obj.data = QueryUtil.format_data_payload(data, coerce_to_bins=oidset.frequency*1000)
        obj.data = Fill.verify_fill(obj.begin_time, obj.end_time, oidset.frequency,
                                    obj.data)

        return obj

"""Connect the 'root' resources to the URL schema."""
v1_api = Api(api_name='v1')
v1_api.register(DeviceResource())
v1_api.register(TimeseriesResource())
v1_api.register(OidsetResource())
v1_api.register(InterfaceResource())
v1_api.register(OidsetEndpointResource())
v1_api.register(BulkDispatch())
v1_api.register(PDUResource())
v1_api.register(OutletResource())

__doc__ = '\n\n'.join([snmp_ns_doc, bulk_ns_doc, bulk_interface_ns_doc, ts_ns_doc, bulk_namespace_ns_doc])
