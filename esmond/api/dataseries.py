"""
Classes used by the rest api and other utilities that handle data formatting
and gaps in a series of data.
"""
import datetime

from collections import OrderedDict

from esmond.util import atdecode, atencode
from tastypie.exceptions import BadRequest

class QueryUtil(object):
    """Class holding common query methods used by multiple resources 
    and data structures to validate incoming request elements."""

    _timerange_limits = {
        30: datetime.timedelta(days=30),
        60: datetime.timedelta(days=30),
        300: datetime.timedelta(days=30),
        3600: datetime.timedelta(days=365),
        86400: datetime.timedelta(days=365*10),
    }

    timeseries_request_types = ['RawData', 'BaseRate', 'Aggs']
    bulk_request_types = ['timeseries', 'interface']

    @staticmethod
    def decode_datapath(datapath):
        return [ atdecode(step) for step in datapath ]

    @staticmethod
    def encode_datapath(datapath):
        return [ atencode(step) for step in datapath ]

    @staticmethod
    def valid_timerange(obj, in_ms=False):
        """Check the requested time range against the requested aggregation 
        level and limit if too much data was requested.

        The in_ms flag is set to true if a given resource (like the 
        /timeseries/ namespace) is doing business in milliseconds rather 
        than seconds."""
        if in_ms:
            s = datetime.timedelta(milliseconds=obj.begin_time)
            e = datetime.timedelta(milliseconds=obj.end_time)
        else:
            s = datetime.timedelta(seconds=obj.begin_time)
            e = datetime.timedelta(seconds=obj.end_time)
        
        divs = { False: 1, True: 1000 }

        try:
            if e - s > QueryUtil._timerange_limits[obj.agg/divs[in_ms]]:
                return False
        except KeyError:
            raise BadRequest('invalid aggregation level: %s' %
                    obj.agg)

        return True

    @staticmethod
    def format_data_payload(data, in_ms=False, coerce_to_bins=None):
        """Massage results from cassandra for json return payload.

        The in_ms flag is set to true if a given resource (like the 
        /timeseries/ namespace) is doing business in milliseconds rather 
        than seconds.

        If coerce_to_bins is not None, truncate the timestamp to the
        the bins spaced coerce_to_bins ms apart. This is useful for 
        fitting raw data to bin boundaries."""

        divs = { False: 1000, True: 1 }

        results = []

        for row in data:
            ts = row['ts']

            if coerce_to_bins:
                ts -= ts % coerce_to_bins

            d = [ts/divs[in_ms], row['val']]
            
            # Further options for different data sets.
            if row.has_key('is_valid'): # Base rates
                if row['is_valid'] == 0: d[1] = None
            elif row.has_key('cf'): # Aggregations
                pass
            else: # Raw Data
                pass
            
            results.append(d)

        return results

class Fill(object):
    """Set of methods to verify that a series of binned data contains
    the correct number of datapoints over a given time range, and if 
    not, fill the missing bins with an invalid value before returning
    the data to the client.

    Normally persister will backfill gaps in the data in the DB but gaps
    could be returned under the following circumstances:

    1 - The most common scenario is when requesting up to the minute 
    binned data where the most recent value might not have been written 
    yet.

    2 - The query might span when a new device started having data 
    recorded.

    3 - A gap (like if a device was offline for a period of time) might 
    exceed the "heartbeat limit" and generate a span too long to reasonably
    fill with invalid data points.
    """
    @staticmethod
    def expected_bin_count(start_bin, end_bin, freq):
        """Get expected number of bins in a given range of bins."""
        return ((end_bin - start_bin) / freq) + 1

    @staticmethod
    def get_expected_first_bin(begin, freq):
        """Get the first bin of a given frequency based on the begin ts
        of a timeseries query."""
        # Determine the first bin in the series based on the begin
        # timestamp in the timeseries request.
        #
        # Bin math will round down to last bin but timerange queries will
        # return the next bin.  That is, given a 30 second bin, a begin
        # timestamp of 15 seconds past the minute will yield a bin calc
        # of on the minute, but but the time range query will return 
        # 30 seconds past the minute as the first result.
        #
        # A begin timestamp falling directly on a bin will return 
        # that bin.
        bin = (begin/freq)*freq
        if bin < begin:
            return bin+freq
        elif bin == begin:
            return bin
        else:
            # Shouldn't happen
            raise RuntimeError

    @staticmethod
    def get_bin_alignment(begin, end, freq):
        """Generate a few values needed for checking and filling a series if 
        need be."""
        start_bin = Fill.get_expected_first_bin(begin,freq)
        end_bin = (end/freq)*freq
        expected_bins = Fill.expected_bin_count(start_bin, end_bin, freq)
        
        return start_bin, end_bin, expected_bins

    @staticmethod
    def generate_filled_series(start_bin, end_bin, freq, data):
        """Genrate a new 'filled' series if the returned series has unexpected
        gaps.  Initialize a new range based in the requested time range as
        an OrderedDict, then iterate through original series to retain original
        values.
        """
        # Generate the empty "proper" timerange
        filled_range = []
        s = start_bin + 0 # copy it
        while s <= end_bin:
            filled_range.append((s,None))
            s += freq

        # Make it a ordered dict
        fill = OrderedDict(filled_range)

        # Go through the original data and plug in 
        # good values

        for dp in data:
            fill[dp[0]] = dp[1]

        for i in fill.items():
            yield list(i)

    @staticmethod
    def verify_fill(begin, end, freq, data):
        """Top-level function to inspect a returned series for gaps.
        Returns the original series of the count is correct, else will
        return a new filled series."""
        begin, end, freq = int(begin), int(end), int(freq)
        start_bin,end_bin,expected_bins = Fill.get_bin_alignment(begin, end, freq)
        #print 'got :', len(data)
        #print 'need:', Fill.expected_bin_count(start_bin,end_bin,freq)
        if len(data) == Fill.expected_bin_count(start_bin,end_bin,freq):
            #print 'verify: not filling'
            return data
        else:
            #print 'verify: filling'
            return list(Fill.generate_filled_series(start_bin,end_bin,freq,data))


