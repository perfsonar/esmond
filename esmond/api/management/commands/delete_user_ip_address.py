from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from esmond.api.models import UserIpAddress

class Command(BaseCommand):
    help = 'Delete IP subnet(s) associated with a user account'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('ip', nargs='+')

    def handle(self, *args, **options):
        user = options['username']

        u = None

        try:
            u = User.objects.get(username=user)
        except User.DoesNotExist:
            raise CommandError('User {0} does not exist'.format(user))
        
        error = False
        for ip_addr in options['ip']:
            try:
                userip = UserIpAddress.objects.get(ip=ip_addr, user=u).delete()
                self.stdout.write('Deleted IP {0} for user {1}'.format(ip_addr, user))
            except UserIpAddress.DoesNotExist:
                error = True
                self.stderr.write('Unable to find {0} belonging to {1}'.format(ip_addr, user))
                
        if error:
            raise CommandError('Some or all deletions failed. See output above for details.')
        else:
            self.stdout.write(self.style.SUCCESS('Successfully deleted user IP(s)'))
