from esmond.api.models import PSMetadata
from tastypie.resources import ModelResource

class PSMetadataResource(ModelResource):
    class Meta:
        queryset=PSMetadata.objects.all()
        resource_name = 'archive'
        allowed_methods = ['get']