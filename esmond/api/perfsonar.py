from esmond.api.models import PSMetadata
from tastypie.api import Api
from tastypie.resources import ModelResource

class PSMetadataResource(ModelResource):
    class Meta:
        queryset=PSMetadata.objects.all()
        resource_name = 'archive'
        allowed_methods = ['get']

perfsonar_api = Api(api_name='perfsonar')
perfsonar_api.register(PSMetadataResource())