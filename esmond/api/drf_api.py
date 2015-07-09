import copy

from rest_framework import viewsets, serializers, status, fields, relations
from rest_framework.response import Response
from rest_framework.reverse import reverse

from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_extensions.fields import ResourceUriField

from .models import *
from esmond.util import atdecode, atencode

class OidsetSerializer(serializers.ModelSerializer):
    class Meta:
        model = OIDSet
        fields = ('name',)

class OidsetViewset(viewsets.ModelViewSet):
    queryset = OIDSet.objects.all()
    model = OIDSet
    serializer_class = OidsetSerializer


class DecodeMixin(object):
    def get_object(self):
        """
        atdecode() the incoming args before the lookup_field lookup happens.
        """
        for k in self.kwargs.keys():
            self.kwargs[k] = atdecode(self.kwargs[k])

        return super(DecodeMixin, self).get_object()

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

# Code to deal with handling interface endpoints in the main REST series.
# ie: /v2/interface/
# Also subclassed by the interfaces nested under the device endpoint.

class InterfaceHyperlinkField(relations.HyperlinkedIdentityField):
    """
    Generate urls to "fully qualified" interface detail url.

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

class InterfaceSerializer(serializers.ModelSerializer):
    serializer_url_field = InterfaceHyperlinkField

    class Meta:
        model = IfRef
        fields = ('url', 'ifName', 'children', 'device', 'device_url',
        'end_time', 'id', 'ifAdminStatus', 'ifAlias', 'ifDescr',
        'ifHighSpeed', 'ifIndex', 'ifMtu', 'ifName', 'ifOperStatus',
        'ifPhysAddress', 'ifSpeed', 'ifType', 'ipAddr', 'begin_time',
        'end_time', )
        extra_kwargs={'url': {'lookup_field': 'ifName'}}

    children = serializers.ListField(child=serializers.DictField())
    device = serializers.SlugRelatedField(queryset=Device.objects.all(), slug_field='name')
    device_url = serializers.URLField()

    def to_representation(self, obj):
        # generate the list of oid endpoints with actual measurements.
        obj.children = []
        for i in obj.device.oidsets.all():
            for ii in i.oids.all():
                if ii.endpoint_alias:
                    obj.children.append( 
                        dict(
                            name=ii.endpoint_alias, 
                            url=self.serializer_url_field._oid_detail_url(obj.ifName, obj.device.name, self.context.get('request'), ii.endpoint_alias)
                        )
                    )
        obj.device_url = self.serializer_url_field._device_detail_url(obj.device.name, self.context.get('request'))
        return super(InterfaceSerializer, self).to_representation(obj)

class InterfaceViewset(DecodeMixin, viewsets.ModelViewSet):
    queryset = IfRef.objects.all()
    serializer_class = InterfaceSerializer
    lookup_field = 'ifName'

# Classes for devices in the "main" rest URI series, ie:
# /v2/device/$DEVICE/interface/

class DeviceSerializer(DecodeMixin, serializers.ModelSerializer):
    serializer_url_field = EncodedHyperlinkField
    class Meta:
        model = Device
        fields = ('url', 'name', 'active', 'begin_time', 'end_time',
            'community', 'oidsets', 'ifref_set',)
        extra_kwargs={'url': {'lookup_field': 'name'}}

    oidsets = OidsetSerializer(required=False, many=True)

    def to_representation(self, obj):
        self.fields['ifref_set'] = NestedInterfaceSerializer(required=False, many=True)
        return super(DeviceSerializer, self).to_representation(obj)

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

class DataSerializer(serializers.Serializer):
    url = fields.URLField()
    data = fields.DictField()

class DataViewset(viewsets.GenericViewSet):
    queryset = IfRef.objects.all()
    serializer_class = DataSerializer

    def _endpoint_alias(self, **kwargs):
        if kwargs.get('subtype', None):
            return '{0}/{1}'.format(kwargs.get('type'), kwargs.get('subtype'))
        else:
            return kwargs.get('type')

    def retrieve(self, request, **kwargs):
        """
        Incoming kwargs will look like this:

        {'ifName': u'xe-0@2F0@2F0', 'type': u'in', 'name': u'rtr_a'}

        or this:

        {'subtype': u'in', 'ifName': u'xe-0@2F0@2F0', 'type': u'discard', 'name': u'rtr_a'}
        """
        iface = IfRef.objects.get(ifName=atdecode(kwargs.get('ifName')))
        ifname =  iface.ifName
        device_name = iface.device.name
        alias = self._endpoint_alias(**kwargs)
        d = dict(
            data=dict(ts=3, val='foo'),
            url=InterfaceHyperlinkField._oid_detail_url(ifname, device_name, request, alias)
        )
        serializer = DataSerializer(d, context={'request': request})
        return Response(serializer.data)


