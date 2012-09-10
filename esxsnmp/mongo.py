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
# TSDB
from tsdb.error import *
from tsdb.row import Aggregate, ROW_VALID, ROW_TYPE_MAP
from tsdb.chunk_mapper import CHUNK_MAPPER_MAP
from tsdb.util import write_dict, calculate_interval, calculate_slot
from tsdb.filesystem import get_fs

class ConnectionException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class MONGO_DB(object):
    
    database = 'esxsnmp'
    raw_coll = 'raw_data'
    meta_coll = 'metadata'
    
    raw_idx = []
    meta_idx = [('device',1),('oidset',1),('oid',1),('path',1)]
    
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
        
        # Indexes
        self.metadata.ensure_index(self.meta_idx)
        
        
    def set_raw_data(self, raw_data):
        self.raw_data.insert(raw_data.get_document(), **self.insert_flags)
        
    def set_metadata(self, meta_d):
        self.metadata.insert(meta_d.get_document(), **self.insert_flags)
        
    def get_metadata(self, raw_data):
        
        meta_d = self.metadata.find_one(raw_data.get_path())
        
        if not meta_d:
            # Seeing first row - intialize with vals
            meta_d = Metadata(last_update=raw_data.ts, last_val=raw_data.val,
                **raw_data.get_path())
            self.set_metadata(meta_d)
        else:
            meta_d = Metadata(**meta_d)
        
        return meta_d
        
        
class DataContainerBase(object):
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
    def __init__(self, device=None, oidset=None, oid=None, path=None, 
            ts=None, flags=None, val=None, rate=None, _id=None):
        DataContainerBase.__init__(self, device, oidset, oid, path, _id)
        self.ts = self._handle_date(ts)
        self.flags = flags
        self.val = val
        self.rate = rate
        
    @property
    def min_last_update(self):
        return self.ts_to_unixtime() - self.rate * 40
        
    @property
    def slot(self):
        return (self.ts_to_unixtime() / self.rate) * self.rate
    
        
class Metadata(DataContainerBase):
    def __init__(self, device=None, oidset=None, oid=None, path=None,
            last_update=None, last_val=None, _id=None):
        DataContainerBase.__init__(self, device, oidset, oid, path, _id)
        self.last_update = self._handle_date(last_update)
        self.last_val = last_val
