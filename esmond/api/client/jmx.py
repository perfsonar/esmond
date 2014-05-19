"""
Client to fetch cassandra/os information from MX4J

See:

http://mx4j.sourceforge.net/
http://wiki.apache.org/cassandra/Operations#Monitoring_with_MX4J
"""

import urllib
import warnings
import xml.etree.ElementTree as ET

import requests

class CassandraJMXException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class CassandraJMXWarning(Warning): pass

class CassandraJMX(object):
    def __init__(self, url='http://localhost:8081'):
        self.url = url.rstrip('/')
        # - JMX variables
        # Activity/number of ops
        self.jmx_readstage = 'org.apache.cassandra.request:type=ReadStage'
        self.jmx_mutationstage = 'org.apache.cassandra.request:type=MutationStage'
        self.jmx_gossipstage = 'org.apache.cassandra.internal:type=GossipStage'
        # Latency
        self.jmx_storageproxy = 'org.apache.cassandra.db:type=StorageProxy'
        # Memory
        self.jmx_memory = 'java.lang:type=Memory'
        # Java garbage collection
        self.jmx_garbage = 'java.lang:type=GarbageCollector,name=ConcurrentMarkSweep'
        # Operating system information
        self.jmx_os = 'java.lang:type=OperatingSystem'
        # Compaction information
        self.jmx_compaction = 'org.apache.cassandra.db:type=CompactionManager'

    def _make_request(self, var):
        qs = dict(objectname=var, template='identity')
        url = '{0}/mbean?{1}'.format(self.url, urllib.urlencode(qs))
        r = requests.get(url)
        if r.status_code != 200:
            warnings.warn('Bad request: {0} got return code: {1}'.format(url, r.status_code), 
                CassandraJMXWarning, stacklevel=2)
        return r.content

    def _get_attribute_value(self, root, name):
        for i in root.iterfind('Attribute[@name="{0}"]'.format(name)):
            return i.attrib['value']

    def _fetch_value(self, jmx_var, attr):
        root = ET.fromstring(self._make_request(jmx_var))
        val = self._get_attribute_value(root, attr)
        try:
            val = int(val)
        except ValueError:
            pass
        return val

    def _get_contents_dict(self, s):
        d = {}
        for i in s[s.find('contents=')+10:-2].split(','):
            k,v = i.strip().split('=')
            d[k] = int(v)
        return d

    # Memory stats

    def get_heap_memory(self):
        value = self._fetch_value(self.jmx_memory, 'HeapMemoryUsage')
        return self._get_contents_dict(value)

    def get_non_heap_memory(self):
        value = self._fetch_value(self.jmx_memory, 'NonHeapMemoryUsage')
        return self._get_contents_dict(value)

    # Latency stats

    def get_read_latency(self):
        return self._fetch_value(self.jmx_storageproxy, 'RecentReadLatencyMicros')

    def get_write_latency(self):
        return self._fetch_value(self.jmx_storageproxy, 'RecentWriteLatencyMicros')

    def get_range_latency(self):
        return self._fetch_value(self.jmx_storageproxy, 'RecentRangeLatencyMicros')

    # Java garbage collector stats

    def get_gc_count(self):
        return self._fetch_value(self.jmx_garbage, 'CollectionCount')

    def get_gc_time(self):
        return self._fetch_value(self.jmx_garbage, 'CollectionTime')

    # Read/write/gossip operations

    def get_read_active(self):
        return self._fetch_value(self.jmx_readstage, 'ActiveCount')

    def get_read_pending(self):
        return self._fetch_value(self.jmx_readstage, 'PendingTasks')

    def get_read_completed(self):
        return self._fetch_value(self.jmx_readstage, 'CompletedTasks')

    def get_write_active(self):
        return self._fetch_value(self.jmx_mutationstage, 'ActiveCount')

    def get_write_pending(self):
        return self._fetch_value(self.jmx_mutationstage, 'PendingTasks')

    def get_write_completed(self):
        return self._fetch_value(self.jmx_mutationstage, 'CompletedTasks')

    def get_gossip_active(self):
        return self._fetch_value(self.jmx_gossipstage, 'ActiveCount')

    def get_gossip_pending(self):
        return self._fetch_value(self.jmx_gossipstage, 'PendingTasks')

    def get_gossip_completed(self):
        return self._fetch_value(self.jmx_gossipstage, 'CompletedTasks')

    # OS information

    def get_os_load(self):
        return self._fetch_value(self.jmx_os, 'SystemLoadAverage')

    def get_os_free_memory(self):
        return self._fetch_value(self.jmx_os, 'FreePhysicalMemorySize')

    def get_os_free_swap(self):
        return self._fetch_value(self.jmx_os, 'FreeSwapSpaceSize')

    def get_os_committed_virtual_memory(self):
        return self._fetch_value(self.jmx_os, 'CommittedVirtualMemorySize')

    # Compaction information

    def get_compaction_pending(self):
        return self._fetch_value(self.jmx_compaction, 'PendingTasks')

    def get_compaction_complete(self):
        return self._fetch_value(self.jmx_compaction, 'CompletedTasks')

available_tests = filter(lambda x: x.startswith('get_'), dir(CassandraJMX('')))
