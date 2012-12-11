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
import pprint
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

class CassandraException(Exception):
    """Common base"""
    pass

class ConnectionException(CassandraException):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)
        
class CASSANDRA_DB(object):
    
    database = 'esxsnmp'
    raw_coll = 'raw_data'
    meta_coll = 'metadata'
    rate_coll = 'base_rates'
    agg_coll = 'aggregations'
    
    def __init__(self, config, clear_on_test=False):
        # Connection
        try:
            pass
            # thrift.transport.TTransport.TTransportException: Could not connect to localhost:9160

        except:
            raise ConnectionException("Couldn't connect to DB "
                            "at %s:%d" % (config.mongo_host, config.mongo_port))
                                      
        # Column Families
        #self.raw_data = self.db[self.raw_coll]
        #self.metadata = self.db[self.meta_coll]
        #self.rates    = self.db[self.rate_coll]
        #self.aggs     = self.db[self.agg_coll]
        
        if clear_on_test and os.environ.get("ESXSNMP_TESTING", False):
            #self.raw_data.remove({})
            #self.metadata.remove({})
            #self.rates.remove({})
            #self.aggs.remove({})
            pass
        
        if config.mongo_raw_expire:
            pass
        
        # Timing
        self.stats = DatabaseMetrics()
        
        
    def set_raw_data(self, raw_data):
        t = time.time()
        
        self.stats.raw_insert(time.time() - t)
        
    def set_metadata(self, meta_d):
        pass
        
    def get_metadata(self, raw_data):
        t = time.time()

        meta_d = None
        
        if not meta_d:
            # Seeing first row - intialize with vals
            meta_d = Metadata(last_update=raw_data.ts, last_val=raw_data.val,
                min_ts=raw_data.ts, freq=raw_data.freq, **raw_data.get_path())
        else:
            meta_d = Metadata(**meta_d)
        
        self.stats.meta_fetch((time.time() - t))
        return meta_d
        
    def update_metadata(self, metadata):
        t = time.time()
        
        self.stats.meta_update((time.time() - t))
        
    def update_rate_bin(self, ratebin):
        t = time.time()
        
        self.stats.baserate_update((time.time() - t))
        
        
    def update_aggregation(self, raw_data, agg_ts, freq):
        t = time.time()
        
        # old find and modify
        if not ret:
            # There's not an existing document - insert a new one.
            agg = AggregationBin(
                ts=agg_ts, freq=freq, val=raw_data.val, base_freq=raw_data.freq, count=1,
                min=raw_data.val, max=raw_data.val, **raw_data.get_path()
            )
        else:
            # Do we need to update min or max in the aggregation?
            #update_attr = None
            #if raw_data.val > ret['max'] or raw_data.val < ret['min']:
            #    update_attr = 'max' if raw_data.val > ret['max'] else 'min'    
            
            if update_attr:
                t1 = time.time()

                self.stats.aggregation_update((time.time() - t1))
        
        self.stats.aggregation_total((time.time() - t))
        
    def query_baserate_timerange(self, device=None, path=None, oid=None, 
                ts_min=None, ts_max=None, as_json=False):
        
        ret = [] # query stuff
        
        # Just return the results and format elsewhere.
        results = []
        
        for r in ret:
            results.append(r)
            
        if as_json: # format results for query interface
            freq = None
            # Get the frequency from the metatdata if the result set is empty
            if not results:
                pass
            return FormattedOutput.base_rate(ts_min, ts_max, results, freq)
        else:
            return results
            
    def query_aggregation_timerange(self, device=None, path=None, oid=None, 
                ts_min=None, ts_max=None, freq=None, cf=None, as_json=False):
                
        ret = []

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
                
        ret = []

        # Just return the results and format elsewhere.
        results = []

        for r in ret:
            results.append(r)
            
        if as_json: # format results for query interface
            freq = None
            # Get the frequency from the metatdata if the result set is empty
            if not results:
                #freq = m_lookup['freq']
                pass
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
