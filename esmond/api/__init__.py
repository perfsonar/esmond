"""
Things used by the REST API (api.py) that are also imported by
other modules.  Reduces the overhead/etc of importing api.py itself.
"""

from esmond.config import get_config_path, get_config
from esmond.api.models import OIDSet

from tastypie.authorization import Authorization
from tastypie.authentication import ApiKeyAuthentication

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

# Custom Authn/Authz classes that are now being used by other API components.

def anonymous_username(request):
    return 'AnonymousUser_{0}'.format(request.META.get('REMOTE_ADDR', 'noaddr'))

class AnonymousGetElseApiAuthentication(ApiKeyAuthentication):
    """Allow GET without authentication, rely on API keys for all else"""
    def is_authenticated(self, request, **kwargs):
        authenticated = super(AnonymousGetElseApiAuthentication, self).is_authenticated(
                request, **kwargs)

        # we always allow GET, but is_authenticated() has side effects which add
        # the user data to the request, which we want if available, so do
        # is_authenticated first then return True for all GETs

        if request.method == 'GET':
            return True

        return authenticated

    def get_identifier(self, request):
        if request.user.is_anonymous():
            return anonymous_username(request)
        else:
            return super(AnonymousGetElseApiAuthentication,
                    self).get_identifier(request)

class EsmondAuthorization(Authorization):
    """
    Uses a custom set of ``django.contrib.auth`` permissions to manage
    authorization for various actions in the API.  Since many of of esmond's
    resources don't map directly (or at all) to Django models we can't use the
    ``tastypie.authorization.DjangoAuthorization`` class.
    """

    perm_prefix = "auth.esmond_api"

    def __init__(self, resource_name):
        """There is not way to get the resource name from what is passed into
        the checks below, so for now we list it explicitly."""

        self.resource_name = resource_name
        return super(Authorization, self).__init__()

    def read_list(self, object_list, bundle):
        # GET-style methods are always allowed.
        return object_list

    def read_detail(self, object_list, bundle):
        # GET-style methods are always allowed.
        return True

    def create_list(self, object_list, bundle):
        permission = '%s.add_%s' % (self.perm_prefix, self.resource_name)

        if not bundle.request.user.has_perm(permission):
            raise Unauthorized("Permission denied")

        return object_list

    def create_detail(self, object_list, bundle):
        permission = '%s.add_%s' % (self.perm_prefix, self.resource_name)

        if not bundle.request.user.has_perm(permission):
            raise Unauthorized("Permission denied")

        return True

    def update_list(self, object_list, bundle):
        permission = '%s.change_%s' % (self.perm_prefix, self.resource_name)

        if not bundle.request.user.has_perm(permission):
            raise Unauthorized("Permission denied")

        return object_list

    def update_detail(self, object_list, bundle):
        permission = '%s.change_%s' % (self.perm_prefix, self.resource_name)

        if not bundle.request.user.has_perm(permission):
            raise Unauthorized("Permission denied")

        return True

    def delete_list(self, object_list, bundle):
        permission = '%s.delete_%s' % (self.perm_prefix, self.resource_name)

        if not bundle.request.user.has_perm(permission):
            raise Unauthorized("Permission denied")

        return object_list

    def delete_detail(self, object_list, bundle):
        permission = '%s.delete_%s' % (self.perm_prefix, self.resource_name)

        if not bundle.request.user.has_perm(permission):
            raise Unauthorized("Permission denied")

        return True



