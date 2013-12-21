from esmond.api.models import PSMetadata, PSPointToPointSubject, PSEventTypes
from django.conf.urls.defaults import url
from tastypie import fields
from tastypie.api import Api
from tastypie.bundle import Bundle
from tastypie.resources import ModelResource

SUBJECT_FIELDS = ['p2p_subject']

def format_key(k):
    formatted_k = k.replace('_', '-')
    return formatted_k

def format_detail_keys(obj):
    formatted_data = {}
    for k in obj.data.keys():
        formatted_k = ""
        if k == "resource_uri":
            formatted_k = "uri"
        else:
            formatted_k = format_key(k)
        formatted_data[formatted_k] = obj.data[k]
    
    return formatted_data
    
def format_list_keys(data):
    formatted_objs = []
    for obj in data["objects"]:
        formatted_objs.append(format_detail_keys(obj))
    
    return formatted_objs
    
class PSEventTypesResource(ModelResource):
    class Meta:
        queryset=PSEventTypes.objects.all()
        resource_name = 'event-type'
        allowed_methods = ['get']
        excludes = ['id']
        filtering = {
            "summary_type": ['exact']    
        }
        
    def alter_list_data_to_serialize(self, request, data):
        formatted_objs = format_list_keys(data)
        return formatted_objs
    
    def get_resource_uri(self, bundle_or_obj=None):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        if obj:
            uri = "%s%s" % (
                PSArchiveResource().get_resource_uri(obj.metadata),
                obj.encoded_summary_type())
            if obj.summary_type != 'base':
                uri = "%s/%d" % (uri, obj.summary_window)
        else:
            uri = ''

        return uri

class PSPointToPointSubjectResource(ModelResource):
    class Meta:
        queryset=PSPointToPointSubject.objects.all()
        resource_name = 'event-type'
        allowed_methods = ['get']
        excludes = ['id']
    
    def alter_detail_data_to_serialize(self, request, data):
        formatted_objs = format_detail_keys(data)
        return formatted_objs
        
    def alter_list_data_to_serialize(self, request, data):
        formatted_objs = format_list_keys(data)
        return formatted_objs
        
class PSArchiveResource(ModelResource):
    event_types = fields.ToManyField(PSEventTypesResource, 'pseventtypes_set', full=True)
    p2p_subject = fields.ToOneField(PSPointToPointSubjectResource, 'pspointtopointsubject', full=True)
    
    class Meta:
        queryset=PSMetadata.objects.all()
        resource_name = 'archive'
        detail_uri_name = 'metadata_key'
        allowed_methods = ['get']
        excludes = ['id']
    
    def alter_list_data_to_serialize(self, request, data):
        formatted_objs = format_list_keys(data)
        formatted_subj_fields = []
        for subj_field in SUBJECT_FIELDS:
            formatted_subj_fields.append(format_key(subj_field))
      
        for obj in formatted_objs:
            # Format subject
            for subj_field in formatted_subj_fields:
                if subj_field in obj.keys():
                    subj_obj = format_detail_keys(obj[subj_field])
                    for subj_k in subj_obj:
                        if subj_k == 'uri':
                            continue
                        obj[subj_k] =  subj_obj[subj_k]
                    del obj[subj_field]
                    break
            
            #Format event types
            formatted_event_type_map = {}
            for event_type_bundle in obj['event-types']:
                event_type = event_type_bundle.data
                #Build new or use existing
                formatted_event_type = {}
                if(event_type['event_type'] in formatted_event_type_map):
                    formatted_event_type = formatted_event_type_map[event_type['event_type']]
                else:
                    formatted_event_type['event-type'] = event_type['event_type']
                    formatted_event_type['base-uri'] = ""
                    formatted_event_type['summaries'] = []
                    formatted_event_type_map[event_type['event_type']] = formatted_event_type
                 
                #Determine summary type and update accordingly   
                if(event_type['summary_type'] == 'base'):
                    formatted_event_type['base-uri'] = event_type['resource_uri']
                else:
                    summary_obj = {}
                    summary_obj['uri'] = event_type['resource_uri']
                    summary_obj['summary-type'] = event_type['summary_type']
                    summary_obj['summary-window'] = event_type['summary_window']
                    formatted_event_type['summaries'].append(summary_obj)
                    
            obj['event-types'] = formatted_event_type_map.values()
            
        return formatted_objs
    
    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/$" \
                % self._meta.resource_name, self.wrap_view('dispatch_detail'),
                  name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/base/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_base_data'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/(?P<summary_type>[\w\d_.\-@]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_summary_descriptor'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/(?P<summary_type>[\w\d_.\-@]+)/(?P<summary_window>[\w\d_.\-@]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_summary_data'),
                name="api_get_children"),
                ]
     
    def dispatch_summary_descriptor(self, request, **kwargs):
        return PSEventTypesResource().dispatch_list(request,
                metadata__metadata_key=kwargs['metadata_key'], summary_type=kwargs['summary_type'] )
    
    def dispatch_summary_data(self, request, **kwargs):
        pass
    
    def dispatch_base_data(self, request, **kwargs):
        #call dispatch_summary_data
        pass
        
perfsonar_api = Api(api_name='perfsonar')
perfsonar_api.register(PSArchiveResource())
perfsonar_api.register(PSEventTypesResource())