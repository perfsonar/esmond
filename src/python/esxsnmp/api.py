import time
import httplib2
import urllib
import simplejson
from esxsnmp.util import remove_metachars

class ESxSNMPAPI(object):
    def __init__(self, url):
        if url[-1] == '/':
            url = url[:-1]
        self.url = url
        self.http = httplib2.Http()

    def get_routers(self):
        response, content = self.http.request(self.url + "/snmp/", 'GET')
        return self._deserialize(content)

    def get_interfaces(self, router):
        url = self.url + "/snmp/%s/interface/" % router
        response, content = self.http.request(url, 'GET')
        return self._deserialize(content)

    def get_interface(self, router, iface):
        iface = remove_metachars(iface)
        url = self.url + "/snmp/%s/interface/%s/" % (router, iface)
        response, content = self.http.request(url, 'GET')
        return self._deserialize(content)

    @classmethod
    def build_interface_data_uri(self, url, router, interface, begin, end, direction, agg):
        uri = "%s/snmp/%s/interface/%s/%s/?begin=%s&end=%s" % (url, router,
                urllib.quote(interface, safe=''),
                direction, int(begin), int(end))
        if agg:
            uri += "&agg=%d" % agg

        return uri

    def get_interface_data(self, router, interface, begin, end, direction,
            agg=30):

        uri = self.build_interface_data_uri(self.url, router, interface, begin, end, direction, agg)

        response, content = self.http.request(uri, 'GET')
        return self._deserialize(content)

    def get_bulk(self, uri_list):
        response, content = self.http.request(self.url + "/bulk/", 'POST',
                urllib.urlencode(dict(uris=simplejson.dumps(uri_list))))

        return self._deserialize(content)

    def _deserialize(self, data):
        try:
            return simplejson.loads(data)
        except ValueError:
            print "BOGUS DATA"
            print data
            raise

if __name__ == '__main__':
    api = ESxSNMPAPI('http://snmp-west.es.net:8001/')
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

    d = api.get_bulk([
        '/snmp/ameslab-rt1/interface/fe-0_3_0/in/?begin=1256076131&end=1256076731&agg=30',
        '/snmp/ameslab-rt1/interface/fe-0_3_0/in/?begin=1256076131&end=1256076731&agg=30'])
    for k,v in d.iteritems():
        print k, v['result']['data'][0]
