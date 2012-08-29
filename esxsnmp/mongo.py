#!/usr/bin/env python
# encoding: utf-8
"""
Work in progress code for mongo development.  These things will get a new 
home.
"""

import sys
import os
import unittest

from tsdb.error import *
from tsdb.row import Aggregate, ROW_VALID, ROW_TYPE_MAP
from tsdb.chunk_mapper import CHUNK_MAPPER_MAP
from tsdb.util import write_dict, calculate_interval, calculate_slot
from tsdb.filesystem import get_fs

class MONGODBBase(object):
    """TSDBBase is a base class for other TSDB containers.

    It is abstract and should not be instantiated."""

    tag = None
    metadata_map = None

    def __init__(self, metadata=None):
        if self.tag is None:
            raise NotImplementedError("TSDBBase is abstract.")

        if metadata is None:
            self.metadata = {}
        else:
            self.metadata = metadata

        self.vars = {}
        self.sets = {}
        self.aggs = {}
        self.agg_list = []

        if not self.tag == 'TSDB':
            self.db = self._find_db()
            self.fs = self.db.fs

    def __str__(self):
        return "%s [%s]" % (self.tag, self.path)

    def __repr__(self):
        return '<%s %s>' % (self.tag, self.path)

    def _find_db(self):
        parent = self
        while parent:
            if isinstance(parent, MONGODB):
                return parent
            parent = parent.parent
        raise TSDBError("Unable to locate root")

    def load_metadata(self):
        """Load metadata for this container.

        Metadata is stored in the file specified by the tag class attribute.

        Data is stored in the format:

        NAME: VALUE

        With one name/value pair per line.  Lists are stored as the str()
        representation of the actual list."""

        f = self.fs.open(os.path.join(self.path, self.tag), "r")

        for line in f:
            line = line.strip()
            if line.startswith("#"):
                continue
            (var, val) = line.split(':', 1)
            val = val.strip()
            # XXX probably want to revist this
            if self.metadata_map.has_key(var):
                if self.metadata_map[var] == list:
                    val = eval(val)
                else:
                    val = self.metadata_map[var](val)
            self.metadata[var] = val

        f.close()

    def save_metadata(self):
        """Save metadata for this container."""
        write_dict(self.fs, os.path.join(self.path, self.tag), self.metadata)

    def list_sets(self):
        """List TSDBSets in this container."""
        return filter( \
                lambda x: TSDBSet.is_tsdb_set(self.fs, os.path.join(self.path, x)),
                self.fs.listdir(self.path))

    def get_set(self, name):
        """Get named TSDBSet."""
        if not self.sets.has_key(name):
            self.sets[name] = TSDBSet(self, os.path.join(self.path, name))

        return self.sets[name]

    def add_set(self, name):
        """Create a new TSDBSet in this container."""
        prefix = self.path
        tsdb_set = self
        steps = name.split('/')
        for step in steps[:-1]:
            try:
                tsdb_set = tsdb_set.get_set(step)
            except TSDBSetDoesNotExistError:
                TSDBSet.create(self.fs, prefix, step)
                tsdb_set = tsdb_set.get_set(step)

            prefix = os.path.join(prefix, step)

        TSDBSet.create(self.fs, prefix, steps[-1])
        tsdb_set = tsdb_set.get_set(steps[-1])

        return tsdb_set

    def list_vars(self):
        """List TSDBVars in this container."""
        return filter(lambda x: \
                TSDBVar.is_tsdb_var(self.fs, os.path.join(self.path, x)),
                self.fs.listdir(self.path))

    def get_var(self, name, **kwargs):
        """Get named TSDBVar."""
        if not self.vars.has_key(name):
            self.vars[name] = \
                    MONGODBVar(self, os.path.join(self.path, name), **kwargs) 
        return self.vars[name]

    def add_var(self, name, type, step, chunk_mapper, metadata=None):
        prefix = os.path.dirname(name)
        """Create a new TSDBVar in this container."""
        if prefix != '':
            try:
                self.get_set(prefix)
            except TSDBSetDoesNotExistError:
                self.add_set(prefix)

        TSDBVar.create(self.fs, self.path, name, type, step, chunk_mapper, metadata)
        return self.get_var(name)

    def list_aggregates(self):
        """Sorted list of existing aggregates."""

	if not self.agg_list:
            if not TSDBSet.is_tsdb_set(self.fs, os.path.join(self.path, "TSDBAggregates")):
                return [] # XXX should this raise an exception instead?

            def is_aggregate(x):
                return MONGODBVar.is_tsdb_var(self.fs,
                        os.path.join(self.path, "TSDBAggregates", x))

            aggs = filter(is_aggregate,
                self.fs.listdir(os.path.join(self.path, "TSDBAggregates")))

            weighted = [ (calculate_interval(x), x) for x in aggs ]
            weighted.sort()
            self.agg_list = [ x[1] for x in weighted ]

        return self.agg_list

    def get_aggregate(self, name):
        """Get an existing aggregate."""
        name = str(calculate_interval(name))
        if not self.aggs.has_key(name):
            try:
                set = self.get_set("TSDBAggregates")
            except TSDBSetDoesNotExistError:
                raise TSDBAggregateDoesNotExistError(name)

            try:
                self.aggs[name] = set.get_var(name)
            except TSDBVarDoesNotExistError:
                raise TSDBAggregateDoesNotExistError(name)
    
        return self.aggs[name]

    def add_aggregate(self, step, chunk_mapper, aggregates, metadata=None):
        """Add an aggregate at the current level.
        
        aggregates is a list of strings containing the names of the aggregates
        to compute.
        """
        # XXX should add error checking to aggregates?
        if metadata is None:
            metadata = {}

        secs = calculate_interval(step)

        metadata['AGGREGATES'] = aggregates

        if not metadata.has_key('LAST_UPDATE'):
            metadata['LAST_UPDATE'] = 0

        if not metadata.has_key('VALID_RATIO'):
            metadata['VALID_RATIO'] = 0.5

        if not metadata.has_key('HEARTBEAT'):
            metadata['HEARTBEAT'] = 3 * secs

        try:
            aggset = self.get_set("TSDBAggregates")
        except:
            aggset = self.add_set("TSDBAggregates")

        self.agg_list = []

        return aggset.add_var(str(secs), Aggregate, secs, chunk_mapper, metadata)

    @classmethod
    def is_tag(klass, fs, path):
        """Is the current container a TSDB container of type tag?"""
        if fs:
            isdir = fs.isdir
            isfile = fs.isfile
        else:
            isdir = os.path.isdir
            isfile = os.path.isfile


        if isdir(path) and isfile(os.path.join(path,klass.tag)):
            return True
        else:
            return False

class MONGODB(MONGODBBase):
    """A time series data base (TSDB).

    Each TSDB is made up of collection of sets and variables.  Each set or
    variable may contain any arbitrary collection of sets and variables.

    """

    tag = "TSDB"
    metadata_map = {'CHUNK_PREFIXES': list}

    def __init__(self, root, mode="r+" ):
        """Load the TSDB located at ``path``.

            ``mode`` control the mode used by open() 
        """

        MONGODBBase.__init__(self)
        self.path = "/"
        self.mode = mode
        self.fs = get_fs(root, [])
        self.load_metadata()
        self.chunk_prefixes = self.metadata.get('CHUNK_PREFIXES', [])
        if self.chunk_prefixes:
            # the root is listed as the first prefix, don't add it again
            self.fs = get_fs(root, self.chunk_prefixes[1:])

        if self.metadata.has_key('MEMCACHED_URI'):
            self.memcache = True
            try:
                import cmemcache as memcache
            except ImportError:
                try:
                    import memcache
                except:
                    self.memcache = False

            if self.memcache:
                self.memcache = memcache.Client([self.metadata['MEMCACHED_URI']])

    @classmethod
    def is_tsdb(klass, fs, path):
        """Does path contain a TSDB?"""
        return klass.is_tag(fs, path)

    @classmethod 
    def create(klass, path, metadata=None, chunk_prefixes=[]):
        """Create a new TSDB.

            ``chunk_prefixes``
                a list of alternate prefixes to locate chunks
        """

        if metadata is None:
            metadata = {}

        if os.path.exists(os.path.join(path, "TSDB")):
            raise TSDBAlreadyExistsError("database already exists")

        metadata["CREATION_TIME"] = time.time()
        metadata["CHUNK_PREFIXES"] = chunk_prefixes

        if not os.path.exists(path):
            os.mkdir(path)

        fs = get_fs(path, [])
        write_dict(fs, os.path.join("/", klass.tag), metadata)

        return klass(path)

        
class TSDBSet(MONGODBBase):
    """A TSDBSet is used to organize TSDBVars into groups.

    A TSDBSet has metadata but no actual data, it is a container for
    TSDBVars."""

    tag = "TSDBSet"
    metadata_map = {}
    def __init__(self, parent, path, metadata=None):
        """Load the TSDBSet at path."""
        self.path = path
        self.parent = parent
        MONGODBBase.__init__(self)

        if not self.fs.exists(path) or not self.is_tsdb_set(self.fs, path):
            raise TSDBSetDoesNotExistError("TSDBSet does not exist " + path)

        self.load_metadata()

    @classmethod
    def is_tsdb_set(klass, fs, path):
        """Does path contain a TSDBSet?"""
        return klass.is_tag(fs, path)

    @classmethod
    def create(klass, fs, root, name, metadata=None):
        """Create a new TSDBSet with name name rooted at root."""
        if metadata is None:
            metadata = {}

        path = os.path.join(root, name)
        if fs.exists(path):
            raise TSDBNameInUseError("%s already exists at %s" % (name, path))

        fs.makedir(path)
        write_dict(fs, os.path.join(path, klass.tag), metadata)

    def lock(self, block=True):
        """Acquire a write lock.

        Note: NOT IMPLEMENTED."""
        warnings.warn("locking not implemented yet")

    def unlock(self):
        """Release a write lock.

        Note: NOT IMPLEMENTED."""
        warnings.warn("locking not implemented yet")
        
class MONGODBVar(MONGODBBase):
    """A TSDBVar represent a timeseries.

    A TSDBVar is broken into TSDBVarChunks of a size dictated by the
    ChunkMapper in use for a given TSDBVar.

    TSDBVars can be nested arbitrarily, but by convention the only TSDBVars
    inside a TSDBVar are aggregates.  By convetion aggregate sub variables
    will be named n representing the number of seconds in the aggregate.
    For example 20 minute aggregates would be 120."""

    tag = "TSDBVar"
    metadata_map = {'STEP': int, 'TYPE_ID': int, 'MIN_TIMESTAMP': int,
            'MAX_TIMESTAMP': int, 'VERSION': int, 'CHUNK_MAPPER_ID': int,
            'AGGREGATES': list, 'LAST_UPDATE': int, 'VALID_RATIO': float,
            'HEARTBEAT': int}

    def __init__(self, parent, path, use_mmap=False, cache_chunks=False,
            metadata=None):
        """Load the TSDBVar at path."""
        self.parent = parent
        self.path = path
        self.use_mmap = use_mmap
        self.cache_chunks = cache_chunks
        self.chunk_list = []

        MONGODBBase.__init__(self)

        if not self.fs.exists(path) or not self.is_tsdb_var(self.fs, path):
            raise TSDBVarDoesNotExistError("TSDBVar does not exist:" + path)

        self.load_metadata()

        try:
            typeid = self.metadata['TYPE_ID']
            chunk_mapper_id = self.metadata['CHUNK_MAPPER_ID']
        except KeyError:
            raise InvalidMetaData

        self.type = ROW_TYPE_MAP[typeid]
        self.chunk_mapper = CHUNK_MAPPER_MAP[chunk_mapper_id]

        self.chunks = {} # memory resident chunks
        self.size = self.type.size(self.metadata)

    @classmethod
    def is_tsdb_var(klass, fs, path):
        """Does path contain a TSDBVar?"""
        return klass.is_tag(fs, path)

    @classmethod
    def create(klass, fs, root, name, vartype, step, chunk_mapper, metadata=None):
        """Create a new TSDBVar."""
        if metadata is None:
            metadata = {}

        path = os.path.join(root, name)
        if fs.exists(path):
            raise TSDBNameInUseError("%s already exists at %s" % (name, path))

        if type(vartype) == str:
            exec("vartype = tsdb.%s" % vartype)
        elif type(vartype) == int:
            vartype = ROW_TYPE_MAP[vartype]

        metadata["NAME"] = name
        metadata["TYPE_ID"] = vartype.type_id
        metadata["VERSION"] = vartype.version
        metadata["STEP"] = step
        metadata["CREATION_TIME"] = time.time()
        metadata["CHUNK_MAPPER_ID"] = chunk_mapper.chunk_mapper_id

        fs.makedir(path)

        write_dict(fs, os.path.join(path, klass.tag), metadata)

    def _get_aggregate_ancestor(self, agg_name):
        agg_list = self.list_aggregates()
        idx = agg_list.index(agg_name)
        if idx > 0:
            return self.get_aggregate(agg_list[idx-1])
        else:
            return self

    def update_aggregate(self, name, uptime_var=None, min_last_update=0,
            max_rate=None, max_rate_callback=None):
        """Update the named aggreagate."""
        return Aggregator(self.get_aggregate(name),
                          self._get_aggregate_ancestor(name)
                         ).update(uptime_var=uptime_var,
                                  min_last_update=int(min_last_update),
                                  max_rate=max_rate,
                                  max_rate_callback=max_rate_callback)

    def update_all_aggregates(self, **kwargs):
        """Update all aggregates for this TSDBVar."""
        for agg in self.list_aggregates():
            self.update_aggregate(agg, **kwargs)

    def all_chunks(self):
        """Generate a sorted list of all chunks in this TSDBVar."""
        if not self.chunk_list:
            files = self.fs.listdir(self.path)

            self.chunk_list = filter(\
                lambda x: x != self.tag and \
                not self.fs.isdir(os.path.join(self.path,x)), files)

            if not self.chunk_list:
                raise TSDBVarEmpty("no chunks")

            self.chunk_list.sort()

        return self.chunk_list

    def rowsize(self):
        """Returns the size of a row."""
        return self.size #self.type.size(self.metadata)

    def _chunk(self, timestamp, create=False):
        """Retrieve the chunk that contains the given timestamp.

        If create is True then create the chunk if it does not exist.  Chunks
        are memoized in the chunks attribute of TSDBVar.

        _chunk is an internal function and should not be called externally.
        """
        name = self.chunk_mapper.name(timestamp)

        if not self.chunks.has_key(name):
            if not self.cache_chunks:
                for chunk in self.chunks.keys():
                    self.chunks[chunk].close()
                    del self.chunks[chunk]

            try:
                self.chunks[name] = \
                        TSDBVarChunk(self, name, use_mmap=self.use_mmap)
            except TSDBVarChunkDoesNotExistError:
                if create:
                    self.chunks[name] = \
                            TSDBVarChunk.create(self, name,
                                                use_mmap=self.use_mmap)
                    #self.min_timestamp(recalculate=True)
                    #self.max_timestamp(recalculate=True)
                    if self.chunk_list:
                        self.chunk_list.append(name)
                else:
                    raise

        return self.chunks[name]

    def min_timestamp(self, recalculate=False):
        """Finds the minimum possible timestamp for this TSDBVar.

        This is the beginning timestamp of the oldest chunk.  It may not be
        the minimum _valid_ timestamp."""
        if recalculate or not self.metadata.has_key('MIN_TIMESTAMP'):
            chunks = self.all_chunks()

            self.metadata['MIN_TIMESTAMP'] = self.chunk_mapper.begin(chunks[0])
            try:
                self.save_metadata() # XXX good idea?
            except IOError:
                pass

        return self.metadata['MIN_TIMESTAMP']

    def max_timestamp(self, recalculate=False):
        """Finds the maximum possible timestamp for this TSDBVar.

        This is the ending timestamp of the newest chunk. It may not be the
        maximum _valid_ timestamp."""
        if recalculate or not self.metadata.has_key('MAX_TIMESTAMP'):
            chunks = self.all_chunks()

            self.metadata['MAX_TIMESTAMP'] = self.chunk_mapper.end(chunks[-1])
            try:
                self.save_metadata() # XXX good idea?
            except IOError:
                pass

        return self.metadata['MAX_TIMESTAMP']

    def min_valid_timestamp(self):
        """Finds the timestamp of the minimum valid row."""
        # XXX fails if the oldest chunk is all invalid
        ts = self.min_timestamp()
        while True:
            try:
                chunk = self._chunk(ts)
            except TSDBVarChunkDoesNotExistError:
                raise TSDBVarNoValidData("no valid data found in %s" % (self.path,))

            row = chunk.read_row(ts)
            if row.flags & ROW_VALID:
                return row.timestamp

            ts += self.metadata['STEP']

    def max_valid_timestamp(self):
        """Finds the timestamp of the maximum valid row."""
        ts = self.max_timestamp()
        while True:
            try:
                chunk = self._chunk(ts)
            except TSDBVarChunkDoesNotExistError:
                raise TSDBVarNoValidData("no valid data found in %s" % (self.path,))
            row = chunk.read_row(ts)
            if row.flags & ROW_VALID:
                return row.timestamp

            ts -= self.metadata['STEP']

    def get(self, timestamp):
        """Get the TSDBRow located at timestamp.

        .. note::

            The timestamp of the returned row may be different from the
            timestamp requested.  This is due to the fact that the application
            storing the row used an actual timestamp but the query refers to
            the slot in which the timestamp argument falls.

        .. note::

            If an invalid row is fetched, the timestamp is set to the
            requested timestamp since an invalid row has a timestamp of 0.

        .. note::

            If the chunk does not exist it is created with all zeros and thus
            an invalid row is returned.  For the current use case creating the
            chunk is acceptable as the datasets are not expected to be sparse.
        """
        slot = calculate_slot(timestamp, self.metadata['STEP'])
        try:
            min_slot = calculate_slot(self.min_timestamp(), self.metadata['STEP'])
            if slot < min_slot:
                raise TSDBVarRangeError(
                        "%d is less than the minimum slot %d" % (timestamp, min_slot))

            max_slot = calculate_slot(self.max_timestamp(), self.metadata['STEP']) + self.metadata['STEP'] - 1
            if slot > max_slot:
                raise TSDBVarRangeError(
                        "%d is greater than the maximum slot %d" % (timestamp, max_slot))

        except TSDBVarEmpty:
            raise TSDBVarRangeError(timestamp)

        try:
            chunk = self._chunk(timestamp)
            val = chunk.read_row(timestamp)
        except TSDBVarChunkDoesNotExistError:
            val = self.type.get_invalid_row()

        if not val.flags & ROW_VALID:
            # if row isn't valid the timestamp is 0
            # set the timestamp to the slot timestamp instead
            val.timestamp = timestamp

        return val

    def select(self, begin=None, end=None, flags=None):
        """Select data based on timestamp or flags.

        None is interpreted as "don't care".  The timestamp ranges are
        inclusive to the recorded timestamp of the row, not to the entire slot
        that the row represents.

        .. example::

            v = TSDB.get_var('foo')

            # all data for this var, valid or not
            v.select()

            # all data with a timestamp equal to or greater than 10000
            v.select(begin=10000)

            # all data with a timestamp equal to or less than 10000
            v.select(end=10000)

            # all data in the range of timestamps 10000 to 20000 inclusive
            v.select(begin=10000, end=20000)

            # all valid data
            v.select(flags=ROW_VALID)
        """

        if begin is None:
            begin = self.min_timestamp()
        else:
            begin = int(begin)
            if begin < self.min_timestamp():
                begin = self.min_timestamp()

        if end is None:
            end = self.max_timestamp()
        else:
            end = int(end)
            if end > self.max_timestamp():
                end = self.max_timestamp()

        if flags is not None:
            flags = int(flags)

        def select_generator(var, begin, end, flags):
            current = calculate_slot(begin, self.metadata['STEP'])
            max_ts = self.max_timestamp()

            while current <= end:
                try:
                    row = var.get(current)
                except TSDBVarRangeError:
                    # looking for data beyond the end of recorded data so stop.
                    if current > max_ts:
                        raise StopIteration

                if row.timestamp > end:
                    break

                if not flags or row.flags & flags == flags:
                    yield row

                current += var.metadata['STEP']

            raise StopIteration

        return select_generator(self, begin, end, flags)

    def insert(self, data):
        """Insert data.  

        Data should be a subclass of TSDBRow."""
        chunk = self._chunk(data.timestamp, create=True)

        max = self.metadata.get('MAX_TIMESTAMP')
        if max is None or max < data.timestamp:
            self.metadata['MAX_TIMESTAMP'] = data.timestamp

        min = self.metadata.get('MIN_TIMESTAMP')
        if min is None or min > data.timestamp:
            self.metadata['MIN_TIMESTAMP'] = data.timestamp

        return chunk.write_row(data)

    def flush(self):
        """Flush all the chunks for this TSDBVar to disk."""
        for chunk in self.chunks:
            self.chunks[chunk].flush()
        self.save_metadata()

    def close(self):
        """Close this TSDBVar."""
        self.flush()
        for chunk in self.chunks:
            self.chunks[chunk].close()

    def lock(self, block=True):
        """Acquire a write lock.

        Note: NOT IMPLEMENTED."""
        warnings.warn("locking not implemented yet")

    def unlock(self):
        """Release a write lock.

        Note: NOT IMPLEMENTED."""
        warnings.warn("locking not implemented yet")
        
# ====

class Aggregator(object):
    """Calculate Aggregates.
    
    XXX ultimately there should be an aggregator for each class of TSDBVars.
    This one is really targeted at Counters and should become
    CounterAggregator.  It should be possible to generalize some of this
    functionality into a base Aggregator class though."""

    def __init__(self, agg, ancestor):
        self.agg = agg
        self.ancestor = ancestor

    def _empty_row(self, var, timestamp):
        aggs = {}
        for a in var.metadata['AGGREGATES']:
            aggs[a] = 0

        return var.type(timestamp, 0, **aggs)

    def _increase_delta(self, var, timestamp, value):
        if var.type != Aggregate:
            raise TSDBVarIsNotAggregate("not an Aggregate")

        try:
            row = var.get(timestamp)
        except (TSDBVarEmpty, TSDBVarRangeError):
            row = self._empty_row(var, timestamp)

        row.delta += value
        row.flags |= ROW_VALID
        var.insert(row)

    def update(self, uptime_var=None, min_last_update=None, max_rate=None,
            max_rate_callback=None):
        """Update an aggregate.

        ``uptime_var``
            A monotonically increasing variable that shows how long the system
            was up at a given time.  Usually it is of type TimeTicks.
        ``min_last_update``
            When updating this aggregate go back no further than
            `min_last_update`.
        ``max_rate``
            if rate > max_rate then the row in the computed aggregate is set
            to invalid.  if ``max_rate_callback`` is not None then
            ``max_rate_callback`` to notify the upper level application of
            potentially bad data. 
        ``max_rate_callback``
            a function that takes five arguments:
                ``ancestor``
                    a TSDBVar which is the ancestor of the aggregate being computed
                ``agg``
                    a TSDBVar which is the aggregate being computed
                ``rate``
                    the computed rate
                ``prev``
                    the earlier data point
                ``curr``
                    the current data point
        """
        try:
            if self.ancestor.type == Aggregate:
                self.update_from_aggregate(min_last_update=min_last_update,
                        max_rate=max_rate, max_rate_callback=max_rate_callback)
            else:
                self.update_from_raw_data(uptime_var=uptime_var,
                        min_last_update=min_last_update, max_rate=max_rate,
                        max_rate_callback=max_rate_callback)
        except TSDBVarEmpty:
            # not enough data to build aggregate
            pass

    def update_from_raw_data(self, uptime_var=None, min_last_update=None,
            max_rate=None, max_rate_callback=None):
        """Update this aggregate from raw data.

        The first aggregate MUST have the same step as the raw data.  (This
        the only aggregate with a raw data ancestor.)

        Scan all of the new data and bin it in the appropriate place.  At
        either end a bin may have only partial data.  Detect and handle
        rollovers.  We process all data with a timestamp >= begin and
        with ROW_VALID set.

        Diagram of the relationship between the prev and curr elements in the
        main loop::

            prev_slot          curr_slot
            |                  |
            v                  v
            +----------+       +----------+
            |   prev   | . . . |   curr   |
            +----------+       +----------+
                ^                   ^
                |                   |
                prev.timestamp      curr.timestamp
                |                   |
                |<---- delta_t ---->|
        """
        step = self.agg.metadata['STEP']
        assert self.ancestor.metadata['STEP'] == step

        last_update = self.agg.metadata['LAST_UPDATE']
        if min_last_update and min_last_update > last_update:
            last_update = min_last_update

        min_ts = self.ancestor.min_timestamp()
        if min_ts > last_update:
            last_update = min_ts
            self.agg.metadata['LAST_UPDATE'] = last_update
       
        prev = self.ancestor.get(last_update)
        
        print sys.exit()

        # XXX this only works for Counter types right now
        for curr in self.ancestor.select(begin=last_update+step,
                flags=ROW_VALID):
            # Pulling all data since the last update - this starts 
            # at one past the last update and pulls all the data
            # since then - this SHOULD just be one.
            # will need to keep track of when last update happened
            # and then when all the updates occur. XXX(mmg)
            # these are raw values and NOT rates
            delta_t = curr.timestamp - prev.timestamp
            delta_v = curr.value - prev.value
            # These should give increments of 30
            prev_slot = (prev.timestamp / step) * step
            curr_slot = (curr.timestamp / step) * step

            # tests for edge cases: rollover, invalid, large gaps in data
            # not sure how to properly invalidate individual rows

            # This is edge case code XXX(mmg)
            # have negative delta - rare with 32 bit counters
            if self.ancestor.type.can_rollover and delta_v < 0:
                if uptime_var is not None:
                    try:
                        delta_uptime = uptime_var.get(curr.timestamp).value - \
                            uptime_var.get(prev.timestamp).value
                        if delta_uptime < 0:
                            # this is a reset
                            delta_v = curr.value
                        else:
                            delta_v = self.ancestor.type.rollover(delta_v)
                    except TSDBVarRangeError:
                        # uptime var no help, assume reset
                        delta_v = curr.value
                else:
                    # no uptime var, assume reset
                    delta_v = curr.value

            # XXX(mmg) back to the relevant code
            # delta_t should be 30 seconds in a perfect world but....
            # the rate will be the same even if we missed a step
            # if we missed time "1" we still counted from "0" to "2"
            rate = float(delta_v) / float(delta_t)

            # XXX(mmg) this is sanity checking the rate
            if max_rate and rate > max_rate:
                if max_rate_callback:
                    max_rate_callback(self.ancestor, self.agg, rate, prev, curr)

                prev = curr
                continue

            assert delta_v >= 0

            # allocate a portion of this data to a given bin
            # XXX(mmg) - generally when we have a missed collection - when we
            # have t0 and t2 and missing t1
            # this is looking to see which bin it should fall in if we
            # are missing a value - or just having the collection
            # being slightly "off"
            prev_frac = int( floor(
                        delta_v * (prev_slot+step - prev.timestamp)
                        / float(delta_t)
                    ))

            curr_frac = int( ceil(
                        delta_v * (curr.timestamp - curr_slot)
                        / float(delta_t)
                    ))

            # XXX(mmg) if we have missed more than heartbeat seconds
            # in a row, then we are going to fill it in with "invalid"
            # values - comes from RRDtool, Jon not sure if he likes it.
            # heartbeat is a defined metadata value
            if delta_t > self.agg.metadata['HEARTBEAT']:
                for slot in range(prev_slot, curr_slot, step):
                    try:
                        row = self.agg.get(slot)
                    except TSDBVarRangeError:
                        row = self._empty_row(self.agg, slot)

                    row.invalidate()
                    self.agg.insert(row)
                # now write current values for sometime, after the fill
                # has been written.
                self._increase_delta(self.agg, curr_slot, curr_frac)
                prev = curr
                continue

            # XXX(mmg) passed the sanity check, now update the actual slots
            # this is writing the current values to the correct bins.
            # trying to fill slot 30, poll is at 32 - 2 seconds go to 
            # bin 30 and the other 28 to slot 60
            self._increase_delta(self.agg, curr_slot, curr_frac)
            self._increase_delta(self.agg, prev_slot, prev_frac)
            # !!! ._increase_delta is where the writes happen.
            # this is really just incrementing a value - we can
            # use 

            # XXX(mmg) if we have some left, try to backfill
            # less than heartbeat but greater that general collection rate.
            # find other places to backfill.
            if curr_frac + prev_frac != delta_v:
                missed_slots = range(prev_slot+step, curr_slot, step)
                if not missed_slots:
                    missed_slots = [curr_slot]
                missed = delta_v - (curr_frac + prev_frac)
                if missed > 0:
                    missed_frac = missed / len(missed_slots)
                    missed_rem = missed % (missed_frac * len(missed_slots))
                    for slot in missed_slots:
                        self._increase_delta(self.agg, slot, missed_frac)

                    # distribute the remainder
                    for i in range(missed_rem):
                        self._increase_delta(self.agg, missed_slots[i], 1)

            prev = curr

        # XXX(mmg) delta.min.max.average is every row
        for row in self.agg.select(begin=last_update, flags=ROW_VALID):
            if row.delta != 0:
                row.average = float(row.delta) / step
            else:
                row.average = 0.0
            self.agg.insert(row) # this is an upsert XXX(mmg)

        self.agg.metadata['LAST_UPDATE'] = prev.timestamp
        self.agg.flush()

    def update_from_aggregate(self, min_last_update=None, max_rate=None,
            max_rate_callback=None):
        """Update this aggregate from another aggregate."""
        # LAST_UPDATE points to the last step updated

        step = self.agg.metadata['STEP']
        steps_needed = step // self.ancestor.metadata['STEP']
        # XXX what to do if our step isn't divisible by ancestor steps?

        last_update = self.agg.metadata['LAST_UPDATE'] + \
                        self.ancestor.metadata['STEP']

        if min_last_update and min_last_update > last_update:
            last_update = min_last_update

        data = self.ancestor.select(
                begin=last_update,
                end=self.ancestor.max_valid_timestamp())

        # get all timestamps since the last update
        # fill as many bins as possible
        work = list(itertools.islice(data, 0, steps_needed))

        slot = None
        while len(work) == steps_needed:
            slot = ((work[0].timestamp / step) * step) #+ step

#            assert work[-1].timestamp == slot

            valid = 0
            row = Aggregate(slot, ROW_VALID, delta=0, average=None,
                    min=None, max=None)

            for datum in work:
                if datum.flags & ROW_VALID:
                    valid += 1
                    row.delta += datum.delta
    
                    if isNaN(row.min) or datum.delta < row.min:
                        row.min = datum.delta
    
                    if isNaN(row.max) or datum.delta > row.max:
                        row.max = datum.delta
            row.average = row.delta / float(step)
            valid_ratio = float(valid)/float(len(work))

            if valid_ratio < self.agg.metadata['VALID_RATIO']:
                row.invalidate()

            self.agg.insert(row)

            work = list(itertools.islice(data, 0, steps_needed))
       
        if slot is not None:
            self.agg.metadata['LAST_UPDATE'] = slot
            self.agg.flush()
