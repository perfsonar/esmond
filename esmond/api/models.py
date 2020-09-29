from django.db import models
from django.utils.timezone import now
import datetime

from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from netfields import CidrAddressField, NetManager

from esmond.util import atencode

"""
We historically laid the project out as 'esmond.api' when a much earlier 
version of Django was being used. This layout strategy led to issues with
later versions of Django, so the model Meta uses app_label = 'api' (rather
than 'esmond.api'), so things load properly with modern versions of 
django.
"""

class APIPermissionManager(models.Manager):
    def get_query_set(self):
        return super(APIPermissionManager, self).\
            get_queryset().filter(content_type__name='api_permission')


class APIPermission(Permission):
    """A global permission, not attached to a model"""

    objects = APIPermissionManager()

    class Meta:
        app_label = 'api'
        proxy = True
        permissions = (
            ("esmond_api.view_timeseries", "View timseries data"),
            ("esmond_api.add_timeseries", "Add timseries data"),
            ("esmond_api.delete_timeseries", "Delete timseries data"),
            ("esmond_api.change_timeseries", "Change timseries data"),
        )

    def save(self, *args, **kwargs):
        ct, created = ContentType.objects.get_or_create(
            name="api_permission", app_label=self._meta.app_label
        )
        self.content_type = ct
        super(APIPermission, self).save(*args, **kwargs)

# Additional PS specific models.

class PSMetadataManager(models.Manager):
    def search():
        return []
    
class PSMetadata(models.Model):
    metadata_key = models.SlugField(max_length=128, db_index=True, unique=True )
    subject_type = models.CharField(max_length=128)
    checksum = models.CharField(max_length=128, db_index=True, unique=True)
    objects = PSMetadataManager()
    
    class Meta:
        app_label = 'api'
        db_table = "ps_metadata"
        ordering = ["metadata_key"] #gives consistent ordering
        
    def __unicode__(self):
        return self.metadata_key
    
class PSPointToPointSubject(models.Model):
    metadata = models.OneToOneField(PSMetadata)
    tool_name = models.CharField(max_length=128)
    source = models.GenericIPAddressField(db_index=True)
    destination = models.GenericIPAddressField(db_index=True)
    measurement_agent = models.GenericIPAddressField()
    input_source = models.CharField(max_length=128)
    input_destination = models.CharField(max_length=128)
    
    class Meta:
        app_label = 'api'
        db_table = "ps_p2p_subject"
        ordering = ["source","destination"]
    
    def __unicode__(self):
        return "%s-%s" % (self.source, self.destination)

class PSNetworkElementSubject(models.Model):
    metadata = models.OneToOneField(PSMetadata)
    tool_name = models.CharField(max_length=128)
    source = models.GenericIPAddressField(db_index=True)
    measurement_agent = models.GenericIPAddressField()
    input_source = models.CharField(max_length=128)
    
    class Meta:
        app_label = 'api'
        db_table = "ps_networkelement_subject"
        ordering = ["source","tool_name"]
    
    def __unicode__(self):
        return "%s-%s" % (self.source, self.tool_name)
    
class PSEventTypes(models.Model):
    metadata = models.ForeignKey(PSMetadata, related_name='pseventtypes')
    event_type =  models.CharField(max_length=128, db_index=True)
    summary_type =  models.CharField(max_length=128)
    summary_window =  models.BigIntegerField()
    time_updated = models.DateTimeField(null=True)
    
    class Meta:
        app_label = 'api'
        db_table = "ps_event_types"
        ordering = ["metadata","event_type", "summary_type", "summary_window"]
    
    def __unicode__(self):
        return "%s:%s:%d" % (self.event_type, self.summary_type, self.summary_window)
    
    def encoded_event_type(self):
        return atencode(self.event_type)
    
    def encoded_summary_type(self):
        return atencode(self.summary_type)
    
class PSMetadataParameters(models.Model):
    metadata = models.ForeignKey(PSMetadata, related_name='psmetadataparameters')
    parameter_key = models.CharField(max_length=128, db_index=True)
    parameter_value = models.TextField()
    
    class Meta:
        app_label = 'api'
        db_table = "ps_metadata_parameters"
    
    def __unicode__(self):
        return "%s" % (self.parameter_key)

class UserIpAddress(models.Model):
    ip = CidrAddressField(unique=True, db_index=True)
    user = models.ForeignKey(User, related_name='user')
    objects = NetManager()
    
    class Meta:
        app_label = 'api'
        db_table = "useripaddress"
        verbose_name = "User IP Address"
        verbose_name_plural = "User IP Addresses"
    
    def __unicode__(self):
        return "%s - %s" % (self.ip, self.user)
