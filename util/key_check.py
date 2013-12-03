#!/usr/bin/env python

"""
Sketch to play with checking for valid keys.  Probably temporary.
Based on api.test test data.
"""

import os
import sys
import time

from esmond.config import get_config, get_config_path
from esmond.cassandra import CASSANDRA_DB

begin = 1343955600000 # real start
end   = 1343957400000

def check(db, path, begin, end):
    t = db.check_for_valid_keys(path=path, freq=30000, 
            ts_min=begin, ts_max=end)
    return t


def main():
    config = get_config(get_config_path())

    db = CASSANDRA_DB(config)

    print 'bogus key, valid time range:',

    path = ['snmp','rtr_d','FastPollHC','ifHCInOctets','fxp0.0', 'bogus']

    print check(db, path, begin, end)

    print 'valid key, valid time range:',

    path = ['snmp','rtr_d','FastPollHC','ifHCInOctets','fxp0.0']

    print check(db, path, begin, end)

    print 'valid key path, valid AND invalid range keys:',

    print check(db, path, begin, end+31557600000)
    # print check(db, path, begin-31557600000, end)

    pass

if __name__ == '__main__':
    main()