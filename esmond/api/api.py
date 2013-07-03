import json
import time
import datetime

from django.core.serializers.json import DjangoJSONEncoder
from django.conf.urls.defaults import url
from django.utils.timezone import now

from tastypie.resources import ModelResource, Resource, ALL, ALL_WITH_RELATIONS
from tastypie.api import Api
from tastypie.serializers import Serializer
from tastypie.bundle import Bundle
from tastypie import fields
from tastypie.exceptions import NotFound

from esmond.api.models import Device, IfRef

"""
/$DEVICE/
/$DEVICE/interface/
/$DEVICE/interface/$INTERFACE/
/$DEVICE/interface/$INTERFACE/in
/$DEVICE/interface/$INTERFACE/out
"""

OIDSET_INTERFACE_ENDPOINTS = {
    'FastPollHC': {
        'in': 'ifHCInOctets',
        'out': 'ifHCOutOctets',
    },
    'Errors': {
        'error/in': 'ifInErrors',
        'error/out': 'ifOutErrors',
        'discard/in': 'ifInDiscards',
        'discard/out': 'ifOutDiscards',
    },
    'InfFastPollHC': {
        'in': 'gigeClientCtpPmRealInOctets',
        'out': 'gigeClientCtpPmRealOutOctets',
    },
}

def build_time_filters(filters, orm_filters):
    """Build default time filters.

    By default we want only currently active items.  This will inspect
    orm_filters and fill in defaults if they are missing."""

    if 'begin' in filters:
        orm_filters['end_time__gte'] = datetime.datetime.fromtimestamp(
                float(filters['begin']))

    if 'end' in filters:
        orm_filters['begin_time__lte'] = datetime.datetime.fromtimestamp(
                float(filters['end']))

    filter_keys = map(lambda x: x.split("__")[0], orm_filters.keys())
    now = datetime.datetime.now()

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

    def dehydrate_begin_time(self, bundle):
        return int(time.mktime(bundle.data['begin_time'].timetuple()))

    def dehydrate_end_time(self, bundle):
        return int(time.mktime(bundle.data['end_time'].timetuple()))

    def prepend_urls(self):
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

    def get_interface_list(self, request, **kwargs):
        return InterfaceResource().get_list(request, device__name=kwargs['name'])

    def get_interface_detail(self, request, **kwargs):
        return InterfaceResource().get_detail(request,
                device__name=kwargs['name'], ifDescr=kwargs['iface'] )

    def get_interface_data(self, request, **kwargs):
        return InterfaceDataResource().get_detail(request, **kwargs)

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

    def obj_get(self, bundle, **kwargs):
        kwargs['ifDescr'] = kwargs['ifDescr'].replace("_", "/")
        return super(InterfaceResource, self).obj_get(bundle, **kwargs)

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
