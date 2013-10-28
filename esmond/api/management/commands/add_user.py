import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group, Permission

from tastypie.models import ApiKey

from esmond.api.models import Device, OIDSet, DeviceOIDSetMap

class Command(BaseCommand):
    args = 'username'
    help = 'Add a user for POST access'

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
            new_user = User(username=user, is_staff=True)
            new_user.save()
            seeall = Permission.objects.get(codename="can_see_hidden_ifref")
            new_user.user_permissions.add(seeall)
            for resource in ['timeseries']:
                for perm_name in ['view', 'add', 'change', 'delete']:
                    perm = Permission.objects.get(
                        codename="esmond_api.{0}_{1}".format(perm_name, resource))
                    new_user.user_permissions.add(perm)

            new_user.save()
            new_user_apikey = ApiKey(user=new_user)
            new_user_apikey.key = new_user_apikey.generate_key()
            new_user_apikey.save()
            new_user.save()

        if not u:
            u = User.objects.get(username=user)

        key = ApiKey.objects.get(user=u)

        print 'Key: {0}'.format(key)

        