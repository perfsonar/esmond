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


class InterfaceHyperlinkField(relations.HyperlinkedIdentityField):
    """
    Generate urls to "fully qualified" interface detail.
    """
    def get_url(self, obj, view_name, request, format):
        if hasattr(obj, 'pk') and obj.pk is None:
            return None

        lookup_value = getattr(obj, self.lookup_field)
        kwargs = { 
            'ifName': atencode(lookup_value),
            'parent_lookup_device__name': obj.device.name,
        }

        view_name = 'device-interface-detail'

        return reverse(view_name, kwargs=kwargs, request=request, format=format)


class InterfaceSerializer(serializers.ModelSerializer):
    serializer_url_field = InterfaceHyperlinkField
    class Meta:
        model = IfRef
        fields = ('ifName','url')
        extra_kwargs={'url': {'lookup_field': 'ifName'}}

class InterfaceViewset(DecodeMixin, viewsets.ModelViewSet):
    queryset = IfRef.objects.all()
    serializer_class = InterfaceSerializer
    lookup_field = 'ifName'



class DeviceSerializer(DecodeMixin, serializers.ModelSerializer):
    serializer_url_field = EncodedHyperlinkField
    class Meta:
        model = Device
        fields = ('url', 'name', 'ifref_set')
        extra_kwargs={'url': {'lookup_field': 'name'}}

    def to_representation(self, obj):
        self.fields['ifref_set'] = NestedInterfaceSerializer(required=False, many=True)
        return super(DeviceSerializer, self).to_representation(obj)

class DeviceViewset(viewsets.ModelViewSet):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    lookup_field = 'name'


# Not sure if we need different resources for the nested interface resources,
# but slip in these subclasses just in case.

class NestedInterfaceSerializer(InterfaceSerializer):
    pass

class NestedInterfaceViewset(InterfaceViewset):
    serializer_class = NestedInterfaceSerializer



class DataSerializer(serializers.Serializer):
    data = fields.DictField() 

class DataViewset(viewsets.GenericViewSet):
    queryset = IfRef.objects.all()
    serializer_class = DataSerializer

    def retrieve(self, request, **kwargs):
        print 'retrieve', kwargs
        m = Device.objects.get(name='rtr_a')
        print m, dir(m)
        d = dict(data=dict(ts=3, val='foo'))
        serializer = DataSerializer(d, context={'request': request})
        return Response(serializer.data)


