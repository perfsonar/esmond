import sys

from graphite.storage import Branch, Leaf, is_pattern
from esxsnmp.api import ESxSNMPAPI, ClientError
from esxsnmp.util import remove_metachars

class Store:
    def __init__(self, uri):
        self.uri = uri

        self.client = ESxSNMPAPI(uri, debug=True)

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

        print >>sys.stderr, "path: " + path
        print >>sys.stderr, "patt: " + str(pattern)

        r = self.client.get(path)

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
                        continue
                    name = child['name']
                    if child.has_key('descr'):
                        if ':hide:' in child['descr'] and  \
                                not request.user.is_authenticated():
                            continue
                        label = "%s %s" % (name, child['descr'])
                else:
                    name = parts[-1]

                cpath += name.replace('.','@')

                print >>sys.stderr, "foo ", cpath, label

                if child['leaf']:
                    yield ESxSNMPLeaf(cpath, cpath, client=self.client,
                            name=name, label=label)
                else:
                    yield ESxSNMPBranch(cpath, cpath, name=name, label=label)
        else:
            print >>sys.stderr, "leaf2: " + path
            yield ESxSNMPLeaf(path, path, client=self.client)


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
        print >>sys.stderr, "fpath: %s" % path
        q = self.client.build_query(start_time, end_time)
        try:
            r = self.client.get("%s?%s" % (path, q))
        except ClientError:
            return []
        data = [x[1] for x in r['data']]
        return (r['begin_time'], r['end_time'], r['agg']), data


