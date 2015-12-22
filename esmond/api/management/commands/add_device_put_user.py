import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group, Permission

from esmond.api.models import Device, OIDSet, DeviceOIDSetMap
from .add_api_key_user import generate_api_key_for_user

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
            u = User(username=user, is_staff=True)
            u.save()

        print 'Setting device PUT permissions.'
        for model_name in ['device', 'deviceoidsetmap', 'devicetagmap']:
            for perm_name in ['add', 'change', 'delete']:
                perm = Permission.objects.get(codename='{0}_{1}'.format(perm_name, model_name))
                print perm
                u.user_permissions.add(perm)

        u.save()
            
        generate_api_key_for_user(u)

        