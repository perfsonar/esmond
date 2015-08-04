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

from rest_framework import (viewsets, serializers, status, 
        fields, relations, pagination, mixins, throttling)
from rest_framework.exceptions import (ParseError, NotFound, APIException)
from rest_framework.response import Response
from rest_framework.reverse import reverse

import rest_framework_filters as filters

from esmond.api.models import (PSMetadata, PSPointToPointSubject, PSEventTypes, 
    PSMetadataParameters, PSNetworkElementSubject)

from esmond.api.api_v2 import DataObject

#
# Bases, etc
#

class BaseMixin(object):
    def undash_dict(self, d):
        """Dict key dash => underscore conversion."""
        for i in d.keys():
            d[i.replace('-', '_')] = d.pop(i)

    def to_dash_dict(self, d):
        """Dict key underscore => dash conversion."""
        for i in d.keys():
            d[i.replace('_', '-')] = d.pop(i)

    def _add_uris(self, o):
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

#
# Base /archive/ endpoint
#

class ArchiveDataObject(DataObject):
    pass

class ArchiveSerializer(BaseMixin, serializers.ModelSerializer):
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
        obj.event_types = list()

        et_map = dict()

        for et in obj.pseventtypes.all():
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
                time_updated=v.get('time_updated'),
                summaries=[],
                )
            
            if v.get('summaries'):
                for a in v.get('summaries'):
                    s = dict(   
                        uri='/aggregations/{0}'.format(a[1]),
                        summary_type=a[0],
                        summary_window=a[1],
                        time_updated=a[2],
                    )   
                    self.to_dash_dict(s)
                    d['summaries'].append(s)

            self.to_dash_dict(d)
            obj.event_types.append(d)

        # serialize it now
        ret = super(ArchiveSerializer, self).to_representation(obj)

        # now add the arbitrary metadata values from the PSMetadataParameters
        # table.
        for p in obj.psmetadataparameters.all():
            ret[p.parameter_key] = p.parameter_value

        # add uris to various payload elements based on serialized URL field.
        self._add_uris(ret)
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
                    viewsets.GenericViewSet):

    """Implements GET, PUT and POST model operations w/specific mixins rather 
    than using viewsets.ModelSerializer for all the ops."""

    serializer_class = ArchiveSerializer
    lookup_field = 'metadata_key'

    def get_queryset(self):
        # Modify for custom filtering logic, etc
        ret = PSMetadata.objects.all()
        return ret

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




