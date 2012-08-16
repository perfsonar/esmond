from django.db import models
import datetime

from esxsnmp.util import datetime_to_unixtime

class DeviceTag(models.Model):
    """A tag for a :py:class:`.Device.`"""

    name = models.CharField(max_length = 256, unique=True)

    class Meta:
        db_table = "devicetag"

    def __unicode__(self):
        return self.name

class Device(models.Model):
    """A system which is pollable via SNMP.

    Referred to as a Managed Device in SNMP terminology.

    """
    name = models.CharField(max_length = 256)
    begin_time = models.DateTimeField(default=datetime.datetime.now)
    end_time = models.DateTimeField(default=datetime.datetime.max)
    community = models.CharField(max_length = 128)
    active = models.BooleanField(default = True)
    devicetag = models.ManyToManyField(DeviceTag, through = "DeviceTagMap")
    oidset = models.ManyToManyField("OIDSet", through = "DeviceOIDSetMap")

    class Meta:
        db_table = "device"

    def __unicode__(self):
        return self.name

    def to_dict(self):
        return dict(
                begin_time=datetime_to_unixtime(self.begin_time),
                end_time=datetime_to_unixtime(self.end_time),
                name=self.name,
                active=self.active)


class DeviceTagMap(models.Model):
    """Associates a set of :py:class:`.DeviceTag`s with a :py:class:`.Device`"""

    deviceID = models.ForeignKey(Device, db_column="deviceid")
    deviceTagId = models.ForeignKey(DeviceTag, db_column="devicetagid")

    class Meta:
        db_table = "devicetagmap"

class OIDType(models.Model):
    """Defines the type for an :py:class:`.OID`"""

    name = models.CharField(max_length=256)
    class Meta:
        db_table = "oidtype"

    def __unicode__(self):
        return self.name

class OIDCorrelator(models.Model):
    """Defines the name of a correlator for a given :py:class:`.OID`"""

    name = models.CharField(max_length=256)

    class Meta:
        db_table = "oidcorrelator"

    def __unicode__(self):
        return self.name

class Poller(models.Model):
    """Defines a Poller that can be used to collect data."""

    name = models.CharField(max_length=256)

    class Meta:
        db_table = "poller"

    def __unicode__(self):
        return self.name

class OID(models.Model):
    """An Object Identifier.  

    This is a variable that can be measured via SNMP.

    """

    name = models.CharField(max_length=256)
    aggregate = models.BooleanField(default = False)
    OIDtypeId = models.ForeignKey(OIDType,db_column = "oidtypeid")
    OIDCorrelatorId = models.ForeignKey(OIDCorrelator,blank=True,
                                        null=True,db_column="oidcorrelatorid")
    class Meta:
        db_table = "oid"

    def __unicode__(self):
        return self.name

class OIDSet(models.Model):
    """A collection of :py:class:`.OID`s that are collected together."""

    name = models.CharField(max_length=256, help_text="Name for OIDSet.")
    frequency = models.IntegerField(help_text="Polling frequency in seconds.")
    pollerid = models.ForeignKey(Poller,db_column="pollerid", 
        help_text="Which poller to use for this OIDSet")
    poller_args = models.CharField(max_length=256, 
        help_text="Arguments for the Poller")
    oid_set = models.ManyToManyField(OID, through = "OIDSetMember", 
            help_text="List of OIDs in the OIDSet")

    class Meta:
        db_table = "oidset"

    def __unicode__(self):
        return self.name

class OIDSetMember(models.Model):
    """Associate :py:class:`.OID`s with :py:class:`.OIDSets`"""

    OIDId = models.ForeignKey(OID,db_column="oidid")
    OIDSetId = models.ForeignKey(OIDSet,db_column="oidsetid")

    class Meta:
        db_table = "oidsetmember"

class DeviceOIDSetMap(models.Model):
    """Associate :py:class:`.OIDSet`s with :py:class:`.Device`s"""

    deviceId = models.ForeignKey(Device,db_column="deviceid")
    OIDSetId = models.ForeignKey(OIDSet,db_column="oidsetid")

    class Meta:
        db_table = "deviceoidsetmap"

class IfRef(models.Model):
    """Interface metadata.

    Data is stored with a begin_time and end_time.  A new row is only created
    when one or more columns change.  This provides a historical view of the
    interface metadata.
    
    """

    device = models.ForeignKey(Device, db_column="deviceid")
    ifIndex = models.IntegerField(db_column="ifindex")
    ifDescr = models.CharField(max_length=512, db_column="ifdescr")
    ifAlias = models.CharField(max_length=512, db_column="ifalias")
    ipAddr = models.IPAddressField(blank=True, db_column="ipaddr")
    ifSpeed = models.IntegerField(db_column="ifspeed")
    ifHighSpeed = models.IntegerField(db_column="ifhighspeed")
    ifMtu = models.IntegerField(db_column="ifmtu")
    ifType = models.IntegerField(db_column="iftype")
    ifOperStatus = models.CharField(max_length=1, db_column="ifoperstatus")
    ifAdminStatus = models.CharField(max_length=1, db_column="ifadminstatus")
    begin_time = models.DateTimeField(default=datetime.datetime.now)
    end_time = models.DateTimeField(default=datetime.datetime.max)
    ifPhysAddress = models.CharField(max_length=32, db_column="ifphysaddress")

    class Meta:
        db_table = "ifref"

    def __unicode__(self):
        return "%s (%s)"%(self.ifDescr,self.ifIndex)

    def to_dict(self):

        if not self.ifHighSpeed or self.ifHighSpeed == 0:
            speed = self.ifSpeed
        else:
            speed = self.ifHighSpeed * int(1e6)

        return dict(name=self.ifDescr,
                    descr=self.ifAlias,
                    speed=speed, 
                    begin_time=datetime_to_unixtime(self.begin_time),
                    end_time=datetime_to_unixtime(self.end_time),
                    device=self.device.name,
                    ifIndex=self.ifIndex,
                    ifDescr=self.ifDescr,
                    ifAlias=self.ifAlias,
                    ifSpeed=self.ifSpeed,
                    ifHighSpeed=self.ifHighSpeed,
                    ipAddr=self.ipAddr)

class ALUSAPRef(models.Model):
    """Metadata about ALU SAPs."""

    device = models.ForeignKey(Device, db_column="deviceid")
    name = models.CharField(max_length=128)
    sapDescription = models.CharField(max_length=512,
            db_column="sapdescription")
    sapIngressQosPolicyId = models.IntegerField(
            db_column="sapingressqospolicyid")
    sapEgressQosPolicyId = models.IntegerField(
            db_column="sapegressqospolicyid")

    begin_time = models.DateTimeField(default=datetime.datetime.now)
    end_time = models.DateTimeField(default=datetime.datetime.max)

    class Meta:
        db_table = "alusapref"

    def __unicode__(self):
        return "%s %s" % (self.device, self.name)

    def to_dict(self):
        return dict(name=self.name,
                device=self.device.name,
                sapDescription=self.sapDescription,
                sapEgressQosPolicyId=self.sapEgressQosPolicyId,
                sapIngressQosPolicyId=self.sapIngressQosPolicyId,
                end_time=datetime_to_unixtime(self.end_time),
                begin_time=datetime_to_unixtime(self.begin_time))

class LSPOpStatus(models.Model):
    """Metadata about MPLS LSPs."""
    device = models.ForeignKey(Device, db_column="deviceid")
    name = models.CharField(max_length=128)
    srcAddr = models.IPAddressField()
    dstAddr = models.IPAddressField()
    state = models.IntegerField()

    begin_time = models.DateTimeField(default=datetime.datetime.now)
    end_time = models.DateTimeField(default=datetime.datetime.max)

    class Meta:
        db_table = "lspopstatus"

    def __unicode__(self):
        return "%s %s" % (self.device, self.name)
