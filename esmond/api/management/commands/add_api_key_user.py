import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from rest_framework.authtoken.models import Token

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
            tok = Token.objects.get(user=u)
            print 'User {0} already has api key, skipping creation'.format(user)
        except Token.DoesNotExist:
            print 'User {0} does not have an api key - creating'.format(user)
            tok = Token.objects.create(user=u)

        print 'Key: {0}'.format(tok.key)

        