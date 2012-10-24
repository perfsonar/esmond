import os
import os.path
import sys
import site

try:
    ESXSNMP_GRAPHITE_ROOT = os.environ['ESXSNMP_GRAPHITE_ROOT']
except:
    ESXSNMP_GRAPHITE_ROOT = os.path.dirname(os.path.abspath(__file__)) + "/.."

sys.path.append(ESXSNMP_GRAPHITE_ROOT)
os.environ['DJANGO_SETTINGS_MODULE'] = 'esxsnmp_graphite.settings'

# This assumes you have deployed Graphite in a virtual env
site.addsitedir('%s/venv/lib/python2.7/site-packages' % (ESXSNMP_GRAPHITE_ROOT,))

import django.core.handlers.wsgi

application = django.core.handlers.wsgi.WSGIHandler()
