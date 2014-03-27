#!/usr/bin/env python

"""
Sketch/etc for gap filling code.
"""

import calendar
import datetime
import os
import sys
import time

from optparse import OptionParser

from esmond.api.models import Device, IfRef, DeviceOIDSetMap, OIDSet, OID, \
     Inventory, GapInventory
from esmond.api.api import SNMP_NAMESPACE
from esmond.api.dataseries import QueryUtil, Fill
from esmond.cassandra import get_rowkey, KEY_DELIMITER, CASSANDRA_DB, _split_rowkey
from esmond.util import max_datetime
from esmond.config import get_config_path, get_config

from django.utils.timezone import utc, make_aware
from django.db.utils import IntegrityError
from django.db import connection
from django.core.exceptions import ObjectDoesNotExist

import signal

class IntHandler(object):
    def __init__(self, sig=signal.SIGINT):
        self.interrupted = False
        self._calls = 0
        signal.signal(sig, self.catch)

    def catch(self, signum, frame):
        self._calls += 1
        print 'SIGINT {0}'.format(self._calls)
        self.interrupted = True
        # Multiple calls will exit if pycassa driver holds on
        # while it is querying.
        # Normally should exit loop gracefully.
        if self._calls >= 3:
            sys.exit()

sig_handler = IntHandler()

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

def get_interface_list(device, oidset):

    oidsets = {
        'ALUSAPPoll': ('alusapref_set', 'name'),
    }

    if oidsets.has_key(oidset.name):
        interface_set, ifdescr_source = oidsets[oidset.name]
        interfaces = getattr(device, interface_set).all()
        # If the set does not have the same named attributes
        # as an IfRef object, massage the objects so the usual
        # generation logic works correctly.
        if ifdescr_source:
            for i in interfaces:
                i.ifAlias = getattr(i, ifdescr_source)
                i.ifDescr = getattr(i, ifdescr_source)
        return interfaces
    else:
        return device.ifref_set.all()

def generate_or_update_inventory(limit=0, allow_blank_ifalias=False, verbose=False):

    if limit:
        devices = Device.objects.all().order_by('name')[:limit]
    else:
        devices = Device.objects.all().order_by('name')

    for device in devices:
        print device.name
        oidsets = device.oidsets.all()
        for oidset in oidsets:
            for oid in oidset.oids.all():

                ifaces = get_interface_list(device, oidset)

                if limit:
                    ifaces = ifaces[:limit]

                for iface in ifaces:
                    # Skip interfaces that do not have an ifalias 
                    # defined in the metadata since we do not collect
                    # data from these by default.
                    if not allow_blank_ifalias and \
                        (iface.ifAlias == None or iface.ifAlias == ''):
                        if verbose: print '  * skipping:', iface
                        continue
                    
                    ts_min = calendar.timegm(iface.begin_time.utctimetuple())

                    if iface.end_time == max_datetime or \
                        iface.end_time.year == 9999:
                        # If the end time is max time/not defined, set the 
                        # time to now and it will only generate row keys
                        # in the inventory up to the current year.
                        ts_max = time.time()
                    else:
                        ts_max = calendar.timegm(iface.end_time.utctimetuple())

                    row_key_range = get_key_range(
                        [SNMP_NAMESPACE, device.name, oidset.set_name, oid.name, iface.ifDescr], 
                        oidset.frequency_ms, ts_min, ts_max)

                    for key in row_key_range:
                        if verbose: print '  *', key
                        year_start,year_end = get_year_boundries(key)
                          
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


def find_gaps_in_series(data):

    gaps = []

    gap_scanning = False
    gap_start = None
    last_val = None

    for row in data:
        if row[1] == None and gap_scanning == False:
            gap_scanning = True
            gap_start = int(row[0])

        if row[1] != None and gap_scanning == True:
            gaps.append((gap_start, int(last_val[0])))
            gap_start = None
            gap_scanning = False

        last_val = row[:]

    # fallthrough - end of row and still scanning
    if gap_scanning:
        gaps.append((gap_start, int(last_val[0])))

    del last_val[:]

    return gaps

def generate_or_update_gap_inventory(limit=0, threshold=0, verbose=False):

    db = CASSANDRA_DB(get_config(get_config_path()))

    gap_duration_lower_bound = datetime.timedelta(seconds=threshold)

    if limit:
        row_inventory = Inventory.objects.filter(scan_complete=False).order_by('row_key')[:limit]
    else:
        row_inventory = Inventory.objects.filter(scan_complete=False).order_by('row_key')

    count = 1

    inv_count = len(row_inventory)

    for entry in row_inventory:
        print entry
        if verbose:
            print '  *', entry.start_time, ts_epoch(entry.start_time)
            print '  *', entry.end_time, ts_epoch(entry.end_time)
            print '  * inventory item # {0}/{1}'.format(count, inv_count)

        count += 1

        # Check for valid timestamps
        if entry.start_time > entry.end_time:
            print '   * Bad start/end times!'
            entry.issues = 'ifref start_time/end_time mismatch'
            entry.save()
            continue

        ts_start = ts_epoch(entry.start_time)
        ts_end = ts_epoch(entry.end_time)

        # If end_time of current row is in the
        # future (ie: probably when run on the row of the
        # current year), adjust end time arg to an hour ago.  
        # Use this in both the query and when setting up fill 
        # boundaries.
        #
        # Will also be setting last_scan_point to that
        # value in the main inventory table.

        future_end_time = False
        if ts_end > int(time.time()):
            future_end_time = True
            # fit it to a bin
            ts_end = (int(time.time()-3600)/entry.frequency)*entry.frequency

        # if last scan point is set, adjust the start time to that
        if entry.last_scan_point != None:
            print '  * setting start to last scan point'
            ts_start = ts_epoch(entry.last_scan_point)

        path = _split_rowkey(entry.row_key)[0:5]

        if sig_handler.interrupted:
            print 'shutting down'
            break

        if entry.get_column_family_display() == 'base_rates':
            data = db.query_baserate_timerange(path=path, 
                    freq=entry.frequency*1000,
                    ts_min=ts_start*1000,
                    ts_max=ts_end*1000)


        else:
            # XXX(mmg): figure out what data is being stored
            # in the raw data cf and process accordingly.
            print '  * not processing'
            continue

        if data:
            entry.data_found = True
            print '  * data found'

        # Format the data payload (transform ms timestamps back
        # to seconds and set is_valid = 0 values to None) and 
        # build a filled series over the query range out of 
        # the returned data.
        formatted_data = QueryUtil.format_data_payload(data)
        filled_data = Fill.verify_fill(ts_start, ts_end, entry.frequency, formatted_data)

        gaps = find_gaps_in_series(filled_data)

        del filled_data[:]
        del formatted_data[:]
        del data[:]

        if sig_handler.interrupted:
            print 'shutting down'
            break

        for gap in gaps:
            g_start = make_aware(datetime.datetime.utcfromtimestamp(gap[0]), utc)
            g_end = make_aware(datetime.datetime.utcfromtimestamp(gap[1]), utc)

            # Skip gaps too small to be considered gaps
            if g_end - g_start < gap_duration_lower_bound:
                continue

            if verbose:
                print '  * gap'
                print '   *', g_start
                print '   *', g_end
                print '   * dur: ', g_end - g_start
            
            # See if there is already an existing gap ending on the 
            # current last_scan_point.  If so just "extend" the existing
            # gap (as long as it hasn't been processed) with up to date 
            # information rather than creating a new gap entry.
            #
            # This prevents subsequent scans during the current year
            # from creating a bunch of gap_inventory entries for 
            # a prolonged gap/inactive interface.
            g = None

            try:
                g = GapInventory.objects.get(row=entry, 
                        end_time=entry.last_scan_point,
                        processed=False)
            except ObjectDoesNotExist:
                pass

            if g:
                if verbose: print '   * update gap'
                g.end_time = g_end
            else:
                if verbose: print '   * new gap'
                g = GapInventory(row=entry, start_time=g_start, end_time=g_end)

            g.save()
            if verbose: print '   * +++'

        if future_end_time:
            # Current year, keep our spot
            entry.last_scan_point = make_aware(datetime.datetime.utcfromtimestamp(ts_end), utc)
        else:
            # Previous year, mark the row as processed
            entry.last_scan_point = entry.end_time
            entry.scan_complete = True

        entry.save()
        del gaps[:]
        if verbose: print '======='
        if sig_handler.interrupted:
            print 'shutting down'
            break
                    
    pass

def get_input(s):
    response = raw_input('ALERT: {0} [Y/n] '.format(s))
    if response and (response[0] == 'y' or response[0] == 'Y'):
        return True
    return False

def main():
    usage = '%prog [ --inventory | --gapscan | -l LIMIT | -v ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-i', '--inventory',
            dest='inventory', action='store_true', default=False,
            help='Generate main inventory.')
    parser.add_option('-g', '--gapscan',
            dest='gapscan', action='store_true', default=False,
            help='Use inventory to scan and inventory gaps in data.')
    parser.add_option('-t', '--threshold', metavar='THRESHOLD',
            type='int', dest='threshold', default=0,
            help='Length in seconds that a gap duration must be to be considered a gap (default=%default).')
    parser.add_option('-l', '--limit', metavar='LIMIT',
            type='int', dest='limit', default=0,
            help='Limit query loops for development (default=No Limit).')
    parser.add_option('-b', '--blank_ifalias',
            dest='blank', action='store_true', default=False,
            help='Allow interfaces with a blank/NULL ifalias value when generating primary inventory (default=%default).')
    parser.add_option('-v', '--verbose',
        dest='verbose', action='store_true', default=False,
        help='Verbose output.')
    options, args = parser.parse_args()

    if not options.inventory and not options.gapscan:
        print 'Select an action to perform'
        parser.print_help()
        return -1

    if options.limit == 0:
        if not get_input('Perform actions with no limit?'):
            print 'Aborting'
            return -1

    if options.inventory:
        print 'Generating inventory'
        generate_or_update_inventory(options.limit, options.blank,
                options.verbose)
    
    if options.gapscan:
        print 'Scanning data for gaps'
        generate_or_update_gap_inventory(options.limit, options.threshold,
                options.verbose)
    pass

if __name__ == '__main__':
    main()



