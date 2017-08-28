import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from esmond.api.models import Device, OIDSet, DeviceOIDSetMap

class Command(BaseCommand):
    help = 'Add a device'

    def add_arguments(self, parser):
        parser.add_argument('name')
        parser.add_argument('community')
        parser.add_argument('oidset', nargs='*')

    def handle(self, *args, **options):
        name = options['name']
        community = options['community']

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

        oidsets = []
        for oidset_name in options['oidset']:
            try:
                oidset = OIDSet.objects.get(name=oidset_name)
                oidsets.append(oidset)
            except OIDSet.DoesNotExist:
                print >>sys.stderr, "No such oidset: %s" % (oidset_name)
                print >>sys.stderr, "Aborting. No OIDSets were added."
                return

        for oidset in oidsets:
            print device, oidset
            DeviceOIDSetMap(device=device, oid_set=oidset).save()
