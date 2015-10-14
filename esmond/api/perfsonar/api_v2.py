import calendar
import collections
import copy
import datetime
import inspect
import json
import time
import urlparse

import pprint

pp = pprint.PrettyPrinter(indent=4)

from django.db.models import Q
from django.utils.timezone import utc

from socket import getaddrinfo, AF_INET, AF_INET6, SOL_TCP, SOCK_STREAM

from rest_framework import (viewsets, serializers, status, 
        fields, relations, pagination, mixins, throttling)
from rest_framework.exceptions import (ParseError, NotFound, APIException)
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.permissions import (IsAuthenticatedOrReadOnly, AllowAny)

import rest_framework_filters as filters

from esmond.api.models import (PSMetadata, PSPointToPointSubject, PSEventTypes, 
    PSMetadataParameters, PSNetworkElementSubject)

from esmond.api.api_v2 import (DataObject, _get_ersatz_esmond_api_queryset,
    DjangoModelPerm)

from esmond.api.perfsonar.types import *

from esmond.cassandra import KEY_DELIMITER, CASSANDRA_DB, AGG_TYPES, ConnectionException, RawRateData, BaseRateBin, RawData, AggregationBin

from esmond.config import get_config_path, get_config

from esmond.util import get_logger

#
# Logger
#
log = get_logger(__name__)

#
# Cassandra db connection
#
try:
    db = CASSANDRA_DB(get_config(get_config_path()), qname='perfsonar')
except ConnectionException, e:
    error_msg = "Unable to connect to cassandra. Please verify cassandra is running."
    log.error(error_msg)
    log.debug(str(e))
    raise ConnectionException(error_msg)

#
# Column families
#
EVENT_TYPE_CF_MAP = {
    'histogram': db.raw_cf,
    'integer': db.rate_cf,
    'json': db.raw_cf,
    'percentage': db.agg_cf,
    'subinterval': db.raw_cf,
    'float': db.agg_cf
}

#
# Bases, etc
#

class UtilMixin(object):
    def undash_dict(self, d):
        """Dict key dash => underscore conversion."""
        for i in d.keys():
            d[i.replace('-', '_')] = d.pop(i)

    def to_dash_dict(self, d):
        """Dict key underscore => dash conversion."""
        for i in d.keys():
            d[i.replace('_', '-')] = d.pop(i)

    def datetime_to_ts(self, dt):
        """Convert internal DB timestamp to unixtime."""
        if dt:
            return calendar.timegm(dt.utctimetuple())

    def add_uris(self, o):
        """Add Uris to payload from serialized URL value."""
        if o.get('url', None):
            # Parse DRF-generated URL field into chunks.
            up = urlparse.urlparse(o.get('url'))
            # Assign uri element to "main" payload
            o['uri'] = up.path
            # If there are event types associated, process them. If so,
            # the dicts in the events types list have already been 
            # "dashed" (ie: base-uri) even though the "main" payload
            # values (ie: event_types) have not.
            if o.get('event_types', None):
                for et in o.get('event_types'):
                    et['base-uri'] = o.get('uri') + et.get('base-uri')
                    for s in et.get('summaries'):
                        s['uri'] = o.get('uri') + s.get('uri')
        else:
            # no url, can't do anything
            return

    def build_event_type_list(self, queryset):
        """Given a filtered queryset/list, generate a formatted 
        list of event types."""
        et_map = dict()
        ret = list()

        for et in queryset:
            if not et_map.has_key(et.event_type):
                et_map[et.event_type] = dict(time_updated=None, summaries=list())
            if et.summary_type == 'base':
                et_map[et.event_type]['time_updated'] = et.time_updated
            else:
                et_map[et.event_type]['summaries'].append((et.summary_type, et.summary_window, et.time_updated))

        for k,v in et_map.items():
            d = dict(
                base_uri='{0}/base'.format(k),
                event_type=k,
                time_updated=self.datetime_to_ts(v.get('time_updated')),
                summaries=[],
                )
            
            if v.get('summaries'):
                for a in v.get('summaries'):
                    s = dict(   
                        uri='{0}/aggregations/{1}'.format(k, a[1]),
                        summary_type=a[0],
                        summary_window=a[1],
                        time_updated=self.datetime_to_ts(a[2]),
                    )   
                    self.to_dash_dict(s)
                    d['summaries'].append(s)

            self.to_dash_dict(d)
            ret.append(d)

        return ret

    def row_prefix(self, event_type):
        return ['ps', event_type.replace('-', '_') ]

class FilterUtilMixin(object):

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
            raise ParseError(detail="Invalid %s parameter %s" % (DNS_MATCH_RULE_FILTER, dns_match_rule))
        
        #add results to list
        if addr4: addrs.append(addr4)
        if addr6: addrs.append(addr6)
        if len(addrs) == 0:
            raise ParseError(detail="Unable to find address for host %s" % host)
        return addrs
    
    def valid_time(self, t):
        try:
            t = int(t)
        except ValueError:
            raise ParseError(detail="Time parameter must be an integer")
        return t
    
    def handle_time_filters(self, filters):
        end_time = int(time.time())
        begin_time = 0
        has_filters = True
        if filters.has_key(TIME_FILTER):
            begin_time = self.valid_time(filters[TIME_FILTER])
            end_time = begin_time
        elif filters.has_key(TIME_START_FILTER) and filters.has_key(TIME_END_FILTER):
            begin_time = self.valid_time(filters[TIME_START_FILTER])
            end_time = self.valid_time(filters[TIME_END_FILTER])
        elif filters.has_key(TIME_START_FILTER) and filters.has_key(TIME_RANGE_FILTER):
            begin_time = self.valid_time(filters[TIME_START_FILTER])
            end_time = begin_time + self.valid_time(filters[TIME_RANGE_FILTER])
        elif filters.has_key(TIME_END_FILTER) and filters.has_key(TIME_RANGE_FILTER):
            end_time = self.valid_time(filters[TIME_END_FILTER])
            begin_time = end_time - self.valid_time(filters[TIME_RANGE_FILTER])
        elif filters.has_key(TIME_START_FILTER):
            begin_time = self.valid_time(filters[TIME_START_FILTER])
            end_time = None
        elif filters.has_key(TIME_END_FILTER):
            end_time = self.valid_time(filters[TIME_END_FILTER])
        elif filters.has_key(TIME_RANGE_FILTER):
            begin_time = end_time - self.valid_time(filters[TIME_RANGE_FILTER])
            end_time = None
        else:
            has_filters = False
        if (end_time is not None) and (end_time < begin_time):
            raise ParseError(detail="Requested start time must be less than end time")
        return {"begin": begin_time,
                "end": end_time,
                "has_filters": has_filters}
                
    def valid_summary_window(self, sw):
        try:
            sw = int(sw)
        except ValueError:
            raise ParseError(detail="Summary window parameter must be an integer")
        return sw


class PSPaginator(pagination.LimitOffsetPagination):
    """
    General paginator that defaults to a set number of items and returns an
    unmodified response.
    """
    default_limit = 1000
    
    ## I actually kinda like the default pagination better
    ## but sticking with backward compatibility here
    def get_paginated_response(self, data):
    
        #create some pagination links in headers
        next_url = self.get_next_link()
        previous_url = self.get_previous_link()
        if next_url is not None and previous_url is not None:
            link = '<{next_url}>; rel="next", <{previous_url}>; rel="prev"'
        elif next_url is not None:
            link = '<{next_url}>; rel="next"'
        elif previous_url is not None:
            link = '<{previous_url}>; rel="prev"'
        else:
            link = ''
        link = link.format(next_url=next_url, previous_url=previous_url)
        headers = {'Link': link} if link else {}
        
        #return response with unmodified data and links in headers
        return Response(data, headers=headers)
        
class PSMetadataPaginator(PSPaginator):
    """
    Metadata API spec requires us to put pagination details in the first
    item returned so that is down here.
    """

    def get_paginated_response(self, data):
        
        if len(data) > 0:
            data[0]['metadata-count-total'] = self.count
            data[0]['metadata-previous-page'] = self.get_previous_link()
            data[0]['metadata-next-page'] = self.get_next_link()
            
        return super(PSMetadataPaginator, self).get_paginated_response(data)
        
class ViewsetBase(viewsets.GenericViewSet):
    # XXX(mmg): enable permission_classes attr later.
    # permission_classes = (IsAuthenticatedOrReadOnly, DjangoModelPerm,)
    permission_classes = (AllowAny,) # lack of comma == error
    pagination_class = PSPaginator
#
# Base endpoint(s) 
# (GET and POST) /archive/
# (GET and PUT)  /archive/$METADATA_KEY/ 
#

class ArchiveDataObject(DataObject):
    pass

class ArchiveSerializer(UtilMixin, serializers.ModelSerializer):
    class Meta:
        model = PSMetadata
        fields = (
            'url',
            'metadata_key', 
            'subject_type', 
            'destination',
            'source',
            'tool_name',
            'measurement_agent',
            'input_source',
            'input_destination',
            'event_types',
            )
        # These are for generation of the URL field. The view name corresponds
        # to the base_name of where this is wired to the router, and lookup_field 
        # is metadata_key since that's what the details are keying off of.
        extra_kwargs={'url': {'view_name': 'archive-detail', 'lookup_field': 'metadata_key'}}
    
    ## elements from PSPointToPointSubject
    # ips
    source = fields.IPAddressField(source='pspointtopointsubject.source')
    destination = fields.IPAddressField(source='pspointtopointsubject.destination')
    measurement_agent = fields.IPAddressField(source='pspointtopointsubject.measurement_agent')
    # char fields
    tool_name = fields.CharField(source='pspointtopointsubject.tool_name')
    input_source = fields.CharField(source='pspointtopointsubject.input_source')
    input_destination = fields.CharField(source='pspointtopointsubject.input_destination')
    ## elements from event type table - this is dynamically generated, 
    # so just use the type elements.
    event_types = fields.ListField(child=serializers.DictField())

    def to_representation(self, obj):
        """
        Generate event_types list.
        Modify outgoing data: massage underscore => dash.
        Add arbitrary values from PS metadata parameters.
        """

        # generate event type list for outgoing payload
        obj.event_types = self.build_event_type_list(obj.pseventtypes.all())

        # serialize it now
        ret = super(ArchiveSerializer, self).to_representation(obj)

        # now add the arbitrary metadata values from the PSMetadataParameters
        # table.
        for p in obj.psmetadataparameters.all():
            ret[p.parameter_key] = p.parameter_value

        # add uris to various payload elements based on serialized URL field.
        self.add_uris(ret)
        # convert underscores to dashes in attr names
        self.to_dash_dict(ret)
        
        return ret

    def to_internal_value(self, data):
        """
        Modify incoming json: massage dash => underscore before calling 
        base code. Probably irrelevant since input will be handled 
        by custom create methods.
        """
        # convert dashes to underscores before doing object
        # conversion.
        self.undash_dict(data)
        ret = super(ArchiveSerializer, self).to_internal_value(data)
        return ret

class ArchiveViewset(mixins.CreateModelMixin,
                    mixins.ListModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.UpdateModelMixin,
                    FilterUtilMixin,
                    ViewsetBase):

    """Implements GET, PUT and POST model operations w/specific mixins rather 
    than using viewsets.ModelSerializer for all the ops."""

    serializer_class = ArchiveSerializer
    lookup_field = 'metadata_key'
    pagination_class = PSMetadataPaginator
    
    def get_queryset(self):
        """
        Customize to do three things:
        1. Make sure event type parameters match the same event type object
        2. Apply the free-form metadata parameter filters also making sure they match the same row
        3. Create an OR condition between different subject types with same name
        """
        
        ret = PSMetadata.objects.all()
        metadata_only_filters = {}
        subject_qs = []
        event_type_qs = []
        parameter_qs = []
        #we need to make sure we have this before processing IP values
        dns_match_rule = self.request.query_params.get(DNS_MATCH_RULE_FILTER, None)
        
        #Convert get parameters to Django model filters
        for filter in self.request.query_params:
            filter_val = self.request.query_params.get(filter)
            
            #Determine type of filter
            if filter in SUBJECT_FILTER_MAP:
                # map subject to subject field
                subject_q = None
                for subject_db_field in SUBJECT_FILTER_MAP[filter]:
                    tmp_filters = {}
                    if filter in IP_FIELDS:
                        ip_val = self.prepare_ip(filter_val, dns_match_rule)
                        filter_key = "%s__in" % subject_db_field
                        tmp_filters[filter_key] = ip_val
                    else:
                        tmp_filters[subject_db_field] = filter_val
                    
                    if(subject_q is None):
                        subject_q = Q(**tmp_filters)
                    else:
                        subject_q = subject_q | Q(**tmp_filters)
                if(subject_q is not None):
                    subject_qs.append(subject_q)
            elif filter == EVENT_TYPE_FILTER:
                event_type_qs.append(Q(pseventtypes__event_type=filter_val))
            elif filter == SUMMARY_TYPE_FILTER:
                event_type_qs.append(Q(pseventtypes__summary_type=filter_val))
            elif filter == SUMMARY_WINDOW_FILTER:
                event_type_qs.append(Q(pseventtypes__summary_window=filter_val))            
            elif filter == SUBJECT_TYPE_FILTER:
                ret = ret.filter(subject_type=filter_val)
            elif filter == METADATA_KEY_FILTER:
                ret = ret.filter(metadata_key=filter_val)
            elif filter not in RESERVED_GET_PARAMS:
                if filter in IP_FIELDS:
                    ip_val = self.prepare_ip(filter_val, dns_match_rule)
                    # map to ps_metadata_parameters
                    parameter_qs.append(Q(
                        psmetadataparameters__parameter_key=filter,
                        psmetadataparameters__parameter_value__in=ip_val))
                else:
                    # map to ps_metadata_parameters
                    parameter_qs.append(Q(
                    psmetadataparameters__parameter_key=filter,
                    psmetadataparameters__parameter_value=filter_val))
        
        #add time filters if there are any
        time_filters = self.handle_time_filters(self.request.query_params)
        if(time_filters["has_filters"]):
            #print "begin_ts=%d, end_ts=%d" % (time_filters['begin'], time_filters['end'])
            begin = datetime.datetime.utcfromtimestamp(time_filters['begin']).replace(tzinfo=utc)
            event_type_qs.append(Q(pseventtypes__time_updated__gte=begin))
            if time_filters['end'] is not None:
                end = datetime.utcfromtimestamp(time_filters['end']).replace(tzinfo=utc)
                event_type_qs.append(Q(pseventtypes__time_updated__lte=end))
            
        #apply filters. this is done down here to ensure proper grouping
        if event_type_qs:
            ret = ret.filter(*event_type_qs)
        for parameter_q in parameter_qs:
            ret = ret.filter(parameter_q)
        for subject_q in subject_qs:
            ret = ret.filter(subject_q)
        
        return ret.distinct()

    def list(self, request):
        """Stub for list GET ie:

        GET /perfsonar/archive/

        Probably won't need modification, just here for reference.
        """
        return super(ArchiveViewset, self).list(request)

    def retrieve(self, request, **kwargs):
        """Stub for detail GET 'metadata_key', will be one of 
        the kwargs since that is defined as the lookup field for the 
        detail view - ie:

        /GET perfsonar/archive/$METADATA_KEY/

        Probably won't need modification, just here for reference.
        """
        return super(ArchiveViewset, self).retrieve(request, **kwargs)

    def create(self, request):
        """Stub for POST metadata object creation - ie:

        POST /perfsonar/archive/"""
        # validate the incoming json and data contained therein.
        if not request.content_type.startswith('application/json'):
            return Response({'error': 'Must post content-type: application/json header and json-formatted payload.'},
                status.HTTP_400_BAD_REQUEST)

        if not request.body:
            return Response({'error': 'No data payload POSTed.'}, status.HTTP_400_BAD_REQUEST)

        try:
            request_data = json.loads(request.body)
        except ValueError:
            return Response({'error': 'POST data payload could not be decoded to a JSON object - given: {0}'.format(request.body)},
                status.HTTP_400_BAD_REQUEST)

        # process the json blob that was sent to the server.
        # print request_data

        # assemble return payload and send back to the client, or 
        # empty string/etc.
        return_payload = dict(thanks='for that')
        return Response(return_payload, status.HTTP_201_CREATED)

    def update(self, request, **kwargs):
        """Stub for PUT detail object creation to a metadata instance 
        for bulk data/event type creation. ie:

        PUT /perfsonar/archive/$METADATA_KEY/

        'metadata_key' will be in kwargs
        """
        # validate the incoming json and data contained therein.
        if not request.content_type.startswith('application/json'):
            return Response({'error': 'Must post content-type: application/json header and json-formatted payload.'},
                status.HTTP_400_BAD_REQUEST)

        if not request.body:
            return Response({'error': 'No data payload POSTed.'}, status.HTTP_400_BAD_REQUEST)

        try:
            request_data = json.loads(request.body)
        except ValueError:
            return Response({'error': 'POST data payload could not be decoded to a JSON object - given: {0}'.format(request.body)},
                status.HTTP_400_BAD_REQUEST)

        # process the json blob that was sent to the server.
        # print request_data

        # assemble return payload and send back to the client, or 
        # empty string/etc.
        return_payload = dict(thanks='for that')
        return Response(return_payload, status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        """
        No PATCH verb.
        """
        return Response({'error': 'does not support PATCH verb'}, status.HTTP_400_BAD_REQUEST)

#
# Event type detail endpoint
# (GET and POST) /archive/$METADATA_KEY/$EVENT_TYPE/
# 

class EventTypeDetailSerializer(serializers.Serializer):
    """Not used since output will just be generated by existing code."""
    pass

class EventTypeDetailViewset(UtilMixin, ViewsetBase):
    # no queryset attr, override get_queryset instead
    serializer_class = EventTypeDetailSerializer # mollify viewset

    def get_queryset(self):

        ret = PSEventTypes.objects.filter(
            metadata__metadata_key=self.kwargs.get('metadata_key'),
            event_type=self.kwargs.get('event_type'),
            )

        return ret

    def add_uris(self, l, request):
        mdata_url = reverse(
            'archive-detail',
            kwargs={
                'metadata_key': self.kwargs.get('metadata_key')
            },
            request=request,
            )

        up = urlparse.urlparse(mdata_url)

        for i in l:
            i['base-uri'] = up.path + i['base-uri']
            for s in i['summaries']:
                s['uri'] = up.path + s['uri']


    def retrieve(self, request, **kwargs):
        """
        Detail for event type - ie:

        GET /perfsonar/archive/$METADATA_KEY/$EVENT_TYPE/

        kwargs will look like this:
        {'metadata_key': u'0CB19291FB6D40EAA1955376772BF5D2', 'event_type': u'histogram-owdelay'}
        """
        qs = self.get_queryset()
        payload = self.build_event_type_list(qs)

        self.add_uris(payload, request)

        return Response(payload)


    def create(self, request, **kwargs):
        """
        Create for event type - ie:

        POST /perfsonar/archive/$METADATA_KEY/$EVENT_TYPE/

        kwargs will look like this:
        {'metadata_key': u'0CB19291FB6D40EAA1955376772BF5D2', 'event_type': u'histogram-owdelay'}
        """
        # validate the incoming json and data contained therein.
        if not request.content_type.startswith('application/json'):
            return Response({'error': 'Must post content-type: application/json header and json-formatted payload.'},
                status.HTTP_400_BAD_REQUEST)

        if not request.body:
            return Response({'error': 'No data payload POSTed.'}, status.HTTP_400_BAD_REQUEST)

        try:
            request_data = json.loads(request.body)
        except ValueError:
            return Response({'error': 'POST data payload could not be decoded to a JSON object - given: {0}'.format(request.body)},
                status.HTTP_400_BAD_REQUEST)

        # process the json blob that was sent to the server.
        # print request_data

        return Response('', status.HTTP_201_CREATED)

#
# Data retrieval endpoint
# (GET and POST) /archive/$METADATA_KEY/$EVENT_TYPE/$SUMMARY_TYPE
# (GET and POST) /archive/$METADATA_KEY/$EVENT_TYPE/$SUMMARY_TYPE/$SUMMARY_WINDOW
# 

class TimeSeriesSerializer(serializers.Serializer):
    
    def to_representation(self, obj):
        if obj.has_key('ts'):
            obj['ts'] = int( obj['ts'] / 1e3 )
        if obj.has_key('is_valid'):
            del obj['is_valid']
        if obj.has_key('cf'):
            del obj['cf']
            
        return obj

class TimeSeriesViewset(UtilMixin, FilterUtilMixin, ViewsetBase):
    """
    The queryset attribute on this non-model resource is fake.
    It's there so we can use our custom resource permissions 
    (see models.APIPermission) with the standard DjangoModelPermissions
    classes.
    """
    queryset = _get_ersatz_esmond_api_queryset('timeseries')
    serializer_class = TimeSeriesSerializer # mollify viewset
    pagination_class = PSPaginator
    
    def _query_database(self, metadata_key, event_type, summary_type, freq, begin_time, end_time, max_results):
        results = []
        datapath = self.row_prefix(event_type)
        datapath.append(metadata_key)
        if(summary_type != 'base'):
            datapath.append(SUMMARY_TYPES[summary_type])
        
        query_type = EVENT_TYPE_CONFIG[event_type]["type"]
        if query_type not in EVENT_TYPE_CF_MAP:
            raise ParseError(detail="Misconfigured event type on server side. Invalid 'type' %s" % query_type)
        col_fam = TYPE_VALIDATOR_MAP[query_type].summary_cf(db, SUMMARY_TYPES[summary_type])
        if col_fam is None:
            col_fam = EVENT_TYPE_CF_MAP[query_type]
            
        #prep times
        begin_millis = begin_time*1000
        end_millis = None
        if end_time is None:
            # we need a value here so we know what years to look at when we get row keys
            # add a 3600 second buffer to capture results that may have been updated after we 
            # calculate this timestamp.
            end_millis = (int(time.time()) + 3600) * 1000
        else:
            end_millis = end_time*1000
        log.debug("action=query_timeseries.start md_key=%s event_type=%s summ_type=%s summ_win=%s start=%s end=%s start_millis=%s end_millis=%s cf=%s datapath=%s" %
                  (metadata_key, event_type, summary_type, freq, begin_time, end_time, begin_millis, end_millis, col_fam, datapath))

        if col_fam == db.agg_cf:
            results = db.query_aggregation_timerange(path=datapath, freq=freq,
                   cf='average', ts_min=begin_millis, ts_max=end_millis, column_count=max_results)
        elif col_fam == db.rate_cf:
            results = db.query_baserate_timerange(path=datapath, freq=freq,
                    cf='delta', ts_min=begin_millis, ts_max=end_millis, column_count=max_results)
        elif col_fam == db.raw_cf:
            results = db.query_raw_data(path=datapath, freq=freq,
                   ts_min=begin_millis, ts_max=end_millis, column_count=max_results)
        else:
            log.debug("action=query_timeseries.end status=-1")
            raise ParseError(detail="Requested data does not map to a known column-family")

        return results
        
    def retrieve(self, request, **kwargs):
        """
        GET request for timeseries data.

        GET /archive/$METADATA_KEY/$EVENT_TYPE/$SUMMARY_TYPE
        GET /archive/$METADATA_KEY/$EVENT_TYPE/$SUMMARY_TYPE/$SUMMARY_WINDOW

        kwargs will look like:
        {'metadata_key': u'0CB19291FB6D40EAA1955376772BF5D2', 'summary_type': u'base', 'event_type': u'histogram-owdelay'}

        or

        {'summary_window': u'86400', 'metadata_key': u'0CB19291FB6D40EAA1955376772BF5D2', 'summary_type': u'aggregations', 'event_type': u'histogram-owdelay'}

        depending on the request.
        """
        
        #verify URL
        if 'event_type' not in kwargs:
            raise ParseError(detail="No event type specified for data query")
        elif 'metadata_key' not in kwargs:
            raise ParseError(detail="No metadata key specified for data query")
        elif kwargs['event_type'] not in EVENT_TYPE_CONFIG:
            raise ParseError(detail="Unsupported event type '%s' provided" % kwargs['event_type'])
        elif "type" not in EVENT_TYPE_CONFIG[kwargs['event_type']]:
            raise ParseError(detail="Misconfigured event type on server side. Missing 'type' field")
        event_type = kwargs['event_type']
        metadata_key = kwargs['metadata_key']
        summary_type = 'base'
        if 'summary_type' in kwargs:
            summary_type = kwargs['summary_type']
            if summary_type not in SUMMARY_TYPES:
                raise ParseError(detail="Invalid summary type '%s'" % summary_type)
        freq = None
        if 'summary_window' in kwargs:
            freq = self.valid_summary_window(kwargs['summary_window'])

        #Handle time filters
        time_result = self.handle_time_filters(request.query_params)
        begin_time = time_result['begin']
        end_time = time_result['end']
        
        #Handle pagination
        ##set high limit by default. This is a performance gain so pycassa doesn't have to count
        max_results = 1000000 
        #if specified, make sure we grab enough results so can handle offset
        if LIMIT_FILTER in request.query_params:
            max_results = int(request.query_params[LIMIT_FILTER])
            if OFFSET_FILTER in request.query_params:
                max_results += int(request.query_params[OFFSET_FILTER])
                
        #send query
        results = self._query_database(metadata_key, event_type, summary_type, freq, begin_time, end_time, max_results)
        #serialize result
        data = self.serializer_class(results, many=True).data
        #paginate result
        data = self.paginator.paginate_queryset(data, self.request, view=self)
        
        #return response with pagination headers set
        return self.paginator.get_paginated_response(data)


    def create(self, request, **kwargs):
        """
        POST request for timeseries data.

        POST /archive/$METADATA_KEY/$EVENT_TYPE/$SUMMARY_TYPE
        POST /archive/$METADATA_KEY/$EVENT_TYPE/$SUMMARY_TYPE/$SUMMARY_WINDOW

        kwargs will look like:
        {'metadata_key': u'0CB19291FB6D40EAA1955376772BF5D2', 'summary_type': u'base', 'event_type': u'histogram-owdelay'}

        or

        {'summary_window': u'86400', 'metadata_key': u'0CB19291FB6D40EAA1955376772BF5D2', 'summary_type': u'aggregations', 'event_type': u'histogram-owdelay'}

        depending on the request.
        """
        # validate the incoming json and data contained therein.
        if not request.content_type.startswith('application/json'):
            return Response({'error': 'Must post content-type: application/json header and json-formatted payload.'},
                status.HTTP_400_BAD_REQUEST)

        if not request.body:
            return Response({'error': 'No data payload POSTed.'}, status.HTTP_400_BAD_REQUEST)

        try:
            request_data = json.loads(request.body)
        except ValueError:
            return Response({'error': 'POST data payload could not be decoded to a JSON object - given: {0}'.format(request.body)},
                status.HTTP_400_BAD_REQUEST)

        # process the json blob that was sent to the server.
        print request_data

        return Response('', status.HTTP_201_CREATED)
