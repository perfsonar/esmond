import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from rest_framework.authtoken.models import Token

def generate_api_key_for_user(u):
    try:
        tok = Token.objects.get(user=u)
        print 'User {0} already has api key, skipping creation'.format(u)
    except Token.DoesNotExist:
        print 'User {0} does not have an api key - creating'.format(u)
        tok = Token.objects.create(user=u)

    print 'Key: {0}'.format(tok.key)

class Command(BaseCommand):
    help = 'Add a user with just an api key - no extended permissions.'

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

        generate_api_key_for_user(u)
