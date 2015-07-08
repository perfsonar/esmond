import os

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from esmond.api.tests.example_data import build_default_metadata

class Command(BaseCommand):
    help = 'Loads the test/sample metadata from esmond.api.test.example_data. Make sure to "python manage.py loaddata oidsets.json" first.'

    def handle(self, *args, **options):
        build_default_metadata()
        pass