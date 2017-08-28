import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from esmond.api.models import Device, OIDSet, DeviceOIDSetMap

class Command(BaseCommand):
    help = 'Add an OIDSet to a Device'

    def add_arguments(self, parser):
        parser.add_argument('device_name')
        parser.add_argument('oidset_name', nargs='+')

    def handle(self, *args, **options):
        device_name = options['device_name']

        try:
            device = Device.objects.get(name=device_name)
        except Device.DoesNotExist:
            print >>sys.stderr, "No such device: %s" % (device_name)
            return

        oidsets = []
        for oidset_name in options['oidset_name']:
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
