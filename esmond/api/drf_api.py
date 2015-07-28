import calendar
import collections
import copy
import datetime
import inspect
import json
import time
import urlparse

import pprint

pp = pprint.PrettyPrinter(indent=4)

from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import make_aware, utc
from django.utils.timezone import now as django_now

from rest_framework import (viewsets, serializers, status, 
        fields, relations, pagination, mixins, throttling)
from rest_framework.exceptions import (ParseError, NotFound, APIException)
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.permissions import (AllowAny, DjangoModelPermissions)

from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_extensions.fields import ResourceUriField

import rest_framework_filters as filters

from .models import *
from esmond.api import SNMP_NAMESPACE, ANON_LIMIT, OIDSET_INTERFACE_ENDPOINTS
from esmond.util import atdecode, atencode
from esmond.api.dataseries import QueryUtil, Fill, TimerangeException
from esmond.cassandra import CASSANDRA_DB, AGG_TYPES, ConnectionException, RawRateData, BaseRateBin
from esmond.config import get_config_path, get_config

#
# Cassandra connection
# 

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

def check_connection():
    """Called by testing suite to produce consistent errors.  If no 
    cassandra instance is available, test_api might silently hide that 
    fact with mock.patch causing unclear errors in other modules 
    like test_persist."""
    global db
    if not db:
        db = CASSANDRA_DB(get_config(get_config_path()))

#
# Superclasses, mixins, helpers,etc.
#

class QueryErrorException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class QueryErrorWarning(Warning): pass

class BaseMixin(object):
    def get_object(self):
        """
        atdecode() the incoming args before the lookup_field lookup happens.
        """
        for k in self.kwargs.keys():
            self.kwargs[k] = atdecode(self.kwargs[k])

        return super(BaseMixin, self).get_object()

    def _add_uris(self, o, uri=True, resource=True):
        """
        Slap a uri and resource_uri on an outgoing object based on 
        the properly DRF generated url attribute.
        """
        if o.get('url', None):
            up = urlparse.urlparse(o.get('url'))
            if uri:
                o['uri'] = up.path
            if resource:
                o['resource_uri'] = up.path

    def _add_device_uri(self, o):
        if o.get('uri', None):
            o['device_uri'] = o['uri'].split('interface')[0]

    def _add_pdu_uri(self, o):
        if o.get('uri', None):
            o['pdu'] = o['uri'].split('outlet')[0]

class EncodedHyperlinkField(relations.HyperlinkedIdentityField):
    """
    General url generator that handles atencoding the lookup_field.
    """
    def get_url(self, obj, view_name, request, format):
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, 'pk') and obj.pk is None:
            return None

        lookup_value = getattr(obj, self.lookup_field)
        kwargs = {self.lookup_url_kwarg: atencode(lookup_value)}
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)

class UnixEpochDateField(serializers.DateTimeField):
    """
    Hat tip to: http://stackoverflow.com/questions/19375753/django-rest-framework-updating-time-using-epoch-time
    """
    def to_representation(self, value):
        """ Return epoch time for a datetime object or ``None``"""
        try:
            return int(calendar.timegm(value.timetuple()))
        except (AttributeError, TypeError):
            return None

    def to_internal_value(self, value):
        return make_aware(datetime.datetime.utcfromtimestamp(int(value)), utc)

class DataObject(object):
    def __init__(self, initial=None):
        self.__dict__['_data'] = collections.OrderedDict()

    def __getattr__(self, name):
        return self._data.get(name, None)

    def __setattr__(self, name, value):
        self.__dict__['_data'][name] = value

    def to_dict(self):
        return self._data

class InterfaceHyperlinkField(relations.HyperlinkedIdentityField):
    """
    Generate urls to "fully qualified" nested interface detail url.

    Also exposes some static methods to generate urls that are called 
    by other resources.
    """
    @staticmethod
    def _iface_detail_url(ifname, device_name, request, format=None):
        """
        Generate a URL to a "fully qualified" interface detail. Used by 
        get_url and also to generate oid-alias endpoint lists.
        """
        # While a legal URI character, the '.' in some interface names
        # makes the reverse() function unhappy.
        return reverse(
            'device-interface-detail',
            kwargs={
                'ifName': atencode(ifname).replace('.', 'PERIOD_TOKEN'),
                'parent_lookup_device__name': atencode(device_name),
            },
            request=request,
            format=format,
            ).replace('PERIOD_TOKEN', '.').rstrip('/')

    @staticmethod
    def _oid_detail_url(ifname, device_name, request, alias):
        """
        Helper method for oid endpoints to call.
        """
        return InterfaceHyperlinkField._iface_detail_url(ifname, device_name, request) + '/' + alias

    @staticmethod
    def _device_detail_url(device_name, request):
        """
        Helper method to generate url to a device.
        """
        return reverse('device-detail', kwargs={'name': atencode(device_name)},request=request)

    def get_url(self, obj, view_name, request, format):
        if hasattr(obj, 'pk') and obj.pk is None:
            return None

        lookup_value = getattr(obj, self.lookup_field)

        return self._iface_detail_url(lookup_value, obj.device.name, request, format)

class BaseDataSerializer(BaseMixin, serializers.Serializer):
    url = fields.URLField()
    data = serializers.ListField(child=serializers.DictField())
    
    begin_time = serializers.IntegerField()
    end_time = serializers.IntegerField()

class BaseDataViewset(viewsets.GenericViewSet):
    def _endpoint_map(self, device, iface_name):

        endpoint_map = {}

        for oidset in device.oidsets.all():
            if oidset.name not in OIDSET_INTERFACE_ENDPOINTS.endpoints:
                continue

            for endpoint, varname in \
                    OIDSET_INTERFACE_ENDPOINTS.endpoints[oidset.name].iteritems():
                endpoint_map[endpoint] = [
                    SNMP_NAMESPACE,
                    device.name,
                    oidset.name,
                    varname,
                    iface_name
                ]

        return endpoint_map

    def _parse_data_default_args(self, request, obj, in_ms=False, time_only=False):

        # depending on http method...
        filter_map = dict(
            GET=getattr(request, 'GET', {}),
            POST=getattr(request, 'data', {}),
        )

        filters = filter_map.get(request.method, {})

        # defaults for values in ms vs. seconds.
        ms_map = {False: 1, True: 1000}

        # Make sure incoming begin/end timestamps are ints
        if filters.has_key('begin'):
            obj.begin_time = int(float(filters['begin']))
        else:
            obj.begin_time = int(time.time() - 3600) * ms_map.get(in_ms)

        if filters.has_key('end'):
            obj.end_time = int(float(filters['end']))
        else:
            obj.end_time = int(time.time()) * ms_map.get(in_ms)

        if time_only: 
            return

        if filters.has_key('cf'):
            obj.cf = filters['cf']
        elif getattr(obj, 'r_type'):
            # logic used by the /v2/timeseries endpoint
            if obj.r_type == 'RawData':
                obj.cf = 'raw'
            else:
                obj.cf = 'average'
        else:
            obj.cf = 'average'

        if getattr(obj, 'r_type'):
            # agg is explicitly set by timeseries logic so quit
            return

        if filters.has_key('agg'):
            obj.agg = int(filters['agg'])
        else:
            obj.agg = None

#
# Filter classes and functions
# 

class DeviceFilter(filters.FilterSet):
    class Meta:
        model = Device
        fields = ['name']

    name = filters.AllLookupsFilter(name='name')
    # XXX(mmg): might need to flesh this out with more options.

class InterfaceFilter(filters.FilterSet):
    class Meta:
        model = IfRef
        fields = ['ifName', 'ifAlias']

    ifName = filters.AllLookupsFilter(name='ifName')
    ifAlias = filters.AllLookupsFilter(name='ifAlias')
    device = filters.RelatedFilter(DeviceFilter, name='device')

def build_time_filters(request):
    """Build default time filters.

    By default we want only currently active items.  This will inspect
    orm_filters and fill in defaults if they are missing.

    Logic pulled from old API. Will generate a dict of model 
    query args one can pass to Model.objects.filter() in an 
    overridden get_queryset() method.
    """

    # depending on http method...
    filter_map = dict(
        GET=getattr(request, 'GET', {}),
        POST=getattr(request, 'data', {}),
    )

    filters = filter_map.get(request.method, {})
    # print filters

    orm_filters = dict()

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

    # print orm_filters
    return orm_filters 

def get_single_iface(ifname, device_name, request):
    """
    The standard time range filtering is applied to get_object since there may
    actually be more than one underlying IfRef for this interface. If there
    is more than one IfRef during the selected time period the IfRef with
    the greatest end_time is returned.

    This also massages the incoming URL fragment to restore characters in 
    ifName which were encoded to avoid URL metacharacters back to
    their original state.

    This is abstracted out since it is used in more than one place.
    """

    kw = dict(
        ifName=ifname,
        device__name=device_name,
    )

    # sanitize input, set up device__name
    kw['ifName'] = atdecode(kw.get('ifName'))

    # add in the time filters
    kw = dict(kw, **build_time_filters(request))

    # make the query and prune hidden if need be
    qs = IfRef.objects.filter(**kw)
    if not request.user.has_perm("api.can_see_hidden_ifref"):
        qs = qs.exclude(ifAlias__contains=":hide:")

    if len(qs) == 0:
        # Let the recieving code decide how to handle this.
        return None
    else:
        # there might be more than one, so sort and return.
        return qs.order_by('-end_time')[0]

def get_single_outlet(outlet_id, device_name, request):
    """
    Filter out the potential for duplicates in much the same 
    way as the nested interfaces.
    """
    kw = dict(
        outletID=outlet_id,
        device__name=device_name,
    )
    # just in case
    kw['outletID'] = atdecode(kw.get('outletID'))
    # add time filters
    kw = dict(kw, **build_time_filters(request))

    qs = OutletRef.objects.filter(**kw)

    if len(qs) == 0:
        return None
    else:
        return qs.order_by('-end_time')[0]

#
# Throttle, auth classes
#

class CustomThrottleAuth(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = _('Auth-based bulk throttling.')

class BaseBulkThrottle(throttling.BaseThrottle):

    def _check_payload_and_request(self, post_payload):
        """
        Override in subclasses. Raise ParseError if the payload is flawed, 
        otherwise extract and return the number of "things" the request is 
        asking for.
        """
        raise NotImplementedError

    def allow_request(self, request, view):

        if request.user.is_authenticated():
            # Authenticated users can as for however much data
            return True

        if request.body and request.content_type.startswith('application/json'):
            post_payload = json.loads(request.body)
        else:
            # status 400
            raise ParseError('Did not receive json payload for bulk POST request.')

        num_request = self._check_payload_and_request(post_payload)

        if num_request <= ANON_LIMIT:
            return True
        else:
            raise CustomThrottleAuth('Request for {0} endpoints exceeds the unauthenticated limit of {1}'.format(num_request, ANON_LIMIT))

class DjangoModelPerm(DjangoModelPermissions):
    """
    Just allowing unauth for read ops
    """
    authenticated_users_only = False

def _get_ersatz_esmond_api_queryset(ersatz_device):
    """
    We have a custom set of django.contrib.auth permissions (see 
    models.APIPermission) for non-model API resources. This function 
    generates a fake queryset that can be put on these non-model resources 
    so that they can use the (above) standard DjangoModelPermissions as 
    a permissions class instead of needing to roll a new custom 
    permission class up to deal with these resources.
    """
    class ErsatzValues(object):
        model_name = ersatz_device
        app_label = 'auth.esmond_api'
    class ErsatzModel(object):
        _meta = ErsatzValues
    class ErsatzQueryset(object):
        model = ErsatzModel

    return ErsatzQueryset

#
# Endpoints for main URI series.
# 

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

# Classes for /v2/oidset/ and /v2/oidsetmap/

class OidsetSerializer(serializers.ModelSerializer):
    class Meta:
        model = OIDSet
        fields = ('name',)

    def to_representation(self, obj):
        ret = super(OidsetSerializer, self).to_representation(obj)
        return ret.get('name')

class OidsetViewset(viewsets.ReadOnlyModelViewSet):
    queryset = OIDSet.objects.all()
    model = OIDSet
    serializer_class = OidsetSerializer

class OidsetMapViewset(viewsets.GenericViewSet):
    """
    Read-only endpoint that returns an "oidset map".
    """
    def list(self, request):
        payload = dict()

        for os in OIDSet.objects.all():
            for oid in os.oids.all():
                if oid.endpoint_alias:
                    if not payload.has_key(os.name):
                        payload[os.name] = dict()
                    payload[os.name][oid.endpoint_alias] = oid.name

        return Response(payload)

# Code to deal with handling interface endpoints in the main REST series.
# ie: /v2/interface/
# Also subclassed by the interfaces nested under the device endpoint.

class EsmondPaginator(pagination.LimitOffsetPagination):
    default_limit = 20

    def _get_count(self, queryset):
        try:
            return queryset.count()
        except (AttributeError, TypeError):
            return len(queryset)

    def get_next_link(self):
        if self.limit == 0 and self.offset == 0:
            return None
        else:
            return super(EsmondPaginator, self).get_next_link()

    def paginate_queryset(self, queryset, request, view=None):
        """
        Modified to make ?limit=0 return the whole dataset.
        """
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None

        self.count = self._get_count(queryset)
        self.request = request

        if self.count > self.limit and self.template is not None:
                self.display_page_controls = True

        if self.limit == 0:
            self.offset = 0
            return list(queryset)
        else:
            self.offset = self.get_offset(request)
            return list(queryset[self.offset:self.offset + self.limit])

    def get_paginated_response(self, data):
        """
        Format the return envelope.
        """
        return Response(
            {
                'meta': {
                    'next': self.get_next_link(),
                    'previous': self.get_previous_link(),
                    'limit': self.limit,
                    'total_count': self.count,
                    'offset': self.offset,
                },

                'children': data,
            }
        )

class InterfaceSerializer(BaseMixin, serializers.ModelSerializer):
    serializer_url_field = InterfaceHyperlinkField

    class Meta:
        model = IfRef
        fields = ('begin_time','children','device', 'device_uri',
        'end_time', 'id', 'ifAdminStatus', 'ifAlias', 'ifDescr',
        'ifHighSpeed', 'ifIndex', 'ifMtu', 'ifName', 'ifOperStatus',
        'ifPhysAddress', 'ifSpeed', 'ifType', 'ipAddr', 
        'end_time', 'leaf','url',)
        extra_kwargs={'url': {'lookup_field': 'ifName'}}

    children = serializers.ListField(child=serializers.DictField())
    leaf = serializers.BooleanField(default=False)

    # XXX(mmg) - what's up with this? The interface endpoint is returning timestamps.
    # presuming that's a bug and do it this way.
    begin_time = UnixEpochDateField()
    end_time = UnixEpochDateField()

    # XXX(mmg) - This and device_uri are duplicitous, so I'm letting this 
    # be an actual relation until I'm convinced that something is broken.
    device = serializers.SlugRelatedField(queryset=Device.objects.all(), slug_field='name')
    device_uri = serializers.CharField(allow_blank=True, trim_whitespace=True)

    def to_representation(self, obj):
        obj.children = list()
        obj.device_uri = ''
        obj.leaf = False
        # list of actual data-bearing OID endpoints.
        for i in obj.device.oidsets.all():
            for ii in i.oids.all():
                if ii.endpoint_alias:
                    d = dict(
                            name=ii.endpoint_alias, 
                            url=self.serializer_url_field._oid_detail_url(obj.ifName, obj.device.name, self.context.get('request'), ii.endpoint_alias),
                            leaf=True,
                        )
                    self._add_uris(d, resource=False)
                    obj.children.append(d)
        ret =  super(InterfaceSerializer, self).to_representation(obj)
        self._add_uris(ret)
        self._add_device_uri(ret)
        return ret

class InterfaceViewset(BaseMixin, viewsets.ReadOnlyModelViewSet):
    # queryset returned by overridden get_queryset()
    serializer_class = InterfaceSerializer
    lookup_field = 'ifName'
    filter_class = InterfaceFilter
    pagination_class = EsmondPaginator

    def get_queryset(self):
        filters = build_time_filters(self.request)

        ret = IfRef.objects.filter(**filters)

        # filter out hidden ifrefs based on perms
        if not self.request.user.has_perm('api.can_see_hidden_ifref'):
            ret = ret.exclude(ifAlias__contains=":hide:")

        return ret      

# Classes for devices in the "main" rest URI series, ie:
# /v2/device/
# /v2/device/$DEVICE/

class DeviceSerializer(BaseMixin, serializers.ModelSerializer):
    serializer_url_field = EncodedHyperlinkField
    class Meta:
        model = Device
        fields = ('id', 'url', 'name', 'active', 'begin_time', 'end_time',
            'oidsets', 'leaf', 'children',)
        extra_kwargs={'url': {'lookup_field': 'name'}}

    # oidsets attr set read_only=True since that's handled differently
    oidsets = OidsetSerializer(required=False, many=True, read_only=True)
    leaf = serializers.BooleanField(default=False)
    children = serializers.ListField(child=serializers.DictField())
    begin_time = UnixEpochDateField()
    end_time = UnixEpochDateField()

    # These get used by to_representation() to generate 
    # the children/leaf list.
    _child_endpoints = ['interface', 'system', 'all']

    def to_representation(self, obj):
        obj.leaf = False
        obj.children = list()
        ret = super(DeviceSerializer, self).to_representation(obj)
        ## - 'cosmetic' (non database) additions to outgoing payload.
        # add the URIs after the "proper" url was generated.
        self._add_uris(ret)
        # generate children for graphite navigation
        for e in self._child_endpoints:
            ret['children'].append(
                dict(
                    leaf=False, 
                    name=e, 
                    uri=ret.get('uri')+ e + '/'
                )
            )
        return ret

class DeviceViewset(viewsets.ModelViewSet):
    # queryset returned by overridden get_queryset()
    serializer_class = DeviceSerializer
    permission_classes = (DjangoModelPerm,)
    lookup_field = 'name'

    def get_queryset(self):
        filters = build_time_filters(self.request)
        return Device.objects.filter(**filters)

    def _no_verb(self):
        return Response({'error': 'Endpoint only supports GET and PUT'}, status.HTTP_400_BAD_REQUEST)

    def create(self, request, **kwargs):
        """No POST"""
        return self._no_verb()

    def update(self, request, pk=None, **kwargs):
        """Process PUT"""

        instance = self.get_object()
        payload = copy.copy(request.data)

        # pull out oidsets and handle the m2m thing first.
        incoming_oidsets = payload.get('oidsets', [])
        oidsets = list()

        for os in incoming_oidsets:
            try:
                o = OIDSet.objects.get(name=os)
                oidsets.append(o)
            except OIDSet.DoesNotExist:
                return Response({'error': 'Invalid OIDSet: {0}'.format(os)}, status.HTTP_400_BAD_REQUEST)

        instance.oidsets.clear()
        for o in oidsets:
            omap = DeviceOIDSetMap(device=instance, oid_set=o)
            omap.save()

        # deal with the rest
        serializer = self.get_serializer(instance, data=payload, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    def partial_update(self, request, pk=None, **kwargs):
        """No PATCH"""
        return self._no_verb()

    def destroy(self, request, pk=None, **kwargs):
        """No DESTROY"""
        return self._no_verb()

# Subclasses that handles the interface resource nested under the devices, ie: 
# /v1/device/$DEVICE/interface/
# /v1/device/$DEVICE/interface/$INTERFACE/


class NestedInterfaceSerializer(InterfaceSerializer):
    pass

class NestedInterfaceViewset(InterfaceViewset):
    serializer_class = NestedInterfaceSerializer
    filter_class = None # don't inherit filtering from superclass

    def get_queryset(self):
        """
        This is used for the /v2/device/rtr_a/interface/ relation
        in the nested subclass."""
        # base time filters
        filters = build_time_filters(self.request)

        # make sure that it's only the iface paired with the parent router
        if self.kwargs.get('parent_lookup_device__name', None):
            filters['device__name'] = self.kwargs.get('parent_lookup_device__name')

        ret = IfRef.objects.filter(**filters)

        # filter out hidden ifrefs based on perms
        if not self.request.user.has_perm('api.can_see_hidden_ifref'):
            ret = ret.exclude(ifAlias__contains=":hide:")

        return ret

    def get_object(self):
        """
        Get a single filtered interface.
        """
        instance = get_single_iface(self.kwargs.get('ifName'),
            self.kwargs.get('parent_lookup_device__name'), self.request)

        if instance is None:
            raise NotFound

        return instance

# Classes to handle the data fetching on in the "main" REST deal:
# ie: /v2/device/$DEVICE/interface/$INTERFACE/out

class InterfaceDataObject(DataObject):
    pass

class InterfaceDataSerializer(BaseDataSerializer):
    # Other fields defined in superclass.
    agg = serializers.CharField(trim_whitespace=True)
    cf = serializers.CharField(trim_whitespace=True)

    def to_representation(self, obj):
        ret = super(InterfaceDataSerializer, self).to_representation(obj)
        self._add_uris(ret, uri=False)
        return ret

class InterfaceDataViewset(BaseDataViewset):
    queryset = IfRef.objects.all()
    serializer_class = InterfaceDataSerializer

    def _endpoint_alias(self, **kwargs):
        if kwargs.get('subtype', None):
            return '{0}/{1}'.format(kwargs.get('type'), kwargs.get('subtype').rstrip('/'))
        else:
            return kwargs.get('type')

    def retrieve(self, request, **kwargs):
        """
        Incoming kwargs will look like this:

        {'ifName': u'xe-0@2F0@2F0', 'type': u'in', 'name': u'rtr_a'}

        or this:

        {'subtype': u'in', 'ifName': u'xe-0@2F0@2F0', 'type': u'discard', 'name': u'rtr_a'}
        """

        iface = get_single_iface(self.kwargs.get('ifName'),
            self.kwargs.get('name'), self.request)

        if iface is None:
            return Response(
                {'error': 'no such device/interface: dev: {0} int: {1}'.format(kwargs['name'], atdecode(kwargs['ifName']))},
                status.HTTP_400_BAD_REQUEST
                )

        ifname = iface.ifName
        device_name = iface.device.name
        iface_dataset = self._endpoint_alias(**kwargs)

        endpoint_map = self._endpoint_map(iface.device, iface.ifName)

        if iface_dataset not in endpoint_map:
            return Response(
                {'error': 'no such dataset: {0}'.format(iface_dataset)},
                status.HTTP_400_BAD_REQUEST
                )

        oidset = iface.device.oidsets.get(name=endpoint_map[iface_dataset][2])

        obj = InterfaceDataObject()
        obj.url = InterfaceHyperlinkField._oid_detail_url(ifname, device_name, request, iface_dataset)
        obj.datapath = endpoint_map[iface_dataset]
        obj.datapath[2] = oidset.set_name  # set_name defaults to oidset.name, but can be overidden in poller_args
        obj.iface_dataset = iface_dataset
        obj.iface = iface
        obj.user = request.user

        self._parse_data_default_args(request, obj)

        obj.data = list()

        try:
            obj = self._execute_query(oidset, obj)
            serializer = InterfaceDataSerializer(obj.to_dict(), context={'request': request})
            return Response(serializer.data)
        except (QueryErrorException, TimerangeException) as e:
            return Response({'query error': '{0}'.format(str(e))}, status.HTTP_400_BAD_REQUEST)

    def _execute_query(self, oidset, obj):
        """
        Executes a couple of reality checks (making sure that a valid 
        aggregation was requested and checks/limits the time range), and
        then make calls to cassandra backend.
        """

        # If no aggregate level defined in request, set to the frequency, 
        # # otherwise, check if the requested aggregate level is valid.
        if not obj.agg:
            obj.agg = oidset.frequency
        elif obj.agg and not oidset.aggregates:
            raise QueryErrorException('there are no aggregations for oidset {0} - {1} was requested'.format(oidset.name, obj.agg))
        elif obj.agg not in oidset.aggregates:
            raise QueryErrorException('no valid aggregation {0} in oidset {1}'.format(obj.agg, oidset.name))

        # Make sure we're not exceeding allowable time range.
        if not QueryUtil.valid_timerange(obj) and \
            not obj.user.username:
            raise QueryErrorException('exceeded valid timerange for agg level: {0}'.format(obj.agg))


        if obj.agg == oidset.frequency:
            # Fetch the base rate data.
            data = db.query_baserate_timerange(path=obj.datapath, freq=obj.agg*1000,
                    ts_min=obj.begin_time*1000, ts_max=obj.end_time*1000)
        else:
            # Get the aggregation.
            if obj.cf not in AGG_TYPES:
                raise QueryErrorException('%s is not a valid consolidation function' %
                        (obj.cf))
            data = db.query_aggregation_timerange(path=obj.datapath, freq=obj.agg*1000,
                    ts_min=obj.begin_time*1000, ts_max=obj.end_time*1000, cf=obj.cf)

        obj.data = QueryUtil.format_data_payload(data)
        obj.data = Fill.verify_fill(obj.begin_time, obj.end_time,
                obj.agg, obj.data)

        return obj

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

class BulkInterfaceDataObject(DataObject):
    pass

class BulkInterfaceThrottle(BaseBulkThrottle):
    def _check_payload_and_request(self, post_payload):

        if not post_payload.has_key('interfaces') or \
            not post_payload.has_key('endpoint'):
            raise ParseError('JSON payload must have endpoint and interfaces keys.')  

        if not isinstance(post_payload['interfaces'], list) or \
            not isinstance(post_payload['endpoint'], list):
            raise ParseError('Both endpoint and interfaces keys must be a list')

        return len(post_payload.get('interfaces', []))

class BulkInterfaceRequestSerializer(BaseDataSerializer):
    # other fields defined in superclass
    iface_dataset = serializers.ListField(child=serializers.CharField())
    device_names = serializers.ListField(child=serializers.CharField())

class BulkInterfaceRequestViewset(BaseDataViewset):
    throttle_classes = (BulkInterfaceThrottle,)
    # This overrides the global "auth or read only" because this uses 
    # post and the throttle class will perform auth-based gating.
    permission_classes = (AllowAny,)

    def create(self, request, **kwargs):

        if not request.content_type.startswith('application/json'):
            return Response({'error', 'Must post content-type: application/json header and json-formatted payload.'}, status.HTTP_400_BAD_REQUEST)

        if not request.data:
            return Response({'error', 'No data payload POSTed.'}, status.HTTP_400_BAD_REQUEST)

        if not request.data.has_key('interfaces') or not \
            request.data.has_key('endpoint'):
            return Response({'error', 'Payload must contain keys interfaces and endpoint.'}, status.HTTP_400_BAD_REQUEST)

        # set up basic return envelope
        ret_obj = BulkInterfaceDataObject()
        ret_obj.iface_dataset = request.data['endpoint']
        ret_obj.data = []
        ret_obj.device_names = []
        ret_obj.url = reverse('bulk-interface', request=request)

        self._parse_data_default_args(request, ret_obj)

        # process request
        for i in request.data['interfaces']:
            device_name = i['device'].rstrip('/').split('/')[-1]
            iface_name = i['iface']

            # XXX(mmg): should we do an "if in" test first to avoid dupes?
            ret_obj.device_names.append(device_name)

            device = Device.objects.get(name=device_name)
            endpoint_map = self._endpoint_map(device, iface_name)

            for end_point in request.data['endpoint']:

                if end_point not in endpoint_map:
                    return Response({'error': 'no such dataset {0}'.format(end_point)}, status.HTTP_400_BAD_REQUEST)

                oidset = device.oidsets.get(name=endpoint_map[end_point][2])

                obj = BulkInterfaceDataObject()
                obj.datapath = endpoint_map[end_point]
                obj.iface_dataset = end_point
                obj.iface = iface_name

                obj.begin_time = ret_obj.begin_time
                obj.end_time = ret_obj.end_time
                obj.cf = ret_obj.cf
                obj.agg = ret_obj.agg

                try:
                    data = InterfaceDataViewset()._execute_query(oidset, obj)
                except QueryErrorException, e:
                    return Response({'query error': '{0}'.format(str(e))}, status.HTTP_400_BAD_REQUEST)

                row = dict(
                    data=data.data,
                    path={'dev': device_name,'iface': iface_name,'endpoint': end_point}
                )

                ret_obj.data.append(row)

        serializer = BulkInterfaceRequestSerializer(ret_obj.to_dict(), context={'request': request})
        return Response(serializer.data, status.HTTP_201_CREATED)

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
    pass

class TimeseriesRequestSerializer(BaseDataSerializer):
    def to_representation(self, obj):
        ret = super(TimeseriesRequestSerializer, self).to_representation(obj)
        self._add_uris(ret, uri=False)
        return ret

class TimeseriesRequestViewset(BaseDataViewset):
    """
    The queryset attribute on this non-model resource is fake.
    It's there so we can use our custom resource permissions 
    (see models.APIPermission) with the standard DjangoModelPermissions
    classes.
    """
    queryset = _get_ersatz_esmond_api_queryset('timeseries')
    permission_classes = (DjangoModelPerm,)

    def _ts_url(self, request, **kwargs):
        return reverse(
            'timeseries',
            kwargs={
                'ts_type': kwargs.get('ts_type'),
                # datapath keys
                'ts_ns': kwargs.get('ts_ns'),
                'ts_device': kwargs.get('ts_device'),
                'ts_oidset': kwargs.get('ts_oidset'),
                'ts_oid': kwargs.get('ts_oid'),
                'ts_iface': kwargs.get('ts_iface'),
                # /datapath
                'ts_frequency': kwargs.get('ts_frequency'),
            },
            request=request,
        )

    def _get_datapath(self, **kwargs):
        return QueryUtil.decode_datapath([
                kwargs.get('ts_ns'),
                kwargs.get('ts_device'),
                kwargs.get('ts_oidset'),
                kwargs.get('ts_oid'),
                kwargs.get('ts_iface'),
            ])

    def retrieve(self, request, **kwargs):
        obj = TimeseriesDataObject()
        obj.url = self._ts_url(request, **kwargs)
        obj.r_type = kwargs.get('ts_type')
        obj.datapath = self._get_datapath(**kwargs)
        obj.user = request.user

        obj.data = list()

        try:
            obj.agg = int(kwargs.get('ts_frequency', None))
        except ValueError:
            return Response({'error': 'Last segment of URI must be frequency integer'}, status.HTTP_400_BAD_REQUEST)

        if obj.r_type not in QueryUtil.timeseries_request_types:
            return Response(
                {'error': 'Request type must be one of {0} - {1} was given.'.format(QueryUtil.timeseries_request_types, obj.r_type)},
                status.HTTP_400_BAD_REQUEST
                )

        self._parse_data_default_args(request, obj, in_ms=True)

        try:
            obj = self._execute_query(obj)
            serializer = TimeseriesRequestSerializer(obj.to_dict(), context={'request': request})
            return Response(serializer.data)
        except (QueryErrorException, TimerangeException) as e:
            return Response({'query error': '{0}'.format(str(e))}, status.HTTP_400_BAD_REQUEST)

    def _execute_query(self, obj):
        """
        Sanity check the requested timerange, and then make the appropriate
        method call to the cassandra backend.
        """
        # Make sure we're not exceeding allowable time range.
        if not QueryUtil.valid_timerange(obj, in_ms=True) and \
            not obj.user.username:
            raise QueryErrorException('exceeded valid timerange for agg level: {0}'.format(obj.agg))
        
        data = []

        if obj.r_type == 'BaseRate':
            data = db.query_baserate_timerange(path=obj.datapath, freq=obj.agg,
                    ts_min=obj.begin_time, ts_max=obj.end_time)
        elif obj.r_type == 'Aggs':
            if obj.cf not in AGG_TYPES:
                raise QueryErrorException('{0} is not a valid consolidation function'.format(obj.cf))
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
                raise QueryErrorException('The request path {0} has no corresponding keys.'.format([obj.r_type] + obj.datapath + [obj.agg]))

        if obj.r_type != 'RawData':
            obj.data = Fill.verify_fill(obj.begin_time, obj.end_time,
                    obj.agg, obj.data)

        return obj

    def create(self, request, **kwargs):

        # validate the incoming json and data contained therein.
        if not request.content_type.startswith('application/json'):
            return Response({'error': 'Must post content-type: application/json header and json-formatted payload.'},
                status.HTTP_400_BAD_REQUEST)

        if not request.body:
            return Response({'error': 'No data payload POSTed.'}, status.HTTP_400_BAD_REQUEST)

        try:
            input_payload = json.loads(request.body)
        except ValueError:
            return Response({'error': 'POST data payload could not be decoded to a JSON object - given: {0}'.format(bundle.body)},
                status.HTTP_400_BAD_REQUEST)

        if not isinstance(input_payload, list):
            return Response({'error': 'Successfully decoded JSON, but expecting a list - got: {0} from input: {1}'.format(type(input_payload), input_payload)},
                status.HTTP_400_BAD_REQUEST)

        for i in input_payload:
            if not isinstance(i, dict):
                return Response({'error': 'Expecting a JSON formtted list of dicts - contained {0} as an array element.'.format(type(i))},
                    status.HTTP_400_BAD_REQUEST)
            if not i.has_key('ts') or not i.has_key('val'):
                return Response({'error': 'Expecting list of dicts with keys \'val\' and \'ts\' - got: {0}'.format(i)},
                    status.HTTP_400_BAD_REQUEST)
            try:
                int(float(i.get('ts')))
                float(i.get('val'))
            except ValueError:
                return Response({'error': 'Must supply valid numeric args for ts and val dict attributes - got: {0}'.format(i)},
                    status.HTTP_400_BAD_REQUEST)

        objs = list()

        for i in input_payload:

            obj = TimeseriesDataObject()

            obj.r_type = kwargs.get('ts_type')
            obj.datapath = self._get_datapath(**kwargs)
            obj.ts = i.get('ts')
            obj.val = i.get('val')

            try:
                obj.agg = int(kwargs.get('ts_frequency', None))
            except ValueError:
                return Response({'error': 'Last segment of URI must be frequency integer'}, status.HTTP_400_BAD_REQUEST)

            if obj.r_type not in QueryUtil.timeseries_request_types:
                return Response({'error': 'Request type must be one of {0} - {1} was given.'.format(QueryUtil.timeseries_request_types, obj.r_type)},
                    status.HTTP_400_BAD_REQUEST)

            # Currently only doing raw and base.
            if obj.r_type not in [ 'RawData', 'BaseRate' ]:
                return Response({'error': 'Only POSTing RawData or BaseRate currently supported.'},
                    status.HTTP_400_BAD_REQUEST)

            objs.append(obj)

        try:
            self._execute_inserts(objs)
            return Response('', status.HTTP_201_CREATED)
        except QueryErrorException, e:
            return Response({'query error': '{0}'.format(str(e))}, status.HTTP_400_BAD_REQUEST)


    def _execute_inserts(self, objs):
        """
        Iterate through a list of TimeseriesDataObject, execute the 
        appropriate inserts, and then explicitly flush the db so the 
        inserts don't sit in the batch wating for more data to auto-flush.

        snmp:rtr_test:FastPollHC:ifHCInOctets:30000:2015
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

class BulkTimeseriesDataObject(DataObject):
    pass

class BulkTimeseriesThrottle(BaseBulkThrottle):
    def _check_payload_and_request(self, post_payload):

        if not post_payload.has_key('paths') or \
            not isinstance(post_payload['paths'], list):
            raise ParseError('Payload must contain the element paths and that element must be a list.')

        return len(post_payload.get('paths', []))

class BulkTimeseriesSerializer(BaseDataSerializer):
    def to_representation(self, obj):
        ret = super(BulkTimeseriesSerializer, self).to_representation(obj)
        self._add_uris(ret, uri=False)
        return ret

class BulkTimeseriesViewset(BaseDataViewset):
    throttle_classes = (BulkTimeseriesThrottle,)
    # This overrides the global "auth or read only" because this uses 
    # post and the throttle class will perform auth-based gating.
    permission_classes = (AllowAny,)

    def create(self, request, **kwargs):
        
        # validate the incoming json and data contained therein.
        if not request.content_type.startswith('application/json'):
            return Response({'error': 'Must post content-type: application/json header and json-formatted payload.'},
                status.HTTP_400_BAD_REQUEST)

        if not request.data:
            return Response({'error': 'No data payload POSTed.'}, status.HTTP_400_BAD_REQUEST)

        if not request.data.has_key('paths') or not \
            request.data.has_key('type'):
            return Response({'error': 'Payload must contain keys paths and type.'},
                status.HTTP_400_BAD_REQUEST)

        if not isinstance(request.data['paths'], list):
            return Response({'error': 'Payload paths element must be a list - got: {0}'.format(bundle.data['lists'])},
                status.HTTP_400_BAD_REQUEST)

        ret_obj = BulkTimeseriesDataObject()
        ret_obj.url = reverse('bulk-timeseries', request=request)
        ret_obj.agg = None
        ret_obj.r_type = request.data.get('type')

        ret_obj.data = []

        self._parse_data_default_args(request, ret_obj, in_ms=True)

        for p in request.data['paths']:
            obj = BulkTimeseriesDataObject()
            obj.r_type = request.data['type']
            obj.cf = ret_obj.cf
            obj.begin_time = ret_obj.begin_time
            obj.end_time = ret_obj.end_time
            obj.datapath = p
            obj.agg = int(obj.datapath.pop())

            try:
                obj = TimeseriesRequestViewset()._execute_query(obj)
            except QueryErrorException, e:
                return Response({'query error': '{0}'.format(str(e))}, status.HTTP_400_BAD_REQUEST)

            row = {
                'data': obj.data,
                'path': obj.datapath + [obj.agg]
            }

            ret_obj.data.append(row)

        serializer = BulkTimeseriesSerializer(ret_obj.to_dict(), context={'request': request})
        return Response(serializer.data, status.HTTP_201_CREATED)

"""
**/v2/outlet/**

/v2/outlet/
"""

OUTLET_DATASETS = ['load']

class NestedOutletHyperlinkField(relations.HyperlinkedIdentityField):
    """
    URLS for nested PDU resources/etc.
    """

    @staticmethod
    def _get_outlet_detail(outlet_id, device_name, request, format=None):
        return reverse(
            'pdu-outlet-detail',
            kwargs={
                'outletID': outlet_id,
                'parent_lookup_device__name': device_name,
            },
            request=request,
            format=format,
            ).rstrip('/')

    @staticmethod
    def _get_dataset_detail(outlet_id, device_id, request, dataset):
        return NestedOutletHyperlinkField._get_outlet_detail(outlet_id, device_id, request) + '/' + dataset

    def get_url(self, obj, view_name, request, format):
        if hasattr(obj, 'pk') and obj.pk is None:
            return None

        return self._get_outlet_detail(obj.outletID, obj.device.name, request, format)

class OutletSerializer(BaseMixin, serializers.ModelSerializer):
    serializer_url_field = NestedOutletHyperlinkField

    class Meta:
        model = OutletRef
        fields = ('begin_time',
            'children',
            'end_time', 
            'id', 
            'leaf',
            'outletControlState',
            'outletID',
            'outletName',
            'outletStatus',
            'url',)
        extra_kwargs={'url': {'lookup_field': 'outletID',}}

    children = serializers.ListField(child=serializers.DictField())
    leaf = serializers.BooleanField(default=False)

    begin_time = UnixEpochDateField()
    end_time = UnixEpochDateField()

    def to_representation(self, obj):
        obj.children = list()
        obj.leaf = False
        # add in dataset details
        for ds in OUTLET_DATASETS:
            d = dict(
                leaf=False,
                name=ds,
                url=NestedOutletHyperlinkField._get_dataset_detail(obj.outletID, obj.device.name, self.context.get('request'), ds)
            )
            self._add_uris(d, resource=False)
            obj.children.append(d)
        ret =  super(OutletSerializer, self).to_representation(obj)
        self._add_uris(ret)
        self._add_pdu_uri(ret)
        return ret


"""
**/v2/pdu/**

/v2/pdu/
/v2/pdu/$NAME/
/v2/pdu/$NAME/outlet/
/v2/pdu/$NAME/outlet/$NAME/
/v2/pdu/$NAME/outlet/$NAME/$DATASET
"""

class PDUSerializer(DeviceSerializer):
    class Meta(DeviceSerializer.Meta):
        # Inherit most of the stuff from superclass, but override this bit 
        # with the view name so the URLs get generated correctly.
        extra_kwargs={'url': {'lookup_field': 'name', 'view_name': 'pdu-detail'}}

    _child_endpoints = ['outlet']

class PDUViewset(DeviceViewset):
    # queryset returned by overridden get_queryset()
    serializer_class = PDUSerializer
    lookup_field = 'name'

    def get_queryset(self):
        """
        queryset = Device.objects.filter(pk__in=OutletRef.objects.values_list("device__pk")).distinct()
        """
        filters = build_time_filters(self.request)
        filters['pk__in'] = OutletRef.objects.values_list("device__pk")

        return Device.objects.filter(**filters).distinct()

    def _no_verb(self):
        """Change superclass message."""
        return Response({'error': 'Endpoint only supports GET.'}, status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None, **kwargs):
        """No PUT - overriding superclass PUT verb."""
        return self._no_verb()


class NestedOutletSerializer(OutletSerializer):
    pass

class NestedOutletViewset(BaseMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = NestedOutletSerializer
    lookup_field = 'outletID'
    # filter_class = InterfaceFilter
    pagination_class = EsmondPaginator

    def get_queryset(self):
        # base time filters
        filters = build_time_filters(self.request)

        # make sure that it's only the iface paired with the parent router
        if self.kwargs.get('parent_lookup_device__name', None):
            filters['device__name'] = self.kwargs.get('parent_lookup_device__name')

        ret = OutletRef.objects.filter(**filters)

        return ret

    def get_object(self):

        instance = get_single_outlet(self.kwargs.get('outletID'), self.kwargs.get('parent_lookup_device__name'), self.request)

        if instance is None:
            raise NotFound

        return instance

class OutletDataObject(DataObject):
    pass

class OutletDataSerializer(BaseDataSerializer):
    def to_representation(self, obj):
        ret = super(OutletDataSerializer, self).to_representation(obj)
        self._add_uris(ret, uri=False)
        return ret

class OutletDataViewset(BaseDataViewset):
    queryset = OutletRef.objects.all()
    serializer_class = OutletDataSerializer
    def retrieve(self, request, **kwargs):
        """
        kwargs look like this:

        {'outlet_dataset': u'load', 'outletID': u'AA', 'name': u'sentry_pdu'}
        """

        outlet = get_single_outlet(kwargs.get('outletID'), kwargs.get('name'), request)

        outlet_id = atdecode(kwargs.get('outletID'))

        if not outlet:
            return Response({'error': 'no such device/oulet: dev: {0} outlet: {1}'.format(kwargs.get('name'), outlet_id)},
                status.HTTP_400_BAD_REQUEST
                )

        if not kwargs.get('outlet_dataset') in OUTLET_DATASETS:
            return Response({'error': 'no such dataset: {0}'.format(kwargs.get('outlet_dataset'))},
                status.HTTP_400_BAD_REQUEST)

        oidset_name = 'SentryPoll'
        datapath = [SNMP_NAMESPACE, outlet.device.name, oidset_name, 'outletLoadValue', outlet_id]

        obj = OutletDataObject()
        obj.url = NestedOutletHyperlinkField._get_dataset_detail(outlet_id, kwargs.get('name'), request, kwargs.get('outlet_dataset'))
        obj.outlet = outlet
        obj.datapath = datapath
        obj.outlet_dataset = kwargs.get('outlet_dataset')

        oidset = outlet.device.oidsets.get(name=oidset_name)

        self._parse_data_default_args(request, obj, time_only=True)

        obj.data = list()

        try:
            obj = self._execute_query(oidset, obj)
            serializer = OutletDataSerializer(obj.to_dict(), context={'request': request})
            return Response(serializer.data)
        except (QueryErrorException, TimerangeException) as e:
            return Response({'query error': '{0}'.format(str(e))}, status.HTTP_400_BAD_REQUEST)

    def _execute_query(self, oidset, obj):
        data = db.query_raw_data(obj.datapath, oidset.frequency*1000,
                                 obj.begin_time*1000, obj.end_time*1000)

        obj.data = QueryUtil.format_data_payload(data, coerce_to_bins=oidset.frequency*1000)
        obj.data = Fill.verify_fill(obj.begin_time, obj.end_time, oidset.frequency,
                                    obj.data)

        return obj








