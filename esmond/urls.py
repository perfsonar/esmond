from django.conf.urls import url, include

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

from rest_framework import routers
from rest_framework_extensions.routers import ExtendedSimpleRouter

from esmond.api.perfsonar.api_v2 import (
    ArchiveViewset,
    EventTypeDetailViewset,
    TimeSeriesViewset,
)

router = routers.DefaultRouter()
#
# Perfsonar V2 router/etc

PS_ROOT = 'perfsonar'

ps_router = routers.DefaultRouter()
ps_router.register('archive', ArchiveViewset, base_name='archive')

# This object attribute has all of the patterns - helpful
# when you need to look at the view names for reverse(), etc.
# print extended_router.urls

urlpatterns = [
    # Original urls - built in the original api.py files and attached here.
    url(r'^admin/', include(admin.site.urls)),
    ## URL definitions for V2 Perfsonar API
    # main archive/metadata endpoint.
    url(r'{0}/'.format(PS_ROOT), include(ps_router.urls)),
    # event type detail endpoint.
    url(r'{0}/archive/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/?$'.format(PS_ROOT), EventTypeDetailViewset.as_view({'post': 'create', 'get': 'retrieve'})),
    # timeseries data endpoint.
    url(r'{0}/archive/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/(?P<summary_type>[\w\d_.\-@]+)/?$'.format(PS_ROOT), TimeSeriesViewset.as_view({'post': 'create', 'get': 'retrieve'})),
    url(r'{0}/archive/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/(?P<summary_type>[\w\d_.\-@]+)/(?P<summary_window>[\w\d_.\-@]+)/?$'.format(PS_ROOT), TimeSeriesViewset.as_view({'post': 'create', 'get': 'retrieve'})),
]
