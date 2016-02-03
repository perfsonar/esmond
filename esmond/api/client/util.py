"""Utils for esmond.api.client modules and scripts."""

import calendar
import os.path
import sys
import warnings

import ConfigParser


def add_apikey_header(user, key, header_dict):
    """Format an auth header for rest api key."""
    # header_dict['Authorization'] = 'ApiKey {0}:{1}'.format(user, key)
    header_dict['Authorization'] = 'Token {0}'.format(key)


class AlertMixin(object):
    """Mixin class for client libs to emit custom alerts and warnings."""
    def http_alert(self, r):
        """
        Issue a subclass specific alert in the case that a call to the REST
        api does not return a 200 status code.
        """
        warnings.warn('Request for {0} got status: {1} - response: {2}'.format(
            r.url, r.status_code, r.content), self.wrn, stacklevel=2)

    def warn(self, msg):
        """Issue a stack-formatted warning."""
        warnings.warn(msg, self.wrn, stacklevel=2)

# -- defines and config handling for summary scripts/code

SUMMARY_NS = 'summary'
MONTHLY_NS = 'monthly'


class ConfigException(Exception):
    """Custom Config exception"""
    def __init__(self, value):
        # pylint: disable=super-init-not-called
        self.value = value

    def __str__(self):
        return repr(self.value)


class ConfigWarning(Warning):
    """Custom Config warning"""
    pass


def get_config():
    """Grab and parse the summary config file."""
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
    """Generate type map from summary config file."""
    type_map = {}

    cfg = get_config()
    for section in cfg.sections():
        type_map[section] = {}
        for items in cfg.items(section):
            type_map[section][items[0]] = items[1]

    return type_map


def get_summary_name(filterdict):
    """Called from summary programs, return the summary details."""
    # pylint: disable=line-too-long
    if not isinstance(filterdict, dict):
        raise ConfigException('Arg needs to be a dict of the form: {{django_query_filter: filter_criteria}} - got {0}.'.format(
            filterdict))

    elif len(filterdict.keys()) > 1:
        raise ConfigException('Dict must contain a single key/value pair of the form: {{django_query_filter: filter_criteria}} - got {0}.'.format(
            filterdict))

    django_query_filter = filterdict.keys()[0]
    filter_criteria = filterdict[django_query_filter]

    type_map = get_type_map()

    if django_query_filter not in type_map:
        raise ConfigException('Config file did does not contain a section for {0} - has: {1}'.format(
            django_query_filter, type_map.keys()))

    elif filter_criteria not in type_map[django_query_filter]:
        raise ConfigException('Config section for {0} does not contain an key/entry for {1} - has: {2}'.format(
            django_query_filter, filter_criteria, type_map[django_query_filter].keys()))

    return type_map[django_query_filter][filter_criteria]

# -- aggregation functions


def aggregate_to_ts_and_endpoint(data, verbosity=False):
    """Aggregate/sum the returned data by timestamp and endpoint alias."""
    aggs = {}

    # Aggregate/sum the returned data by timestamp and endpoint alias.
    for row in data.data:
        if verbosity:
            print ' *', row
        for data in row.data:
            if verbosity > 1:
                print '  *', data
            # if not aggs.has_key(data.ts_epoch):
            if data.ts_epoch not in aggs:
                aggs[data.ts_epoch] = {}
            # if not aggs[data.ts_epoch].has_key(row.endpoint):
            if row.endpoint not in aggs[data.ts_epoch]:
                aggs[data.ts_epoch][row.endpoint] = 0
            if data.val is not None:
                aggs[data.ts_epoch][row.endpoint] += data.val

    return aggs


def aggregate_to_device_interface_endpoint(data, verbosity=False):  # pylint: disable=invalid-name
    """Aggregate/sum the returned data to device/interface/endpoint alias."""
    aggs = {}

    # Aggregate/sum the returned data to device/interface/endpoint alias.
    for row in data.data:
        if verbosity:
            print ' *', row

        if row.device not in aggs:
            aggs[row.device] = {}

        if row.interface not in aggs[row.device]:
            aggs[row.device][row.interface] = {}

        if row.endpoint not in aggs[row.device][row.interface]:
            aggs[row.device][row.interface][row.endpoint] = 0

        for data in row.data:
            if verbosity > 1:
                print '  *', data
            if data.val is not None:
                aggs[row.device][row.interface][row.endpoint] += data.val

    return aggs


def iterate_device_interface_endpoint(aggs):  # pylint: disable=invalid-name
    """Iterate over aggs down to dev/ifact/endpoint/val."""
    for device in aggs.keys():
        for interface in aggs[device].keys():
            for endpoint, val in aggs[device][interface].items():
                yield device, interface, endpoint, val


# -- timehandling code for summary scripts

# pylint doesn't like these constant names
# pylint: disable=invalid-name

def lastmonth(yr, mo):
    """get last month from yr/mo pair"""
    return [(y, m+1) for y, m in (divmod((yr*12+mo-2), 12),)][0]


def nextmonth(yr, mo):
    """get next month from yr/mo pair"""
    return (yr+mo / 12, mo % 12+1)


def get_month_start_and_end(start_point):
    """Get the start and end of the month a datetime object is in."""

    start = calendar.timegm((start_point.year, start_point.month, 1, 0, 0, 0, 0, 0, -1))

    n_mo_yr, n_mo = nextmonth(start_point.year, start_point.month)

    end = calendar.timegm((n_mo_yr, n_mo, 1, 0, 0, 0, 0, 0, -1)) - 1

    return start, end


# -- atencode code for handling rest URIs

_atencode_safe = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXWZ0123456789_.-'
_atencode_map = {}
for i, c in zip(xrange(256), str(bytearray(xrange(256)))):
    _atencode_map[c] = c if c in _atencode_safe else '@{:02X}'.format(i)

_atencode_unsafe = ' $&+,/:;=?@\x7F'
_atencode_map_minimal = {}
for i, c in zip(xrange(256), str(bytearray(xrange(256)))):
    _atencode_map_minimal[c] = \
        c if (i > 31 and i < 128 and c not in _atencode_unsafe) else '@{:02X}'.format(i)

_atencode_safe_graphite = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXWZ012345689_-'
_atencode_map_graphite = {}
for i, c in zip(xrange(256), str(bytearray(xrange(256)))):
    _atencode_map_graphite[c] = c if c in _atencode_safe_graphite else '@{:02X}'.format(i)

_atdecode_map = {}

for i in xrange(256):
    _atdecode_map['{:02X}'.format(i)] = chr(i)
    _atdecode_map['{:02x}'.format(i)] = chr(i)


def atencode(s, minimal=False, graphite=False):
    """Atencode a string."""
    # pylint: disable=bad-builtin
    if minimal:
        return ''.join(map(_atencode_map_minimal.__getitem__, s))
    elif graphite:
        return ''.join(map(_atencode_map_graphite.__getitem__, s))
    else:
        return ''.join(map(_atencode_map.__getitem__, s))


def atdecode(s):
    """atdecode a string.8"""
    parts = s.split('@')
    r = [parts[0]]

    for part in parts[1:]:
        try:
            r.append(_atdecode_map[part[:2]])
            r.append(part[2:])
        except KeyError:
            r.append('@')
            r.append(part)

    return ''.join(r)
