#!/usr/bin/env python
# encoding: utf-8
"""
Cassandra DB interface calls and data encapsulation objects.
"""
# Standard
import calendar
import datetime
import json
import os
import pprint
import sys
import time
from collections import OrderedDict
# Third party
from pycassa.pool import ConnectionPool, AllServersUnavailable
from pycassa.columnfamily import ColumnFamily
from pycassa.system_manager import *

from thrift.transport.TTransport import TTransportException

INVALID_VALUE = -9999

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
    
    _queue_size = 2000
    
    def __init__(self, config, clear_on_test=False):
        # Connect with SystemManager, do a schema check and setup if need be
        try:
            sysman = SystemManager('%s:%s' % \
                (config.cassandra_host, config.cassandra_port))                              
        except TTransportException, e:
            raise ConnectionException("System Manager can't connect to Cassandra "
                "at %s:%d - %s" % (config.cassandra_host, config.cassandra_port, e))
        
        # Blow everything away if we're testing
        if clear_on_test and os.environ.get("ESXSNMP_TESTING", False):
            if self.keyspace in sysman.list_keyspaces():
                sysman.drop_keyspace(self.keyspace)
        # Create keyspace
        if not self.keyspace in sysman.list_keyspaces():
            sysman.create_keyspace(self.keyspace, SIMPLE_STRATEGY, 
                {'replication_factor': '1'})
        # Create column families
        # Raw Data CF
        if not sysman.get_keyspace_column_families(self.keyspace).has_key(self.raw_cf):
            sysman.create_column_family(self.keyspace, self.raw_cf, super=False, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=LONG_TYPE,
                    key_validation_class=UTF8_TYPE)
        # Base Rate CF
        if not sysman.get_keyspace_column_families(self.keyspace).has_key(self.rate_cf):
            sysman.create_column_family(self.keyspace, self.rate_cf, super=False, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=COUNTER_COLUMN_TYPE,
                    key_validation_class=UTF8_TYPE)
        # Rate aggregation CF
        if not sysman.get_keyspace_column_families(self.keyspace).has_key(self.agg_cf):
            sysman.create_column_family(self.keyspace, self.agg_cf, super=True, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=COUNTER_COLUMN_TYPE,
                    key_validation_class=UTF8_TYPE)
        # Stat aggregation CF
        if not sysman.get_keyspace_column_families(self.keyspace).has_key(self.stat_cf):
            sysman.create_column_family(self.keyspace, self.stat_cf, super=True, 
                    comparator_type=LONG_TYPE, 
                    default_validation_class=LONG_TYPE,
                    key_validation_class=UTF8_TYPE)
                    
        sysman.close()
        
        # Now, set up the ConnectionPool
        try:
            self.pool = ConnectionPool(self.keyspace, 
                        ['%s:%s' % (config.cassandra_host, config.cassandra_port)])
        except AllServersUnavailable, e:
            raise ConnectionException("Couldn't connect to Cassandra "
                    "at %s:%d - %s" % (config.cassandra_host, config.cassandra_port, e))
        
        # Column family connections
        self.raw_data = ColumnFamily(self.pool, self.raw_cf).batch(self._queue_size)
        self.rates    = ColumnFamily(self.pool, self.rate_cf).batch(self._queue_size)
        self.aggs     = ColumnFamily(self.pool, self.agg_cf).batch(self._queue_size)
        
        # Timing
        self.stats = DatabaseMetrics(no_profile=False)
        
        # Class members
        self.raw_expire = config.cassandra_raw_expire
        self.metadata_cache = {}
        
    def flush(self):
        self.raw_data.send()
        self.rates.send()
        self.aggs.send()
        
    def set_raw_data(self, raw_data):
        if self.raw_expire:
            # set up time to live expiry time here.
            pass
        t = time.time()
        self.raw_data.insert(raw_data.get_key(), 
            {raw_data.ts_to_unixtime(): raw_data.val})
        self.stats.raw_insert(time.time() - t)
        
    def set_metadata(self, meta_d):
        # Do this in memory for now
        self.metadata_cache[meta_d.get_meta_key()] = meta_d.get_document()
        
    def get_metadata(self, raw_data):
        t = time.time()

        meta_d = None
        
        if not self.metadata_cache.has_key(raw_data.get_meta_key()):
            # Seeing first row - intialize with vals
            meta_d = Metadata(last_update=raw_data.ts, last_val=raw_data.val,
                min_ts=raw_data.ts, freq=raw_data.freq, **raw_data.get_path())
            self.set_metadata(meta_d)
        else:
            meta_d = Metadata(**self.metadata_cache[raw_data.get_meta_key()])
        
        #self.stats.meta_fetch((time.time() - t))
        return meta_d
        
    def update_metadata(self, metadata):
        """
        """
        t = time.time()
        for i in ['last_val', 'min_ts', 'last_update']:
            self.metadata_cache[metadata.get_meta_key()][i] = getattr(metadata, i)
        #self.stats.meta_update((time.time() - t))
        
    def update_rate_bin(self, ratebin):
        t = time.time()
        self.rates.insert(ratebin.get_key(),
            {ratebin.ts_to_unixtime(): ratebin.val})
        self.stats.baserate_update((time.time() - t))
        
        
    def update_rate_aggregation(self, raw_data, agg_ts, freq):
        
        t = time.time()
        
        agg = AggregationBin(
            ts=agg_ts, freq=freq, val=raw_data.val, base_freq=raw_data.freq, count=1,
            min=raw_data.val, max=raw_data.val, **raw_data.get_path()
        )
        
        self.aggs.insert(agg.get_key(), 
            {agg.ts_to_unixtime(): {'val': agg.val, str(agg.base_freq): 1}})
        
        self.stats.aggregation_update((time.time() - t))
        
    def update_stat_aggregation(self, raw_data, agg_ts, freq):
        t = time.time()
        
        self.stats.stat_fetch((time.time() - t))
        
        t = time.time()
        
        self.stats.stat_update((time.time() - t))
        
    def _get_row_keys(self, device, path, oid, freq, ts_min, ts_max):
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
                freq=None, ts_min=None, ts_max=None, as_json=False):
        
        ret = self.rates._column_family.multiget(
                self._get_row_keys(device,path,oid,freq,ts_min,ts_max), 
                column_start=ts_min, column_finish=ts_max)
        
        # Just return the results and format elsewhere.
        results = []
        
        for k,v in ret.items():
            for kk,vv in v.items():
                results.append({'ts': kk, 'val': vv})
            
        if as_json: # format results for query interface
            # Get the frequency from the metatdata if the result set is empty
            if not results:
                pass
            return FormattedOutput.base_rate(ts_min, ts_max, results, freq)
        else:
            return results
            
    def query_aggregation_timerange(self, device=None, path=None, oid=None, 
                ts_min=None, ts_max=None, freq=None, cf=None, as_json=False):
        
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
        else:
            # Look for the min or max in the base rates
            ret = self.rates._column_family.multiget(
                    self._get_row_keys(device,path,oid,freq,ts_min,ts_max), 
                    column_start=ts_min, column_finish=ts_max)
            
            results = []
            ts_min = ts_max = minimum = maximum = None
            
            for k,v in ret.items():
                for kk,vv in v.items():
                    if not ts_min and not ts_max and not minimum and not maximum:
                        ts_min = kk
                        ts_max = kk
                        minimum = vv
                        maximum = vv
                    else:
                        if vv < minimum:
                            ts_min = kk
                            minimum = vv
                        if vv > maximum:
                            ts_max = kk
                            maximum = vv
                            
            if cf == 'min':
                results.append({'ts': ts_min, 'min': minimum})
            else:
                results.append({'ts': ts_max, 'max': maximum})
                            
        
        if as_json: # format results for query interface
            return FormattedOutput.aggregate_rate(ts_min, ts_max, results, freq,
                    cf.replace('average', 'avg'))
        else:
            return results
            
    def query_raw_data(self, device=None, path=None, oid=None, freq=None,
                ts_min=None, ts_max=None, as_json=False):
                
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
    
    @staticmethod
    def _from_datetime(d):
        if type(d) != type(datetime.datetime.now()):
            return d
        else:
            return calendar.timegm(d.utctimetuple())
    
    @staticmethod
    def base_rate(ts_min, ts_max, results, freq=None):
        fmt = [
            ('agg', freq if freq else results[0]['freq']),
            ('end_time', ts_max),
            ('data', []),
            ('cf', 'average'),
            ('begin_time', ts_min)
        ]
        
        fmt = OrderedDict(fmt)
        
        for r in results:
            fmt['data'].append(
                [
                    FormattedOutput._from_datetime(r['ts']), 
                    None if r['val'] == INVALID_VALUE else float(r['val'])
                ]
            )
        
        return json.dumps(fmt)
        
    @staticmethod
    def aggregate_rate(ts_min, ts_max, results, freq, cf):
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
                    getattr(ro, cf)
                ]
            )
            
        return json.dumps(fmt)
        
    @staticmethod
    def raw_data(ts_min, ts_max, results, freq=None):
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
    
    _individual_metrics = [
        'raw_insert', 
        'baserate_update',
        'aggregation_update',
        'stat_fetch', 
        'stat_update',
    ]
    _all_metrics = _individual_metrics + ['total', 'all']
    
    def __init__(self, no_profile=False):
        self.no_profile = no_profile
        
        if self.no_profile: return
        
        for im in self._individual_metrics:
            setattr(self, '%s_time' % im, 0)
            setattr(self, '%s_count' % im, 0)
        
    def _increment(self, m, t):
        if self.no_profile: return
        setattr(self, '%s_time' % m, getattr(self, '%s_time' % m) + t)
        setattr(self, '%s_count' % m, getattr(self, '%s_count' % m) + 1)

    def raw_insert(self, t):
        if self.no_profile: return
        self._increment('raw_insert', t)

    def baserate_update(self, t):
        if self.no_profile: return
        self._increment('baserate_update', t)

    def aggregation_update(self, t):
        if self.no_profile: return
        self._increment('aggregation_update', t)
        
    def stat_fetch(self, t):
        if self.no_profile: return
        self._increment('stat_fetch', t)

    def stat_update(self, t):
        if self.no_profile: return
        self._increment('stat_update', t)
        
    def report(self, metric='all'):
        
        if self.no_profile:
            print 'Not profiling'
            return
        
        if metric not in self._all_metrics:
            print 'bad metric' # XXX(mmg): log this
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
                    
        if len(s): print s # XXX(mmg): log this


# Data encapsulation objects
        
class DataContainerBase(object):
    
    _doc_properties = []
    _key_delimiter = ':'
    
    def __init__(self, device, oidset, oid, path, _id):
        self.device = device
        self.oidset = oidset
        self.oid = oid
        self.path = path
        self._id = _id
        
    def _handle_date(self,d):
        # don't reconvert if we are instantiating from 
        # returned mongo document
        if type(d) == type(datetime.datetime.now()):
            return d
        else:
            return datetime.datetime.utcfromtimestamp(d)

    def get_document(self):
        doc = {}
        for k,v in self.__dict__.items():
            if k.startswith('_'):
                continue
            doc[k] = v
            
        for p in self._doc_properties:
            doc[p] = getattr(self, '%s' % p)
        
        return doc
        
    def get_key(self):
        # Get the cassandra row key for an object
        return '%s%s%s%s%s%s%s%s%s' % (
            self.device, self._key_delimiter,
            self.path, self._key_delimiter,
            self.oid, self._key_delimiter,
            self.freq, self._key_delimiter,
            self.ts.year
        )
        
    def get_meta_key(self):
        # Get a "metadata row key" - metadata don't have timestamps
        # but some other objects need access to this to look up
        # entires in the metadata_cache.
        return '%s%s%s%s%s%s%s' % (
            self.device, self._key_delimiter,
            self.path, self._key_delimiter,
            self.oid, self._key_delimiter,
            self.freq
        )
        
    def get_path(self):
        p = {}
        for k,v in self.__dict__.items():
            if k not in ['device', 'oidset', 'oid', 'path']:
                continue
            p[k] = v
        return p
        
    def get_path_tuple(self):
        p = self.get_path()
        return (p['device'], p['oidset'], p['oid'], p['path'])
        
    def ts_to_unixtime(self, t='ts'):
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
            ts=None, flags=None, val=None, freq=None, _id=None):
        DataContainerBase.__init__(self, device, oidset, oid, path, _id)
        self._ts = None
        self.ts = ts
        self.flags = flags
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
        if self.min_ts > data.ts:
            self.min_ts = data.ts
        self.last_update = data.ts
        self.last_val = data.val
        

class BaseRateBin(DataContainerBase):
    
    _doc_properties = ['ts']
    
    def __init__(self, device=None, oidset=None, oid=None, path=None, _id=None, 
            ts=None, freq=None, val=None):
        DataContainerBase.__init__(self, device, oidset, oid, path, _id)
        self._ts = None
        self.ts = ts
        self.freq = freq
        self.val = val

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
