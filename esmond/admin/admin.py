from django.contrib import admin

from esmond.api.models import *

admin.site.register(PSMetadata)
admin.site.register(PSPointToPointSubject)
admin.site.register(PSEventTypes)
admin.site.register(PSMetadataParameters)
admin.site.register(UserIpAddress)
