import sys
import time

from graphite.storage import Branch, Leaf, is_pattern
from esxsnmp.api import ESxSNMPAPI, ClientError
from esxsnmp.util import remove_metachars

class Store:
    def __init__(self, uri, username=None, password=None, debug=False):
        self.uri = uri

        self.client = ESxSNMPAPI(uri, debug=debug)
        if username and password:
            self.auth_client = ESxSNMPAPI(uri, debug=debug,
                    username=username, password=password)
        else:
            self.auth_client = self.client

    def get(self, metric_path):
        pass

    def find(self, query, request):
        # XXX --- revisit this code
        query = remove_metachars(query)
        parts = query.split('.')
        if is_pattern(parts[-1]):
            path = '/'.join([p.replace('@', '.') for p in parts[:-1]])
            metric_path = '.'.join(parts[:-1])
            pattern = parts[-1]
        else:
            path = '/'.join([p.replace('@', '.') for p in parts])
            metric_path = '.'.join(parts)
            pattern = None


        if request and request.user and request.user.is_authenticated():
            client = self.auth_client
        else:
            client = self.client

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
                    yield ESxSNMPLeaf(cpath, cpath, client=client,
                            name=name, label=label)
                else:
                    yield ESxSNMPBranch(cpath, cpath, name=name, label=label)
        else:
            yield ESxSNMPLeaf(path, path, client=client)

    def searchable(self):
        return 1

    def search(self, patterns):
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

class ESxSNMPBranch(Branch):
    def __init__(self, *args, **kwargs):
        name = None
        label = None
        if kwargs.has_key('name'):
            name = kwargs['name']
            del kwargs['name']
        if kwargs.has_key('label'):
            label = kwargs['label']
            del kwargs['label']
        Branch.__init__(self, *args, **kwargs)
        if name:
            self.name = name
        if label:
            self.label = label


    def __str__(self):
        return "<ESxSNMPBranch: %s %s>" % (self.name, self.metric_path)


class ESxSNMPLeaf(Leaf):
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

        Leaf.__init__(self, *args, **kwargs)
        if name:
            self.name = name
        if label:
            self.label = label

    def __str__(self):
        return "<ESxSNMPLeaf: %s %s>" % (self.name, self.metric_path)

    def fetch(self, start_time, end_time):
        #path = self.metric_path.replace('.', '/')
        path = self.metric_path.replace('@', '.')
        q = self.client.build_query(start_time, end_time)
        if end_time - start_time > 6*30*24*3600:
            q += '&calc=86400'
        elif end_time - start_time > 30*24*3600:
            q += '&calc=3600'
        elif end_time - start_time > 24*3600:
            q += '&calc=300'
        
        t0 = time.time()
        try:
            r = self.client.get("%s?%s" % (path, q))
        except ClientError:
            return []
        print >>sys.stderr, "timing %f %s?%s" % (time.time() - t0, path, q)

        def transform_data(data):
            d = []
            for x in data:
                if x[1]:
                    d.append(x[1] * 8)
                else:
                    d.append(x[1])
            return d
        data = transform_data(r['data'])
        try:
            agg = int(r['agg'])
        except KeyError:
            agg = int(r['calc'])
       
        # if we don't have enough data pad with Nones
        expected_len = int(((end_time - start_time) / agg)-1)
        if expected_len > len(data):
            nones = [None,] * (expected_len - len(data))
            data = nones + list(data)

        return (int(r['begin_time']), int(r['end_time']), agg), data


