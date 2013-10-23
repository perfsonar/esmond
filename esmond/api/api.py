import inspect
import json
import time
import datetime
import calendar

from django.core.serializers.json import DjangoJSONEncoder
from django.conf.urls.defaults import url
from django.utils.timezone import make_aware, utc
from django.utils.timezone import now as django_now
from django.core.exceptions import ObjectDoesNotExist

from tastypie.resources import ModelResource, Resource, ALL, ALL_WITH_RELATIONS
from tastypie.api import Api
from tastypie.authentication import ApiKeyAuthentication
from tastypie.authorization import Authorization
from tastypie.serializers import Serializer
from tastypie.bundle import Bundle
from tastypie import fields
from tastypie.exceptions import NotFound, BadRequest
from tastypie.http import HttpCreated

from esmond.api.models import Device, IfRef, DeviceOIDSetMap, OIDSet
from esmond.cassandra import CASSANDRA_DB, AGG_TYPES, ConnectionException, RawRateData, BaseRateBin
from esmond.config import get_config_path, get_config
from esmond.util import atdecode, atencode

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

"""
Namespace to retrieve traffic data with a simplfied helper syntax.

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

Namespace to retrive a list of valid oidsets.

/v1/oidset/

This endpoint is not 'browsable' and it takes no GET arguments.  It merely 
return a list of valid oidsets from the metadata database for user 
reference.

Namespace to retrieve information about discrete interfaces without 
having to "go through" information about a specific device.

/v1/interface/

This endpoint is not 'browsable.'  It takes common GET arguments that 
would apply like begin and end to filter active interfaces.  Additionally, 
standard django filtering arguments can be applied to the ifDesc and 
ifAlias fields (ex: &ifAlias__contains=intercloud) to get information 
about specifc subsets of interfaces.

"""

SNMP_NAMESPACE = 'snmp'

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
        'in': 'gigeClientCtpPmRealRxOctets',
        'out': 'gigeClientCtpPmRealTxOctets',
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
        # authentication = AnonymousGetElseApiAuthentication()
        # XXX(mmg): this needs to be done away with!
        authorization = Authorization()

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

    # XXX(jdugan): next steps
    # data formatting
    # time based limits on view
    # decide to how represent -infinity/infinity timestamps
    # figure out what we need from newdb.py
    # add docs, start with stuff in newdb.py
    #
    # add mapping between oidset and REST API.  Something similar to declarative
    # models/resources ala Django models

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

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()
        return qs

    def obj_get_list(self, bundle, **kwargs):
        return super(OidsetResource, self).obj_get_list(bundle, **kwargs)

    def alter_list_data_to_serialize(self, request, data):
        return data['objects']

    def dehydrate(self, bundle):
        return bundle.data['name']


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

        # XXX(jdugan): we might want to do something different here, such as
        # return a reference to or a list of other valid IfRefs at this point.
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
            if oidset.name not in OIDSET_INTERFACE_ENDPOINTS:
                continue 

            for endpoint, varname in \
                    OIDSET_INTERFACE_ENDPOINTS[oidset.name].iteritems():
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
        return obj

# ---

"""
Namespace to retrive bulk traffic data from multiple interfaces without 
needing to make multiple round trip http requests via the main 
device/interface/endpoint namespace documented at the top of the module.

/v1/bulk/

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

class BulkRequestDataObject(DataObject):
    """Data encapsulation."""
    pass

class BulkRequestResource(Resource):
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
        resource_name = 'bulk'
        allowed_methods = ['post']
        always_return_data = True
        object_class = BulkRequestDataObject
        serializer = DeviceSerializer()

    def obj_create(self, bundle, **kwargs):
        if bundle.request.META.get('CONTENT_TYPE') != 'application/json':
            raise BadRequest('Must post content-type: application/json header and json-formatted payload.')

        if not bundle.data:
            raise BadRequest('No data payload POSTed.')

        if not bundle.data.has_key('interfaces') or not \
            bundle.data.has_key('endpoint'):
            raise BadRequest('Payload must contain keys interfaces and endpoint.')

        ret_obj = BulkRequestDataObject()
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
                    if oidset.name not in OIDSET_INTERFACE_ENDPOINTS:
                        continue
                    for endpoint, varname in \
                        OIDSET_INTERFACE_ENDPOINTS[oidset.name].iteritems():
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

                obj = BulkRequestDataObject()
                obj.datapath = endpoint_map[end_point]
                obj.iface_dataset = end_point
                obj.iface = iface_name

                obj.begin_time = ret_obj.begin_time
                obj.end_time = ret_obj.end_time
                obj.cf = ret_obj.cf
                obj.agg = ret_obj.agg

                # Recycle existing query code for interface details
                data = InterfaceDataResource()._execute_query(oidset, obj)
                # There are limitations to what we can send back in json,
                # so append a dict with information about this batch of
                # data and pop() it off on the other end.  Sucks less 
                # than trying to delimit and parse it. -mmg
                data.data.append({'dev': device_name,'iface': iface_name,'endpoint': end_point})

                ret_obj.data.append(data.data)

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

"""
Namespace to retrive data with explicit Cassandra schema-like syntax.  

/v1/timeseries/
/v1/timeseries/$TYPE/ (where $TYPE is RawData, BaseRate or Aggs)
/v1/timeseries/$TYPE/$NS/ (this is actually just a prefix/construct of the cassandra keys)
/v1/timeseries/$TYPE/$NS/$DEVICE/
/v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/
/v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/$OID/
/v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/$OID/$INTERFACE/
/v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/$OID/$INTERFACE/$FREQUENCY

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
        # authentication = AnonymousGetElseApiAuthentication()

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

    def post_detail(self, bundle, **kwargs):
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
        # Validate incoming POST/JSON payload:

        if bundle.META.get('CONTENT_TYPE') != 'application/json':
            raise BadRequest('Must post content-type: application/json header and json-formatted payload.')

        if not bundle.body:
            raise BadRequest('No data payload POSTed.')

        try:
            input_payload = json.loads(bundle.body)
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
                raise BadRequest('Only POSTing RawData currently supported.')

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

class QueryUtil(object):
    """Class holding common query methods used by multiple resources 
    and data structures to validate incoming request elements."""

    _timerange_limits = {
        30: datetime.timedelta(days=30),
        300: datetime.timedelta(days=30),
        3600: datetime.timedelta(days=365),
        86400: datetime.timedelta(days=365*10),
    }

    timeseries_request_types = ['RawData', 'BaseRate', 'Aggs']

    @staticmethod
    def decode_datapath(datapath):
        return [ atdecode(step) for step in datapath ]

    @staticmethod
    def encode_datapath(datapath):
        return [ atencode(step) for step in datapath ]

    @staticmethod
    def valid_timerange(obj, in_ms=False):
        """Check the requested time range against the requested aggregation 
        level and limit if too much data was requested.

        The in_ms flag is set to true if a given resource (like the 
        /timeseries/ namespace) is doing business in milliseconds rather 
        than seconds."""
        if in_ms:
            s = datetime.timedelta(milliseconds=obj.begin_time)
            e = datetime.timedelta(milliseconds=obj.end_time)
        else:
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
        """Massage results from cassandra for json return payload.

        The in_ms flag is set to true if a given resource (like the 
        /timeseries/ namespace) is doing business in milliseconds rather 
        than seconds."""

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
        
"""Connect the 'root' resources to the URL schema."""
v1_api = Api(api_name='v1')
v1_api.register(DeviceResource())
v1_api.register(TimeseriesResource())
v1_api.register(OidsetResource())
v1_api.register(InterfaceResource())
v1_api.register(BulkRequestResource())
