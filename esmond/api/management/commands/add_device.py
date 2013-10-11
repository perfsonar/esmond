import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from esmond.api.models import Device, OIDSet, DeviceOIDSetMap

class Command(BaseCommand):
    args = 'name community [oidset ...]'
    help = 'Add a device'

    def handle(self, *args, **options):
        self.options = options

        if len(args) < 2:
            print >>sys.stderr, "takes at least 2 arguments: %s" % self.args
            return

        name, community = args[:2]

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
        for oidset_name in args[2:]:
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
