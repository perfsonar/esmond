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

from esmond.util import get_logger

#
# Logger
#
log = get_logger(__name__)

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

class ViewsetBase(viewsets.GenericViewSet):
    # XXX(mmg): enable permission_classes attr later.
    # permission_classes = (IsAuthenticatedOrReadOnly, DjangoModelPerm,)
    permission_classes = (AllowAny,) # lack of comma == error

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
    """Not used since timeseries data will be in several forms."""
    pass

class TimeSeriesViewset(UtilMixin, ViewsetBase):
    """
    The queryset attribute on this non-model resource is fake.
    It's there so we can use our custom resource permissions 
    (see models.APIPermission) with the standard DjangoModelPermissions
    classes.
    """
    queryset = _get_ersatz_esmond_api_queryset('timeseries')
    serializer_class = TimeSeriesSerializer # mollify viewset

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

        # generate response based on kwargs and query args, 
        # feed response payload to Response()
        payload = [
            dict(ts=30, val=10), dict(ts=60, val=20)
            ]

        return Response(payload)


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



