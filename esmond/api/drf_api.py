import calendar
import collections
import copy
import datetime
import inspect
import time
import urlparse

import pprint

pp = pprint.PrettyPrinter(indent=4)

from rest_framework import (viewsets, serializers, status, 
        fields, relations, pagination, mixins)
from rest_framework.response import Response
from rest_framework.reverse import reverse

from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_extensions.fields import ResourceUriField

import rest_framework_filters as filters

from .models import *
from esmond.api import SNMP_NAMESPACE, ANON_LIMIT, OIDSET_INTERFACE_ENDPOINTS
from esmond.util import atdecode, atencode
from esmond.api.dataseries import QueryUtil, Fill
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
        return datetime.datetime.utcfromtimestamp(int(value))

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
    agg = serializers.CharField(trim_whitespace=True)
    cf = serializers.CharField(trim_whitespace=True)
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

    def _parse_data_default_args(self, request, obj):

        # depending on http method...
        filter_map = dict(
            GET=getattr(request, 'GET', {}),
            POST=getattr(request, 'data', {}),
        )

        filters = filter_map.get(request.method, {})

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

#
# Filter classes
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

#
# Endpoints for main URI series.
# 

"""
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

class OidsetSerializer(serializers.ModelSerializer):
    class Meta:
        model = OIDSet
        fields = ('name',)

    def to_representation(self, obj):
        ret = super(OidsetSerializer, self).to_representation(obj)
        return ret.get('name')

    # # Read only, so don't need this.
    # def to_internal_value(self, data):
    #     return super(OidsetSerializer, self).to_internal_value(data)

class OidsetViewset(viewsets.ReadOnlyModelViewSet):
    queryset = OIDSet.objects.all()
    model = OIDSet
    serializer_class = OidsetSerializer

# Code to deal with handling interface endpoints in the main REST series.
# ie: /v2/interface/
# Also subclassed by the interfaces nested under the device endpoint.

class InterfacePaginator(pagination.LimitOffsetPagination):
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
            return super(InterfacePaginator, self).get_next_link()

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

    # XXX(mmg) - will also need to put in Meta "pagination?" element?


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
    queryset = IfRef.objects.all()
    serializer_class = InterfaceSerializer
    lookup_field = 'ifName'
    filter_class = InterfaceFilter
    pagination_class = InterfacePaginator

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

    oidsets = OidsetSerializer(required=False, many=True)
    leaf = serializers.BooleanField(default=False)
    children = serializers.ListField(child=serializers.DictField())
    begin_time = UnixEpochDateField()
    end_time = UnixEpochDateField()

    def to_representation(self, obj):
        obj.leaf = False
        obj.children = list()
        ret = super(DeviceSerializer, self).to_representation(obj)
        ## - 'cosmetic' (non database) additions to outgoing payload.
        # add the URIs after the "proper" url was generated.
        self._add_uris(ret)
        # generate children for graphite navigation
        for e in ['interface', 'system', 'all']:
            ret['children'].append(
                dict(
                    leaf=False, 
                    name=e, 
                    uri=ret.get('uri')+ e + '/'
                )
            )
        return ret

class DeviceViewset(viewsets.ModelViewSet):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    lookup_field = 'name'

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
        This is used for the /v2/device/rtr_a/interface/ relation.
        In the nested subclass since there is no filtering on 
        this endpoint and don't want this logic to potentailly 
        interfere with filtering on the /v2/interface/ endpoint.
        """
        if self.kwargs.get('parent_lookup_device__name', None):
            return IfRef.objects.filter(device__name=self.kwargs.get('parent_lookup_device__name'))
        else:
            return super(InterfaceViewset, self).get_queryset()

# Classes to handle the data fetching on in the "main" REST deal:
# ie: /v2/device/$DEVICE/interface/$INTERFACE/out

class InterfaceDataObject(DataObject):
    pass

class InterfaceDataSerializer(BaseDataSerializer):
    # Fields defined in superclass.

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

        try:
            iface = IfRef.objects.get(
                ifName=atdecode(kwargs.get('ifName')),
                device__name=atdecode(kwargs.get('name')),
                )
        except IfRef.DoesNotExist:
            return Response(
                {'error': 'no such device/interface: dev: {0} int: {1}'.format(kwargs['name'], atdecode(kwargs['ifName']))},
                status.HTTP_400_BAD_REQUEST
                )

        ifname =  iface.ifName
        device_name = iface.device.name
        iface_dataset = self._endpoint_alias(**kwargs)

        endpoint_map = self._endpoint_map(iface.device, iface.ifName)

        if iface_dataset not in endpoint_map:
            return Response(
                {'error': 'no such dataset: {0}'.format(iface_dataset)}
                )

        oidset = iface.device.oidsets.get(name=endpoint_map[iface_dataset][2])

        obj = InterfaceDataObject()
        obj.url = InterfaceHyperlinkField._oid_detail_url(ifname, device_name, request, iface_dataset)
        obj.datapath = endpoint_map[iface_dataset]
        obj.datapath[2] = oidset.set_name  # set_name defaults to oidset.name, but can be overidden in poller_args
        obj.iface_dataset = iface_dataset
        obj.iface = iface

        self._parse_data_default_args(request, obj)

        obj.data = list()

        try:
            obj = self._execute_query(oidset, obj)
            serializer = InterfaceDataSerializer(obj.to_dict(), context={'request': request})
            return Response(serializer.data)
        except QueryErrorException, e:
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

"""
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

class BulkInterfaceRequestSerializer(BaseDataSerializer):
    # other fields defined in superclass
    iface_dataset = serializers.ListField(child=serializers.CharField())
    device_names = serializers.ListField(child=serializers.CharField())


class BulkInterfaceRequestViewset(BaseDataViewset):
    def create(self, request, **kwargs):
        print pp.pprint(request.data)
        if request.content_type != 'application/json':
            raise BadRequest('Must post content-type: application/json header and json-formatted payload.')

        if not request.data:
            raise BadRequest('No data payload POSTed.')

        if not request.data.has_key('interfaces') or not \
            request.data.has_key('endpoint'):
            raise BadRequest('Payload must contain keys interfaces and endpoint.')

        ret_obj = BulkInterfaceDataObject()
        ret_obj.iface_dataset = request.data['endpoint']
        ret_obj.data = []
        ret_obj.device_names = []
        ret_obj.url = reverse('bulk-interface', request=request)

        self._parse_data_default_args(request, ret_obj)

        serializer = BulkInterfaceRequestSerializer(ret_obj.to_dict(), context={'request': request})
        return Response(serializer.data, status.HTTP_201_CREATED)






