import sys
import time

from graphite.node import BranchNode, LeafNode
from graphite.util import is_pattern
from graphite.intervals import Interval, IntervalSet

from esmond.api import EsmondAPI, ClientError
from esmond.util import remove_metachars

class EsmondFinder:
    def __init__(self, uri, username=None, password=None, debug=True):
        self.uri = uri
        self.username = username
        self.password = password
        self.debug = debug

        self.client = EsmondAPI(uri, debug=debug)
        if username and password:
            self.auth_client = EsmondAPI(uri, debug=debug,
                    username=username, password=password)
        else:
            self.auth_client = self.client

    def get(self, metric_path):
        pass

    def find_nodes(self, query, request=None):
        # XXX --- revisit this code
        #print query
        #print query.pattern
        pattern = remove_metachars(query.pattern)
        parts = pattern.split('.')
        if is_pattern(parts[-1]):
            path = '/'.join([p.replace('@', '.') for p in parts[:-1]])
            metric_path = '.'.join(parts[:-1])
            pattern = parts[-1]
        else:
            path = '/'.join([p.replace('@', '.') for p in parts])
            metric_path = '.'.join(parts)
            pattern = None

        if request.user and request.user.is_authenticated():
            print "WE GOT ONE!!!"
            client = self.auth_client
        else:
            client = self.client

        #print ">>> path", path
        r = client.get(path)

        if type(r) == list:
            # XXX hack -- if we get multiple results use the most recent
            r = r[-1]

        if r.has_key('children'):
            for child in r['children']:
                if path != '':
                    cpath = metric_path + '.'
                else:
                    cpath = ''

                label = None
                if child.has_key('name'):
                    if path.endswith('interface') and \
                            (not child.has_key('descr')
                                    or child['descr'] == ''):
                        if not 'dev-alu' in path:
                            continue
                    name = child['name']
                    if child.has_key('descr'):
                        label = "%s %s" % (name, child['descr'])
                        label = label.replace('"','')
                else:
                    name = parts[-1]

                cpath += name.replace('.','@')
                # XXX KLUDGE! need to revist various path translation crap
                if 'error/' in cpath:
                    cpath = cpath.replace('error/', 'error.')
                if 'discard/' in cpath:
                    cpath = cpath.replace('discard/', 'discard.')

                if child['leaf']:
                    #print "CHILD", child, cpath
                    reader = EsmondReader(self.uri, cpath, query.startTime,
                            query.endTime, username=self.username,
                            password=self.password, debug=self.debug)
                    yield EsmondLeaf(cpath, reader, client=client,
                            name=name, label=label)
                else:
                    yield EsmondBranch(cpath, name=name, label=label)
        else:
            reader = EsmondReader(self.uri, path, query.startTime,
                    query.endTime, username=self.username, 
                    password=self.password, debug=self.debug)

            yield EsmondLeaf(path, reader, client=client)

    def searchable(self):
        return 1

    def search(self, patterns):
        #print "SEARCHING"
        data = []
        for pattern in patterns:
            data.extend(self.client.get("?interface_descr=%s" % pattern))

        r = []
        for d in data:
            for child in d["children"]:
                r.append( dict(
                    label="%s %s %s" % (child["uri"].split("/")[-1], d["ifDescr"], d["ifAlias"]),
                    metric_path=child["uri"].replace("/snmp/", "").replace(".", "@").replace("/", ".") 
                    ))

        return r

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
        self.client = kwargs['client']
        del kwargs['client']
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
    def __init__(self, uri, metric_path, start_time, end_time, username=None,
            password=None, debug=False):
        self.metric_path = metric_path
        self.start_time = start_time
        self.end_time = end_time
        self.username = username
        self.password = password
        self.debug = debug

        self.client = EsmondAPI(uri, debug=debug)
        if username and password:
            self.auth_client = EsmondAPI(uri, debug=debug,
                    username=username, password=password)
        else:
            self.auth_client = self.client

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
        #path = self.metric_path.replace('.', '/')
        path = self.metric_path.replace('@', '.')
        q = self.client.build_query(self.start_time, self.end_time)
        if self.step:
            q += "&calc=%d" % self.step
        
        t0 = time.time()
        try:
            r = self.client.get("%s?%s" % (path, q))
        except ClientError:
            return []
        print >>sys.stderr, "timing %f %s?%s" % (time.time() - t0, path, q)

        def transform_data(data, scalar=1):
            d = []
            for x in data:
                if x[1]:
                    d.append(x[1] * scalar)
                else:
                    d.append(x[1])
            return d
#XXX This is not the appropriate place to determine bit/byte scaling but
# it works in the short term. -David Mitchell
        if 'all' in path or 'error' in path or 'discard' in path:
            data = transform_data(r['data'])
        else:
            data = transform_data(r['data'], scalar=8)
        try:
            agg = int(r['agg'])
        except KeyError:
            agg = int(r['calc'])
       
        # if we don't have enough data pad with Nones
        expected_len = int(((end_time - start_time) / agg)-1)
        if expected_len > len(data):
            nones = [None,] * (expected_len - len(data))
            data = nones + list(data)

        return ((int(r['begin_time']), int(r['end_time']), agg), data)


