from esmond.api.models import PSMetadata, PSPointToPointSubject, PSEventTypes, PSMetadataParameters
from django.conf.urls.defaults import url
from django.db.models import Q
from tastypie import fields
from tastypie.api import Api
from tastypie.bundle import Bundle
from tastypie.resources import ModelResource, ALL_WITH_RELATIONS

SUBJECT_FIELDS = ['p2p_subject']
SUBJECT_FILTER_MAP = {
    #point-to-point subject fields
    "source": 'p2p_subject__source',
    "destination": 'p2p_subject__destination',
    "tool-name": 'p2p_subject__tool_name',
    "measurement-agent": 'p2p_subject__measurement_agent',
    "input-source": 'p2p_subject__input_source',
    "input-destination": 'p2p_subject__input_destination'
}
EVENT_TYPE_FILTER = "event-type"
SUMMARY_TYPE_FILTER = "summary-type"
SUMMARY_WINDOW_FILTER = "summary-window"
RESERVED_GET_PARAMS = ["format"]

def format_key(k):
    formatted_k = k.replace('_', '-')
    return formatted_k

def deformat_key(k):
    deformatted_k = ""
    if k == "uri":
        deformatted_k = "resource_uri"
    else:
        deformatted_k = k.replace('-', '_')
    return deformatted_k

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
            "event_type": ['exact'],  
            "summary_type": ['exact'],
            "summary_window": ['exact']    
        }
    
    @staticmethod
    def format_summary_obj(event_type):
        summary_obj = {}
        summary_obj['uri'] = event_type['resource_uri']
        summary_obj['summary-type'] = event_type['summary_type']
        summary_obj['summary-window'] = event_type['summary_window']
        return summary_obj
    
    @staticmethod
    def format_event_types(event_types):
        formatted_event_type_map = {}
        for event_type_bundle in event_types:
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
                summary_obj = PSEventTypesResource.format_summary_obj(event_type)
                formatted_event_type['summaries'].append(summary_obj) 
                
        return formatted_event_type_map.values()
    
    def alter_list_data_to_serialize(self, request, data):
        return PSEventTypesResource.format_event_types(data['objects'])
    
    def get_resource_uri(self, bundle_or_obj=None):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        if obj:
            uri = "%s%s/%s" % (
                PSArchiveResource().get_resource_uri(obj.metadata),
                obj.encoded_event_type(),
                obj.encoded_summary_type())
            if obj.summary_type != 'base':
                uri = "%s/%d" % (uri, obj.summary_window)
        else:
            uri = ''

        return uri

class PSEventTypeSummaryResource(PSEventTypesResource):
    class Meta:
        queryset=PSEventTypes.objects.all()
        resource_name = 'summary'
        allowed_methods = ['get']
        excludes = ['id']
        filtering = {
            "event_type": ['exact'],  
            "summary_type": ['exact'],
            "summary_window": ['exact']
        }
    
    def alter_list_data_to_serialize(self, request, data):
        formatted_summary_objs = []
        for event_type in data['objects']:
             formatted_summary_obj = PSEventTypesResource.format_summary_obj(event_type.data)
             formatted_summary_objs.append(formatted_summary_obj)
             
        return formatted_summary_objs

class PSPointToPointSubjectResource(ModelResource):
    class Meta:
        queryset=PSPointToPointSubject.objects.all()
        resource_name = 'event-type'
        allowed_methods = ['get']
        excludes = ['id']
        filtering = {
            "source": ['exact'],  
            "destination": ['exact'],
            "tool_name": ['exact'],
            "measurement_agent": ['exact'],
            "input_source":['exact'],
            "input_destination": ['exact']
        }
        
    def alter_detail_data_to_serialize(self, request, data):
        formatted_objs = format_detail_keys(data)
        return formatted_objs
        
    def alter_list_data_to_serialize(self, request, data):
        formatted_objs = format_list_keys(data)
        return formatted_objs

class PSMetadataParametersResource(ModelResource):
    class Meta:
        queryset=PSMetadataParameters.objects.all()
        resource_name = 'metadata-parameters'
        allowed_methods = ['get']
        excludes = ['id']
        
class PSArchiveResource(ModelResource):
    event_types = fields.ToManyField(PSEventTypesResource, 'pseventtypes', full=True, null=True, blank=True)
    p2p_subject = fields.ToOneField(PSPointToPointSubjectResource, 'pspointtopointsubject', full=True)
    md_parameters = fields.ToManyField(PSMetadataParametersResource, 'psmetadataparameters', full=True, null=True, blank=True)
    
    class Meta:
        queryset=PSMetadata.objects.all()
        resource_name = 'archive'
        detail_uri_name = 'metadata_key'
        allowed_methods = ['get']
        excludes = ['id']
        filtering = {
            "metadata_key": ['exact'],
            "subject_type": ['exact'],
            "event_types" : ALL_WITH_RELATIONS,
            "p2p_subject" : ALL_WITH_RELATIONS
        }
    
    def format_metadata_obj(self, obj, formatted_subj_fields):     
        obj = format_detail_keys(obj)
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
        obj['event-types'] = PSEventTypesResource.format_event_types(obj['event-types'])
      
        #Format parameters
        for md_param in obj['md-parameters']:
            obj[md_param.data['parameter_key']] = md_param.data['parameter_value']
        del obj['md-parameters']
        
        return obj
    
    def alter_detail_data_to_serialize(self, request, data):
        formatted_subj_fields = []
        for subj_field in SUBJECT_FIELDS:
            formatted_subj_fields.append(format_key(subj_field))
        
        formatted_obj = self.format_metadata_obj(data, formatted_subj_fields)
            
        return formatted_obj
    
    def alter_list_data_to_serialize(self, request, data):
        formatted_subj_fields = []
        for subj_field in SUBJECT_FIELDS:
            formatted_subj_fields.append(format_key(subj_field))
        
        formatted_objs = []
        for obj in data['objects']:
            formatted_obj = self.format_metadata_obj(obj, formatted_subj_fields)
            formatted_objs.append(formatted_obj)
            
        return formatted_objs
    
    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/$" \
                % self._meta.resource_name, self.wrap_view('dispatch_detail'),
                  name="api_dispatch_detail"),
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_event_type_detail'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/base/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_base_data'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/(?P<summary_type>[\w\d_.\-@]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_summary_detail'),
                name="api_get_children"),
            url(r"^(?P<resource_name>%s)/(?P<metadata_key>[\w\d_.-]+)/(?P<event_type>[\w\d_.-]+)/(?P<summary_type>[\w\d_.\-@]+)/(?P<summary_window>[\w\d_.\-@]+)/?$"
                % (self._meta.resource_name,),
                self.wrap_view('dispatch_summary_data'),
                name="api_get_children"),
                ]
    
    def dispatch_event_type_detail(self, request, **kwargs):
        return PSEventTypesResource().dispatch_list(request,
                metadata__metadata_key=kwargs['metadata_key'], event_type=kwargs['event_type'] )
    
    def dispatch_summary_detail(self, request, **kwargs):
        return PSEventTypeSummaryResource().dispatch_list(request,
                metadata__metadata_key=kwargs['metadata_key'], event_type=kwargs['event_type'], summary_type=kwargs['summary_type'] )
    
    def dispatch_summary_data(self, request, **kwargs):
        pass
    
    def dispatch_base_data(self, request, **kwargs):
        #call dispatch_summary_data
        pass
    
    def build_filters(self, filters=None):
        if filters is None:
            filters = {}
        
        # Process get parameters
        formatted_filters = {}
        event_type_qs = []
        parameter_qs = []
        for filter in filters:
            if filter in SUBJECT_FILTER_MAP:
                # map subject to subject field
                formatted_filters[SUBJECT_FILTER_MAP[filter]] = filters[filter]
            elif filter == EVENT_TYPE_FILTER:
                event_type_qs.append(Q(pseventtypes__event_type=filters[filter]))
            elif filter == SUMMARY_TYPE_FILTER:
                event_type_qs.append(Q(pseventtypes__summary_type=filters[filter]))
            elif filter == SUMMARY_WINDOW_FILTER:
                event_type_qs.append(Q(pseventtypes__summary_window=filters[filter]))            
            elif deformat_key(filter) in self.fields:
                # match metdadata table key
                formatted_filters[deformat_key(filter)] = filters[filter]
            elif filter not in RESERVED_GET_PARAMS:
                # map to ps_metadata_parameters
                parameter_qs.append(Q(
                    psmetadataparameters__parameter_key=filter,
                    psmetadataparameters__parameter_value=filters[filter]))
                
        # Create standard ORM filters
        orm_filters = super(ModelResource, self).build_filters(formatted_filters)
        
        #Add event type and parameters filters separatel for special processing in apply_filters
        orm_filters.update({'event_type_qs': event_type_qs})
        orm_filters.update({'parameter_qs': parameter_qs})
        
        return orm_filters
    
    def apply_filters(self, request, applicable_filters):
        """
        Customize to do two things:
        1. Make sure event type parameters match the same event type object
        2. Apply the free-form metadata parameter filters also making sure they match the same row
        """
        event_type_qs = None
        if 'event_type_qs' in applicable_filters:
            event_type_qs = applicable_filters.pop('event_type_qs')
            
        parameter_qs = []
        if 'parameter_qs' in applicable_filters:
            parameter_qs = applicable_filters.pop('parameter_qs')
            
        query = super(ModelResource, self).apply_filters(request, applicable_filters)
        if event_type_qs:
            query = query.filter(*event_type_qs)
        for parameter_q in parameter_qs:
            query = query.filter(parameter_q)
            
        return query
    
perfsonar_api = Api(api_name='perfsonar')
perfsonar_api.register(PSArchiveResource())
perfsonar_api.register(PSEventTypesResource())