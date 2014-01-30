#!/usr/bin/env python

import argparse
from pycassa.pool import ConnectionPool
from pycassa.columnfamily import ColumnFamily
from pycassa.system_manager import *
from pycassa.cassandra.ttypes import NotFoundException
import json
import timeit
import time
import uuid
import datetime
import random

class CassandraTester:
    #database settings
    dbaddress = 'localhost:9160'  
    cf_counter = 'base_rates'
    cf_json = 'raw_data'
    
    def __init__(self, keyspace_name, savedb=True):
        #initialize db
        self.keyspace_name = keyspace_name
        self.create_column_families(savedb)
        
        #create connection pool
        self.pool = ConnectionPool(self.keyspace_name, [self.dbaddress])

    def create_column_families(self, savedb=False):
        #create system manager for checking schema
        try:
            sysman = SystemManager(self.dbaddress)                              
        except TTransportException, e:
            raise ConnectionException("System Manager can't connect to Cassandra "
                "at %s - %s" % (self.dbaddress, e))
        
        #clear database if desired
        if not savedb:
            if self.keyspace_name in sysman.list_keyspaces():
                sysman.drop_keyspace(self.keyspace_name)
                
        #check if keyspace exists
        if not self.keyspace_name in sysman.list_keyspaces():
            sysman.create_keyspace(self.keyspace_name, SIMPLE_STRATEGY, 
                {'replication_factor': '1'})
        
        #check for column families
        if not sysman.get_keyspace_column_families(self.keyspace_name).has_key(self.cf_counter):
            sysman.create_column_family(self.keyspace_name, self.cf_counter, super=True, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=COUNTER_COLUMN_TYPE,
                    key_validation_class=UTF8_TYPE)
        
        
        if not sysman.get_keyspace_column_families(self.keyspace_name).has_key(self.cf_json):
            sysman.create_column_family(self.keyspace_name, self.cf_json, super=False, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=UTF8_TYPE,
                    key_validation_class=UTF8_TYPE)
    
    def generate_int_data(self, key_prefix, metatdata_key, num_rows, start_ts, end_ts, summary_type, time_int, min_val, max_val):    
        cf = ColumnFamily(self.pool, self.cf_counter)
        row_keys = []
        for n in range(num_rows):
            if metatdata_key is None:
                metatdata_key, = uuid.uuid4().hex
            key = "%s:%s" % (key_prefix, metatdata_key)
            if summary_type and summary_type != 'base':
                key += ":%s:%d" % (summary_type, time_int)
            row_keys.append(key.lower())
            for ts in range(start_ts, end_ts, time_int):
                millis = ts * 1000
                cf.insert(self.gen_key(key, ts), {millis : {'val': random.randint(min_val, max_val), 'is_valid': 1}})
        return row_keys
    
    def generate_histogram_data(self, key_prefix, metatdata_key, num_rows, start_ts, end_ts, summary_type, summ_window, sample_size, bucket_min, bucket_max):    
        cf = ColumnFamily(self.pool, self.cf_json)
        row_keys = []
        for n in range(num_rows):
            if metatdata_key is None:
                metatdata_key, = uuid.uuid4().hex
            key = "%s:%s" % (key_prefix, metatdata_key)
            if summary_type and summary_type != 'base':
                key += ":%s:%d" % (summary_type, summ_window)
            row_keys.append(key.lower())
            for ts in range(start_ts, end_ts, summ_window):
                histogram = {}
                sample = sample_size
                while(sample > 0):
                    bucket = random.randint(bucket_min, bucket_max)
                    val = random.randint(1,sample)
                    if not histogram.has_key(str(bucket)):
                        histogram[str(bucket)] = val
                    else:
                        histogram[str(bucket)] += val
                    sample -= val
                millis = ts * 1000
                cf.insert(self.gen_key(key, ts), {millis : json.dumps(histogram)})
        return row_keys
    
    def get_data(self, cf_name, key, start_time, end_time, output_json=False):
        cf = ColumnFamily(self.pool, cf_name)
        try:
            result = cf.multiget(self.gen_key_range(key, start_time, end_time), column_start=start_time*1000, column_finish=end_time*1000, column_count=10000000)
            if output_json:
                self.dump_json(result)
        except NotFoundException:
            pass
    
    def dump_json(self, db_result):
        time_series = []
        for row in db_result.keys():
            for ts in db_result[row].keys():
                time_series.append({'time': ts, 'value': db_result[row][ts]})
        print json.dumps(time_series)
    
    def gen_key(self, key, ts):
        year = datetime.datetime.utcfromtimestamp(ts).year
        key = "%s:%d" % (key,year)
        return key.lower();
    
    def gen_key_range(self, key, start_time, end_time):
        key_range = []
        start_year = datetime.datetime.utcfromtimestamp(start_time).year
        end_year = datetime.datetime.utcfromtimestamp(end_time).year
        year_range = range(start_year, end_year+1)
        for year in year_range:
            key_range.append("%s:%d" % (key,year))
        return key_range


#create option parser
parser = argparse.ArgumentParser(description="Generate test data and time queries in cassandra")
parser.add_argument("-d", "--datatype", dest="data_type", help="the type of data to generate", choices=['base_rate', 'rate_agg', 'traceroute', 'histogram' ], default='base_rate')
parser.add_argument("-k", "--keyspace", dest="ks_name", help="the keyspace to use for testing", default='ma_test')
parser.add_argument("-s", "--sample-size", dest="sample_size", type=int, help="for histogram data, the size of each histogram sample", default=600)
parser.add_argument("-t", "--time-range", dest="time_range", type=int, help="the time range for which to generate data (in seconds)", default=(86400*365))
parser.add_argument("-T", "--summary-type", dest="summ_type", help="the type of sumnmarization", choices=['base', 'aggregation', 'composite', 'statistics', 'subinterval' ], default='base')
parser.add_argument("-w", "--summary-window", dest="summ_window", type=int, help="the frequency with which to gernerate columns (in seconds)", default=0)
parser.add_argument("-m", "--metadata-key", dest="metadata_key", help="the metadata key to use when generating data. --num-rows must be 1 when using this option.", default=None)
parser.add_argument("--minval", dest="min_val", type=int, help="the minimum value to be stored. This is the bucket value for histograms and the stored value for the other column-families.", default=1)
parser.add_argument("--maxval", dest="max_val", type=int, help="the maximum value to be stored. This is the bucket value for histograms and the stored value for the other column-families", default=1000)
parser.add_argument("--keep-data", dest="keep_data", action="store_true", help="if present data will not be deleted before running test")
parser.add_argument("--key-prefix", dest="key_prefix", help="the prefix to append to the key", default="ps:test")
parser.add_argument("--num-rows", dest="num_rows", type=int, help="the number of rows to generate and then query", default=1)
args = parser.parse_args()

#create tester
tester = CassandraTester(args.ks_name, args.keep_data)

#set column-family to test
data_type = args.data_type

#check if metadata key specified
if((args.metadata_key is not None) and args.num_rows > 1):
    raise Exception("--num-rows must be 1 when providing metadata key")
    
#generate data
end_time= int(time.time())
gen_interval = args.time_range
print "Generating %d seconds of data..." % gen_interval
gen_timer = time.time()
row_keys = []
if data_type == 'base_rate':
    row_keys = tester.generate_int_data(args.key_prefix, args.metadata_key, args.num_rows, (end_time - gen_interval), end_time, args.summ_type, args.summ_window, args.min_val, args.max_val)
elif data_type == 'histogram':
    row_keys = tester.generate_histogram_data(args.key_prefix, args.metadata_key, args.num_rows, (end_time - gen_interval), end_time, args.summ_type, args.summ_window, args.sample_size, args.min_val, args.max_val)
else:
    raise Exception("Invalid data type: %s" % data_type)
print "Data generated in %f seconds." % (time.time() - gen_timer)
print ""
