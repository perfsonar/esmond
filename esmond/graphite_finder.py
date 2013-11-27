import sys
import time

from graphite.node import BranchNode, LeafNode
from graphite.util import is_pattern
from graphite.intervals import Interval, IntervalSet

from esmond.api.client.snmp import ApiConnect, ApiFilters
from esmond.api.client.timeseries import GetRawData, GetBaseRate
from esmond.api.client.util import atencode, atdecode

class EsmondFinder:
    """Finder to integrate Graphite with esmond.

    Only the SNMP section of Esmond is browseable, so that is the only part 
    which is exposed in a browseable way. However, there is a facility to 
    access raw timeseries data.

    Unless the first segment of the query is 'timeseries' data will be retrieved
    from the SNMP interface of esmond.

    If the first segment of query is 'timeseries', the data the query
    looks at the raw timeseries data. Which part of the data depends on the second
    segment of the query.  If it is 'raw' then the raw data is queried, if it is
    'baserate' the BaseRate data is queried. Although these are not broweseable via
    the Graphite interface, they can be used in as the target argument to a render, 
    for example:

        http://localhost:8000/render/?target=timeseries.raw.foo.bar.baz.30000

    """
    def __init__(self, uri, username=None, apikey=None, debug=True):
        self.uri = uri
        self.username = username
        self.apikey = apikey
        self.debug = debug

        filters = ApiFilters()

        if debug:
            filters.verbose = 2
        else:
            filters.verbose = 0

        self.client = ApiConnect(uri, filters=filters)

    def _encode_path(self, p):
        return ".".join(map(lambda x: atencode(x, graphite=True), p))

    def find_nodes(self, query, request=None):
        parts = query.pattern.split(".")


        if parts[-1] == "*":
            parts = parts[:-1]

        if len(parts) == 0:
            for child in self.client.children:
                yield EsmondBranch(child, name=child, label=child)
        elif parts[0] == "timeseries":
            query_type = parts[1]
            freq = parts[-1]
            path = map(atdecode, parts[2:-1])

            if query_type == "raw":
                endpoint = GetRawData(self.uri, path, freq,
                    {"begin": query.startTime*1000, "end": query.endTime*1000})
            elif query_type == "baserate":
                endpoint = GetBaseRate(self.uri, path, freq,
                    {"begin": query.startTime*1000, "end": query.endTime*1000})

            reader = EsmondReader(endpoint, query.startTime, query.endTime, debug=self.debug, timeseries=True)
            yield EsmondLeaf(".".join(parts), reader, name="", label="")
        else:
            path = map(atdecode, parts)
            obj = self.client.get_child(path)

            if obj.leaf:
                leaf_path = self._encode_path(path)
                if self.debug:
                    print "[LEAF SIBLING {0}]".format(leaf_path)

                reader = EsmondReader(obj, query.startTime, query.endTime, debug=self.debug)
                yield EsmondLeaf(leaf_path, reader, name=obj.name, label=obj.name)
            else:
                for child in obj.children:
                    if self.debug:
                        print "[CHILD {0}]".format(child)

                    child_path = self._encode_path(path + [child['name']])
                    if child.get("leaf"):
                        if self.debug:
                            print "[LEAF CHILD {0}]".format(child)
                        endpoint = obj.get_endpoint(child.get("name"))
                        reader = EsmondReader(endpoint, query.startTime, query.endTime, debug=self.debug)
                        yield EsmondLeaf(child_path, reader, name=child['name'], label=child['label'])
                    else:
                        yield EsmondBranch(child_path, name=child['name'], label=child['label'])

class EsmondBranch(BranchNode):
    def __init__(self, *args, **kwargs):
        name = None
        label = None
        if kwargs.has_key('name'):
            name = kwargs['name']
            del kwargs['name']
        if kwargs.has_key('label'):
            label = kwargs['label']
            del kwargs['label']
        BranchNode.__init__(self, *args, **kwargs)
        if name:
            self.name = name
        if label:
            self.label = label
        # XXX workaround for renaming in graphite
        self.metric_path = self.path


    def __str__(self):
        return "<EsmondBranch: %s %s>" % (self.name, self.metric_path)


class EsmondLeaf(LeafNode):
    def __init__(self, *args, **kwargs):
        name = None
        label = None
        if kwargs.has_key('name'):
            name = kwargs['name']
            del kwargs['name']
        if kwargs.has_key('label'):
            label = kwargs['label']
            del kwargs['label']

        LeafNode.__init__(self, *args, **kwargs)
        if name:
            self.name = name
        if label:
            self.label = label
        self.metric_path = self.path

    def __str__(self):
        return "<EsmondLeaf: %s %s>" % (self.name, self.metric_path)

class EsmondReader(object):
    """Reader for esmond data.

    If the data is from the raw timeseries section of esmond, then `timeseries`
    should be set to True. Raw timeseries data will not be multiplied by 8."""

    def __init__(self, endpoint, start_time, end_time, debug=False, timeseries=False):
        self.endpoint = endpoint
        self.start_time = start_time
        self.end_time = end_time
        self.timeseries = timeseries
        self.debug = debug

        if start_time and end_time:
            if end_time - start_time > 6*30*24*3600:
                self.step = 86400
            elif end_time - start_time > 30*24*3600:
                self.step = 3600
            elif end_time - start_time > 24*3600:
                self.step = 300
            else:
                self.step = None

            self.intervals = IntervalSet([Interval(start_time, end_time)])
        else:
            self.intervals = IntervalSet([Interval(0, 2**32 -1)])

    def get_intervals(self):
        return self.intervals

    def fetch(self, start_time, end_time):
        if self.timeseries:
            payload = self.endpoint.get_data()
        else:
            payload = self.endpoint.get_data(begin=start_time, end=end_time)

        data = []
        for d in payload.data:
            # preserve None
            if d.val and not self.timeseries:
                data.append(d.val*8)
            else:
                data.append(d.val)

        agg = int(payload.agg)
        expected_len = int(((end_time - start_time) / agg)-1)
        if expected_len > len(data):
            nones = [None] * (expected_len - len(data))
            data = data + nones

        if len(payload.data) == 0:
            begin = start_time
            end = end_time
        else:
            if self.timeseries:
                begin = payload.data[0].ts / 1000
                end = payload.data[-1].ts / 1000
                agg = agg / 1000
            else:
                begin = payload.data[0].ts_epoch
                end = payload.data[-1].ts_epoch

        r = ((begin, end, agg), data)

        if self.debug:
            print "[DATA begin: {0} end: {1} step: {2} size: {3}]".format(r[0][0], r[0][1], r[0][2], len(r[1]))

        return r
