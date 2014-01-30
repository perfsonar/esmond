from calendar import timegm
from esmond.api.models import PSMetadata, PSPointToPointSubject, PSEventTypes, PSMetadataParameters
from esmond.cassandra import KEY_DELIMITER, CASSANDRA_DB, AGG_TYPES, ConnectionException, RawRateData, BaseRateBin
from esmond.config import get_config_path, get_config
from datetime import datetime
from django.conf.urls.defaults import url
from django.db.models import Q
from django.utils.text import slugify
from socket import getaddrinfo, AF_INET, AF_INET6, SOL_TCP, SOCK_STREAM
from string import join
from tastypie import fields
from tastypie.api import Api
from tastypie.bundle import Bundle
from tastypie.exceptions import BadRequest
from tastypie.resources import Resource, ModelResource, ALL_WITH_RELATIONS
from time import time

'''
START MOVE TO CONFIG
'''
EVENT_TYPE_CONFIG = {
    "failures": {
        "type": "json",
        "row_prefix": "ps:failures"
    },
    "histogram-owdelay": {
        "type": "histogram",
        "row_prefix": "ps:histogram_owdelay"
    },
    "histogram-rtt": {
        "type": "histogram",
        "row_prefix": "ps:histogram_rtt"
    },
    "histogram-ttl": {
        "type": "histogram",
        "row_prefix": "ps:histogram_ttl"
    },
    "packet-duplicates": {
        "type": "integer",
        "row_prefix": "ps:packet_duplicates"
    },
    "packet-loss-rate": {
        "type": "rate",
        "row_prefix": "ps:packet_loss_rate",
        "numerator": "packet-count-lost",
        "denominator": "packet-count-sent"
    },
    "packet-trace": {
        "type": "json",
        "row_prefix": "ps:packet_trace"
    },
    "packet-count-lost": {
        "type": "integer",
        "row_prefix": "ps:packet_count_lost"
    },
    "packet-count-sent": {
        "type": "integer",
        "row_prefix": "ps:packet_count_sent"
    },
    "throughput": {
        "type": "integer",
        "row_prefix": "ps:throughput"
    },
    "time-error-estimates": {
        "type": "float",
        "row_prefix": "ps:time_error_estimates"
    }
}
SUMMARY_TYPES = {
    "base": "base",
    "aggregations": "aggregation",
    "composites": "composite",
    "statistics": "statistics",
    "subintervals": "subinterval"
}
INVERSE_SUMMARY_TYPES = {v:k for k,v in SUMMARY_TYPES.items()}
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
IP_FIELDS = ["source","destination","measurement-agent"]
EVENT_TYPE_FILTER = "event-type"
'''
END MOVE TO CONFIG
'''

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
    'rate': db.agg_cf,
    'numeric': db.raw_cf

}
SUMMARY_TYPE_FILTER = "summary-type"
SUMMARY_WINDOW_FILTER = "summary-window"
DNS_MATCH_RULE_FILTER = "dns-match-rule"
DNS_MATCH_PREFER_V6 = "prefer-v6"
DNS_MATCH_PREFER_V4 = "prefer-v4"
DNS_MATCH_ONLY_V6 = "only-v6"
DNS_MATCH_ONLY_V4 = "only-v4"
DNS_MATCH_V4_V6 = "v4v6"
RESERVED_GET_PARAMS = ["format", DNS_MATCH_RULE_FILTER]

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
    class Meta:
        queryset=PSEventTypes.objects.all()
        resource_name = 'event-type'
        allowed_methods = ['get', 'post']
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
        allowed_methods = ['get', 'post']
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
    class Meta:
        queryset=PSMetadataParameters.objects.all()
        resource_name = 'metadata-parameters'
        allowed_methods = ['get', 'post']
        excludes = ['id']
        
class PSArchiveResource(ModelResource):
    event_types = fields.ToManyField(PSEventTypesResource, 'pseventtypes', full=True, null=True, blank=True)
    p2p_subject = fields.ToOneField(PSPointToPointSubjectResource, 'pspointtopointsubject', full=True)
    md_parameters = fields.ToManyField(PSMetadataParametersResource, 'psmetadataparameters', full=True, null=True, blank=True)
    
    class Meta:
        queryset=PSMetadata.objects.all()
        resource_name = 'archive'
        detail_uri_name = 'metadata_key'
        allowed_methods = ['get', 'post']
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
    
    def alter_deserialized_list_data(self, request, data):
        print data    
        raise BadRequest("Not yet implemented")
    
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

class PSTimeSeriesResource(Resource):
    
    class Meta:
        resource_name = 'pstimeseries'
        allowed_methods = ['get', 'post']
        limit = 0
    
    def iso_to_ts(self, isotime):
        ts = 0
        try:
            dt = datetime.strptime(isotime, "%Y%m%dT%H%M%S")
            ts = timegm(dt.timetuple())
            print ts
        except ValueError:
            raise BadRequest("Time parameter be in ISO8601 basic format YYYYMMDDThhmmss.")
            
        return ts
    
    def valid_time_range(self, tr):
        try:
            tr = int(tr)
        except ValueError:
            raise BadRequest("Time range parameter must be an integer")
        return tr
    
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
            begin_time = self.iso_to_ts(filters['time'])
            end_time = begin_time
        elif filters.has_key('time-start') and filters.has_key('time-end'):
            begin_time = self.iso_to_ts(filters['time-start'])
            end_time = self.iso_to_ts(filters['time-end'])
        elif filters.has_key('time-start') and filters.has_key('time-range'):
            begin_time = self.iso_to_ts(filters['time-start'])
            end_time = begin_time + self.valid_time_range(filters['time-range'])
        elif filters.has_key('time-end') and filters.has_key('time-range'):
            end_time = self.iso_to_ts(filters['time-end'])
            begin_time = end_time - self.valid_time_range(filters['time-range'])
        elif filters.has_key('time-start'):
           begin_time = self.iso_to_ts(filters['time-start'])
        elif filters.has_key('time-end'):
           end_time = self.iso_to_ts(filters['time-end'])
        elif filters.has_key('time-range'):
           begin_time = end_time - self.valid_time_range(filters['time-range'])
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
        metadata_key = slugify( kwargs['metadata_key'])
        datapath = EVENT_TYPE_CONFIG[event_type]["row_prefix"].split(KEY_DELIMITER)
        datapath.append(metadata_key)
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
        elif EVENT_TYPE_CF_MAP[query_type] == db.rate_cf:
            results = db.query_baserate_timerange(path=datapath, freq=freq,
                    cf='delta', ts_min=begin_time*1000, ts_max=end_time*1000)
        elif EVENT_TYPE_CF_MAP[query_type] == db.raw_cf:
            results = db.query_raw_data(path=datapath, freq=freq,
                   ts_min=begin_time*1000, ts_max=end_time*1000)
        elif EVENT_TYPE_CF_MAP[query_type] == db.agg_cf:
            results = db.query_aggregation_timerange(path=datapath, freq=freq,
                   cf='average', ts_min=begin_time*1000, ts_max=end_time*1000)
        else:
            raise BadRequest("Requested data does not map to a known column-family")
            
        return results
    
    def format_ts_obj(self, obj):
        formatted_obj = {'time': None, 'value': None}
        if obj.has_key('ts'):
            dt = datetime.utcfromtimestamp(obj['ts'] / 1e3)
            formatted_obj['time'] = dt.isoformat() + 'Z' #add timezone
            
        if obj.has_key('val'):
            formatted_obj['value'] = obj['val']
        
        return formatted_obj
    
    def alter_list_data_to_serialize(self, request, data):
        formatted_data = []
        for obj in data['objects']:
            formatted_data.append(self.format_ts_obj(obj.obj))
            
        return formatted_data
    
perfsonar_api = Api(api_name='perfsonar')
perfsonar_api.register(PSArchiveResource())
perfsonar_api.register(PSEventTypesResource())