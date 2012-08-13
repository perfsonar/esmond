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

class IfRef(models.Model):
    deviceid = models.ForeignKey(Device,db_column="deviceid")
    ifIndex = models.IntegerField(db_column="ifindex")
    ifDescr = models.CharField(max_length=512, db_column="ifdescr")
    ifAlias = models.CharField(max_length=512, db_column="ifalias")
# The ifpath is just for us to keep something with problematic characters
# removed
    ifpath = models.CharField(max_length=512)
    ipAddr = models.IPAddressField(blank=True, db_column="ipaddr")
# These should be BigIntegerField's, but that requries Django 1.2
    ifSpeed = models.IntegerField(db_column="ifspeed")
    ifHighSpeed = models.IntegerField(db_column="ifhighspeed")
    ifMtu = models.IntegerField(db_column="ifmtu")
    ifType = models.IntegerField(db_column="iftype")
# Django doesn't have a char() based field, only varchar(). The difference
# is only at DB creation time so this will work fine.
    ifOperStatus = models.CharField(max_length=1, db_column="ifoperstatus")
    ifAdminStatus = models.CharField(max_length=1, db_column="ifadminstatus")
    begin_time = models.DateTimeField(default=datetime.datetime.now)
    end_time = models.DateTimeField(default=datetime.datetime.max)
# There is no Django MAC address field. 
#    ifPhysAddress = models.MacAddressField()
#
    def __unicode__(self):
        return "%s (%s)"%(self.ifDescr,self.ifIndex)
    class Meta:
        db_table = "ifref"
# Unique together is desirable, maybe even needed. But it will be tricky to
# put in after the fact. Adding the ifpath column will have them all defaulting
# to blank, making for lots of non-unique combinations.
#        unique_together = ("deviceid","ifpath")

admin.site.register(DeviceTag)
admin.site.register(DeviceTagMap)
admin.site.register(OIDCorrelator)
admin.site.register(OIDType)
admin.site.register(OID)
admin.site.register(Poller)
class IfRefAdmin(admin.ModelAdmin):
    list_filter = ('deviceid',)
admin.site.register(IfRef,IfRefAdmin)
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
