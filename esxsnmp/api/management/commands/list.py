import sys
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from esxsnmp.api.models import Device

class Command(BaseCommand):
    args = ''
    help = 'List Devices and associated OIDSets'

    def handle(self, *args, **options):
        for device in Device.objects.active():
            oidsets = [o.name for o in device.oidsets.all()]
            print device.name + ": " + " ".join(oidsets)
