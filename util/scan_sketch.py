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
from esmond.api.api import SNMP_NAMESPACE
from esmond.api.dataseries import QueryUtil, Fill
from esmond.cassandra import get_rowkey, KEY_DELIMITER, CASSANDRA_DB, _split_rowkey
from esmond.util import max_datetime
from esmond.config import get_config_path, get_config

from django.utils.timezone import utc
from django.db.utils import IntegrityError
from django.db import connection

def ts_epoch(ts):
    return calendar.timegm(ts.utctimetuple())

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

def generate_or_update_inventory():

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
                        [SNMP_NAMESPACE, device.name, oidset.name, oid.name, iface.ifDescr], 
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

                        i = Inventory(row_key=key, frequency=oidset.frequency,
                            start_time=table_start, end_time=table_end, 
                            column_family=cf)
                        try:
                            i.save()
                        except IntegrityError as e:
                            print e
                            connection._rollback()

def main():

    # generate_or_update_inventory()

    db = CASSANDRA_DB(get_config(get_config_path()))

    data_found = 0

    for entry in Inventory.objects.filter(frequency__exact=30)[:20]:
        print entry
        print '  *', entry.start_time, ts_epoch(entry.start_time)
        print '  *', entry.end_time, ts_epoch(entry.end_time)

        # XXX(mmg): if end_time of current row is in the
        # future (ie: probably when run on the row of the
        # current year), adjust end time arg to a couple
        # of minutes in the past.  Use this in both the 
        # query and when setting up fill boundaries.
        #
        # Will also be setting last_scan_point to that
        # value in the main inventory table.

        ts_start = ts_epoch(entry.start_time)
        ts_end = ts_epoch(entry.end_time)

        path = _split_rowkey(entry.row_key)[0:5]

        if entry.get_column_family_display() == 'base_rates':
            

            data = db.query_baserate_timerange(path=path, 
                    freq=entry.frequency*1000,
                    ts_min=ts_start*1000,
                    ts_max=ts_end*1000)

        else:
            # Not sure if we'll be scanning any other cfs?
            continue

        # XXX(mmg): throttle things back to first pair of data
        # while developing.
        if data:
            data_found += 1

        print data[0:10]

        # Format the data payload (transform ms timestamps back
        # to seconds and set is_valid = 0 values to None) and 
        # build a filled series over the query range out of 
        # the returned data.
        data = QueryUtil.format_data_payload(data)
        data = Fill.verify_fill(ts_start, ts_end, entry.frequency, data)

        print data[0:10]
        
        print Fill.get_expected_first_bin(ts_start,
                entry.frequency)
        if data_found >= 2:
            break
        print '======='




                    
    pass

if __name__ == '__main__':
    main()


