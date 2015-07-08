import copy

from rest_framework import viewsets, serializers, status, fields, relations
from rest_framework.response import Response
from rest_framework.reverse import reverse

from rest_framework_extensions.mixins import NestedViewSetMixin

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

class HyperlinkedRelatedEncodedField(relations.HyperlinkedIdentityField):
    """
    We need this for urls where the lookup_field names need to be 
    atencoded.
    """
    def get_url(self, obj, view_name, request, format):
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, 'pk') and obj.pk is None:
            return None

        lookup_value = getattr(obj, self.lookup_field)
        kwargs = {self.lookup_url_kwarg: atencode(lookup_value)}
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)

class DecodeMixin(object):
    def get_object(self):
        """
        atdecode() the incoming args before the lookup_field lookup happens.
        """
        for k in self.kwargs.keys():
            self.kwargs[k] = atdecode(self.kwargs[k])

        return super(DecodeMixin, self).get_object()

class InterfaceSerializer(serializers.ModelSerializer):
    serializer_url_field = HyperlinkedRelatedEncodedField
    class Meta:
        model = IfRef
        fields = ('ifName','url')
        extra_kwargs={'url': {'lookup_field': 'ifName'}}
        # lookup_field = 'ifName'

class InterfaceViewset(DecodeMixin, viewsets.ModelViewSet):
    queryset = IfRef.objects.all()
    serializer_class = InterfaceSerializer
    lookup_field = 'ifName'

class DeviceSerializer(DecodeMixin, serializers.ModelSerializer):
    serializer_url_field = HyperlinkedRelatedEncodedField
    class Meta:
        model = Device
        fields = ('name', 'url')
        extra_kwargs={'url': {'lookup_field': 'name'}}
        # lookup_field = 'name'

class DeviceViewset(viewsets.ModelViewSet):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    lookup_field = 'name'

class DataSerializer(serializers.Serializer):
    data = fields.DictField()

class DataViewset(viewsets.GenericViewSet):
    queryset = IfRef.objects.all()
    serializer_class = DataSerializer

    def retrieve(self, request, **kwargs):
        print 'retrieve', kwargs
        d = dict(data=dict(ts=3, val='foo'))
        serializer = DataSerializer(d, context={'request': request})
        return Response(serializer.data)


