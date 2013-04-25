import json
import time

from django.core.serializers.json import DjangoJSONEncoder
from django.conf.urls.defaults import url
from django.utils.timezone import now

from tastypie.resources import ModelResource, Resource, ALL, ALL_WITH_RELATIONS
from tastypie.api import Api
from tastypie.serializers import Serializer
from tastypie.bundle import Bundle
from tastypie import fields
from tastypie.exceptions import NotFound

from esxsnmp.api.models import Device, IfRef

"""
/$DEVICE/
/$DEVICE/interface/
/$DEVICE/interface/$INTERFACE/
/$DEVICE/interface/$INTERFACE/in
/$DEVICE/interface/$INTERFACE/out
"""

class DeviceSerializer(Serializer):
    def to_json(self, data, options=None):
        data = self.to_simple(data, options)
        if data.has_key('objects'):
            d = data['objects']
        else:
            d = data
        print d
        return json.dumps(d, cls=DjangoJSONEncoder, sort_keys=True)


class DeviceResource(ModelResource):
    class Meta:
        queryset = Device.objects.all()
        resource_name = 'device'
        serializer = DeviceSerializer()
        excludes = ['community', ]
        allowed_methods = ['get']

    def dehydrate_begin_time(self, bundle):
        return int(time.mktime(bundle.data['begin_time'].timetuple()))

    def dehydrate_end_time(self, bundle):
        return int(time.mktime(bundle.data['end_time'].timetuple()))

    def override_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/$" \
                % self._meta.resource_name, self.wrap_view('dispatch_detail'),
                  name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/?$"
                % (self._meta.resource_name,),
                self.wrap_view('get_interface_list'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/(?P<iface>[\w\d_.-]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('get_interface_detail'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<name>[\w\d_.-]+)/interface/(?P<iface>[\w\d_.-]+)/(?P<data>[\w\d_.-/]+)/?$" % (self._meta.resource_name,),
                self.wrap_view('get_interface_data'),
                name="api_get_children"),
                ]

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()

        # if the begin or end time is specified respect that, otherwise filter
        # to show only objects that are valid at the current time
        time_filter = False
        if hasattr(request,'GET'):
            for i in ('begin', 'begin_time', 'end', 'end_time'):
                if i in request.GET:
                    time_filter = True
                    break

        if not time_filter:          
            n = now()
            qs.filter(begin_time__lte=n, end_time__gt=n)

        return qs

    # XXX(jdugan): next steps
    # data formatting
    # time based limits on view
    # decide to how represent -infinity/infinity timestamps
    # figure out what we need from newdb.py
    # add docs, start with stuff in newdb.py
    #
    # add mapping between oidset and REST API.  Something similar to declarative
    # models/resources ala Django models

    def get_interface_list(self, request, **kwargs):
        return InterfaceResource().get_list(request, device__name=kwargs['name'])

    def get_interface_detail(self, request, **kwargs):
        device = self.obj_get(name=kwargs['name'])
        return InterfaceResource().get_detail(request,
                device__name=kwargs['name'], ifDescr=kwargs['iface'] )

    def get_interface_data(self, request, **kwargs):
        return InterfaceDataResource().get_detail(request, **kwargs)

    def get_resource_uri(self, bundle_or_obj):
        """
        Use the name of the Device rather than it's pk.
        """
        kwargs = {
            'resource_name': self._meta.resource_name,
        }

        if isinstance(bundle_or_obj, Bundle):
            kwargs['pk'] = bundle_or_obj.obj.name
        else:
            kwargs['pk'] = bundle_or_obj.name

        if self._meta.api_name is not None:
            kwargs['api_name'] = self._meta.api_name

        return self._build_reverse_url("api_dispatch_detail", kwargs=kwargs)

class InterfaceResource(ModelResource):
    """An interface on a device.

    Note: this resource is always nested under a DeviceResource and is not bound
    into the normal namespace for the API."""

    class Meta:
        resource_name = 'interface'
        queryset = IfRef.objects.all()
        allowed_methods = ['get']

    def get_resource_uri(self, bundle_or_obj):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        return '%s%s/%s/' % (
            DeviceResource().get_resource_uri(obj.device),
            self._meta.resource_name,
            obj.ifDescr,)

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
        queryset = IfRef.objects.all()
        allowed_methods = ['get']

    def get_object_list(self, request):
        qs = self._meta.queryset._clone()
        n = now()
        return qs.filter(begin_time__gte=n, end_time__lt=n)

    def get_resource_uri(self, bundle_or_obj):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        uri = "%s%s" % (
                InterfaceResource().get_resource_uri(obj.iface),
                obj.datapath)
        return uri

    def obj_get(self, request, **kwargs):
        try:
            iface = IfRef.objects.get( device__name=kwargs['name'],
                    ifDescr=kwargs['iface'])
        except IfRef.DoesNotExist:
            raise NotFound("no such device/interface")

        datapath = kwargs['data'].rstrip('/')

        if datapath.count('/') == 0:
            data_set = 'traffic'
            args = datapath
        else:
            data_set, args = datapath.split('/', 1)

        obj = InterfaceDataObject()
        obj.iface = iface
        obj.datapath = datapath

        filters = getattr(request, 'GET', {})

        if filters.has_key('begin'):
            obj.begin_time = filters['begin']
        else:
            obj.begin_time = int(time.time() - 3600)

        if filters.has_key('end'):
            obj.end_time = filters['end']
        else:
            obj.end_time = int(time.time())

        if filters.has_key('cf'):
            obj.cf = filters['cf']
        else:
            obj.cf = 'average'

        if filters.has_key('agg'):
            obj.agg = filters['agg']
        else:
            obj.agg="30"

        f = getattr(self, "data_%s" % data_set, None)
        if f:
            data = f(request, obj, args)
        else:
            raise NotFound("no such dataset")

        return data

    def data_traffic(self, request, obj, args):
        if args not in ['in', 'out']:
            raise NotFound("no such sub dataset")

        obj.data = [[0,10], [30,20], [60, 40]]

        return obj

v1_api = Api(api_name='v1')
v1_api.register(DeviceResource())
