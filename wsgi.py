

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
# ESMOND_ROOT should be defined via SetEnv in your Apache configuration.
# This is just a fallback.
if not os.environ.has_key('ESMOND_ROOT'):
    os.environ['ESMOND_ROOT'] = '/services/esmond'

print >>sys.stderr, "path=", sys.path
try:
    import django.core.handlers.wsgi
    application = django.core.handlers.wsgi.WSGIHandler()
except Exception, e:
    print >>sys.stderr,"exception:",e
