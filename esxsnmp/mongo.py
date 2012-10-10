#!/usr/bin/env python
# encoding: utf-8
"""
Mongo DB interface calls and data encapsulation objects.
"""
# Standard
import calendar
import datetime
import json
import os
import sys
import time
# Third party
import pymongo
from pymongo import ASCENDING, DESCENDING
from pymongo.connection import Connection
from pymongo.errors import ConnectionFailure
from pymongo.read_preferences import ReadPreference as rp
from bson.son import SON

INVALID_VALUE = -9999

class MongoException(Exception):
    """Common base"""
    pass

class ConnectionException(MongoException):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)
        
class MONGO_DB(object):
    
    database = 'esxsnmp'
    raw_coll = 'raw_data'
    meta_coll = 'metadata'
    rate_coll = 'base_rates'
    agg_coll = 'aggregations'
    
    path_idx = [
        ('device', ASCENDING),
        ('path', ASCENDING),
        ('oid', ASCENDING),
    ]
    
    raw_idx  = []
    meta_idx = path_idx
    rate_idx = path_idx + [ ('ts', ASCENDING) ]
    agg_idx  = path_idx + [ ('ts', ASCENDING) ]
    
    insert_flags = { 'safe': True }
    
    def __init__(self, config, clear_on_test=False):
        # Connection
        try:
            self.connection = pymongo.Connection(host=config.mongo_host, 
                    port=config.mongo_port, read_preference=rp.SECONDARY_PREFERRED)
        except ConnectionFailure:
            raise ConnectionException("Couldn't connect to DB "
                            "at %s:%d" % (config.mongo_host, config.mongo_port))
                                      
        self.db = self.connection[self.database]
        
        if config.mongo_user != '':
            success = self.db.authenticate(config.mongo_user, config.mongo_pass)
            if not success:
                raise ConnectionException("Could not authenticate to "
                                          "database as user '%s'" % (config.mongo_user))
                                          
        if clear_on_test and os.environ.get("ESXSNMP_TESTING", False):
            self.connection.drop_database(self.database)
            
        # Collections
        self.raw_data = self.db[self.raw_coll]
        self.metadata = self.db[self.meta_coll]
        self.rates    = self.db[self.rate_coll]
        self.aggs     = self.db[self.agg_coll]
        
        # Indexes
        self.metadata.ensure_index(self.meta_idx, unique=True)
        self.rates.ensure_index(self.rate_idx, unique=True)
        self.aggs.ensure_index(self.agg_idx, unique=True)
        
        # Timing
        self.stats = DatabaseMetrics()
        
        
    def set_raw_data(self, raw_data):
        t = time.time()
        ret = self.raw_data.insert(raw_data.get_document(), **self.insert_flags)
        self.stats.raw_insert(time.time() - t)
        
    def set_metadata(self, meta_d):
        ret = self.metadata.insert(meta_d.get_document(), **self.insert_flags)
        
    def _get_query_criteria(self, path, ts=None, freq=None):
        
        q_c = [
            ('device', path['device']),
            ('path', path['path']),
            ('oid', path['oid']),
        ]
        
        if freq:
            q_c.append(('freq', freq))
            
        if ts:
            q_c.append(('ts', ts))
        
        # The SON is an ordered dict (fyi).
        return SON(q_c)
        
    def get_metadata(self, raw_data):
        t = time.time()
        meta_d = self.metadata.find_one(
            self._get_query_criteria(raw_data.get_path()),
        )
        
        if not meta_d:
            # Seeing first row - intialize with vals
            meta_d = Metadata(last_update=raw_data.ts, last_val=raw_data.val,
                min_ts=raw_data.ts, freq=raw_data.freq, **raw_data.get_path())
            self.set_metadata(meta_d)
        else:
            meta_d = Metadata(**meta_d)
        
        self.stats.meta_fetch((time.time() - t))
        return meta_d
        
    def update_metadata(self, metadata):
        t = time.time()
        ret = self.metadata.update(
            { '_id': metadata._id },
            {
                '$set': {
                    'last_val': metadata.last_val,
                    'min_ts': metadata.min_ts,
                    'last_update': metadata.last_update,
                },
            },
            upsert=False, **self.insert_flags
        )
        self.stats.meta_update((time.time() - t))
        
    def update_rate_bin(self, ratebin):
        t = time.time()
        ret = self.rates.update(
            self._get_query_criteria(ratebin.get_path(), ts=ratebin.ts),
            {
                # Manually setting oidset because it has been taken
                # out of the upsert search criteria.
                '$set': { 'freq': ratebin.freq, 'oidset': ratebin.oidset },
                '$inc': { 'val': ratebin.val }
            },
            upsert=True, **self.insert_flags
        )
        self.stats.baserate_update((time.time() - t))
        
        
    def update_aggregation(self, raw_data, agg_ts, freq):
        t = time.time()
        ret = self.aggs.find_and_modify(
            self._get_query_criteria(raw_data.get_path(), ts=agg_ts, freq=freq),
            {
                '$set': { 'freq': freq },
                '$inc': { 'count': 1, 'val': raw_data.val },
            },
            new=True,
            upsert=False
        )
        self.stats.aggregation_find((time.time() - t))
        
        if not ret:
            # There's not an existing document - insert a new one.
            agg = AggregationBin(
                ts=agg_ts, freq=freq, val=raw_data.val, base_freq=raw_data.freq, count=1,
                min=raw_data.val, max=raw_data.val, **raw_data.get_path()
            )
            # Not timing the inserts because they are fast and infrequent.
            self.aggs.insert(agg.get_document())
        else:
            # Do we need to update min or max in the aggregation?
            update_attr = None
            if raw_data.val > ret['max'] or raw_data.val < ret['min']:
                update_attr = 'max' if raw_data.val > ret['max'] else 'min'    
            
            if update_attr:
                t1 = time.time()
                self.aggs.update(
                    { '_id': ret['_id'] },
                    { '$set': { update_attr : raw_data.val} },
                    new=True, upsert=False, **self.insert_flags
                )
                self.stats.aggregation_update((time.time() - t1))
        
        self.stats.aggregation_total((time.time() - t))
        
    def _to_datetime(self,d):
        if type(d) == type(datetime.datetime.now()):
            return d
        else:
            return datetime.datetime.utcfromtimestamp(d)
        
    def query_baserate_timerange(self, device=None, path=None, oid=None, 
                ts_min=None, ts_max=None, as_json=False):
        
        ret = self.rates.find(
            {
                'device': device, 
                'path': path, 
                'oid': oid,
                'ts': {
                    '$gte': self._to_datetime(ts_min),
                    '$lte': self._to_datetime(ts_max),
                },
            }
        ).sort('ts', ASCENDING)
        
        # Just return the results and format elsewhere.
        results = []
        
        for r in ret:
            results.append(r)
            
        if as_json: # format results for query interface
            freq = None
            # Get the frequency from the metatdata if the result set is empty
            if not results:
                m_lookup = self.metadata.find_one(
                    {
                        'device': device, 
                        'path': path, 
                        'oid': oid,
                    }
                )
                freq = m_lookup['freq']
            return FormattedOutput.base_rate(ts_min, ts_max, results, freq)
        else:
            return results
            
    def query_aggregation_timerange(self, device=None, path=None, oid=None, 
                ts_min=None, ts_max=None, freq=None, cf=None, as_json=False):
                
        ret = self.aggs.find(
            {
                'device': device, 
                'path': path, 
                'oid': oid,
                'freq': freq,
                'ts': {
                    '$gte': self._to_datetime(ts_min),
                    '$lte': self._to_datetime(ts_max),
                },
            }
        ).sort('ts', ASCENDING)

        # Just return the results and format elsewhere.
        results = []
        
        for r in ret:
            results.append(r)
        
        if as_json: # format results for query interface
            return FormattedOutput.aggregate_rate(ts_min, ts_max, results, freq,
                    cf.replace('average', 'avg'))
        else:
            return results
            
    def query_raw_data(self, device=None, path=None, oid=None, 
                ts_min=None, ts_max=None, as_json=False):
                
        ret = self.raw_data.find(
            {
                'device': device, 
                'path': path, 
                'oid': oid,
                'ts': {
                    '$gte': self._to_datetime(ts_min),
                    '$lte': self._to_datetime(ts_max),
                },
            }
        ).sort('ts', ASCENDING)

        # Just return the results and format elsewhere.
        results = []

        for r in ret:
            results.append(r)
            
        if as_json: # format results for query interface
            freq = None
            # Get the frequency from the metatdata if the result set is empty
            if not results:
                m_lookup = self.metadata.find_one(
                    {
                        'device': device, 
                        'path': path, 
                        'oid': oid,
                    }
                )
                freq = m_lookup['freq']
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
        
        fmt = SON(fmt)
        
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
    
        fmt = SON(fmt)
        
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
        
        fmt = SON(fmt)
        
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
        'meta_fetch', 
        'meta_update', 
        'baserate_update',
        'aggregation_total',
        'aggregation_find',
        'aggregation_update'
    ]
    _all_metrics = _individual_metrics + ['total', 'all']
    
    def __init__(self):
        for im in self._individual_metrics:
            setattr(self, '%s_time' % im, 0)
            setattr(self, '%s_count' % im, 0)
        
        
    def _increment(self, m, t):
        setattr(self, '%s_time' % m, getattr(self, '%s_time' % m) + t)
        setattr(self, '%s_count' % m, getattr(self, '%s_count' % m) + 1)

    def raw_insert(self, t):
        self._increment('raw_insert', t)

    def meta_fetch(self, t):
        self._increment('meta_fetch', t)

    def meta_update(self, t):
        self._increment('meta_update', t)

    def baserate_update(self, t):
        self._increment('baserate_update', t)

    def aggregation_total(self, t):
        self._increment('aggregation_total', t)

    def aggregation_find(self, t):
        self._increment('aggregation_find', t)

    def aggregation_update(self, t):
        self._increment('aggregation_update', t)
        
    def report(self, metric='all'):
        
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
            s = 'Total: %s db transactions in %.3f (%.3f per sec)' \
                % (count, time, (count/time))
        elif metric == 'all':
            for m in self._all_metrics:
                if m == 'all':
                    continue
                else:
                    self.report(m)
                    
        print s # XXX(mmg): log this


# Data encapsulation objects
        
class DataContainerBase(object):
    
    _doc_properties = []
    
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
