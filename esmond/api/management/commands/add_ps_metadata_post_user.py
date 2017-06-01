import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group, Permission

from .add_api_key_user import generate_api_key_for_user

class Command(BaseCommand):
    help = 'Add a user for POST access to perfSONAR metdata'

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

        print 'Setting metadata POST permissions.'
        for model_name in ['psmetadata', 'pspointtopointsubject', 'pseventtypes', 'psmetadataparameters', 'psnetworkelementsubject']:
            for perm_name in ['add', 'change', 'delete']:
                perm = Permission.objects.get(codename='{0}_{1}'.format(perm_name, model_name))
                print perm
                u.user_permissions.add(perm)

        u.save()

        generate_api_key_for_user(u)
