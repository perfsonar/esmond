import json

from esmond.api import ANON_LIMIT

from tastypie.authorization import Authorization
from tastypie.authentication import ApiKeyAuthentication
from tastypie.throttle import CacheDBThrottle

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

class AnonymousBulkLimitElseApiAuthentication(ApiKeyAuthentication):
    """For bulk data retrieval interface.  If user has valid Api Key,
    allow unthrottled access.  Otherwise, check the size of the 
    quantity of interfaces/endpoints requested and """
    def is_authenticated(self, request, **kwargs):
        authenticated = super(AnonymousBulkLimitElseApiAuthentication, self).is_authenticated(
                request, **kwargs)

        # If they are username/api key authenticated, just
        # let the request go.
        if authenticated == True:
            return authenticated

        # Otherwise, look at the size of the request (ie: number of 
        # endpoints requested) and react accordingly.

        if request.body and request.META.get('CONTENT_TYPE') == 'application/json':
            post_payload = json.loads(request.body)
        else:
            raise BadRequest('Did not receive json payload for bulk POST request.')

        if not post_payload.has_key('interfaces') or \
            not post_payload.has_key('endpoint'):
            raise BadRequest('JSON payload must have endpoint and interfaces keys.')  

        if not isinstance(post_payload['interfaces'], list) or \
            not isinstance(post_payload['endpoint'], list):
            raise BadRequest('Both endpoint and interfaces keys must be a list')

        request_queries = len(post_payload.get('interfaces')) * \
            len(post_payload.get('endpoint'))

        if request_queries <= ANON_LIMIT:
            return True
        else:
            authenticated.content = \
                'Request for {0} endpoints exceeds the unauthenticated limit of {1}'.format(request_queries, ANON_LIMIT)

        return authenticated

    def get_identifier(self, request):
        if request.user.is_anonymous():
            return anonymous_username(request)
        else:
            return super(AnonymousBulkLimitElseApiAuthentication,
                    self).get_identifier(request)

class AnonymousTimeseriesBulkLimitElseApiAuthentication(ApiKeyAuthentication):
    """For bulk data retrieval interface.  If user has valid Api Key,
    allow unthrottled access.  Otherwise, check the size of the 
    quantity of interfaces/endpoints requested and """
    def is_authenticated(self, request, **kwargs):
        authenticated = super(AnonymousTimeseriesBulkLimitElseApiAuthentication, self).is_authenticated(
                request, **kwargs)
        
        # If they are username/api key authenticated, just
        # let the request go.
        if authenticated == True:
            return authenticated

        # Otherwise, look at the size of the request (ie: number of 
        # paths requested) and react accordingly.

        if request.body and request.META.get('CONTENT_TYPE') == 'application/json':
            post_payload = json.loads(request.body)
        else:
            raise BadRequest('Did not receive json payload for bulk POST request.')

        if not post_payload.has_key('paths') or \
            not isinstance(post_payload['paths'], list):
            raise BadRequest('Payload must contain the element paths and that element must be a list.')

        if len(post_payload['paths']) <= ANON_LIMIT:
            return True
        else:
            authenticated.content = \
                'Request for {0} paths exceeds the unauthenticated limit of {1}'.format(len(post_payload['paths']), ANON_LIMIT)

        return authenticated

    def get_identifier(self, request):
        if request.user.is_anonymous():
            return anonymous_username(request)
        else:
            return super(AnonymousTimeseriesBulkLimitElseApiAuthentication,
                    self).get_identifier(request)

class AnonymousThrottle(CacheDBThrottle):
    def __init__(self, **kwargs):
        # Parse incoming args from config, let superclass defaults
        # ride if not set.
        _kw = {}
        for k,v in kwargs.items():
            if v:
                _kw[k] = v
        super(AnonymousThrottle, self).__init__(**_kw)

    def should_be_throttled(self, identifier, **kwargs):
        if not identifier.startswith('AnonymousUser'):
            return False

        return super(AnonymousThrottle, self).should_be_throttled(identifier, **kwargs)


