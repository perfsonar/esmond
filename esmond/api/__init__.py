"""
Things used by the REST API (api.py) that are also imported by
other modules.  Reduces the overhead/etc of importing api.py itself.
"""

from esmond.config import get_config_path, get_config
from esmond.api.models import OIDSet

# Prefix used in all the snmp data cassandra keys
SNMP_NAMESPACE = 'snmp'

# Anon limit configurable in conf/sane default if unset.
alim = lambda x: x.api_anon_limit if x.api_anon_limit else 30
ANON_LIMIT = alim(get_config(get_config_path()))

# Set up data structure mapping oidsets/oids to REST uri endpoints.
class EndpointMap(object):
    """
    The dynamic endpoint map generation has been moved into 
    this class to avoid the map being generated on module import.
    That could cause conflicts with the test suite loading fixtures 
    and allows getting rid of the old "failover" static dict.
    Burying execution of the map generation until after the tests 
    have set up the in-memory db makes things happy.
    """
    def __init__(self):
        self.mapping = None

    def generate_endpoint_map(self):
        payload = {}
        for oidset in OIDSet.objects.all().order_by('name'):
            for oid in oidset.oids.all().order_by('name'):
                if oid.endpoint_alias:
                    if not payload.has_key(oidset.name):
                        payload[oidset.name] = {}
                    payload[oidset.name][oid.endpoint_alias] = oid.name
        return payload

    @property
    def endpoints(self):
        if not self.mapping:
            self.mapping = self.generate_endpoint_map()
        return self.mapping

OIDSET_INTERFACE_ENDPOINTS = EndpointMap()

