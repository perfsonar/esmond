from django.contrib import admin

from esxsnmp.api.models import *

class IfRefAdmin(admin.ModelAdmin):
    list_filter = ('deviceid',)

class OIDSetDeviceInline(admin.TabularInline):
    model=DeviceOIDSetMap
    extra = 3
    max_num = 50

class DeviceAdmin(admin.ModelAdmin):
    inlines = (OIDSetDeviceInline, )

class OIDSetInline(admin.TabularInline):
    model = OIDSetMember
    extra = 5
    max_num = 50

class OIDSetAdmin(admin.ModelAdmin):
    inlines = (OIDSetInline, )

admin.site.register(DeviceTag)
admin.site.register(DeviceTagMap)
admin.site.register(OIDCorrelator)
admin.site.register(OIDType)
admin.site.register(OID)
admin.site.register(Poller)
admin.site.register(IfRef,IfRefAdmin)
admin.site.register(Device,DeviceAdmin)
admin.site.register(OIDSet,OIDSetAdmin)
