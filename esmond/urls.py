from django.conf.urls.defaults import *

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

from esmond.api.api import v1_api
from esmond.api.perfsonar.api import perfsonar_api

from rest_framework import routers
from rest_framework_extensions.routers import ExtendedSimpleRouter

from esmond.api.drf_api import (
    DataViewset,
    DeviceViewset,
    InterfaceViewset,
    NestedInterfaceViewset,
    OidsetViewset
)

router = routers.DefaultRouter()
router.register('oidset', OidsetViewset)
router.register('interface', InterfaceViewset)
# /device/ is registered as a nested resource below. need this
# to make it show up in the DRF browsable API.
router.register('device', DeviceViewset)

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

# This object attribute has all of the patterns - helpful
# when you need to look at the view names for reverse(), etc.
# print extended_router.urls

urlpatterns = patterns('',
    (r'^admin/', include(admin.site.urls)),
    (r'', include(v1_api.urls + perfsonar_api.urls)),
    (r'v2/',include(router.urls)),
    (r'v2/',include(extended_router.urls)),
    (r'v2/device/(?P<name>[^/]+)/interface/(?P<ifName>[^/]+)/(?P<type>[^/]+)$', DataViewset.as_view({'get': 'retrieve'})),
    (r'v2/device/(?P<name>[^/]+)/interface/(?P<ifName>[^/]+)/(?P<type>[^/]+)/(?P<subtype>.+)$', DataViewset.as_view({'get': 'retrieve'})),
)
