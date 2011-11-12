from django.db import models
from django.contrib import admin
import datetime

class DeviceTag(models.Model):
    name = models.CharField(max_length = 256, unique=True)
    def __unicode__(self):
        return self.name
    class Meta:
        db_table = "devicetag"

class Device(models.Model):
    name = models.CharField(max_length = 256)
    begin_time = models.DateTimeField(default=datetime.datetime.now)
    end_time = models.DateTimeField(default=datetime.datetime.max)
    community = models.CharField(max_length = 128)
    active = models.BooleanField(default = True)
    devicetag = models.ManyToManyField(DeviceTag, through = "DeviceTagMap")
    oidset = models.ManyToManyField("OIDSet", through = "DeviceOIDSetMap")
    def __unicode__(self):
        return self.name
    class Meta:
        db_table = "device"

class DeviceTagMap(models.Model):
    deviceID = models.ForeignKey(Device, db_column="deviceid")
    deviceTagId = models.ForeignKey(DeviceTag, db_column="devicetagid")
    class Meta:
        db_table = "devicetagmap"

class OIDType(models.Model):
    name = models.CharField(max_length=256)
    def __unicode__(self):
        return self.name
    class Meta:
        db_table = "oidtype"

class OIDCorrelator(models.Model):
    name = models.CharField(max_length=256)
    def __unicode__(self):
        return self.name
    class Meta:
        db_table = "oidcorrelator"

class OID(models.Model):
    name = models.CharField(max_length=256)
    aggregate = models.BooleanField(default = False)
    OIDtypeId = models.ForeignKey(OIDType,db_column = "oidtypeid")
    OIDCorrelatorId = models.ForeignKey(OIDCorrelator,blank=True,
                                        null=True,db_column="oidcorrelatorid")
    def __unicode__(self):
        return self.name
    class Meta:
        db_table = "oid"

class Poller(models.Model):
    name = models.CharField(max_length=256)
    def __unicode__(self):
        return self.name
    class Meta:
        db_table = "poller"

class OIDSet(models.Model):
    name = models.CharField(max_length=256)
    frequency = models.IntegerField()
    pollerid = models.ForeignKey(Poller,db_column="pollerid")
    poller_args = models.CharField(max_length=256)
    oid = models.ManyToManyField(OID, through = "OIDSetMember")
    def __unicode__(self):
        return self.name
    class Meta:
        db_table = "oidset"

class OIDSetMember(models.Model):
    OIDId = models.ForeignKey(OID,db_column="oidid")
    OIDSetId = models.ForeignKey(OIDSet,db_column="oidsetid")
    class Meta:
        db_table = "oidsetmember"

class DeviceOIDSetMap(models.Model):
    deviceId = models.ForeignKey(Device,db_column="deviceid")
    OIDSetId = models.ForeignKey(OIDSet,db_column="oidsetid")
    class Meta:
        db_table = "deviceoidsetmap"

admin.site.register(DeviceTag)
admin.site.register(DeviceTagMap)
admin.site.register(OIDCorrelator)
admin.site.register(OIDType)
admin.site.register(OID)
admin.site.register(Poller)
class OIDSetDeviceInline(admin.TabularInline):
    model=DeviceOIDSetMap
    extra = 3
    max_num = 50
class DeviceAdmin(admin.ModelAdmin):
    inlines=(OIDSetDeviceInline,)
admin.site.register(Device,DeviceAdmin)
class OIDSetInline(admin.TabularInline):
    model=OIDSetMember
    extra=5
    max_num = 50
class OIDSetAdmin(admin.ModelAdmin):
    inlines=(OIDSetInline,)
admin.site.register(OIDSet,OIDSetAdmin)
