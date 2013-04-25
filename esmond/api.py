import sys
import time
import base64
import httplib2
import urllib
try:
    import json
except ImportError:
    import simplejson as json

#from esmond.util import remove_metachars

def remove_metachars(name):
    """remove troublesome metacharacters from ifDescr"""
    for (char,repl) in (("/", "_"), (" ", "_")):
        name = name.replace(char, repl)
    return name

class ClientError(Exception):
    pass

class EsmondAPI(object):
    def __init__(self, url, debug=False, username=None, password=None):
        if url[-1] == '/':
            url = url[:-1]
        self.url = url
        self.debug = debug
        self.headers = {}


        if username and password:
            # httplib only sends the authorization header on demand
            # esdb doesn't ask for authorization but will use it if it is provided
            self.headers['authorization'] = "Basic " + \
                    base64.b64encode("%s:%s" % (username, password)).strip()

    def _deserialize(self, data):
        try:
            return json.loads(data)
        except ValueError, e:
            if self.debug:
                print >>sys.stderr, "BOGUS DATA"
                print >>sys.stderr, data
            raise ClientError("unable to decode JSON: %s" % str(e))

    def get(self, path):
        if self.debug:
            print >>sys.stderr, ">>> PATH ", self.url, path

        http = httplib2.Http()
        response, content = http.request(self.url + "/snmp/" + path, 'GET',
                headers=self.headers)

        if response['status'] != '200':
            raise ClientError('request failed: %s %s'  % (response['status'],
                content))

        if self.debug:
            print >>sys.stderr, ">>> RESPONSE ", response
            print >>sys.stderr, ">>> CONTENT ", content
       
        return self._deserialize(content)

    def get_routers(self):
        return self.get('')

    def get_interfaces(self, router):
        return self.get("%s/interface/" % router)

    def get_interface(self, router, iface):
        iface = remove_metachars(iface)
        return self.get("%s/interface/%s/" % (router, iface))

    @classmethod
    def build_query(self, begin, end, agg=None):
        q = 'begin=%d&end=%d' % (int(begin), int(end))

        if agg:
            q += "&agg=%d" % agg

        return q
    
    @classmethod
    def build_interface_data_path(self, router, interface, begin, end,
            direction, agg=None, dataset="traffic"):

        q = self.build_query(begin, end, agg)

        if dataset == "traffic":
            path = "%s/interface/%s/%s/?%s" % (router,
                remove_metachars(interface), direction, q)
        else:
            path = "%s/interface/%s/%s/%s/?%s" % (router,
                remove_metachars(interface),
                dataset, direction, q)

        return path

    def get_interface_data(self, router, interface, begin, end, direction,
            agg=None, dataset='traffic'):

        path = self.build_interface_data_path(router, interface,
                begin, end, direction, agg=agg, dataset=dataset)

        return self.get(path)

    def get_bulk(self, uri_list, raw=False):
        http = httplib2.Http()
        response, content = self.http.request(self.url + "/bulk/", 'POST',
                urllib.urlencode(dict(q=json.dumps(uri_list))),
                headers=self.headers)

        if not raw:
            return self._deserialize(content)
        else:
            return content


if __name__ == '__main__':
    api = EsmondAPI('http://snmp-west.es.net:8001/', debug=True)
    print "==== ROUTERS " + "=" * 40
    r = api.get_routers()
    print r
    n = r['children'][0]['name']
    print "==== INTERFACES ", n + "=" * 40
    i = api.get_interfaces(n)
    print i
    iin = i['children'][0]['name'].replace('/', '_')
    t0 = time.time() - 600
    t1 = time.time()
    print "==== DATA ", n, iin, t0, t1, "=" * 30
    data = api.get_interface_data(n, iin, t0, t1, 'in')
    print data

    print api.url
    print api.get_interface_data('ameslab-rt1', 'fe-0_3_0', t0, t1, 'in')

    print "==== BULK"

    d = api.get_bulk([
        {     'uri': '/snmp/ameslab-rt1/interface/fe-0_3_0/in/',
            'begin': '1256076131',
              'end': '1256076731',
              'agg': '30',
               'id': 1},
        {     'uri': '/snmp/ameslab-rt1/interface/fe-0_3_0/in/',
            'begin': '1256076131',
              'end': '1256076731',
              'agg': '30',
               'id': 2}])
    for k,v in d.iteritems():
        print k, v['result']['data'][0]
