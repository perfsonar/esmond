import calendar
import collections
import copy
import datetime
import time
import urlparse

import pprint

pp = pprint.PrettyPrinter(indent=4)

from rest_framework import viewsets, serializers, status, fields, relations
from rest_framework.response import Response
from rest_framework.reverse import reverse

from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_extensions.fields import ResourceUriField

from .models import *
from esmond.api import SNMP_NAMESPACE, ANON_LIMIT, OIDSET_INTERFACE_ENDPOINTS
from esmond.util import atdecode, atencode

#
# Superclasses, mixins, helpers,etc.
#

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

# Code to deal with handling interface endpoints in the main REST series.
# ie: /v2/interface/
# Also subclassed by the interfaces nested under the device endpoint.

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
        return reverse(
            'device-interface-detail',
            kwargs={
                'ifName': atencode(ifname),
                'parent_lookup_device__name': atencode(device_name),
            },
            request=request,
            format=format,
            )

    @staticmethod
    def _oid_detail_url(ifname, device_name, request, alias):
        """
        Helper method for oid endpoints to call.
        """
        return InterfaceHyperlinkField._iface_detail_url(ifname, device_name, request) + alias

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

#
# Endpoints for main URI series.
# 

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
                    print 'XXX', ii.endpoint_alias
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

    def get_queryset(self):
        if self.kwargs.get('parent_lookup_device__name', None):
            return IfRef.objects.filter(device__name=self.kwargs.get('parent_lookup_device__name'))
        else:
            return super(InterfaceViewset, self).get_queryset()

    def list(self, request, **kwargs):
        ret = super(InterfaceViewset, self).list(request, **kwargs)
        # I have no idea why we decided to stuff a perfectly good list of 
        # json objects into this dict with a children key, but we did.
        envelope = collections.OrderedDict()
        envelope['children'] = copy.copy(ret.data)
        ret.data = envelope
        # XXX(mmg) will the meta: {} crap be here too?
        return ret

# Classes for devices in the "main" rest URI series, ie:
# /v2/device/$DEVICE/interface/

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
                    uri=ret.get('uri')+e
                )
            )
        return ret

class DeviceViewset(viewsets.ModelViewSet):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    lookup_field = 'name'


# Not sure if we need different resources for the nested interface resources,
# but slip in these subclasses just in case. Handles the interface nested 
# under the devices, ie: /v1/device/$DEVICE/interface/$INTERFACE/

class NestedInterfaceSerializer(InterfaceSerializer):
    pass

class NestedInterfaceViewset(InterfaceViewset):
    serializer_class = NestedInterfaceSerializer

# Classes to handle the data fetching on in the "main" REST deal:
# ie: /v2/device/$DEVICE/interface/$INTERFACE/out

class InterfaceDataObject(DataObject):
    pass

class InterfaceDataSerializer(BaseMixin, serializers.Serializer):
    url = fields.URLField()
    data = serializers.ListField(child=serializers.DictField())
    agg = serializers.CharField(trim_whitespace=True)
    cf = serializers.CharField(trim_whitespace=True)
    begin_time = serializers.IntegerField()
    end_time = serializers.IntegerField()

    def to_representation(self, obj):
        ret = super(InterfaceDataSerializer, self).to_representation(obj)
        self._add_uris(ret, uri=False)
        return ret


class InterfaceDataViewset(viewsets.GenericViewSet):
    queryset = IfRef.objects.all()
    serializer_class = InterfaceDataSerializer

    def _endpoint_alias(self, **kwargs):
        if kwargs.get('subtype', None):
            return '{0}/{1}'.format(kwargs.get('type'), kwargs.get('subtype').rstrip('/'))
        else:
            return kwargs.get('type')

    def _endpoint_map(self, iface):
        endpoint_map = {}

        for oidset in iface.device.oidsets.all():
            if oidset.name not in OIDSET_INTERFACE_ENDPOINTS.endpoints:
                continue

            for endpoint, varname in \
                    OIDSET_INTERFACE_ENDPOINTS.endpoints[oidset.name].iteritems():
                endpoint_map[endpoint] = [
                    SNMP_NAMESPACE,
                    iface.device.name,
                    oidset.name,
                    varname,
                    iface.ifName
                ]

        return endpoint_map

    def retrieve(self, request, **kwargs):
        """
        Incoming kwargs will look like this:

        {'ifName': u'xe-0@2F0@2F0', 'type': u'in', 'name': u'rtr_a'}

        or this:

        {'subtype': u'in', 'ifName': u'xe-0@2F0@2F0', 'type': u'discard', 'name': u'rtr_a'}
        """
        print 'retrieve', kwargs

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

        endpoint_map = self._endpoint_map(iface)

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

        filters = getattr(request, 'GET', {})

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

        obj.data = list()

        serializer = InterfaceDataSerializer(obj.to_dict(), context={'request': request})
        return Response(serializer.data)


