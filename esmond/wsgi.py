# Season to taste - ESMOND_ROOT will need to be reset if it isn't
# /services/esmond or isn't set correctly in the Apache configuration.

import os
import site
import sys

# ESMOND_ROOT should be defined via SetEnv in your Apache configuration.
# to the directory esmond is installed in.
if not os.environ.has_key('ESMOND_ROOT'):
    print >>sys.stderr, "Please define ESMOND_ROOT in your Apache configuration"
    exit()
rootpath=os.environ['ESMOND_ROOT'] 
# This will make Django run in a virtual env
# Remember original sys.path.
prev_sys_path = list(sys.path)

# Add each new site-packages directory.
site.addsitedir(rootpath+'/venv/lib/python2.7/site-packages')

# Reorder sys.path so new directories at the front.
new_sys_path = [] 
for item in list(sys.path): 
    if item not in prev_sys_path: 
        new_sys_path.append(item) 
        sys.path.remove(item) 
sys.path[:0] = new_sys_path


os.environ['DJANGO_SETTINGS_MODULE'] = 'esmond.settings'

print >>sys.stderr, "path=", sys.path
try:
    import django.core.handlers.wsgi
    application = django.core.handlers.wsgi.WSGIHandler()
except Exception, e:
    print >>sys.stderr,"exception:",e

"""
Example apache httpd.conf directives:

WSGIScriptAlias / /services/esmond/esmond/wsgi.py
WSGIPythonPath /services/esmond/esmond:/services/esmond/venv/lib/python2.7/site-packages
WSGIPythonHome /services/esmond/venv

WSGIDaemonProcess www python-path=/services/esmond/esmond:/services/esmond/venv/lib/python2.7/site-packages home=/services/esmond
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
