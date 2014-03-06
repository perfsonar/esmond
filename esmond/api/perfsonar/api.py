from calendar import timegm
from esmond.api.models import PSMetadata, PSPointToPointSubject, PSEventTypes, PSMetadataParameters
from esmond.api.perfsonar.types import *
from esmond.cassandra import KEY_DELIMITER, CASSANDRA_DB, AGG_TYPES, ConnectionException, RawRateData, BaseRateBin, RawData, AggregationBin
from esmond.config import get_config_path, get_config
from datetime import datetime
from django.conf.urls.defaults import url
from django.db.models import Q
from django.utils.text import slugify
from socket import getaddrinfo, AF_INET, AF_INET6, SOL_TCP, SOCK_STREAM
from string import join
from tastypie import fields
from tastypie.api import Api
from tastypie.authorization import Authorization
from tastypie.bundle import Bundle
from tastypie.exceptions import BadRequest, NotFound
from tastypie.resources import Resource, ModelResource, ALL_WITH_RELATIONS
from time import time
import hashlib
import math
import uuid

#Get db connection
try:
    db = CASSANDRA_DB(get_config(get_config_path()))
except ConnectionException, e:
    # Check the stack before raising an error - if test_api is 
    # the calling code, we won't need a running db instance.
    mod = inspect.getmodule(inspect.stack()[1][0])
    if mod and mod.__name__ == 'api.tests.test_api' or 'sphinx.ext.autodoc':
        print '\nUnable to connect - presuming stand-alone testing mode...'
        db = None
    else:
        raise ConnectionException(str(e))

#set global constants
EVENT_TYPE_CF_MAP = {
    'histogram': db.raw_cf,
    'integer': db.rate_cf,
    'json': db.raw_cf,
    'percentage': db.agg_cf,
    'subinterval': db.raw_cf,
    'float': db.agg_cf
}
EVENT_TYPE_FILTER = "event-type"
SUMMARY_TYPE_FILTER = "summary-type"
SUMMARY_WINDOW_FILTER = "summary-window"
DNS_MATCH_RULE_FILTER = "dns-match-rule"
DNS_MATCH_PREFER_V6 = "prefer-v6"
DNS_MATCH_PREFER_V4 = "prefer-v4"
DNS_MATCH_ONLY_V6 = "only-v6"
DNS_MATCH_ONLY_V4 = "only-v4"
DNS_MATCH_V4_V6 = "v4v6"
RESERVED_GET_PARAMS = ["format", DNS_MATCH_RULE_FILTER]
DATA_KEY_TIME = "ts"
DATA_KEY_VALUE = "val"

#global utility functions
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
        elif k == "checksum":
            continue
        else:
            formatted_k = format_key(k)
        formatted_data[formatted_k] = obj.data[k]
    
    return formatted_data
    
def format_list_keys(data):
    formatted_objs = []
    for obj in data["objects"]:
        formatted_objs.append(format_detail_keys(obj))
    
    return formatted_objs
   
# Resource classes 
class PSEventTypesResource(ModelResource):
    psmetadata = fields.ToOneField('esmond.api.perfsonar.api.PSArchiveResource', 'metadata', null=True, blank=True)
     
    class Meta:
        queryset=PSEventTypes.objects.all()
        resource_name = 'event-type'
        allowed_methods = ['get', 'post']
        authorization = Authorization() #todo replace this
        excludes = ['id']
        filtering = {
            "event_type": ['exact'],  
            "summary_type": ['exact'],
            "summary_window": ['exact'],
            "psmetadata": ALL_WITH_RELATIONS
        }
    
    @staticmethod
    def format_summary_obj(event_type):
        summary_obj = {}
        summary_obj['uri'] = event_type['resource_uri']
        summary_obj['summary-type'] = event_type['summary_type']
        summary_obj['summary-window'] = event_type['summary_window']
        return summary_obj
    
    @staticmethod
    def serialize_event_types(event_types):
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
    
    @staticmethod
    def deserialize_event_types(event_types):
        if event_types is None:
            return []
        
        if not isinstance(event_types, list):
            raise BadRequest("event_types must be a list")
        
        deserialized_event_types = []
        for event_type in event_types:
            #Validate object
            if EVENT_TYPE_FILTER not in event_type:
                #verify event-type defined
                raise BadRequest("No event-type defined")
            elif event_type[EVENT_TYPE_FILTER] not in EVENT_TYPE_CONFIG:
                #verify valid event-type
                raise BadRequest("Invalid event-type %s" % str(event_type[EVENT_TYPE_FILTER]))
            
            #set the data type
            data_type = EVENT_TYPE_CONFIG[event_type[EVENT_TYPE_FILTER]]['type']
            
            #Create base object
            deserialized_event_types.append({
                'event_type': event_type[EVENT_TYPE_FILTER],
                'summary_type': 'base',
                'summary_window': '0'})
            
            #Build summaries
            if 'summaries' in event_type:
                for summary in event_type['summaries']:
                    # Validate summary
                    if 'summary-type' not in summary:
                        raise BadRequest("Summary must contain summary-type")
                    elif summary['summary-type'] not in INVERSE_SUMMARY_TYPES:
                        raise BadRequest("Invalid summary type '%s'" % summary['summary-type'])
                    elif summary['summary-type'] == 'base':
                        continue
                    elif summary['summary-type'] not in ALLOWED_SUMMARIES[data_type]:
                        raise BadRequest("Summary type %s not allowed for event-type %s" % (summary['summary-type'], event_type[EVENT_TYPE_FILTER]))
                    elif 'summary-window' not in summary:
                        raise BadRequest("Summary must contain summary-window")
                    
                    #Verify summary window is an integer
                    try:
                        int(summary['summary-window'])
                    except ValueError:
                        raise BadRequest("Summary window must be an integer")
                    
                    #Everything looks good so add summary
                    deserialized_event_types.append({
                        'event_type': event_type[EVENT_TYPE_FILTER],
                        'summary_type': summary['summary-type'],
                        'summary_window': summary['summary-window']})
            
        return deserialized_event_types
    
    def alter_list_data_to_serialize(self, request, data):
        return PSEventTypesResource.serialize_event_types(data['objects'])
    
    def get_resource_uri(self, bundle_or_obj=None):
        if isinstance(bundle_or_obj, Bundle):
            obj = bundle_or_obj.obj
        else:
            obj = bundle_or_obj

        if obj:
            if(obj.encoded_summary_type() not in INVERSE_SUMMARY_TYPES):
                raise BadRequest("Invalid summary type %s" % obj.encoded_summary_type())
            uri = "%s%s/%s" % (
                PSArchiveResource().get_resource_uri(obj.metadata),
                obj.encoded_event_type(),
                INVERSE_SUMMARY_TYPES[obj.encoded_summary_type()])
            if obj.summary_type != 'base':
                uri = "%s/%d" % (uri, obj.summary_window)
        else:
            uri = ''

        return uri
    
    def build_filters(self, filters=None):
        formatted_filters = {}
        for filter in filters:
            if deformat_key(filter) in self.fields:
                # match metdadata table key
                formatted_filters[deformat_key(filter)] = filters[filter]
            else:
                formatted_filters[filter] = filters[filter]
                
        return super(ModelResource, self).build_filters(formatted_filters)
            
class PSEventTypeSummaryResource(PSEventTypesResource):
    class Meta:
        queryset=PSEventTypes.objects.all()
        resource_name = 'summary'
        allowed_methods = ['get']
        excludes = ['id']
        filtering = {
            "event_type": ['exact'],  
            "summary_type": ['exact'],
            "summary_window": ['exact'],
            "psmetadata": ALL_WITH_RELATIONS
        }
    
    def alter_list_data_to_serialize(self, request, data):
        formatted_summary_objs = []
        for event_type in data['objects']:
             formatted_summary_obj = PSEventTypesResource.format_summary_obj(event_type.data)
             formatted_summary_objs.append(formatted_summary_obj)
             
        return formatted_summary_objs

class PSPointToPointSubjectResource(ModelResource):
    psmetadata = fields.ToOneField('esmond.api.perfsonar.api.PSArchiveResource', 'metadata', null=True, blank=True)
    
    class Meta:
        queryset=PSPointToPointSubject.objects.all()
        resource_name = 'p2p_subject'
        allowed_methods = ['get', 'post']
        authorization = Authorization() #todo replace this
        excludes = ['id']
        filtering = {
            "source": ['exact', 'in'],  
            "destination": ['exact', 'in'],
            "tool_name": ['exact'],
            "measurement_agent": ['exact', 'in'],
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
    psmetadata = fields.ToOneField('esmond.api.perfsonar.api.PSArchiveResource', 'metadata', null=True, blank=True)
    
    class Meta:
        queryset=PSMetadataParameters.objects.all()
        resource_name = 'metadata-parameters'
        allowed_methods = ['get', 'post']
        authorization = Authorization() #todo replace this
        excludes = ['id']
        
class PSArchiveResource(ModelResource):
    event_types = fields.ToManyField(PSEventTypesResource, 'pseventtypes', related_name='psmetadata', full=True, null=True, blank=True)
    p2p_subject = fields.ToOneField(PSPointToPointSubjectResource, 'pspointtopointsubject', related_name='psmetadata', full=True, null=True, blank=True)
    md_parameters = fields.ToManyField(PSMetadataParametersResource, 'psmetadataparameters', related_name='psmetadata', full=True, null=True, blank=True)
    
    class Meta:
        queryset=PSMetadata.objects.all()
        always_return_data = True
        resource_name = 'archive'
        detail_uri_name = 'metadata_key'
        allowed_methods = ['get', 'post']
        excludes = ['id']
        authorization = Authorization() #todo replace this
        filtering = {
            "metadata_key": ['exact'],
            "subject_type": ['exact'],
            "event_types" : ALL_WITH_RELATIONS,
            "p2p_subject" : ALL_WITH_RELATIONS
        }
    
    def obj_create(self, bundle, **kwargs):
        #check if medata already exists. if it does, return existing object
        existing_md = PSMetadata.objects.filter(checksum=bundle.data["checksum"])
        if existing_md.count() > 0:
            bundle.obj = existing_md[0]
        else:
            bundle = super(ModelResource, self).obj_create(bundle, **kwargs)
            
        return bundle
    
    def save_related(self, bundle):
        #don't save subject foreign keys because this is called before metadata has ID
        return 
    
    def save_m2m(self, bundle):
        #Save OneToOneField now that object has been created
        subject_type = SUBJECT_MODEL_MAP[bundle.obj.subject_type]
        subject_obj = bundle.related_objects_to_save.get(subject_type, None)
        if subject_obj is not None:
            subject_obj.metadata_id = bundle.obj.id
        super(ModelResource, self).save_related(bundle)
        
        return super(ModelResource, self).save_m2m(bundle)
    
    def format_metadata_obj(self, obj, formatted_subj_fields):     
        obj = format_detail_keys(obj)
        # Format subject
        for subj_field in formatted_subj_fields:
            if subj_field in obj.keys():
                subj_obj = format_detail_keys(obj[subj_field])
                for subj_k in subj_obj:
                    if subj_k == 'uri' or subj_k=='psmetadata':
                        continue
                    obj[subj_k] =  subj_obj[subj_k]
                del obj[subj_field]
                break
        
        #Format event types          
        obj['event-types'] = PSEventTypesResource.serialize_event_types(obj['event-types'])
      
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
    
    def alter_deserialized_detail_data(self, request, data):
        #Verify subject information provided
        if 'subject-type' not in data:
            raise BadRequest("Missing subject-type field in request")
        
        #Verify event types provided
        if 'event-types' not in data:
            raise BadRequest("Missing event-types field in request")
        
        if data['subject-type'] not in SUBJECT_TYPE_MAP:
            raise BadRequest("Invalid subject type %s" % data['subject-type'])
        
        #Don't allow metadata key to be specified
        if 'metadata-key' in data:
            raise BadRequest("metadata-key is not allowed to be specified")
        
        #Build deserialized object
        subject_model = SUBJECT_TYPE_MAP[data['subject-type']]
        formatted_data = {}
        formatted_data[subject_model] = {}
        formatted_data['md_parameters'] = []
        subject_prefix = "%s__" % subject_model
        for k in data:
            if k == 'subject-type':
                formatted_data[deformat_key(k)] = data[k]
            elif k == 'event-types':
                formatted_data[deformat_key(k)] = PSEventTypesResource.deserialize_event_types(data[k])
            elif k in SUBJECT_FILTER_MAP and SUBJECT_FILTER_MAP[k].startswith(subject_prefix):
                subj_k = SUBJECT_FILTER_MAP[k].replace(subject_prefix, '', 1)
                formatted_data[subject_model][subj_k] = data[k]
            else:
                formatted_data['md_parameters'].append({
                    'parameter_key': k,
                    'parameter_value': data[k]
                    })
        
        #calculate checksum
        formatted_data['checksum'] = self.calculate_checksum(formatted_data, subject_model)
        
        #set metatadatakey
        formatted_data['metadata_key'] = slugify(unicode(uuid.uuid4().hex))
        
        return super(ModelResource, self).alter_deserialized_detail_data(request, formatted_data)
    
    def calculate_checksum(self, data, subject_field):
        data['md_parameters'] = sorted(data['md_parameters'], key=lambda md_param: md_param["parameter_key"])
        data['event_types'] = sorted(data['event_types'], key=lambda et:(et["event_type"], et["summary_type"], et["summary_window"]))
        checksum = hashlib.sha256()
        checksum.update("subject-type::%s" %   data['subject_type'].lower())
        for subj_param in sorted(data[subject_field]):
            checksum.update(",%s::%s" % (str(subj_param).lower(), str(data[subject_field][subj_param]).lower()))
        for md_param in data['md_parameters']:
            checksum.update(",%s::%s" % (str(md_param['parameter_key']).lower(), str(md_param['parameter_value']).lower()))
        for et in data['event_types']:
            checksum.update(",%s::%s::%s" % (str(et['event_type']).lower(), str(et['summary_type']).lower(), str(et['summary_window']).lower()))

        return checksum.hexdigest()
        
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
                psmetadata__metadata_key=kwargs['metadata_key'], event_type=kwargs['event_type'] )
    
    def dispatch_summary_detail(self, request, **kwargs):
        #verify summary type
        if(kwargs['summary_type'] not in SUMMARY_TYPES):
            raise BadRequest("Invalid summary type in URL '%s'" % kwargs['summary_type'])
        return PSEventTypeSummaryResource().dispatch_list(request,
                psmetadata__metadata_key=kwargs['metadata_key'], event_type=kwargs['event_type'], summary_type=SUMMARY_TYPES[kwargs['summary_type']] )
    
    def dispatch_summary_data(self, request, **kwargs):
        return PSTimeSeriesResource().dispatch_list(request,
                metadata_key=kwargs['metadata_key'], event_type=kwargs['event_type'],
                summary_type=kwargs['summary_type'], summary_window=kwargs['summary_window'] )
    
    def dispatch_base_data(self, request, **kwargs):
        return PSTimeSeriesResource().dispatch_list(request,
                metadata_key=kwargs['metadata_key'], event_type=kwargs['event_type'] )
    
    def lookup_hostname(self, host, family):
        """
        Does a lookup of the IP for host in type family (i.e. AF_INET or AF_INET6)
        """
        addr = None
        addr_info = None
        try:
            addr_info = getaddrinfo(host, 80, family, SOCK_STREAM, SOL_TCP)
        except:
            pass
        if addr_info and len(addr_info) >= 1 and len(addr_info[0]) >= 5 and len(addr_info[0][4]) >= 1:
            addr = addr_info[0][4][0]
        return addr
        
    def prepare_ip(self, host, dns_match_rule):
        """
        Maps a given hostname to an IPv4 and/or IPv6 address. The addresses
        it return are dependent on the dns_match_rule. teh default is to return
        both v4 and v6 addresses found. Variations allow one or the other to be
        preferred or even required. If an address is not found a BadRequest is
        thrown.
        """
        #Set default match rule
        if dns_match_rule is None:
            dns_match_rule = DNS_MATCH_V4_V6
        
        #get IP address
        addrs = []
        addr4 = None
        addr6 = None
        if dns_match_rule == DNS_MATCH_ONLY_V6:
            addr6 = self.lookup_hostname(host, AF_INET6)
        elif dns_match_rule == DNS_MATCH_ONLY_V4:
            addr4 = self.lookup_hostname(host, AF_INET)
        elif dns_match_rule == DNS_MATCH_PREFER_V6:
            addr6 = self.lookup_hostname(host, AF_INET6)
            if addr6 is None:
                addr4 = self.lookup_hostname(host, AF_INET)
        elif dns_match_rule == DNS_MATCH_PREFER_V4:
            addr4 = self.lookup_hostname(host, AF_INET)
            if addr4 is None:
                addr6 = self.lookup_hostname(host, AF_INET6)
        elif dns_match_rule == DNS_MATCH_V4_V6:
            addr6 = self.lookup_hostname(host, AF_INET6)
            addr4 = self.lookup_hostname(host, AF_INET)
        else:
            raise BadRequest("Invalid %s parameter %s" % (DNS_MATCH_RULE_FILTER, dns_match_rule))
        
        #add results to list
        if addr4: addrs.append(addr4)
        if addr6: addrs.append(addr6)
        if len(addrs) == 0:
            raise BadRequest("Unable to find address for host %s" % host)
        return addrs
    
    def build_filters(self, filters=None):
        """
        This makes sure that GET parameters are mapped to the correct database
        fields. It also does things like mapping hostnames to IP addresses. The
        filters build by this method are not actually used until the 'apply_filter'
        function.
        """
        if filters is None:
            filters = {}
        
        # Process get parameters
        formatted_filters = {}
        event_type_qs = []
        parameter_qs = []
        dns_match_rule = None
        if DNS_MATCH_RULE_FILTER in filters:
            #added join because given as array
            dns_match_rule = join(filters.pop(DNS_MATCH_RULE_FILTER), "")
            
        for filter in filters:
            #organize into database filters
            if filter in SUBJECT_FILTER_MAP:
                # map subject to subject field
                if filter in IP_FIELDS:
                    filter_val = self.prepare_ip(filters[filter], dns_match_rule)
                    filter_key = "%s__in" % SUBJECT_FILTER_MAP[filter]
                    #call join because super expects comma-delimited string
                    formatted_filters[filter_key] = join(filter_val, ',')
                else:
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
                if filter in IP_FIELDS:
                    filter_val = self.prepare_ip(filters[filter], dns_match_rule)
                    # map to ps_metadata_parameters
                    parameter_qs.append(Q(
                        psmetadataparameters__parameter_key=filter,
                        #keep as list since this skips super build_filter
                        psmetadataparameters__parameter_value__in=filter_val))
                else:
                    # map to ps_metadata_parameters
                    parameter_qs.append(Q(
                    psmetadataparameters__parameter_key=filter,
                    psmetadataparameters__parameter_value=filters[filter]))
                
        # Create standard ORM filters
        orm_filters = super(ModelResource, self).build_filters(formatted_filters)
        
        #Add event type and parameters filters separately for special processing in apply_filters
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

class PSTimeSeriesObject(object):
    def __init__(self, ts, value, metadata_key, event_type=None, summary_type='base', summary_window=0):
        self._time = ts
        self.value = value
        self.metadata_key = metadata_key
        self.event_type = event_type
        self.summary_type = summary_type
        self.summary_window = summary_window
    
    @property
    def datapath(self):
        datapath = EVENT_TYPE_CONFIG[self.event_type]["row_prefix"].split(KEY_DELIMITER)
        datapath.append(self.metadata_key)
        if self.summary_type != "base":
            datapath.append(self.summary_type)
        
        return datapath
    
    @property
    def freq(self):
        freq = None
        if self.summary_window > 0:
            freq = self.summary_window
        
        return freq
    
    @property
    def base_freq(self):
        base_freq = 1000
        if EVENT_TYPE_CONFIG[self.event_type]["type"] == "float":
            #multiply by 1000 to compensate for division in AggregationBin average 
            base_freq = DEFAULT_FLOAT_PRECISION * 1000
        
        return base_freq
    
    @property
    def time(self):
        ts = self._time
        #calculate summary bin
        if self.summary_type != 'base' and self.summary_window > 0:
            ts = math.floor(long(ts)/long(self.summary_window)) * long(self.summary_window)
        
        return ts
    
    def get_datetime(self):
        return datetime.utcfromtimestamp(float(self.time))
        
class PSTimeSeriesResource(Resource):
    
    class Meta:
        resource_name = 'pstimeseries'
        allowed_methods = ['get', 'post']
        limit = 0
        max_limit = 0
    
    def valid_time(self, t):
        try:
            t = int(t)
        except ValueError:
            raise BadRequest("Time parameter must be an integer")
        return t
    
    def valid_summary_window(self, sw):
        try:
            sw = int(sw)
        except ValueError:
            raise BadRequest("Summary window parameter must be an integer")
        return sw
    
    def obj_get_list(self, bundle, **kwargs):
        #format time GET parameters
        filters = getattr(bundle.request, 'GET', {})
        end_time = int(time())
        begin_time = 0
        if filters.has_key('time'):
            begin_time = self.valid_time(filters['time'])
            end_time = begin_time
        elif filters.has_key('time-start') and filters.has_key('time-end'):
            begin_time = self.valid_time(filters['time-start'])
            end_time = self.valid_time(filters['time-end'])
        elif filters.has_key('time-start') and filters.has_key('time-range'):
            begin_time = self.valid_time(filters['time-start'])
            end_time = begin_time + self.valid_time(filters['time-range'])
        elif filters.has_key('time-end') and filters.has_key('time-range'):
            end_time = self.valid_time(filters['time-end'])
            begin_time = end_time - self.valid_time(filters['time-range'])
        elif filters.has_key('time-start'):
           begin_time = self.valid_time(filters['time-start'])
        elif filters.has_key('time-end'):
           end_time = self.valid_time(filters['time-end'])
        elif filters.has_key('time-range'):
           begin_time = end_time - self.valid_time(filters['time-range'])
        if(end_time < begin_time):
            raise BadRequest("Requested start time must be less than end time")
        
        #build data path
        datapath = []
        if 'event_type' not in kwargs:
            raise BadRequest("No event type specified for data query")
        elif 'metadata_key' not in kwargs:
            raise BadRequest("No metadata key specified for data query")
        elif kwargs['event_type'] not in EVENT_TYPE_CONFIG:
            raise BadRequest("Unsupported event type '%s' provided" % kwargs['event_type'])
        elif "type" not in EVENT_TYPE_CONFIG[kwargs['event_type']]:
            raise BadRequest("Misconfigured event type on server side. Missing 'type' field")
        elif "row_prefix" not in EVENT_TYPE_CONFIG[kwargs['event_type']]:
            raise BadRequest("Misconfigured event type on server side. Missing 'row_prefix' field")
        event_type = kwargs['event_type']
        metadata_key = kwargs['metadata_key']
        datapath = EVENT_TYPE_CONFIG[event_type]["row_prefix"].split(KEY_DELIMITER)
        datapath.append(metadata_key)
        summary_type = ''
        if 'summary_type' in kwargs:
            summary_type = kwargs['summary_type']
            if summary_type not in SUMMARY_TYPES:
                raise BadRequest("Invalid summary type '%s'" % summary_type)
            datapath.append(SUMMARY_TYPES[summary_type])
        freq = None
        if 'summary_window' in kwargs:
            freq = self.valid_summary_window(kwargs['summary_window'])

        #send query
        results = []
        query_type = EVENT_TYPE_CONFIG[event_type]["type"]
        if query_type not in EVENT_TYPE_CF_MAP:
            raise BadRequest("Misconfigured event type on server side. Invalid 'type' %s" % query_type)
        col_fam = TYPE_VALIDATOR_MAP[query_type].summary_cf(summary_type)
        if col_fam is None:
            col_fam = EVENT_TYPE_CF_MAP[query_type]
        if col_fam == db.agg_cf:
            results = db.query_aggregation_timerange(path=datapath, freq=freq,
                   cf='average', ts_min=begin_time*1000, ts_max=end_time*1000)
        elif col_fam == db.rate_cf:
            results = db.query_baserate_timerange(path=datapath, freq=freq,
                    cf='delta', ts_min=begin_time*1000, ts_max=end_time*1000)
        elif col_fam == db.raw_cf:
            results = db.query_raw_data(path=datapath, freq=freq,
                   ts_min=begin_time*1000, ts_max=end_time*1000)
        else:
            raise BadRequest("Requested data does not map to a known column-family")
            
        return results
    
    def format_ts_obj(self, obj):
        if obj.has_key('ts'):
            obj['ts'] = int( obj['ts'] / 1e3 )
        if obj.has_key('is_valid'):
            del obj['is_valid']
        if obj.has_key('cf'):
            del obj['cf']
            
        return obj
    
    def alter_list_data_to_serialize(self, request, data):
        formatted_data = []
        for obj in data['objects']:
            formatted_data.append(self.format_ts_obj(obj.obj))
            
        return formatted_data
    
    def get_resource_uri(self, bundle_or_obj=None):
        return None
    
    def obj_create(self, bundle, **kwargs):
        if bundle.data is None:
            raise BadRequest("Empty request body provided")
        if DATA_KEY_TIME not in bundle.data:
            raise BadRequest("Required field %s not provided in request" % DATA_KEY_TIME)
        try:
            long(bundle.data[DATA_KEY_TIME])
        except:
            raise BadRequest("Time must be a unix timestamp")
        if DATA_KEY_VALUE not in bundle.data:
            raise BadRequest("Required field %s not provided in request" % DATA_KEY_VALUE)
        if "metadata_key" not in kwargs:
            raise BadRequest("No metadata key provided in URL")
        if "event_type" not in kwargs:
            raise BadRequest("event_type must be defined in URL.")
        if kwargs["event_type"] not in EVENT_TYPE_CONFIG:
            raise BadRequest("Invalid event_type %s" % kwargs["event_type"])
        if "summary_type" in kwargs and kwargs["summary_type"] not in SUMMARY_TYPES:
            raise BadRequest("Invalid summary type %s" % kwargs["summary_type"])
        if "summary_type" in kwargs and kwargs["summary_type"] != 'base':
            raise BadRequest("Only base summary-type allowed for writing. Cannot use %s" % kwargs["summary_type"])
        
        # create object
        bundle.obj = PSTimeSeriesObject(bundle.data[DATA_KEY_TIME], bundle.data[DATA_KEY_VALUE], kwargs["metadata_key"])
        bundle.obj.event_type =  kwargs["event_type"] 
        if "summary_type" in kwargs:
            bundle.obj.summary_type =  kwargs["summary_type"]
        if "summary_window" in kwargs:
            bundle.obj.summary_window =  kwargs["summary_window"]
        
        #check that this event_type is defined
        event_types = PSEventTypes.objects.filter(
            metadata__metadata_key=bundle.obj.metadata_key,
            event_type=bundle.obj.event_type,
            summary_type=bundle.obj.summary_type,
            summary_window=bundle.obj.summary_window)
        if(event_types.count() == 0):
            raise NotFound("Given event type does not exist for metadata key")
        
        #Insert into cassandra
        #NOTE: Ordering in model allows statistics to go last. If this ever changes may need to update code here.
        et_to_update = PSEventTypes.objects.filter(
            metadata__metadata_key=bundle.obj.metadata_key,
            event_type=bundle.obj.event_type)
        for et in et_to_update:
            ts_obj = PSTimeSeriesObject(bundle.obj.time,
                                            bundle.obj.value,
                                            bundle.obj.metadata_key,
                                            event_type=bundle.obj.event_type,
                                            summary_type=et.summary_type,
                                            summary_window=et.summary_window
                                            )
            self.handle_data_create(ts_obj)
        
        #Write data to database if everything succeeded
        db.flush()
        
        return bundle
    
    def handle_data_create(self, ts_obj):
        data_type = EVENT_TYPE_CONFIG[ts_obj.event_type]["type"]
        validator = TYPE_VALIDATOR_MAP[data_type]
        
        #Determine if we can do the summary
        if ts_obj.summary_type != "base" and ts_obj.summary_type not in ALLOWED_SUMMARIES[data_type]:
            #skip invalid summary. should do logging here
            return
        
        #validate data
        ts_obj.value = validator.validate(ts_obj)
        
        #Determine column family
        col_family = validator.summary_cf(ts_obj.summary_type)
        if col_family is None:
            col_family = EVENT_TYPE_CF_MAP[data_type]
        
        #perform initial summarization
        if  ts_obj.summary_type== "aggregation":
            validator.aggregation(db, ts_obj)
        elif ts_obj.summary_type == "average":
            validator.average(db, ts_obj)
        elif ts_obj.summary_type == "statistics":
            validator.statistics(db, ts_obj)
        
        #insert the data in the target column-family
        if col_family == db.rate_cf:
            ratebin = BaseRateBin(path=ts_obj.datapath, ts=ts_obj.get_datetime(), val=ts_obj.value, freq=ts_obj.freq)
            db.update_rate_bin(ratebin)
        elif col_family == db.agg_cf:
            agg = AggregationBin(path=ts_obj.datapath,
                    ts=ts_obj.get_datetime(), val=ts_obj.value["numerator"],
                    freq=ts_obj.freq, base_freq=ts_obj.base_freq, count=ts_obj.value["denominator"])
            db.aggs.insert(agg.get_key(), {agg.ts_to_jstime(): {'val': agg.val, str(agg.base_freq): agg.count}})
        elif col_family == db.raw_cf:
            rawdata = RawRateData(path=ts_obj.datapath, ts=ts_obj.get_datetime(), val=ts_obj.value, freq=ts_obj.freq)
            db.set_raw_data(rawdata)

perfsonar_api = Api(api_name='perfsonar')
perfsonar_api.register(PSArchiveResource())
perfsonar_api.register(PSEventTypesResource())