import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group, Permission

from tastypie.models import ApiKey

from esmond.api.models import Device, OIDSet, DeviceOIDSetMap

class Command(BaseCommand):
    args = 'username'
    help = 'Add a user with just an api key - no extended permissions.'

    def handle(self, *args, **options):
        self.options = options

        if len(args) < 1 or len(args) > 1:
            print >>sys.stderr, "takes one argument: %s" % self.args
            return

        user = args[0]

        u = None

        try:
            u = User.objects.get(username=user)
            print 'User {0} exists'.format(user)
        except User.DoesNotExist:
            print 'User {0} does not exist - creating'.format(user)
            u = User(username=user, is_staff=True)
            u.save()
            
        try:
            key = ApiKey.objects.get(user=u)
            print 'User {0} already has api key, skipping creation'.format(user)
        except ApiKey.DoesNotExist:
            print 'User {0} does not have an api key - creating'.format(user)
            u_apikey = ApiKey(user=u)
            u_apikey.key = u_apikey.generate_key()
            u_apikey.save()
            u.save()

        key = ApiKey.objects.get(user=u)

        print 'Key: {0}'.format(key)

        