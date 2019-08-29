import ctypes
import datetime
import time
import logging

from django.utils.timezone import utc, make_aware

def get_logger(name):
    return logging.getLogger(name)

_atencode_safe = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXWZ0123456789_.-'
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

def datetime_to_unixtime(dt):
    return int(time.mktime(dt.timetuple()))

# max_datetime is used to represent a time sufficiently far into future such
# that this datetime is effectively infinite.  it is set to be 2 days less than
# datetime.datetime.max to prevent overflow due to timezone variances.
max_datetime = make_aware(datetime.datetime.max - datetime.timedelta(2), utc)
