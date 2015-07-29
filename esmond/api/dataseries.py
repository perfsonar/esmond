"""
Classes used by the rest api and other utilities that handle data formatting
and gaps in a series of data.
"""
import datetime

from collections import OrderedDict

from esmond.util import atdecode, atencode

class TimerangeException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class TimerangeWarning(Warning): pass

class QueryUtil(object):
    """Class holding common query methods used by multiple resources 
    and data structures to validate incoming request elements."""

    _timerange_limits = {
        11: datetime.timedelta(days=30),
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
            raise TimerangeException('invalid aggregation level: %s' %
                    obj.agg)

        return True

    @staticmethod
    def format_cassandra_data_payload(data, in_ms=False, coerce_to_bins=None):
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

            d = {'ts': ts/divs[in_ms], 'val': row['val']}
            
            # Further options for different data sets.
            if row.has_key('is_valid'): # Base rates
                if row['is_valid'] == 0 : d['val'] = None
            elif row.has_key('cf'): # Aggregations
                if row['cf'] == 'min' or row['cf'] == 'max':
                    d['m_ts'] = row['m_ts']
                    if d['m_ts']:
                        d['m_ts'] = d['m_ts']/divs[in_ms]
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
            filled_range.append((s,dict(ts=s, val=None)))
            s += freq
        
        # Make it a ordered dict
        fill = OrderedDict(filled_range)
        
        # Go through the original data and plug in 
        # good values
        for dp in data:
            fill[dp['ts']]['val'] = dp['val']

        for i in fill.values():
            yield i

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


def fit_to_bins(freq, ts_prev, val_prev, ts_curr, val_curr):
    """Fit successive counter measurements into evenly spaced bins.

    The return value is a dictionary with bin names as keys and integer amounts to
    increment the bin by as values.

    In order to be able to compare metrics to one another we need to have a
    common sequence of equally spaced timestamps. The data comes from the
    network in imprecise intervals. This code converts measurements as them come
    in into bins with evenly spaced time stamps.

    bin_prev      bin_mid (0..n bins)         bin_curr      bin_next
    |             |                           |             |
    |   ts_prev   |                           |   ts_curr   |
    |       |     |                           |       |     |
    v       v     v                           v       v     v
    +-------------+-------------+-------------+-------------+
    |       [.....|..... current|measurement .|.......]     |
    +-------------+-------------+-------------+-------------+  ----> time
            \     /\                          /\      /
             \   /  \                        /  \    /
              \ /    \__________  __________/    \  /
               v                \/                \/
            frac_prev        frac_mid           frac_curr

    The diagram shows the equally spaced bins (freq units apart) which this
    function will fit the data into.

    The diagram above captures all the possible collection states, allowing for
    data that belongs a partial bin on the left, zero or more bins in the middle
    and a partial bin on the right.  In the common cases there will be zero or
    one bin in bin_mid, but if measurements are come in less frequently than
    freq there may be more than one bin.

    The input data is the frequency of the bins, followed by the timestamp and
    value of the previous measurement and the timestamp and value of the current
    measurement. The measurements are expect to be counters that always
    increase.

    This code goes to great lengths to deal with allocating the remainder of
    integer division in proporionate fashion.

    Here are some examples.  In this case everything is in bin_prev:

    >>> fit_to_bins(30, 0, 0, 30, 100)
    {0: 100, 30: 0}

    The data is perfectly aligned with the bins and all of the data ends up in
    bin 0.

    In this case, there is no bin_mid at all:

    >>> fit_to_bins(30, 31, 100, 62, 213)
    {60: 7, 30: 106}

    We 29/31 of data goes into bin 30 and the remaining 2/31 goes into bin 60.
    The example counter values here were chosen to show how the remainder code
    operates.

    In this case there is no bin_mid, everything is in bin_prev or bin_curr:

    >>> fit_to_bins(30, 90, 100, 121, 200)
    {120: 3, 90: 97}

    30/31 of the data goes into bin 90 and 1/31 goes into bin 120.

    This example shows where bin_mid is larger than one:

    >>> fit_to_bins(30, 89, 100, 181, 200)
    {120: 33, 180: 1, 90: 33, 60: 0, 150: 33}
    """

    assert ts_curr > ts_prev

    bin_prev = ts_prev - (ts_prev % freq)
    bin_mid = (ts_prev + freq) - (ts_prev % freq)
    bin_curr = ts_curr - (ts_curr % freq)

    delta_t = ts_curr - ts_prev
    delta_v = val_curr - val_prev

    # if samples are less than freq apart and both in the same bin
    # all of the data goes into the same bin
    if bin_curr == bin_prev:
        return {bin_prev: delta_v}

    assert bin_prev < bin_mid <= bin_curr

    frac_prev = (bin_mid - ts_prev)/float(delta_t)
    frac_curr = (ts_curr - bin_curr)/float(delta_t)

    p = int(round(frac_prev * delta_v))
    c = int(round(frac_curr * delta_v))

    # updates maps bins to byte deltas
    updates = {}
    updates[bin_prev] = p
    updates[bin_curr] = c

    fractions = []
    fractions.append((bin_prev, frac_prev))
    fractions.append((bin_curr, frac_curr))

    if bin_curr - bin_mid > 0:
        frac_mid = (bin_curr - bin_mid)/float(delta_t)
        m = frac_mid * delta_v
        n_mid_bins = (bin_curr-bin_mid)/freq
        m_per_midbin = int(round(m / n_mid_bins))
        frac_per_midbin = frac_mid / n_mid_bins

        for b in range(bin_mid, bin_curr, freq):
            updates[b] = m_per_midbin
            fractions.append((b, frac_per_midbin))

    remainder = delta_v - sum(updates.itervalues())
    if remainder != 0:
        #print "%d bytes left over, %d bins" % (remainder, len(updates))
        if remainder > 0:
            incr = 1
            reverse = True
        else:
            incr = -1
            reverse = False

        fractions.sort(key=lambda x: x[1], reverse=reverse)
        for i in range(abs(remainder)):
            b = fractions[i % len(updates)][0]
            updates[b] += incr

    return updates

