import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from esxsnmp.api.models import Device

class Command(BaseCommand):
    args = 'name community'
    help = 'Add a device'

    def handle(self, *args, **options):
        self.options = options

        if len(args) != 2:
            print >>sys.stderr, "takes exactly 2 arguments: %s" % self.args
            return

        name, community = args

        try:
            device = Device.objects.get(name=name)
            print "%s already exists" % (name)
            return
        except Device.DoesNotExist:
            pass

        device = Device(name=name, community=community,
                begin_time=datetime.datetime.now(),
                end_time=datetime.datetime.max,
                active=True)

        device.save()

