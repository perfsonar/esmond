from django.conf.urls import url, patterns, include

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

from esmond.api.api import v1_api
from esmond.api.perfsonar.api import perfsonar_api

from rest_framework import routers
from rest_framework_extensions.routers import ExtendedSimpleRouter

from esmond.api.api_v2 import (
    BulkInterfaceRequestViewset,
    BulkTimeseriesViewset,
    DeviceViewset,
    InterfaceViewset,
    InterfaceDataViewset,
    InventoryViewset,
    NestedInterfaceViewset,
    NestedOutletViewset,
    OidsetMapViewset,
    OidsetViewset,
    OutletDataViewset,
    OutletViewset,
    PDUViewset,
    TimeseriesRequestViewset,
)

from esmond.api.perfsonar.api_v2 import (
    ArchiveViewset,
    EventTypeDetailViewset,
    TimeSeriesViewset,
)

router = routers.DefaultRouter()
router.register('oidset', OidsetViewset)
router.register('oidsetmap', OidsetMapViewset, base_name='oidsetmap')
router.register('interface', InterfaceViewset, base_name='interface')
router.register('outlet', OutletViewset, base_name='outlet')
router.register('inventory', InventoryViewset, base_name='inventory')
# /device/ is registered as a nested resource below. need this
# to make it show up in the DRF browsable API.
router.register('device', DeviceViewset, base_name='device')
# /pdu/ is registered as a nested resource below. need this
# to make it show up in the DRF browsable API.
router.register('pdu', PDUViewset, base_name='pdu')

extended_router = ExtendedSimpleRouter()

device_router = extended_router.register(
    r'device',
    DeviceViewset,
    base_name='device',
)
device_router.register(
    r'interface',
    NestedInterfaceViewset,
    base_name='device-interface',
    parents_query_lookups=['device__name']
)

pdu_router = extended_router.register(
    r'pdu',
    PDUViewset,
    base_name='pdu'
)
pdu_router.register(
    r'outlet',
    NestedOutletViewset,
    base_name='pdu-outlet',
    parents_query_lookups=['device__name']
)

#
# Perfsonar V2 router/etc

PS_ROOT = 'perfsonar'

ps_router = routers.DefaultRouter()
ps_router.register('archive', ArchiveViewset, base_name='archive')

# This object attribute has all of the patterns - helpful
# when you need to look at the view names for reverse(), etc.
# print extended_router.urls

urlpatterns = patterns('',
    # Original urls - built in the original api.py files and attached here.
    (r'^admin/', include(admin.site.urls)),
    (r'', include(v1_api.urls)),
    # (r'', include(perfsonar_api.urls)), # old ps api
    ## URL definitions for V2 esmond API.
    # standard root level urls
    (r'v2/',include(router.urls)),
    # nested urls for main API
    (r'v2/',include(extended_router.urls)),
    # "nested" urls that fetch interface data for main API
    (r'v2/device/(?P<name>[^/]+)/interface/(?P<ifName>[^/]+)/(?P<type>[^/]+)/?$', InterfaceDataViewset.as_view({'get': 'retrieve'})),
    (r'v2/device/(?P<name>[^/]+)/interface/(?P<ifName>[^/]+)/(?P<type>[^/]+)/(?P<subtype>.+)/?$', InterfaceDataViewset.as_view({'get': 'retrieve'})),
    # bulk data retrieval endpoints
    url(r'v2/bulk/interface/', BulkInterfaceRequestViewset.as_view({'post': 'create'}), name='bulk-interface'),
    url(r'v2/bulk/timeseries/', BulkTimeseriesViewset.as_view({'post': 'create'}), name='bulk-timeseries'),
    # timeseries endpoint
    # /v1/timeseries/$TYPE/$NS/$DEVICE/$OIDSET/$OID/$INTERFACE/$FREQUENCY
    url(r'v2/timeseries/(?P<ts_type>[^/]+)/(?P<ts_ns>[^/]+)/(?P<ts_device>[^/]+)/(?P<ts_oidset>[^/]+)/(?P<ts_oid>[^/]+)/(?P<ts_iface>[^/]+)/(?P<ts_frequency>[^/]+)/?$', 
        TimeseriesRequestViewset.as_view({'post': 'create', 'get': 'retrieve'}), name='timeseries'),
    # nested uri for pdu/outlet data endpoint
    (r'v2/pdu/(?P<name>[^/]+)/outlet/(?P<outletID>[^/]+)/(?P<outlet_dataset>[^/]+)/?$', OutletDataViewset.as_view({'get': 'retrieve'})),
    ## URL definitions for V2 Perfsonar API
    # main archive/metadata endpoint.
    (r'{0}/'.format(PS_ROOT), include(ps_router.urls)),
    # event type detail endpoint.
    (r'{0}/archive/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/?$'.format(PS_ROOT), EventTypeDetailViewset.as_view({'post': 'create', 'get': 'retrieve'})),
    # timeseries data endpoint.
    (r'{0}/archive/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/(?P<summary_type>[\w\d_.\-@]+)/?$'.format(PS_ROOT), TimeSeriesViewset.as_view({'post': 'create', 'get': 'retrieve'})),
    (r'{0}/archive/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/(?P<summary_type>[\w\d_.\-@]+)/(?P<summary_window>[\w\d_.\-@]+)/?$'.format(PS_ROOT), TimeSeriesViewset.as_view({'post': 'create', 'get': 'retrieve'})),
)
