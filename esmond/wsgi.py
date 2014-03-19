# Season to taste - ESMOND_ROOT will need to be reset if it isn't
# /services/esmond or isn't set correctly in the Apache configuration.

import os
import site
import sys

# ESMOND_ROOT should be defined via SetEnv in your Apache configuration.
# It needs to point to the directory esmond is installed in.

os.environ['DJANGO_SETTINGS_MODULE'] = 'esmond.settings'

print >>sys.stderr, "path=", sys.path
try:
    import django.core.handlers.wsgi
    _application = django.core.handlers.wsgi.WSGIHandler()
except Exception, e:
    print >>sys.stderr,"exception:",e

# This fixes the hitch that mod_wsgi does not pass Apache SetEnv 
# directives into os.environ.

def application(environ, start_response):
    if not environ.has_key('ESMOND_ROOT'):
        print >>sys.stderr, "Please define ESMOND_ROOT in your Apache configuration"
        exit()
    esmond_root = environ['ESMOND_ROOT']
    os.environ['ESMOND_ROOT'] = esmond_root
    if environ.has_key('ESMOND_CONF'):
        os.environ['ESMOND_CONF'] = environ['ESMOND_CONF']
    return _application(environ, start_response)

"""
Example apache httpd.conf directives:
Make sure that WSGIPassAuthorization is on when using the tastypie/django 
level auth or mod_wsgi will munch the auth headers.

WSGIScriptAlias / /services/esmond/esmond/wsgi.py
WSGIPythonPath /services/esmond/esmond:/services/esmond/venv/lib/python2.7/site-packages
WSGIPythonHome /services/esmond/venv
WSGIPassAuthorization On

WSGIDaemonProcess www python-path=/services/esmond/esmond:/services/esmond/venv/lib/python2.7/site-packages home=/services/esmond processes=3 threads=15
WSGIProcessGroup www

<Directory /services/esmond/esmond>
<Files wsgi.py>
SetEnv ESMOND_ROOT /services/esmond
AuthType None
Order deny,allow
Allow from all
</Files>
</Directory>
"""
