#!/usr/bin/env python

"""
Utility to clean out old perfsonar data from cassandra and relational database

This script accepts the following arguments:

-c <conf-file>: Optional parameter to set location of the config file. Defaults
to DEFAULT_CONFIG_FILE variable value.

-s DATESTRING: Date string with time in past to start looking for expired data. Default
is current time. e.g. "2017-01-01 00:00:00"

-t SECONDS: Number of seconds of data to query at a time. Querying the full range causes 
timeouts. Default is 86400 (1 day).

-m NUMBER: Number of queries that don't return data before giving up on looking for more.
If -t is 1 day and this value is 50, that means it will need to say 50 days without data 
before determining there is nothing left to delete. Default is 50.

The config file is in JSON format and defines data retention policies for the
various types ofdata that the perfSONAR API supports. It allows you to match on
three values currently: event_type, summary_type, and summary_window. You can
pass a value of '*' to these fields to match any value for that field. You also
set an 'expire' value (in days). A value of "never" means to always keep data.
A value of "0" means to delete all data found.

The script will choose the policy with the most specific match with a preference
order of event_type, summary_type and then summary_window. See the ps_remove_data.conf
file in the same directory as this script for an example. A few example polcies:

A policy that expires base throughput data after 6 months:
{
"event_type":      "throughput",
"summary_type":    "base",
"summary_window":  "0",
"expire":          "365"
}

A policy that never expires base throughput data:
{
"event_type":      "throughput",
"summary_type":    "base",
"summary_window":  "0",
"expire":          "never"
}


A policy that always expires base throughput data:
{
"event_type":      "throughput",
"summary_type":    "base",
"summary_window":  "0",
"expire":          "0"
}


A catch-all policy that expires anything that doesn't match another policy
after 1 year (365 days):
{
"event_type":      "*",
"summary_type":    "*",
"summary_window":  "*",
"expire":          "365"
}

A policy that expires any summary with a window of 1 day after 5 years (1825 days)
{
"event_type":      "*",
"summary_type":    "*",
"summary_window":  "86400",
"expire":          "1825"
}

NOTE: Cassandra does not delete data off disk right away. If you are not running a multi-node
cassandra cluster, you can run the following to make it delete stuff faster:

cqlsh -k esmond -e "ALTER TABLE rate_aggregations WITH GC_GRACE_SECONDS = 0"
cqlsh -k esmond -e "ALTER TABLE base_rates WITH GC_GRACE_SECONDS = 0"
cqlsh -k esmond -e "ALTER TABLE raw_data WITH GC_GRACE_SECONDS = 0"

"""

#init django -must happen before other imports
import django
django.setup()

#imports
import argparse
import calendar
import json
import sys
from datetime import datetime, timedelta
import dateutil.parser
from esmond.api.models import PSMetadata, PSPointToPointSubject, PSEventTypes, PSMetadataParameters
from esmond.api.perfsonar.api_v2 import EVENT_TYPE_CF_MAP
from esmond.api.perfsonar.types import *
from esmond.cassandra import CASSANDRA_DB, get_rowkey
from esmond.config import get_config,get_config_path

#globals
DEFAULT_CONFIG_FILE = ['ps_remove_data.conf']
POLICY_MATCH_FIELD_DEFS = [
    {'name': 'event_type', 'type': str, 'special_vals': ['*'], 'valid_vals': [k for k in EVENT_TYPE_CONFIG]},
    {'name': 'summary_type', 'type': str, 'special_vals': ['*'], 'valid_vals': [k for k in INVERSE_SUMMARY_TYPES]},
    {'name': 'summary_window', 'type': int, 'special_vals': ['*'], 'valid_vals': None},
]
POLICY_ACTION_DEFS = [
    {'name': 'expire', 'type': int, 'special_vals': ['never']},
]
#Event types known to be large that need to be chunked when querying
BIG_DATASETS = [
    "histogram-owdelay", 
    "histogram-ttl", 
    "packet-count-lost", 
    "packet-count-sent", 
    "packet-loss-rate", 
    "packet-duplicates",
    "time-error-estimates"
    ]
#The size of the time chunks (in seconds) to grab for big datasets - needs to be < 10000 or cassandra complains
DEFAULT_MAX_TIME_CHUNK = 3600*24
#The number of empty chunks before assuming a dataset has no data - works out to about a year
DEFAULT_MAX_MISSES = 50

def datetime_to_ts(dt):
    """Convert internal DB timestamp to unixtime."""
    if dt:
        return calendar.timegm(dt.utctimetuple())

def row_prefix(event_type):
    return ['ps', event_type.replace('-', '_') ]
        
def query_data( db, metadata_key, event_type, summary_type, freq, begin_time, end_time):
    """Grabs cassandra data"""
    results = []
    datapath = row_prefix(event_type)
    datapath.append(metadata_key)
    if(summary_type != 'base'):
        datapath.append(summary_type)

    query_type = EVENT_TYPE_CONFIG[event_type]["type"]
    if query_type not in EVENT_TYPE_CF_MAP:
        raise RuntimeError("Misconfigured event type on server side. Invalid 'type' %s" % query_type)
    col_fam = TYPE_VALIDATOR_MAP[query_type].summary_cf(db, summary_type)
    if col_fam is None:
        col_fam = EVENT_TYPE_CF_MAP[query_type]
    
    cf = None
    if col_fam == db.agg_cf:
        cf = db.aggs
        results = db.query_aggregation_timerange(path=datapath, freq=freq,
               cf='average', ts_min=begin_time*1000, ts_max=end_time*1000)
    elif col_fam == db.rate_cf:
        cf = db.rates
        results = db.query_baserate_timerange(path=datapath, freq=freq,
                cf='delta', ts_min=begin_time*1000, ts_max=end_time*1000)
    elif col_fam == db.raw_cf:
        cf = db.raw_data
        results = db.query_raw_data(path=datapath, freq=freq,
               ts_min=begin_time*1000, ts_max=end_time*1000)
    else:
        raise RuntimeError("Requested data does not map to a known column-family")

    return (results, cf, datapath)

def get_policy(et, policy, match_fields, i):
    """Recursively determines matching policy"""
    if(i == len(match_fields)):
        return policy
        
    curr_policy = None
    et_attr = str(getattr(et, match_fields[i]))
    if et_attr in policy:
        curr_policy = get_policy(et, policy[et_attr], match_fields, i+1)   
        
    if curr_policy is None and '*' in policy:
        curr_policy = get_policy(et, policy['*'], match_fields, i+1)
    
    return curr_policy

def build_policy_action(policy, val):
    """Verifies and formats policy action"""
    for action in POLICY_ACTION_DEFS:
        if action['name'] not in policy:
            raise RuntimeError("Invalid policy in policies list. Missing required field %s." % (action['name']))
        #check type
        action_val = policy[action['name']]
        if action_val not in action['special_vals']:
            action['type'](policy[action['name']])
        val[action['name']] = policy[action['name']]
             
def main():
    #Parse command-line opts
    parser = argparse.ArgumentParser(description="Remove old data and metadata based on a configuration file")
    parser.add_argument('-c', '--config', metavar='CONFIG', nargs=1,
            dest='config',  default=DEFAULT_CONFIG_FILE,
            help='Configuration file location(default=%default).')
    parser.add_argument('-s', '--start', metavar='START', nargs=1,
            dest='start', default=None,
            help='Start looking for expired record at given time as unix timestamp. Default is current time.')
    parser.add_argument('-t', '--time-chunk', metavar='TIME_CHUNK', nargs=1,
            dest='time_chunk', default=[DEFAULT_MAX_TIME_CHUNK], type=int,
            help='The amount of data to look at each query in seconds. Defaults to {0}'.format(DEFAULT_MAX_TIME_CHUNK))
    parser.add_argument('-m', '--max-misses', metavar='MAX_MISSES', nargs=1,
            dest='max_misses', default=[DEFAULT_MAX_MISSES], type=int,
            help='The maximum number of time chunks with no data before giving up. Defaults to {0}'.format(DEFAULT_MAX_MISSES))
    args = parser.parse_args()
    
    #parse args
    expire_start = None
    if args.start:
        expire_start = dateutil.parser.parse(args.start[0])
     
    #init django
    django.setup()
    
    #Connect to DB
    db = CASSANDRA_DB(get_config(get_config_path()), timeout=60)
    
    #read config file
    policies = {}
    json_file_data = open(args.config[0])
    config = json.load(json_file_data)
    if 'policies' not in config:
        raise RuntimeError("Invalid JSON config. Missing required top-level 'policies' object")
    for p in config['policies']:
        i = 0
        policies_builder = policies
        for req in POLICY_MATCH_FIELD_DEFS:
            i += 1
            if req['name'] not in p:
                raise RuntimeError("Invalid policy in polcies list at position %d. Missing required field %s." % (i,req['name']))
            val = p[req['name']]
            if val not in req['special_vals']:
                req['type'](val)
                if (req['valid_vals'] is not None) and (val not in req['valid_vals']):
                    raise RuntimeError("Invalid policy in polcies list at position %d. Invalid value %s for %s. Allowed values are %s." % (i,val, req['name'], req['valid_vals']))
            if val not in policies_builder: policies_builder[val] = {}
            policies_builder = policies_builder[val]
        build_policy_action(p, policies_builder)
        
    #Clean out data from cassandra
    metadata_counts = {}
    for et in PSEventTypes.objects.all():        
        #determine policy 
        policy = get_policy(et, policies, [v['name'] for v in POLICY_MATCH_FIELD_DEFS], 0)
        if policy is None:
            print "Unable to find matching policy for %s:%s\n" % (et.metadata, et)
            continue
        
        #determine expire time
        if str(policy['expire']).lower() == 'never':
            continue
        expire_time = datetime_to_ts(datetime.utcnow() - timedelta(days=int(policy['expire'])))
        
        #handle command-line option
        if expire_start is not None:
            expire_start_ts = datetime_to_ts(expire_start)
            if expire_start_ts <= expire_time:
                expire_time =expire_start_ts
            else:
                #non-binding expire so skip
                continue
            
            
        #check metadata
        md_key = et.metadata.metadata_key
        if md_key not in metadata_counts:
            metadata_counts[md_key] = {"expired": 0, "total":0, "obj": et.metadata}
        metadata_counts[md_key]['total'] += 1
        if et.time_updated is None:
            metadata_counts[md_key]['expired'] += 1
        elif datetime_to_ts(et.time_updated) <= expire_time:
            metadata_counts[md_key]['expired'] += 1
            expire_time = datetime_to_ts(et.time_updated)
         
        #Some datasets timeout if dataset is too large. in this case grab chunks
        begin_time = expire_time - args.time_chunk[0]
        end_time = expire_time
        
        misses = 0
        while misses < args.max_misses[0]:
            if begin_time == 0:
                #only run one time after seeing begin_time of 0
                misses = args.max_misses[0]
            elif begin_time < 0:
                #make sure begin_time is not below 0
                begin_time = 0
                misses = args.max_misses[0]
            
            #query data to delete
            try:
                (expired_data, cf, datapath) = query_data(db, et.metadata.metadata_key, et.event_type, et.summary_type, et.summary_window, begin_time, end_time)
            except Exception as e:
                print "Query error for metadata_key=%s, event_type=%s, summary_type=%s, summary_window=%s, begin_time=%s, end_time=%s, error=%s" % (md_key, et.event_type, et.summary_type, et.summary_window, begin_time, end_time, e)
                break
            
            #adjust begin_time
            end_time = begin_time
            begin_time = begin_time - args.time_chunk[0]
            
            #check if we got any data
            if len(expired_data) == 0:
                misses += 1
                continue
            
            #delete data    
            for expired_col in expired_data:
                year = datetime.utcfromtimestamp(float(expired_col['ts'])/1000.0).year 
                row_key = get_rowkey(datapath, et.summary_window, year)   
                try:
                    cf.remove(row_key, [expired_col['ts']])
                except Exception as e:
                    sys.stderr.write("Error deleting {0}: {1}\n".format(row_key, e))
                    
            print "Sending request to delete %d rows for metadata_key=%s, event_type=%s, summary_type=%s, summary_window=%s" % (len(expired_data), md_key, et.event_type, et.summary_type, et.summary_window)
            try:
                cf.send()
            except Exception as e:
                sys.stderr.write("Error sending delete: {0}".format(e))
            print "Deleted %d rows for metadata_key=%s, event_type=%s, summary_type=%s, summary_window=%s" % (len(expired_data), md_key, et.event_type, et.summary_type, et.summary_window)
        
    #Clean out metadata from relational database
    for md_key in metadata_counts:
        if  metadata_counts[md_key]['total'] == metadata_counts[md_key]['expired']:
            metadata_counts[md_key]['obj'].delete()
            print "Deleted metadata %s" % md_key
            
if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        sys.stderr.write("Error: %s\n" % e)
        sys.exit(1)
    
