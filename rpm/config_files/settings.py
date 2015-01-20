import os
import os.path
from esmond.config import get_config

# Django settings for esmond project.

DEBUG = False
TEMPLATE_DEBUG = DEBUG
TESTING = os.environ.get("ESMOND_TESTING", False)
ESMOND_CONF = os.environ.get("ESMOND_CONF")
ESMOND_ROOT = os.environ.get("ESMOND_ROOT")
TEST_RUNNER = 'discover_runner.DiscoverRunner'
ALLOWED_HOSTS = [ '*' ]

if not ESMOND_ROOT:
    raise Error("ESMOND_ROOT not definied in environemnt")

if not ESMOND_CONF:
    ESMOND_CONF = os.path.join(ESMOND_ROOT, "esmond.conf")

ESMOND_SETTINGS = get_config(ESMOND_CONF)

ADMINS = (
    # ('Your Name', 'your_email@domain.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': ESMOND_SETTINGS.sql_db_engine,
        'NAME': ESMOND_SETTINGS.sql_db_name,
        'HOST': ESMOND_SETTINGS.sql_db_host,
        'USER': ESMOND_SETTINGS.sql_db_user,
        'PASSWORD': ESMOND_SETTINGS.sql_db_password,
    }
}

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
#TIME_ZONE = 'America/Chicago'
TIME_ZONE = None
USE_TZ = True

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

STATIC_URL = '/esmond-static/'

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
# Examples: "http://media.lawrence.com", "http://example.com/media/"
MEDIA_URL = ''

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

ROOT_URLCONF = 'esmond.urls'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'esmond.api',
    'esmond.admin',
    'discover_runner',
    'tastypie',
)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(pathname)s: %(message)s'
        },
    },
    'handlers': {
        'django_handler': {
            'level':'INFO',
            'class':'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/esmond/django.log',
            'maxBytes': 1024*1024*5, # 5 MB
            'backupCount': 5,
            'formatter':'standard',
        },
        'esmond_handler': {
            'level':'INFO',
            'class':'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/esmond/esmond.log',
            'maxBytes': 1024*1024*5, # 5 MB
            'backupCount': 5,
            'formatter':'standard',
        }
    },
    'loggers': {
        'django.request': { 
            'handlers': ['django_handler'],
            'level': 'INFO',
            'propagate': True
        },
        'esmond': { 
            'handlers': ['esmond_handler'],
            'level': 'INFO',
            'propagate': True
        },
        'espersistd.perfsonar.cass_db': { 
            'handlers': ['esmond_handler'],
            'level': 'INFO',
            'propagate': True
        },
    }
}

