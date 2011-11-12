#!/usr/bin/python

import os, sys

os.environ['DJANGO_SETTINGS_MODULE'] = 'esxdjango.settings'
#os.environ['PYTHON_EGG_CACHE'] = '/tmp'


esxdjango_path = "%s" % os.path.dirname(os.path.abspath(__file__))
sys.path.append("%s/.."%esxdjango_path)
sys.path.append(esxdjango_path)
#sys.path.append("%s/whisper" % graphite_path)
sys.path.append("/home/snmp/lib/")
#sys.path.append("%s/../esxsnmp/src/python" % graphite_path)
#sys.path.append("/a/home/snmp/esxsnmp/eggs/httplib2-0.7.1-py2.6.egg")

print >>sys.stderr, "path=", sys.path
try:
    import django.core.handlers.wsgi

    application = django.core.handlers.wsgi.WSGIHandler()
except Exception, e:
    print >>sys.stderr,"exception:",e
