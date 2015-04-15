"""
Utility code for perfsonar esmond client programs.
"""

import calendar
import copy
import cStringIO
import csv
import datetime
import json
import os
import socket
import sys
import urllib
import urlparse

from optparse import OptionParser
from collections import OrderedDict
from dateutil.parser import parse

from .query import ApiFilters, DataPayload

# Event types with an associated "formatting type" to be 
# used by esmond-get, etc.
EVENT_MAP = OrderedDict([
    ('failures', 'failures'),
    ('histogram-owdelay', 'histogram'),
    ('histogram-rtt', 'histogram'),
    ('histogram-ttl', 'histogram'),
    ('histogram-ttl-reverse', 'histogram'),
    ('ntp-delay', 'numeric'),
    ('ntp-dispersion', 'numeric'),
    ('ntp-jitter', 'numeric'),
    ('ntp-offset', 'numeric'),
    ('ntp-polling-interval', 'numeric'),
    ('ntp-reach', 'numeric'),
    ('ntp-stratum', 'numeric'),
    ('ntp-wander', 'numeric'),
    ('packet-duplicates', 'numeric'),
    ('packet-duplicates-bidir', 'numeric'),
    ('packet-loss-rate', 'numeric'),
    ('packet-loss-rate-bidir', 'numeric'),
    ('packet-trace', 'packet_trace'),
    ('packet-count-lost', 'numeric'),
    ('packet-count-lost-bidir', 'numeric'),
    ('packet-count-sent', 'numeric'),
    ('packet-reorders', 'numeric'),
    ('packet-reorders-bidir', 'numeric'),
    ('packet-retransmits', 'numeric'),
    ('packet-retransmits-subintervals', 'subintervals'),
    ('path-mtu', 'numeric'),
    ('streams-packet-retransmits', 'number_list'),
    ('streams-packet-retransmits-subintervals', 'subinterval_list'),
    ('streams-throughput', 'number_list'),
    ('streams-throughput-subintervals', 'subinterval_list'),
    ('throughput', 'numeric'),
    ('throughput-subintervals', 'subintervals'),
    ('time-error-estimates', 'numeric'),
])

EVENT_TYPES = EVENT_MAP.keys()

def event_format(et):
    return EVENT_MAP[et]

DEFAULT_FIELDS = [
        'source', 
        'destination', 
        'measurement_agent',
        'input_source',
        'input_destination',
        'tool_name', 
]

class HeaderRow(OrderedDict):
    pass

#
# Exceptions for client operations
#

class EsmondClientException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class EsmondClientWarning(Warning): pass

#
# Output classes for clients
#

class EsmondOutput(object):
    """Base class for output classes."""

    def __init__(self, data, columns):
        self._data = data
        self._columns = columns
        self._output = None

        self._list_fields = None

        if not isinstance(self._data, list):
            raise EsmondClientException('Data arg must be a list')

        if len(self._data) and not isinstance(self._data[0], dict):
            raise EsmondClientException('Data arg must be a list of dicts')

    def get_output(self):
        raise NotImplementedError('Implement in subclasses.')

    def has_data(self):
        if len(self._data):
            return True
        else:
            return False

    def add_to_payload(self, d):
        if not isinstance(d, list):
            raise EsmondClientException('Arg to add_to_payload must be a list')

        self._data.extend(d)

    def _massage_row_dict(self, d):
        # scan first instance to see if we need to fix anything - 
        # no point in processing each row if not necessary.
        if self._list_fields == None:
            self._list_fields = []
            for k,v in d.items():
                if isinstance(v, list):
                    self._list_fields.append(k)

        # if no changes need to be made, just quit
        if len(self._list_fields) == 0:
            return d

        # don't change the original data
        new_d = copy.copy(d)

        # turn any lists into comma separated sequences
        for lf in self._list_fields:
            new_d[lf] = ', '.join( [ str(x) for x in new_d.get(lf) ] )

        return new_d


class HumanOutput(EsmondOutput):
    """Output for human/console output."""

    def __init__(self, data, columns, extended_data=False):
        super(HumanOutput, self).__init__(data, columns)

        self._extended_data = extended_data

    def get_output(self):
        entry_delim = '= + = + = + = + = + =\n'

        if not self._output:
            self._output = ''
            if self.has_data():
                for row in self._data:
                    if isinstance(row, HeaderRow):
                        for k,v in row.items():
                            self._output += '{0}: {1}\n'.format(k, v)
                    else:
                        row = self._massage_row_dict(row)
                        for c in self._columns:
                            self._output += '{0}: {1}\n'.format(c, row.get(c))
                        if self._extended_data:
                            for k,v in row.items():
                                if k in self._columns: continue
                                self._output += '{0}: {1}\n'.format(k,v)
                    self._output += entry_delim
                self._output = self._output[:self._output.rfind(entry_delim)]
            else:
                self._output = 'No data found.'

        return self._output

class JsonOutput(EsmondOutput):
    """Output results as a json blob."""

    def get_output(self):
        if not self._output:
            if self.has_data():
                self._output = json.dumps(self._data)
            else:
                self._output = json.dumps( [ {'msg': 'No data found.'} ] )
        return self._output

class CSVOutput(EsmondOutput):
    """Format output for CSV."""
    def get_output(self):
        if not self._output:
            cfile = cStringIO.StringIO()

            writer = csv.DictWriter(cfile, fieldnames=self._columns, extrasaction='ignore')
            writer.writeheader()
            if self.has_data():
                for row in self._data:
                    writer.writerow(self._massage_row_dict(row))
            else:
                d = dict( [ (x, 'No data') for x in self._columns ] )
                writer.writerow(d)

            self._output = cfile.getvalue()
            cfile.close()
        return self._output

def output_factory(options, data, columns):
    """
    Factory function to hand the appropriate output class 
    back to the client programs.
    """
    if options.format == 'human':
        if not options.metadata:
            return HumanOutput(data, columns)
        else:
            return HumanOutput(data, columns, extended_data=True)
    elif options.format == 'json':
        return JsonOutput(data, None)
    elif options.format == 'csv':
        return CSVOutput(data, columns)

class HostnameConversion(object):
    def __init__(self, options):
        self._options = options
        self._ns_cache = {}

        self._ip_fields = ['source', 'destination', 'ip', 'measurement_agent']

    def convert(self, d):
        if not self._options.ip:
            for i in self._ip_fields:
                if d.get(i):
                    ip = d.get(i)
                    if not self._ns_cache.get(ip):
                        self._ns_cache[ip] = socket.getfqdn(ip)
                    d[i] = self._ns_cache.get(ip)
        return d

#
# Generate output for different event types.
# 

def data_format_factory(options, seed_bulk_output=False):
    """
    Factory function to format the actual data for output.

    The appropriate sub-function is identified by the format_map.
    All functions hand back a header list of the appropriate columns
    for that measurment type and a list of dicts with corresponding keys.
    Both of which are passed off to the output rendering code.
    """

    # these columns/values are common to all measurements.
    header_base = [
        'source', 
        'destination', 
        'event_type', 
        'tool', 
        'summary_type', 
        'summary_window',
        'timestamp'
    ]

    ip_convert = HostnameConversion(options)

    def get_summary_type():
        if not options.summary_type:
            return 'base'
        else:
            return options.summary_type

    def get_payload(et):
        if not options.summary_type:
            # unsummarized data
            return et.get_data()
        else:
            # summary data
            s = et.get_summary(options.summary_type, options.summary_window)
            if not s: 
                return DataPayload()
            else:
                return s.get_data()

    def massage_output(d):
        """any modifications to the data dicts here."""

        # ip -> hostname if need be
        d = ip_convert.convert(d)

        return d

    def header_row(m, dp):
        """Special row that will be handled by the human readable 
        output class."""
        header = [
            ('source', m.source),
            ('destination', m.destination),
            ('event_type', options.type),
            ('tool', m.tool_name),
            ('summary_type', get_summary_type()),
            ('summary_window', options.summary_window),
            ('timestamp', str(dp.ts)),
        ]
        return HeaderRow(header)
        

    def format_numeric(conn):
        """aggregation, 300, 3600, 86400"""

        header = header_base + ['value']

        data = list()

        if seed_bulk_output: return header, data

        for m in conn.get_metadata():
            et = m.get_event_type(options.type)

            for dp in get_payload(et).data:
                d = dict(
                        source=m.source,
                        destination=m.destination,
                        event_type=options.type,
                        tool=m.tool_name,
                        summary_type=get_summary_type(),
                        summary_window=options.summary_window,
                        timestamp=str(dp.ts),
                        value=dp.val,
                    )
                data.append(massage_output(d))

        return header, data

    def format_failures(conn):

        header = header_base + ['msg']

        data = list()

        if seed_bulk_output: return header, data

        for m in conn.get_metadata():
            et = m.get_event_type(options.type)
            for dp in et.get_data().data:
                d = dict(
                    source=m.source,
                    destination=m.destination,
                    event_type=options.type,
                    tool=m.tool_name,
                    summary_type=get_summary_type(),
                    summary_window=options.summary_window,
                    timestamp=str(dp.ts),
                    msg=dp.val.get('error')
                )
                data.append(massage_output(d))

        return header, data

    def format_packet_trace(conn):

        test_header = ['ttl', 'query', 'success', 'ip', 'rtt', 'mtu', 'error_message']

        if options.format != 'human':
            header = header_base + test_header
        else:
            header = test_header

        data = list()

        if seed_bulk_output: return header, data

        for m in conn.get_metadata():
            et = m.get_event_type(options.type)
            for dp in et.get_data().data:
                if options.format == 'human':
                    data.append(massage_output(header_row(m,dp)))
                for val in dp.val:
                    if options.format != 'human':
                        d = dict(
                            source=m.source,
                            destination=m.destination,
                            event_type=options.type,
                            tool=m.tool_name,
                            summary_type=get_summary_type(),
                            summary_window=options.summary_window,
                            timestamp=str(dp.ts),
                            ttl=val.get('ttl'),
                            query=val.get('query'),
                            success=val.get('success'),
                            ip=val.get('ip'),
                            rtt=val.get('rtt'),
                            mtu=val.get('mtu'),
                            error_message=val.get('error_message')
                        )
                    else:
                        d = dict(
                            ttl=val.get('ttl'),
                            query=val.get('query'),
                            success=val.get('success'),
                            ip=val.get('ip'),
                            rtt=val.get('rtt'),
                            mtu=val.get('mtu'),
                            error_message=val.get('error_message')
                        )
                    data.append(massage_output(d))

        return header, data

    def format_histogram(conn):
        """aggregation, statistics, 300, 3600, 86400"""

        if options.summary_type == 'statistics':
            header = header_base + ['min', 'median', 'max', 
                'mean', 'mode', 'standard_deviation', 'variance', 
                'percentile_25', 'percentile_75', 'percentile_95']
        else:
            header = header_base + ['bucket', 'value']

        data = list()

        if seed_bulk_output: return header, data

        for m in conn.get_metadata():
            et = m.get_event_type(options.type)

            for dp in get_payload(et).data:
                if options.summary_type == 'statistics':
                    d = dict(
                        source=m.source,
                        destination=m.destination,
                        event_type=options.type,
                        tool=m.tool_name,
                        summary_type=get_summary_type(),
                        summary_window=options.summary_window,
                        timestamp=str(dp.ts),
                        min=dp.val.get('minimum'),
                        median=dp.val.get('median'),
                        max=dp.val.get('maximum'),
                        mean=dp.val.get('mean'),
                        mode=dp.val.get('mode'),
                        standard_deviation=dp.val.get('standard-deviation'),
                        variance=dp.val.get('variance'),
                        percentile_25=dp.val.get('percentile-25'),
                        percentile_75=dp.val.get('percentile-75'),
                        percentile_95=dp.val.get('percentile-95'),

                    )
                else:
                    d = dict(
                        source=m.source,
                        destination=m.destination,
                        event_type=options.type,
                        tool=m.tool_name,
                        summary_type=get_summary_type(),
                        summary_window=options.summary_window,
                        timestamp=str(dp.ts),
                        bucket=m.sample_bucket_width,
                        value=dp.val
                    )
                data.append(massage_output(d))

        return header, data

    def format_subintervals(conn):
        
        header = header_base + ['start', 'duration', 'value']

        data = list()

        if seed_bulk_output: return header, data

        for m in conn.get_metadata():
            et = m.get_event_type(options.type)

            for dp in et.get_data().data:
                for val in dp.val:
                    d = dict(
                        source=m.source,
                        destination=m.destination,
                        event_type=options.type,
                        tool=m.tool_name,
                        summary_type=get_summary_type(),
                        summary_window=options.summary_window,
                        timestamp=str(dp.ts),
                        start=val.get('start'),
                        duration=val.get('duration'),
                        value=val.get('val'),
                    )
                    data.append(massage_output(d))

        return header, data

    def format_number_list(conn):

        header = header_base + ['stream_num', 'value']

        data = list()

        if seed_bulk_output: return header, data

        for m in conn.get_metadata():
            et = m.get_event_type(options.type)
            for dp in et.get_data().data:
                for i in range(len(dp.val)):
                    d = dict(
                        source=m.source,
                        destination=m.destination,
                        event_type=options.type,
                        tool=m.tool_name,
                        summary_type=get_summary_type(),
                        summary_window=options.summary_window,
                        timestamp=str(dp.ts),
                        stream_num=i,
                        value=dp.val[i],
                    )
                    data.append(massage_output(d))

        return header, data

    def format_subinterval_list(conn):

        header = header_base + ['stream_num', 'start', 'duration', 'value']

        data = list()

        if seed_bulk_output: return header, data

        for m in conn.get_metadata():
            et = m.get_event_type(options.type)
            for dp in et.get_data().data:
                for stream_num in range(len(dp.val)):
                    for i in range(len(dp.val[stream_num])):
                        d = dict(
                            source=m.source,
                            destination=m.destination,
                            event_type=options.type,
                            tool=m.tool_name,
                            summary_type=get_summary_type(),
                            summary_window=options.summary_window,
                            timestamp=str(dp.ts),
                            stream_num=stream_num,
                            start=dp.val[stream_num][i].get('start'),
                            duration=dp.val[stream_num][i].get('duration'),
                            value=dp.val[stream_num][i].get('val'),
                        )
                        data.append(massage_output(d))

        return header, data

    format_map = dict(
        failures=format_failures,
        histogram=format_histogram,
        number_list=format_number_list,
        numeric=format_numeric,
        packet_trace=format_packet_trace,
        subintervals=format_subintervals,
        subinterval_list=format_subinterval_list,
    )

    return format_map.get(event_format(options.type))

# 
# Generate a filename and file handle for output.
#

def get_outfile(options, metadata, event_type):

    if not options.ip:
        source = socket.getfqdn(metadata.source)
        dest = socket.getfqdn(metadata.destination)
    else:
        source = metadata.source
        dest = metadata.destination

    def utciso(dt):
        return datetime.datetime.utcfromtimestamp(dt).strftime('%Y-%m-%d')

    s = utciso(metadata.filters.time_start)
    e = utciso(metadata.filters.time_end)

    outfile =  '{0}.{1}'.format('_'.join([source, dest, event_type, s, e]), options.format)

    return open(os.path.join(os.path.abspath(options.output_dir), outfile), 'wb')

#
# Command line argument validation functions
#

def check_url(options, parser):
    if not options.url:
        print '--url is a required arg\n'
        parser.print_help()
        sys.exit(-1)

    # trim URI from --url since people will cut and paste from 
    # the list of MAs.
    url = options.url
    up = urlparse.urlparse(url)
    if up.path.startswith('/esmond/perfsonar/archive'):
        options.url = url.replace(up.path, '')
        print '\n not necessary to add /esmond/perfsonar/archive to --url arg - trimming'

    try:
        urllib.urlopen(options.url)
    except Exception, e:
        print 'Could not open --url {0} - error: {1}'.format(options.url, e)

def check_valid_hostnames(options, parser, hn_args=[]):
    try:
        for hn in hn_args:
            if getattr(options, hn):
                socket.gethostbyname(getattr(options, hn))
    except:
        print '--{0} arg had invalid hostname: {1}'.format(hn, getattr(options, hn))
        sys.exit(-1)

def check_event_types(options, parser, require_event):
    if options.type and options.type not in EVENT_TYPES:
        print '{0} is not a valid event type'.format(options.type)
        list_event_types()
        sys.exit(-1)
    if require_event and not options.type:
        print 'The --event-type arg is required. Use -L to see a list.\n'
        parser.print_help()
        sys.exit(-1)

def check_formats(options, parser):
    f_args = ['human', 'json', 'csv']
    if options.format not in f_args:
        print '{0} is not a valid --output-format arg (one of: {1})'.format(options.format, f_args)
        sys.exit(-1)
    if options.format == 'csv' and options.metadata:
        print '--output-format csv can not be used with --metadata-extended'
        sys.exit(-1)

def check_summary(options, parser):
    s_args = ['aggregation', 'average', 'statistics']
    if options.summary_type and options.summary_type not in s_args:
        print '{0} is not a valid --summary-type arg (one of: {1})'.format(options.summary_type, s_args)
        sys.exit(-1)

def src_dest_required(options, parser):
    if not options.src or not (options.dest or (options.type is not None and options.type.startswith('ntp-'))):
        print '--src and --dest args are both required (ntp-* event types only require --src).\n'
        parser.print_help()
        sys.exit(-1)

def valid_output_dir(options, parser):
    if options.format == 'human':
        print 'please specify either json or csv --output-format for bulk output.\n'
        parser.print_help()
        sys.exit(-1)
    if not os.path.exists(os.path.abspath(options.output_dir)):
        print 'output path {0} does not exist.'.format(os.path.abspath(options.output_dir))
        sys.exit(-1)

#
# Misc command line --arg functions.
#

def list_event_types():
    print '\nValid event types:'
    for et in EVENT_TYPES:
        print '    {0}'.format(et)

#
# Utility functions to import into clients.
#

def get_start_and_end_times(options):
    """
    See:
    https://dateutil.readthedocs.org/en/latest/examples.html#parse-examples
    To see the variety of date formats that it will accept.
    """
    start = end = None

    if not options.start:
        start = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    else:
        try:
            start = parse(options.start)
        except:
            print 'could not parse --start-time arg: {0}'.format(options.start)
            sys.exit(-1)

    if not options.end:
        end = datetime.datetime.utcnow().replace(microsecond=0)
    else:
        try:
            end = parse(options.end)
        except:
            print 'could not parse --end-time arg: {0}'.format(options.end)
            sys.exit(-1)

    return start, end

#
# Canned option parsers for clients
#

def perfsonar_client_opts(require_src_dest=False, require_event=False,
    require_output=False):
    """
    Return a standard option parser for the perfsonar clients.
    """
    usage = '%prog [ -u URL -s SRC -d DEST | -a AGENT | -e EVENT | -t TOOL | -L | -o FORMAT | -v ]'
    usage += '\n--begin and --end args parsed by python-dateutil so fairly flexible with the date formats.'
    parser = OptionParser(usage=usage)
    parser.add_option('-u', '--url', metavar='URL',
            type='string', dest='url', 
            help='URL of esmond API you want to talk to.')
    parser.add_option('-s', '--src', metavar='SRC',
            type='string', dest='src', 
            help='Host originating the test.')
    parser.add_option('-d', '--dest', metavar='DEST',
            type='string', dest='dest', 
            help='Test endpoint.')
    parser.add_option('-a', '--agent', metavar='AGENT',
            type='string', dest='agent', 
            help='Host that initiated the test - useful for central MAs.')
    parser.add_option('-e', '--event-type', metavar='EVENT',
            type='string', dest='type', 
            help='Type of data (loss, latency, throughput, etc) - see -L arg.')
    parser.add_option('-t', '--tool', metavar='TOOL',
            type='string', dest='tool', 
            help='Tool used to run test (bwctl/iperf3, powstream, "bwctl/tracepath,traceroute", gridftp, etc).')
    parser.add_option('-S', '--start-time', metavar='START',
            type='string', dest='start', 
            help='Start time of query (default: 24 hours ago).')
    parser.add_option('-E', '--end-time', metavar='END',
            type='string', dest='end', 
            help='End time of query (default: now).')
    parser.add_option('-F', '--filter', metavar='FILTER',
            type='string', dest='filter', action='append',
            help='Specify additional query filters - format: -F key:value. Can be used multiple times, invalid filters will be ignored.')
    parser.add_option('-L', '--list-events',
            dest='list_event', action='store_true', default=False,
            help='List available event types.')
    parser.add_option('-M', '--metadata-extended',
            dest='metadata', action='store_true', default=False,
            help='Show extended metadata tool-specific values (can not be used with -o csv).')
    parser.add_option('-T', '--summary-type', metavar='SUMMARY_TYPE',
            type='string', dest='summary_type', 
            help='Request summary data of type [aggregation, average, statistics].')
    parser.add_option('-W', '--summary-window', metavar='SUMMARY_WINDOW',
            type='int', dest='summary_window', default=0,
            help='Timeframe in seconds described by the summary (default: %default).')
    parser.add_option('-o', '--output-format', metavar='O_FORMAT',
            type='string', dest='format', default='human',
            help='Output format [human, json, csv] (default: human).')
    if require_output:
        parser.add_option('-D', '--output-directory', metavar='DIR',
                type='string', dest='output_dir', default=os.getcwd(),
                help='Directory to output files to (default: %default).')
    parser.add_option('-I', '--ip',
            dest='ip', action='store_true', default=False,
            help='Show source/dest as IP addresses, not hostnames.')
    parser.add_option('-v', '--verbose',
        dest='verbose', action='store_true', default=False,
        help='Verbose output.')
    options, args = parser.parse_args()

    if options.list_event:
        list_event_types()
        sys.exit(0)

    check_url(options, parser)

    if require_src_dest:
        src_dest_required(options, parser)

    if require_output:
        valid_output_dir(options, parser)

    check_valid_hostnames(options, parser, hn_args=['src', 'dest', 'agent'])

    check_event_types(options, parser, require_event)

    check_summary(options, parser)

    check_formats(options, parser)

    return options, args

def perfsonar_client_filters(options):
    """
    Return a standard filter object based on the opts in 
    perfsonar_client_opts()
    """

    start, end = get_start_and_end_times(options)

    filters = ApiFilters()
    filters.source = options.src
    filters.destination = options.dest
    filters.measurement_agent = options.agent
    filters.event_type = options.type
    filters.time_start = calendar.timegm(start.utctimetuple())
    filters.time_end = calendar.timegm(end.utctimetuple())
    filters.tool_name = options.tool
    filters.summary_type = options.summary_type
    if options.summary_window:
        filters.summary_window = options.summary_window
    filters.verbose = options.verbose

    if options.filter:
        # Apply arbritrary metadata filters
        for f in options.filter:
            if f.find(':') == -1:
                print '--filter arg {0} should be of the format key:value'.format(f)
                continue
            k,v = f.split(':')
            key = k.replace('-', '_')
            if not hasattr(filters, k):
                print '--filter arg {0} is not a valid filtering value'.format(key)
                continue
            setattr(filters, key, v)

    return filters

