import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group, Permission

from .add_api_key_user import generate_api_key_for_user

from esmond.api.models import Device, OIDSet, DeviceOIDSetMap

class Command(BaseCommand):
    help = 'Add a user for POST access'

    def add_arguments(self, parser):
        parser.add_argument('username')

    def handle(self, *args, **options):
        user = options['username']

        u = None

        try:
            u = User.objects.get(username=user)
            print 'User {0} exists'.format(user)
        except User.DoesNotExist:
            print 'User {0} does not exist - creating'.format(user)
            u = User(username=user, is_staff=True)
            u.save()

        print 'Setting timeseries permissions.'
        for resource in ['timeseries']:
            for perm_name in ['view', 'add', 'change', 'delete']:
                perm = Permission.objects.get(
                    codename="esmond_api.{0}_{1}".format(perm_name, resource))
                u.user_permissions.add(perm)

        u.save()

        generate_api_key_for_user(u)
