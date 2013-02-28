#!/usr/bin/env python
# encoding: utf-8
"""
Cassandra DB interface calls and data encapsulation objects.

Esxsnmp schema in json-like notation:

// regular col family
"raw_data" : {
    "router_a:xe-0_2_0:ifHCInOctets:30:2012" : {
        "1343955624" : "16150333739148" // both long values.
    }
}

// supercolumn
"base_rates" : {
    "router_a:xe-0_2_0:ifHCInOctets:30:2012" : {
        "1343955600" : {     // long column name.
            "val": "123",    // string key, counter type value.
            "is_valid" : "2" // zero or positive non-zero.
        }
    }
}

// supercolumn
"rate_aggregations" : {
    "router_a:ge-9_0_5.0:ifHCInOctets:3600:2012" : {
        "1343955600" : {   // long column name.
            "val": "1234", // string key, counter type.
            "30": "38"     // key of the 'non-val' column is freq of the base rate.
        }                  // the value of said is the count used in the average.
    }
}

// supercolumn
"stat_aggregations" : {
    "router_a:ge-9_0_0.44:ifHCInOctets:86400:2012" : {
        "1343955600" : { // long column name.
            "min": "0",  // string keys, long types.
            "max": "484140" 
        }
    }
}
"""
# Standard
import calendar
import datetime
import json
import logging
import os
import pprint
import sys
import time
from collections import OrderedDict

from esxsnmp.util import get_logger

# Third party
from pycassa import PycassaLogger
from pycassa.pool import ConnectionPool, AllServersUnavailable
from pycassa.columnfamily import ColumnFamily, NotFoundException
from pycassa.system_manager import *

from thrift.transport.TTransport import TTransportException

SEEK_BACK_THRESHOLD = 2592000 # 30 days

class CassandraException(Exception):
    """Common base"""
    pass

class ConnectionException(CassandraException):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)
        
class CASSANDRA_DB(object):
    
    keyspace = 'esxsnmp'
    raw_cf = 'raw_data'
    rate_cf = 'base_rates'
    agg_cf = 'rate_aggregations'
    stat_cf = 'stat_aggregations'
    
    _queue_size = 200
    
    def __init__(self, config, qname=None, clear_on_test=False):
        """
        Class contains all the relevent cassandra logic.  This includes:
        
        * schema creation,
        * connection information/pooling, 
        * generating the metadata cache of last val/ts information,
        * store data/update the rate/aggregaion bins,
        * and execute queries to return data to the REST interface.
        """
        
        # Configure logging - if a qname has been passed in, hook
        # into the persister logger, if not, toss together some fast
        # console output for devel/testing.
        if qname:
            self.log = get_logger("espersistd.%s.cass_db" % qname)
        else:
            self.log = logging.getLogger('cassandra_db')
            self.log.setLevel(logging.DEBUG)
            format = logging.Formatter('%(name)s [%(levelname)s] %(message)s')
            handle = logging.StreamHandler()
            handle.setFormatter(format)
            self.log.addHandler(handle)
        
        # Add pycassa driver logging to existing logger.
        plog = PycassaLogger()
        plog.set_logger_name('%s.pycassa' % self.log.name)
        # Debug level is far too noisy, so just hardcode the pycassa 
        # logger to info level.
        plog.set_logger_level('info')

        # Connect to cassandra with SystemManager, do a schema check 
        # and set up schema components if need be.
        try:
            sysman = SystemManager(config.cassandra_servers[0])                              
        except TTransportException, e:
            raise ConnectionException("System Manager can't connect to Cassandra "
                "at %s - %s" % (config.cassandra_servers[0], e))
        
        # Blow everything away if we're testing - be aware of this and use
        # with care.
        if clear_on_test and os.environ.get("ESXSNMP_TESTING", False):
            self.log.info('Dropping keyspace %s' % self.keyspace)
            if self.keyspace in sysman.list_keyspaces():
                sysman.drop_keyspace(self.keyspace)
                time.sleep(3)
        # Create keyspace
        
        _schema_modified = False # Track if schema components are created.
        
        if not self.keyspace in sysman.list_keyspaces():
            _schema_modified = True
            self.log.info('Creating keyspace %s' % self.keyspace)
            sysman.create_keyspace(self.keyspace, SIMPLE_STRATEGY, 
                {'replication_factor': '1'})
            time.sleep(3)
        # Create column families if they don't already exist.
        # If a new column family is added, make sure to set 
        # _schema_modified = True so it will be propigated.
        self.log.info('Checking/creating column families')
        # Raw Data CF
        if not sysman.get_keyspace_column_families(self.keyspace).has_key(self.raw_cf):
            _schema_modified = True
            sysman.create_column_family(self.keyspace, self.raw_cf, super=False, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=LONG_TYPE,
                    key_validation_class=UTF8_TYPE)
            self.log.info('Created CF: %s' % self.raw_cf)
        # Base Rate CF
        if not sysman.get_keyspace_column_families(self.keyspace).has_key(self.rate_cf):
            _schema_modified = True
            sysman.create_column_family(self.keyspace, self.rate_cf, super=True, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=COUNTER_COLUMN_TYPE,
                    key_validation_class=UTF8_TYPE)
            self.log.info('Created CF: %s' % self.rate_cf)
        # Rate aggregation CF
        if not sysman.get_keyspace_column_families(self.keyspace).has_key(self.agg_cf):
            _schema_modified = True
            sysman.create_column_family(self.keyspace, self.agg_cf, super=True, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=COUNTER_COLUMN_TYPE,
                    key_validation_class=UTF8_TYPE)
            self.log.info('Created CF: %s' % self.agg_cf)
        # Stat aggregation CF
        if not sysman.get_keyspace_column_families(self.keyspace).has_key(self.stat_cf):
            _schema_modified = True
            sysman.create_column_family(self.keyspace, self.stat_cf, super=True, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=LONG_TYPE,
                    key_validation_class=UTF8_TYPE)
            self.log.info('Created CF: %s' % self.stat_cf)
                    
        sysman.close()
        
        self.log.info('Schema check done')
        
        # If we just cleared the keyspace/data and there is more than
        # one server, pause to let schema propigate to the cluster machines.
        if _schema_modified == True:
            self.log.info("Waiting for schema to propagate...")
            time.sleep(10)
            self.log.info("Done")
                
        # Now, set up the ConnectionPool
        
        # Read auth information from config file and set up if need be.
        _creds = {}
        if config.cassandra_user and config.cassandra_pass:
            _creds['username'] = config.cassandra_user
            _creds['password'] = config.cassandra_pass
            self.log.debug('Connecting with username: %s' % (config.cassandra_user,))
        
        try:
            self.log.debug('Opening ConnectionPool')
            self.pool = ConnectionPool(self.keyspace, 
                server_list=config.cassandra_servers, 
                pool_size=10,
                max_overflow=5,
                max_retries=10,
                timeout=30,
                credentials=_creds)
        except AllServersUnavailable, e:
            raise ConnectionException("Couldn't connect to any Cassandra "
                    "at %s - %s" % (config.cassandra_servers, e))
                    
        self.log.info('Connected to %s' % config.cassandra_servers)
        
        # Define column family connections for the code to use.
        self.raw_data = ColumnFamily(self.pool, self.raw_cf).batch(self._queue_size)
        self.rates    = ColumnFamily(self.pool, self.rate_cf).batch(self._queue_size)
        self.aggs     = ColumnFamily(self.pool, self.agg_cf).batch(self._queue_size)
        self.stat_agg = ColumnFamily(self.pool, self.stat_cf).batch(self._queue_size)
        
        # Timing - this turns the database call profiling code on and off.
        # This is not really meant to be used in production and generally 
        # just spits out statistics at the end of a run of test data.  Mostly
        # useful for timing specific database calls to aid in development.
        self.profiling = False
        if config.db_profile_on_testing and os.environ.get("ESXSNMP_TESTING", False):
            self.profiling = True
        self.stats = DatabaseMetrics(profiling=self.profiling)
        
        # Class members
        # Set up expiration args for raw data if set in the config file.
        self.raw_opts = {}
        self.raw_expire = config.cassandra_raw_expire
        if self.raw_expire:
            self.raw_opts['ttl'] = int(self.raw_expire)
        # Just the dict for the metadata cache.
        self.metadata_cache = {}
        
    def flush(self):
        """
        Calling this will explicity flush all the batches to the 
        server.  Generally only used in testing/dev scripts and not
        in production when the batches will be self-flushing.
        """
        self.log.debug('Flush called')
        self.raw_data.send()
        self.rates.send()
        self.aggs.send()
        self.stat_agg.send()
        
    def close(self):
        """
        Explicitly close the connection pool.
        """
        self.log.debug('Close/dispose called')
        self.pool.dispose()
        
    def set_raw_data(self, raw_data):
        """
        Called by the persister.  Writes the raw incoming data to the appropriate
        column family.  The optional TTL option is passed in self.raw_opts and 
        is set up in the constructor.
        
        The raw_data arg passes in is an instance of the RawData class defined
        in this module.
        """
        t = time.time()
        # Standard column family update.
        self.raw_data.insert(raw_data.get_key(), 
            {raw_data.ts_to_unixtime(): raw_data.val}, **self.raw_opts)
        
        if self.profiling: self.stats.raw_insert(time.time() - t)
        
    def set_metadata(self, meta_d):
        """
        Just does a simple write to the dict being used as metadata.
        """
        self.metadata_cache[meta_d.get_meta_key()] = meta_d.get_document()
        
    def get_metadata(self, raw_data):
        """
        Called by the persister to get the metadata - last value and timestamp -
        for a given measurement.  If a given value is not found (as in when the 
        program is initially started for example) it will look in the raw data
        as far back as SEEK_BACK_THRESHOLD to find the previous value.  If found,
        This is seeded to the cache and returned.  If not, this is presumed to be
        new, and the cache is seeded with the value that is passed in.
        
        The raw_data arg passes in is an instance of the RawData class defined
        in this module.
        
        The return value is a Metadata object, also defined in this module.
        """
        t = time.time()

        meta_d = None
        
        if not self.metadata_cache.has_key(raw_data.get_meta_key()):
            # Didn't find a value in the metadata cache.  First look
            # back through the raw data for SEEK_BACK_THRESHOLD seconds
            # to see if we can find the last processed value.
            ts_max = raw_data.ts_to_unixtime() - 1 # -1 to look at older vals
            ts_min = ts_max - SEEK_BACK_THRESHOLD
            ret = self.raw_data._column_family.multiget(
                    self._get_row_keys(raw_data.device,raw_data.path,raw_data.oid,
                            raw_data.freq,ts_min,ts_max),
                    # Note: ts_max and ts_min appear to be reversed here - 
                    # that's because this is a reversed range query.
                    column_start=ts_max, column_finish=ts_min,
                    column_count=1, column_reversed=True)
                    
            if self.profiling: self.stats.meta_fetch((time.time() - t))
                    
            if ret:
                # A previous value was found in the raw data, so we can
                # seed/return that.
                key = ret.keys()[0]
                ts = ret[key].keys()[0]
                val = ret[key][ts]
                meta_d = Metadata(last_update=ts, last_val=val, min_ts=ts, 
                    freq=raw_data.freq, **raw_data.get_path())
                self.log.debug('Metadata lookup from raw_data for: %s' %\
                        (meta_d.get_meta_key()))
            else:
                # No previous value was found (or at least not one in the defined
                # time range) so seed/return the current value.
                meta_d = Metadata(last_update=raw_data.ts, last_val=raw_data.val,
                    min_ts=raw_data.ts, freq=raw_data.freq, **raw_data.get_path())
                self.log.debug('Initializing metadata for: %s' %\
                        (meta_d.get_meta_key()))
            self.set_metadata(meta_d)
        else:
            meta_d = Metadata(**self.metadata_cache[raw_data.get_meta_key()])
        
        return meta_d
        
    def update_metadata(self, metadata):
        """
        Update the metadata cache with a recently updated value.  Called by the
        persister.
        
        The metadata arg is a Metadata object defined in this module.
        """
        t = time.time()
        for i in ['last_val', 'min_ts', 'last_update']:
            self.metadata_cache[metadata.get_meta_key()][i] = getattr(metadata, i)
        #self.stats.meta_update((time.time() - t))
    
    def update_rate_bin(self, ratebin):
        """
        Called by the persister.  This updates a base rate bin in the base 
        rate column family.  
        
        The ratebin arg is a BaseRateBin object defined in this module.
        """
        
        t = time.time()
        # A super column insert.  Both val and is_valid are counter types.
        self.rates.insert(ratebin.get_key(),
            {ratebin.ts_to_unixtime(): {'val': ratebin.val, 'is_valid': ratebin.is_valid}})
        
        if self.profiling: self.stats.baserate_update((time.time() - t))
        
    def update_rate_aggregation(self, raw_data, agg_ts, freq):
        """
        Called by the persister to update the rate aggregation rollups.
        
        The args are a RawData object, the "compressed" aggregation timestamp
        and the frequency of the rollups in seconds.
        """
        
        t = time.time()
        
        agg = AggregationBin(
            ts=agg_ts, freq=freq, val=raw_data.val, base_freq=raw_data.freq, count=1,
            min=raw_data.val, max=raw_data.val, **raw_data.get_path()
        )
        
        # Super column update.  The base rate frequency is stored as the column
        # name key that is not 'val' - this will be used by the query interface
        # to generate the averages.  Both values are counter types.
        self.aggs.insert(agg.get_key(), 
            {agg.ts_to_unixtime(): {'val': agg.val, str(agg.base_freq): 1}})
        
        if self.profiling: self.stats.aggregation_update((time.time() - t))
        
    def update_stat_aggregation(self, raw_data, agg_ts, freq):
        """
        Called by the persister to update the stat aggregations (ie: min/max).
        
        Unlike the other update code, this has to read from the appropriate bin 
        to see if the min or max needs to be updated.  The update is done if 
        need be, and the updated boolean is set to true and returned to the
        calling code to flush the batch if need be.  Done that way to flush 
        more than one batch update rather than doing it each time.
        
        The args are a RawData object, the "compressed" aggregation timestamp
        and the frequency of the rollups in seconds.
        """
        
        updated = False
        
        # Create the AggBin object.
        agg = AggregationBin(
            ts=agg_ts, freq=freq, val=raw_data.val, base_freq=raw_data.freq, count=1,
            min=raw_data.val, max=raw_data.val, **raw_data.get_path()
        )
        
        t = time.time()
        
        ret = None
        
        try:
            # Retrieve the appropriate stat aggregation.
            ret = self.stat_agg._column_family.get(agg.get_key(), 
                        super_column=agg.ts_to_unixtime())
        except NotFoundException:
            # Nothing will be found if the rollup bin does not yet exist.
            pass
        
        if self.profiling: self.stats.stat_fetch((time.time() - t))
        
        t = time.time()
        
        if not ret:
            # Bin does not exist, so initialize min and max with the same val.
            self.stat_agg.insert(agg.get_key(),
                {agg.ts_to_unixtime(): {'min': agg.val, 'max': agg.val}})
            updated = True
        elif agg.val > ret['max']:
            # Update max.
            self.stat_agg.insert(agg.get_key(),
                {agg.ts_to_unixtime(): {'max': agg.val}})
            updated = True
        elif agg.val < ret['min']:
            # Update min.
            self.stat_agg.insert(agg.get_key(),
                {agg.ts_to_unixtime(): {'min': agg.val}})
            updated = True
        else:
            pass
        
        if self.profiling: self.stats.stat_update((time.time() - t))
        
        return updated
        
    def _get_row_keys(self, device, path, oid, freq, ts_min, ts_max):
        """
        Utility function used by the query interface.
        
        Row keys are of the following form:
        
        router:interface:oid:frequency:year
        
        Given these values and the starting/stopping timestamp, return a
        list of row keys (ie: more than one if the query spans years) to
        be used as the first argument to a multiget cassandra query.
        """
        full_path = '%s:%s:%s:%s' % (device,path,oid,freq)
        
        year_start = datetime.datetime.utcfromtimestamp(ts_min).year
        year_finish = datetime.datetime.utcfromtimestamp(ts_max).year
        
        key_range = []
        
        if year_start != year_finish:
            for i in range(year_start, year_finish+1):
                key_range.append('%s:%s' % (full_path,i))
        else:
            key_range.append('%s:%s' % (full_path, year_start))
            
        return key_range
        
    def query_baserate_timerange(self, device=None, path=None, oid=None, 
                freq=None, ts_min=None, ts_max=None, cf='average', as_json=False):
        """
        Query interface method to retrieve the base rates (generally average 
        but could be delta as well).  Could return the values programmatically,
        but generally returns formatted json from the FormattedOutput module.
        """
        ret = self.rates._column_family.multiget(
                self._get_row_keys(device,path,oid,freq,ts_min,ts_max), 
                column_start=ts_min, column_finish=ts_max)
        
        if cf not in ['average', 'delta']:
            self.log.error('Not a valid option: %s - defaulting to average' % cf)
            cf = 'average'
        
        # Divisors to return either the average or a delta.        
        value_divisors = { 'average': int(freq), 'delta': 1}
        
        # Just return the results and format elsewhere.
        results = []
        
        for k,v in ret.items():
            for kk,vv in v.items():
                results.append({'ts': kk, 'val': float(vv['val']) / value_divisors[cf], 
                                        'is_valid': vv['is_valid']})
            
        if as_json: # format results for query interface
            return FormattedOutput.base_rate(ts_min, ts_max, results, freq,
                    cf.replace('average', 'avg'))
        else:
            return results
            
    def query_aggregation_timerange(self, device=None, path=None, oid=None, 
                ts_min=None, ts_max=None, freq=None, cf=None, as_json=False):
        """
        Query interface method to retrieve the aggregation rollups - could
        be average/min/max.  Different column families will be queried 
        depending on what value "cf" is set to.  Could return the values 
        programmatically, but generally returns formatted json from 
        the FormattedOutput module.
        """
                
        if cf not in ['average', 'min', 'max']:
            self.log.error('Not a valid option: %s - defaulting to average' % cf)
            cf = 'average'
        
        if cf == 'average':
            ret = self.aggs._column_family.multiget(
                    self._get_row_keys(device,path,oid,freq,ts_min,ts_max), 
                    column_start=ts_min, column_finish=ts_max)

            # Just return the results and format elsewhere.
            results = []
        
            for k,v in ret.items():
                for kk,vv in v.items():
                    ts = kk
                    val = None
                    base_freq = None
                    count = None
                    for kkk in vv.keys():
                        if kkk == 'val':
                            val = vv[kkk]
                        else:
                            base_freq = kkk
                            count = vv[kkk]
                results.append(
                    {'ts': ts, 'val': val, 'base_freq': int(base_freq), 'count': count}
                )
        elif cf == 'min' or cf == 'max':
            ret = self.stat_agg._column_family.multiget(
                    self._get_row_keys(device,path,oid,freq,ts_min,ts_max), 
                    column_start=ts_min, column_finish=ts_max)
            
            results = []
            
            for k,v in ret.items():
                for kk,vv in v.items():
                    ts = kk
                            
                if cf == 'min':
                    results.append({'ts': ts, 'min': vv['min']})
                else:
                    results.append({'ts': ts, 'max': vv['max']})
        
        if as_json: # format results for query interface
            return FormattedOutput.aggregate_rate(ts_min, ts_max, results, freq,
                    cf.replace('average', 'avg'))
        else:
            return results
            
    def query_raw_data(self, device=None, path=None, oid=None, freq=None,
                ts_min=None, ts_max=None, as_json=False):
        """
        Query interface to query the raw data.  Could return the values 
        programmatically, but generally returns formatted json from 
        the FormattedOutput module.
        """        
        ret = self.raw_data._column_family.multiget(
                self._get_row_keys(device,path,oid,freq,ts_min,ts_max), 
                column_start=ts_min, column_finish=ts_max)

        # Just return the results and format elsewhere.
        results = []

        for k,v in ret.items():
            for kk,vv in v.items():
                results.append({'ts': kk, 'val': vv})
        
        if as_json: # format results for query interface
            return FormattedOutput.raw_data(ts_min, ts_max, results, freq)
        else:
            return results
            
    def __del__(self):
        pass

class FormattedOutput(object):
    """
    Class of static methods to handle formatting lists of dicts returned
    by the query methods in the CASSANDRA_DB class to the JSON to be 
    returned to the REST interface.
    """
    
    @staticmethod
    def _from_datetime(d):
        """
        Utility method to convert a datetime object to a unix timestamp.
        """
        if type(d) != type(datetime.datetime.now()):
            return d
        else:
            return calendar.timegm(d.utctimetuple())
    
    @staticmethod
    def base_rate(ts_min, ts_max, results, freq, cf):
        """
        Generate and populate the JSON wrapper to return the 
        base rates to the query interface.
        """
        fmt = [
            ('agg', freq if freq else results[0]['freq']),
            ('end_time', ts_max),
            ('data', []),
            ('cf', cf),
            ('begin_time', ts_min)
        ]
        
        fmt = OrderedDict(fmt)
        
        for r in results:
            fmt['data'].append(
                [
                    FormattedOutput._from_datetime(r['ts']),
                    # Set to non if is_valid is 0.
                    None if r['is_valid'] == 0 else float(r['val'])
                ]
            )
        
        return json.dumps(fmt)
        
    @staticmethod
    def aggregate_rate(ts_min, ts_max, results, freq, cf):
        """
        Generate and populate the JSON wrapper to return the 
        rollups to the query interface.
        """
        fmt = [
            ('agg', freq),
            ('end_time', ts_max),
            ('data', []),
            ('cf', cf),
            ('begin_time', ts_min)
        ]
    
        fmt = OrderedDict(fmt)
        
        for r in results:
            ro = AggregationBin(**r)
            fmt['data'].append(
                [
                    ro.ts_to_unixtime(),
                    # Get the min/max/avg attr frmo Bin object as necessary.
                    getattr(ro, cf)
                ]
            )
            
        return json.dumps(fmt)
        
    @staticmethod
    def raw_data(ts_min, ts_max, results, freq=None):
        """
        Generate and populate the JSON wrapper to return the 
        raw data to the query interface.
        """
        fmt = [
            ('agg', freq if freq else results[0]['freq']),
            ('end_time', ts_max),
            ('data', []),
            ('cf', 'raw'),
            ('begin_time', ts_min)
        ]
        
        fmt = OrderedDict(fmt)
        
        for r in results:
            fmt['data'].append(
                [
                    FormattedOutput._from_datetime(r['ts']), 
                    float(r['val'])
                ]
            )
        
        return json.dumps(fmt)

# Stats/timing code for connection class

class DatabaseMetrics(object):
    """
    Code to handle calculating timing statistics for discrete database
    calls in the CASSANDRA_DB module.  Generally only used in development 
    to produce statistics when pushing runs of test data through it.
    """
    
    # List of attributes to generate/method names.
    _individual_metrics = [
        'raw_insert', 
        'baserate_update',
        'aggregation_update',
        'meta_fetch',
        'stat_fetch', 
        'stat_update',
    ]
    _all_metrics = _individual_metrics + ['total', 'all']
    
    def __init__(self, profiling=False):
        
        self.profiling = profiling
        
        if not self.profiling:
            return
        
        # Populate attrs from list.
        for im in self._individual_metrics:
            setattr(self, '%s_time' % im, 0)
            setattr(self, '%s_count' % im, 0)
        
    def _increment(self, m, t):
        """
        Actual logic called by named wrapper methods.  Increments
        the time sums and counts for the various db calls.
        """
        setattr(self, '%s_time' % m, getattr(self, '%s_time' % m) + t)
        setattr(self, '%s_count' % m, getattr(self, '%s_count' % m) + 1)
        
    # These are all wrapper methods that call _increment()

    def raw_insert(self, t):
        self._increment('raw_insert', t)

    def baserate_update(self, t):
        self._increment('baserate_update', t)

    def aggregation_update(self, t):
        self._increment('aggregation_update', t)
        
    def meta_fetch(self, t):
        self._increment('meta_fetch', t)
        
    def stat_fetch(self, t):
        self._increment('stat_fetch', t)

    def stat_update(self, t):
        self._increment('stat_update', t)
        
    def report(self, metric='all'):
        """
        Called at the end of a test harness or other loading dev script.  
        Outputs the various data to the console.
        """
        
        if not self.profiling:
            print 'Not profiling'
            return
        
        if metric not in self._all_metrics:
            print 'bad metric'
            return
            
        s = ''
        time = count = 0
            
        if metric in self._individual_metrics:
            datatype, action = metric.split('_')
            action = action.title()
            time = getattr(self, '%s_time' % metric)
            count = getattr(self, '%s_count' % metric)
            if time: # stop /0 errors
                s = '%s %s %s data in %.3f (%.3f per sec)' \
                    % (action, count, datatype, time, (count/time))
                if metric.find('total') > -1:
                    s += ' (informational - not in total)'
        elif metric == 'total':
            for k,v in self.__dict__.items():
                if k.find('total') > -1:
                    # don't double count the agg total numbers
                    continue
                if k.endswith('_count'):
                    count += v
                elif k.endswith('_time'):
                    time += v
                else:
                    pass
            if time:
                s = 'Total: %s db transactions in %.3f (%.3f per sec)' \
                    % (count, time, (count/time))
        elif metric == 'all':
            for m in self._all_metrics:
                if m == 'all':
                    continue
                else:
                    self.report(m)
                    
        if len(s): print s


# Data encapsulation objects - these objects wrap the various data
# in an object and provide utility methods and properties to convert 
# timestampes, calculate averages, etc.
        
class DataContainerBase(object):
    """
    Base class for the other encapsulation objects.  Mostly provides 
    utility methods for subclasses.
    """
    
    _doc_properties = []
    _key_delimiter = ':'
    
    def __init__(self, device, oidset, oid, path, _id):
        self.device = device
        self.oidset = oidset
        self.oid = oid
        self.path = path
        self._id = _id
        
    def _handle_date(self,d):
        """
        Return a datetime object given a unix timestamp.
        """
        if type(d) == type(datetime.datetime.now()):
            return d
        else:
            return datetime.datetime.utcfromtimestamp(d)

    def get_document(self):
        """
        Return a dictionary of the attrs/props in the object.
        """
        doc = {}
        for k,v in self.__dict__.items():
            if k.startswith('_'):
                continue
            doc[k] = v
            
        for p in self._doc_properties:
            doc[p] = getattr(self, '%s' % p)
        
        return doc
        
    def get_key(self):
        """
        Return a cassandra row key based on the contents of the object.
        
        Format:
        
        router:interface:oid:frequency:year
        """
        return '%s%s%s%s%s%s%s%s%s' % (
            self.device, self._key_delimiter,
            self.path, self._key_delimiter,
            self.oid, self._key_delimiter,
            self.freq, self._key_delimiter,
            self.ts.year
        )
        
    def get_meta_key(self):
        """
        Get a "metadata row key" - metadata don't have timestamps/years.
        Other objects use this to look up entires in the metadata_cache.
        """
        return '%s%s%s%s%s%s%s' % (
            self.device, self._key_delimiter,
            self.path, self._key_delimiter,
            self.oid, self._key_delimiter,
            self.freq
        )
        
    def get_path(self):
        """
        Return a dict of the key attributes.
        """
        p = {}
        for k,v in self.__dict__.items():
            if k not in ['device', 'oidset', 'oid', 'path']:
                continue
            p[k] = v
        return p
        
    def get_path_tuple(self):
        """
        Return a tuple of the key attributes.
        """
        p = self.get_path()
        return (p['device'], p['oidset'], p['oid'], p['path'])
        
    def ts_to_unixtime(self, t='ts'):
        """
        Return an internally represented datetime value as a unix timestamp. 
        Defaults to returning 'ts' property, but can be given an arg to grab
        a different property/attribute like Metadata.last_update.
        """
        ts = getattr(self, t)
        return calendar.timegm(ts.utctimetuple())
        
        
class RawData(DataContainerBase):
    """
    Container for raw data rows.  Can be instantiated from args when
    reading from persist queue, or via **kw when reading data back
    out of mongo.
    """
    _doc_properties = ['ts']
    
    def __init__(self, device=None, oidset=None, oid=None, path=None,
            ts=None, val=None, freq=None, _id=None):
        DataContainerBase.__init__(self, device, oidset, oid, path, _id)
        self._ts = None
        self.ts = ts
        self.val = val
        self.freq = freq
        
    @property
    def ts(self):
        return self._ts
        
    @ts.setter
    def ts(self, value):
        self._ts = self._handle_date(value)
        
    @property
    def min_last_update(self):
        return self.ts_to_unixtime() - self.freq * 40
        
    @property
    def slot(self):
        return (self.ts_to_unixtime() / self.freq) * self.freq
    
        
class Metadata(DataContainerBase):
    """
    Container for metadata information.
    """
    
    _doc_properties = ['min_ts', 'last_update']
    
    def __init__(self, device=None, oidset=None, oid=None, path=None, _id=None,
            last_update=None, last_val=None, min_ts=None, freq=None):
        DataContainerBase.__init__(self, device, oidset, oid, path, _id)
        self._min_ts = self._last_update = None
        self.last_update = last_update
        self.last_val = last_val
        self.min_ts = min_ts
        self.freq = freq
        
    @property
    def min_ts(self):
        return self._min_ts
        
    @min_ts.setter
    def min_ts(self, value):
        self._min_ts = self._handle_date(value)
    
    @property
    def last_update(self):
        return self._last_update
        
    @last_update.setter
    def last_update(self, value):
        self._last_update = self._handle_date(value)
        
    def refresh_from_raw(self, data):
        """
        Update the internal state of a metadata object from a raw data
        object.  This is called by the persister when calculating 
        base rate deltas to refresh cache with current values after a 
        successful delta is generated.
        """
        if self.min_ts > data.ts:
            self.min_ts = data.ts
        self.last_update = data.ts
        self.last_val = data.val
        

class BaseRateBin(DataContainerBase):
    """
    Container for base rates.  Has 'avg' property to return the averages.
    """
    
    _doc_properties = ['ts']
    
    def __init__(self, device=None, oidset=None, oid=None, path=None, _id=None, 
            ts=None, freq=None, val=None, is_valid=1):
        DataContainerBase.__init__(self, device, oidset, oid, path, _id)
        self._ts = None
        self.ts = ts
        self.freq = freq
        self.val = val
        self.is_valid = is_valid

    @property
    def ts(self):
        return self._ts

    @ts.setter
    def ts(self, value):
        self._ts = self._handle_date(value)
        
    @property
    def avg(self):
        return self.val / self.freq
    

class AggregationBin(BaseRateBin):
    """
    Container for aggregation rollups.  Also has 'avg' property to generage averages.
    """
    
    def __init__(self, device=None, oidset=None, oid=None, path=None, _id=None,
            ts=None, freq=None, val=None, base_freq=None, count=None, 
            min=None, max=None):
        BaseRateBin.__init__(self, device, oidset, oid, path, _id, ts, freq, val)
        
        self.count = count
        self.min = min
        self.max = max
        self.base_freq = base_freq
        
    @property
    def avg(self):
        return self.val / (self.count * self.base_freq)
