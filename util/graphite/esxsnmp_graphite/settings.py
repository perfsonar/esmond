"""ESnet Customized Graphite Settings

"""

import sys, os
from django import VERSION as DJANGO_VERSION
from os.path import abspath, dirname, join
import graphite
import socket

HOSTNAME = socket.gethostname()

WEBAPP_VERSION = '0.10.0-alpha'
DEBUG = False
JAVASCRIPT_DEBUG = False

# Filesystem layout
WEB_DIR = dirname( abspath(graphite.__file__) )
THIRDPARTY_DIR = join(WEB_DIR,'thirdparty')
GRAPHITE_ROOT = abspath(WEB_DIR + "/../../../../../")
WEBAPP_DIR = join(WEB_DIR, "../")

# Initialize additional path variables
# Defaults for these are set after local_settings is imported
CONTENT_DIR = ''
CSS_DIR = ''
CONF_DIR = ''
DASHBOARD_CONF = ''
GRAPHTEMPLATES_CONF = ''
STORAGE_DIR = ''
WHITELIST_FILE = ''
INDEX_FILE = ''
LOG_DIR = ''
CERES_DIR = ''
WHISPER_DIR = ''
RRD_DIR = ''
STANDARD_DIRS = []
CLUSTER_SERVERS = []

STATIC_ROOT = join(GRAPHITE_ROOT, "static")
STATIC_URL = "/content/"
STATICFILES_DIRS = (
        join(GRAPHITE_ROOT, "venv/src/graphite-web/webapp/content"),
        )

# Allow local versions of the libs shipped in thirdparty to take precedence
sys.path.append(THIRDPARTY_DIR)

# Cluster settings
CLUSTER_SERVERS = []
REMOTE_FIND_TIMEOUT = 3.0
REMOTE_FETCH_TIMEOUT = 6.0
REMOTE_RETRY_DELAY = 60.0
REMOTE_READER_CACHE_SIZE_LIMIT = 1000
CARBONLINK_HOSTS = ["127.0.0.1:7002"]
CARBONLINK_TIMEOUT = 1.0
CARBONLINK_HASHING_KEYFUNC = None
CARBONLINK_RETRY_DELAY = 15
REPLICATION_FACTOR = 1
MEMCACHE_HOSTS = []
FIND_CACHE_DURATION = 300
FIND_TOLERANCE = 2 * FIND_CACHE_DURATION
DEFAULT_CACHE_DURATION = 60 #metric data and graphs are cached for one minute by default
LOG_CACHE_PERFORMANCE = False

#Remote rendering settings
REMOTE_RENDERING = False #if True, rendering is delegated to RENDERING_HOSTS
RENDERING_HOSTS = []
REMOTE_RENDER_CONNECT_TIMEOUT = 1.0
LOG_RENDERING_PERFORMANCE = False

#Miscellaneous settings
SMTP_SERVER = "localhost"
DOCUMENTATION_URL = "http://graphite.readthedocs.org/"
ALLOW_ANONYMOUS_CLI = True
LOG_METRIC_ACCESS = False
LEGEND_MAX_ITEMS = 10

#Authentication settings
USE_LDAP_AUTH = False
LDAP_SERVER = "" # "ldapserver.mydomain.com"
LDAP_PORT = 389
LDAP_SEARCH_BASE = "" # "OU=users,DC=mydomain,DC=com"
LDAP_BASE_USER = "" # "CN=some_readonly_account,DC=mydomain,DC=com"
LDAP_BASE_PASS = "" # "my_password"
LDAP_USER_QUERY = "" # "(username=%s)"  For Active Directory use "(sAMAccountName=%s)"
LDAP_URI = None

#Set this to True to delegate authentication to the web server
USE_REMOTE_USER_AUTHENTICATION = False

# Override to link a different URL for login (e.g. for django_openid_auth)
LOGIN_URL = '/account/login'

#Initialize database settings - Old style (pre 1.2)
DATABASE_ENGINE = 'django.db.backends.sqlite3'	# 'postgresql', 'mysql', 'sqlite3' or 'ado_mssql'.
DATABASE_NAME = ''				# Or path to database file if using sqlite3.
DATABASE_USER = ''				# Not used with sqlite3.
DATABASE_PASSWORD = ''				# Not used with sqlite3.
DATABASE_HOST = ''				# Set to empty string for localhost. Not used with sqlite3.
DATABASE_PORT = ''				# Set to empty string for default. Not used with sqlite3.

# If using rrdcached, set to the address or socket of the daemon
FLUSHRRDCACHED = ''

ADMINS = (('Admin', 'admin@example.com'), )  # NEEDS TO BE SET
MANAGERS = ADMINS

TEMPLATE_DIRS = (
  join(WEB_DIR, 'templates'),
)


#Django settings below, do not touch!
APPEND_SLASH = False
TEMPLATE_DEBUG = False
CACHE_BACKEND = "dummy:///"

# Language code for this installation. All choices can be found here:
# http://www.w3.org/TR/REC-html40/struct/dirlang.html#langcodes
# http://blogs.law.harvard.edu/tech/stories/storyReader$15
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# Absolute path to the directory that holds media.

MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT.
# Example: "http://media.lawrence.com"
MEDIA_URL = ''

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/media/'

# Make this unique, and don't share it with anybody.
SECRET_KEY = ''

# List of callables that know how to import templates from various sources.
#XXX Compatibility for Django 1.1. To be removed after 0.9.10
if DJANGO_VERSION < (1,2):
  TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.load_template_source',
    'django.template.loaders.app_directories.load_template_source',
  )
else:
  TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
  )

MIDDLEWARE_CLASSES = (
  'django.middleware.common.CommonMiddleware',
  'django.middleware.gzip.GZipMiddleware',
  'django.contrib.sessions.middleware.SessionMiddleware',
  'django.contrib.auth.middleware.AuthenticationMiddleware',
)

ROOT_URLCONF = 'graphite.urls'

INSTALLED_APPS = (
  'graphite.metrics',
  'graphite.render',
  'graphite.cli',
  'graphite.browser',
  'graphite.composer',
  'graphite.account',
  'graphite.dashboard',
  'graphite.whitelist',
  'graphite.events',
  'django.contrib.auth',
  'django.contrib.sessions',
  'django.contrib.admin',
  'django.contrib.contenttypes',
  'django.contrib.staticfiles',
  'tagging',
)

AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend']

## Set config dependent on flags set in local_settings
# Path configuration
if not CONTENT_DIR:
  CONTENT_DIR = join(WEBAPP_DIR, 'content')
if not CSS_DIR:
  CSS_DIR = join(CONTENT_DIR, 'css')

if not CONF_DIR:
  CONF_DIR = os.environ.get('GRAPHITE_CONF_DIR', join(GRAPHITE_ROOT, 'conf'))
if not DASHBOARD_CONF:
  DASHBOARD_CONF = join(CONF_DIR, 'dashboard.conf')
if not GRAPHTEMPLATES_CONF:
  GRAPHTEMPLATES_CONF = join(CONF_DIR, 'graphTemplates.conf')

if not STORAGE_DIR:
  STORAGE_DIR = os.environ.get('GRAPHITE_STORAGE_DIR', join(GRAPHITE_ROOT, 'storage'))
if not WHITELIST_FILE:
  WHITELIST_FILE = join(STORAGE_DIR, 'lists', 'whitelist')
if not INDEX_FILE:
  INDEX_FILE = join(STORAGE_DIR, 'index')
if not LOG_DIR:
  LOG_DIR = join(STORAGE_DIR, 'log', 'webapp')

ESXSNMP_USERNAME ='snmp'      # NEEDS TO BE SET
ESXSNMP_PASSWORD = '********' # NEEDS TO BE SET
ESXSNMP_REST_URL = 'http://esxsnmp.example.com:8001/' # NEEDS TO BE SET

FINDERS = [
    ('esxsnmp_graphite.finders.ESxSNMPFinder',
    "'%s', username='%s', password='%s'" % (
        ESXSNMP_REST_URL, ESXSNMP_USERNAME, ESXSNMP_PASSWORD)),
]


# Default sqlite db file
# This is set here so that a user-set STORAGE_DIR is available
if 'sqlite3' in DATABASE_ENGINE \
    and not DATABASE_NAME:
  DATABASE_NAME = join(STORAGE_DIR, 'graphite.db')

# Caching shortcuts
if MEMCACHE_HOSTS:
  CACHE_BACKEND = 'memcached://' + ';'.join(MEMCACHE_HOSTS) + ('/?timeout=%d' % DEFAULT_CACHE_DURATION)

# Authentication shortcuts
if USE_LDAP_AUTH and LDAP_URI is None:
  LDAP_URI = "ldap://%s:%d/" % (LDAP_SERVER, LDAP_PORT)

if USE_REMOTE_USER_AUTHENTICATION:
  MIDDLEWARE_CLASSES += ('django.contrib.auth.middleware.RemoteUserMiddleware',)
  AUTHENTICATION_BACKENDS.insert(0,'django.contrib.auth.backends.RemoteUserBackend')

if USE_LDAP_AUTH:
  AUTHENTICATION_BACKENDS.insert(0,'graphite.account.ldapBackend.LDAPBackend')
