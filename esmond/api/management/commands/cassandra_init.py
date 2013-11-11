import sys
import datetime

from django.core.management.base import BaseCommand

from esmond.cassandra import CASSANDRA_DB
from esmond.config import get_config, get_config_path

class Command(BaseCommand):
    args = ''
    help = 'Initialize cassandra esmond keyspace/column families.'

    def handle(self, *args, **options):
        print 'Initializing cassandra esmond keyspace'
        config = get_config(get_config_path())
        db = CASSANDRA_DB(config)
        
