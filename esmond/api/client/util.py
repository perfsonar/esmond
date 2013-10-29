import os.path
import sys

import ConfigParser

"""Utils for esmond.api.client modules and scripts."""

def add_apikey_header(user, key, header_dict):
    """Format an auth header for rest api key."""
    header_dict['Authorization'] = 'ApiKey {0}:{1}'.format(user, key)

# -- defines and config handling for summary scripts/code

SUMMARY_NS = 'summary'
MONTHLY_NS = 'monthly'

class ConfigException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class ConfigWarning(Warning): pass

def get_config():
    c_path = os.path.abspath(sys.argv[0])
    if c_path.endswith('.py'):
        c_path = c_path.replace('.py', '.conf')
    else:
        c_path = c_path + '.conf'
    if not os.path.exists(c_path):
        raise ConfigException('Could not find configuration file {0}'.format(c_path))

    config = ConfigParser.ConfigParser()
    config.read(c_path)
    return config

def get_type_map():
    type_map = {}

    c = get_config()
    for section in c.sections():
        type_map[section] = {}
        for items in c.items(section):
            type_map[section][items[0]] = items[1]

    return type_map

def get_summary_name(filterdict):
    if not isinstance(filterdict, dict):
        raise ConfigException('Arg needs to be a dict of the form: {{django_query_filter: filter_criteria}} - got {0}.'.format(filterdict))
    elif len(filterdict.keys()) > 1:
        raise ConfigException('Dict must contain a single key/value pair of the form: {{django_query_filter: filter_criteria}} - got {0}.'.format(filterdict))

    django_query_filter = filterdict.keys()[0]
    filter_criteria = filterdict[django_query_filter]

    type_map = get_type_map()

    if not type_map.has_key(django_query_filter):
        raise ConfigException('Config file did does not contain a section for {0} - has: {1}'.format(django_query_filter, type_map.keys()))
    elif not type_map[django_query_filter].has_key(filter_criteria):
        raise ConfigException('Config section for {0} does not contain an key/entry for {1} - has: {2}'.format(django_query_filter, filter_criteria, type_map[django_query_filter].keys()))

    return type_map[django_query_filter][filter_criteria]

# -- atencode code for handling rest URIs

_atencode_safe = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXWZ012345689_.-'
_atencode_map = {}
for i, c in (zip(xrange(256), str(bytearray(xrange(256))))):
    _atencode_map[c] = c if c in _atencode_safe else '@{:02X}'.format(i)

_atencode_unsafe = ' $&+,/:;=?@\x7F'
_atencode_map_minimal = {}
for i, c in (zip(xrange(256), str(bytearray(xrange(256))))):
    _atencode_map_minimal[c] = c if (i > 31 and i < 128 and c not in _atencode_unsafe) else '@{:02X}'.format(i)

_atdecode_map = {}
for i in xrange(256):
    _atdecode_map['{:02X}'.format(i)] = chr(i)
    _atdecode_map['{:02x}'.format(i)] = chr(i)

def atencode(s, minimal=False):
    if minimal:
        return ''.join(map(_atencode_map_minimal.__getitem__, s))
    else:
        return ''.join(map(_atencode_map.__getitem__, s))

def atdecode(s):
    parts = s.split('@')
    r = [parts[0]]

    for part in parts[1:]:
        try:
            r.append(_atdecode_map[part[:2]])
            r.append(part[2:])
        except KeyError:
            append('@')
            append(part)

    return ''.join(r)


