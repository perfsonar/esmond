import sys
import datetime

from django.core.management.base import BaseCommand

from esmond.cassandra import CASSANDRA_DB
from esmond.config import get_config, get_config_path

class Command(BaseCommand):
    args = ''
    help = 'Drop esmond keyspace in cassandra and re-initialize. Will blow away all existing data.'

    def handle(self, *args, **options):
        print 'Initializing cassandra esmond keyspace'
        config = get_config(get_config_path())
        config.db_clear_on_testing = True
        db = CASSANDRA_DB(config)
        
