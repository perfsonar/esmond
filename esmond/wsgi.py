# This wsgi file pre-supposes that it is deployed in the root of the esmond
# distribution checkout (rather than in esmond/esmond where it sits in the
# repository) and that the root of the virtualenv is in the same directory. 
#
# Season to taste - ESMOND_ROOT will need to be reset if it isn't
# /services/esmond

import os
import site
import sys

rootpath=os.path.dirname(os.path.realpath(__file__))

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
os.environ['ESMOND_ROOT'] = '/services/esmond'

print >>sys.stderr, "path=", sys.path
try:
    import django.core.handlers.wsgi
    application = django.core.handlers.wsgi.WSGIHandler()
except Exception, e:
    print >>sys.stderr,"exception:",e

"""
Example apache httpd.conf directives:

WSGIScriptAlias / /services/esmond/wsgi.py
WSGIPythonPath /services/esmond/esmond:/services/esmond/venv/lib/python2.7/site-packages
WSGIPythonHome /services/esmond/venv

WSGIDaemonProcess www python-path=/services/esmond/esmond:/services/esmond/venv/lib/python2.7/site-packages home=/services/esmond
WSGIProcessGroup www

<Directory /services/esmond>
<Files wsgi.py>
AuthType None
Order deny,allow
Allow from all
</Files>
</Directory>
"""