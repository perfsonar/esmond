import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from esmond.api.models import UserIpAddress

class Command(BaseCommand):
    help = 'List IP subnet(s) associated with user account(s)'

    def add_arguments(self, parser):
        parser.add_argument('--username', help='only show IPs for the given username')

    def handle(self, *args, **options):
        #get optional user
        user = options.get('username', None)
        
        #if user provided, make sure it exists
        u = None
        if user is not None:
            try:
                u = User.objects.get(username=user)
            except User.DoesNotExist:
                raise CommandError('User {0} does not exist'.format(user))

        userips = UserIpAddress.objects.all()
        str_none_found = 'No IP addresses found'
        if u is not None:
            userips= userips.filter(user=u)
            str_none_found = str_none_found + ' belonging to user {0}'.format(user)
        if len(userips) == 0:
            self.stdout.write(str_none_found)
        else:
            for userip in userips:
                self.stdout.write('{0} {1}'.format(userip.user, userip.ip))

