#!/usr/bin/env python

"""
Sketch/etc for gap filling code.
"""

import calendar
import datetime
import os
import sys
import time

from esmond.api.models import Device, IfRef, DeviceOIDSetMap, OIDSet, OID, \
     Inventory, GapInventory
from esmond.cassandra import get_rowkey, KEY_DELIMITER
from esmond.util import max_datetime

from django.utils.timezone import utc

def get_key_range(path, freq, ts_min, ts_max):
   
    year_start = datetime.datetime.utcfromtimestamp(float(ts_min)).year
    year_finish = datetime.datetime.utcfromtimestamp(float(ts_max)).year
    
    key_range = []
    
    if year_start != year_finish:
        for year in range(year_start, year_finish+1):
            key_range.append(get_rowkey(path, freq=freq, year=year))
    else:
        key_range.append(get_rowkey(path, freq=freq, year=year_start))
    return key_range

def get_year_boundries(key):
    key_year = int(key.split(KEY_DELIMITER)[-1])
    return datetime.datetime(key_year, 1, 1, tzinfo=utc), \
        datetime.datetime(key_year, 12, 31, hour=23, minute=59, second=59, tzinfo=utc)

def main():

    for device in Device.objects.all().order_by('name')[:5]:
        print device.name
        oidsets = device.oidsets.all()
        for oidset in oidsets:
            for oid in oidset.oids.all():
                for iface in device.ifref_set.all()[:5]:
                    ts_min = calendar.timegm(iface.begin_time.utctimetuple())

                    if iface.end_time == max_datetime or \
                        iface.end_time.year == 9999:
                        ts_max = time.time()
                    else:
                        ts_max = calendar.timegm(iface.end_time.utctimetuple())

                    row_key_range = get_key_range(
                        [device.name, oidset.name, oid.name, iface.ifDescr], 
                        oidset.frequency_ms, ts_min, ts_max)

                    for key in row_key_range:
                        year_start,year_end = get_year_boundries(key)

                        # XXX(mmg): get clear on what django/postgres
                        # is doing with the datestamps.  This is working
                        # but what I expect to be happening is not happening
                          
                        if iface.begin_time < year_start:
                            table_start = year_start
                        else:
                            table_start = iface.begin_time

                        if iface.end_time > year_end:
                            table_end = year_end
                        else:
                            table_end = iface.end_time

                        # XXX(mmg): this is probably wrong, follow up on this.
                        if oid.aggregate:
                            cf = Inventory.BASE_RATES
                        else:
                            cf = Inventory.RAW_DATA

                        i = Inventory(row_key=key, start_time=table_start,
                                end_time=table_end, column_family=cf)
                        # i.save()



                    
    pass

if __name__ == '__main__':
    main()