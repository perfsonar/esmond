#!/usr/bin/env python
# encoding: utf-8
"""
Work in progress code for mongo development.  These things will get a new 
home.
"""
# Standard
import calendar
import datetime
import sys
import os
# Third party
import pymongo
from pymongo.connection import Connection
from pymongo.errors import ConnectionFailure

INVALID_VALUE = -9999

class ConnectionException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class MONGO_DB(object):
    
    database = 'esxsnmp'
    raw_coll = 'raw_data'
    meta_coll = 'metadata'
    rate_coll = 'rates'
    
    path_idx = [('device',1),('oidset',1),('oid',1),('path',1)]
    raw_idx = []
    meta_idx = path_idx
    rate_idx = path_idx + [('ts',1)]
    
    insert_flags = { 'safe': True }
    
    def __init__(self, host, port, user='', password='', flush_all=False):
        # Connection
        try:
            self.connection = pymongo.Connection(host=host, port=port)
        except ConnectionFailure:
            raise ConnectionException("Couldn't connect to DB "
                                      "at %s:%d" % (host, port))
                                      
        self.db = self.connection[self.database]
        
        if user != '':
            success = self.db.authenticate(user, password)
            if not success:
                raise ConnectionException("Could not authenticate to "
                                          "database as user '%s'" % (user))
                                          
        if flush_all:
            self.connection.drop_database(self.database)
            
        # Collections
        self.raw_data = self.db[self.raw_coll]
        self.metadata = self.db[self.meta_coll]
        self.rates    = self.db[self.rate_coll]
        
        # Indexes
        self.metadata.ensure_index(self.meta_idx, unique=True)
        self.rates.ensure_index(self.rate_idx, unique=True)
        
        
    def set_raw_data(self, raw_data):
        ret = self.raw_data.insert(raw_data.get_document(), **self.insert_flags)
        
    def set_metadata(self, meta_d):
        ret = self.metadata.insert(meta_d.get_document(), **self.insert_flags)
        
    def get_metadata(self, raw_data):
        
        meta_d = self.metadata.find_one(raw_data.get_path())
        
        if not meta_d:
            # Seeing first row - intialize with vals
            meta_d = Metadata(last_update=raw_data.ts, last_val=raw_data.val,
                min_ts=raw_data.ts, **raw_data.get_path())
            self.set_metadata(meta_d)
        else:
            meta_d = Metadata(**meta_d)
        
        return meta_d
        
    def update_metadata(self, metadata):
        p = metadata.get_path()
        ret = self.metadata.update(
            {
                'device': p['device'],
                'oidset': p['oidset'],
                'oid':    p['oid'],
                'path':   p['path']
            },
            {
                '$set': {
                    'last_val': metadata.last_val,
                    'min_ts': metadata.min_ts,
                    'last_update': metadata.last_update,
                },
            },
            upsert=False, **self.insert_flags
        )
        
    def update_rate_bin(self, ratebin):
        p = ratebin.get_path()
        
        ret = self.rates.update(
            {
               'device': p['device'],
               'oidset': p['oidset'],
               'oid':    p['oid'],
               'path':   p['path'],
               'ts':     ratebin.ts
            }, 
            {
                '$set': { 'freq': ratebin.freq },
                '$inc': { 'val': ratebin.val }
            },
            upsert=True, **self.insert_flags
        )


# Objects to hold the data
        
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
            exec("doc['%s'] = self.%s" % (p, p))
        
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
            last_update=None, last_val=None, min_ts=None):
        DataContainerBase.__init__(self, device, oidset, oid, path, _id)
        self._min_ts = self._last_update = None
        self.last_update = last_update
        self.last_val = last_val
        self.min_ts = min_ts
        
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
        
class RateBin(DataContainerBase):
    
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

