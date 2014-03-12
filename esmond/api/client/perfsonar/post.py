import json
import pprint
import requests
import warnings

from esmond.api.client.util import add_apikey_header
from esmond.api.client.perfsonar.query import Metadata
from esmond.api.perfsonar.types import EVENT_TYPE_CONFIG

class MetadataPostException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class MetadataPostWarning(Warning): pass

class MetadataPost(object):
    wrn = MetadataPostWarning
    """docstring for MetadataPost"""
    def __init__(self, api_url):
        super(MetadataPost, self).__init__()
        self.api_url = api_url
        
