*****************************************************************
Client libraries and programs for esmond: ESnet Monitoring Daemon
*****************************************************************

==================================
Client programs for perfSONAR data
==================================

esmond-ps-get-endpoints
=======================

A discovery tool to quickly see what tests have been stored in an esmond
perfSONAR archive. Give a list of tests in MA with the following sample
information:

::

    source: anl-owamp.es.net
    destination: lsvn-owamp.es.net
    measurement_agent: anl-owamp.es.net
    tool_name: bwctl/tracepath,traceroute
    event_type: packet-trace, failures, path-mtu


esmond-ps-get-metadata
======================

Similar to get-endpoints, but this will fetch the actual metadata test data
from an esmond perfSONAR archive.  By default it will show the measurements
that are common to all tests:

::

    source
    destination
    measurement_agent
    input_source
    input_destination
    tool_name

Including the --metadata-extended will also show the per-test measurements.
This option can not be used with the CSV output option.

Sample default output:

::

    source: perfsonar-latency-v4.esc.qmul.ac.uk
    destination: anl-owamp.es.net
    measurement_agent: anl-owamp.es.net
    input_source: perfsonar-latency.esc.qmul.ac.uk
    input_destination: anl-owamp.es.net
    tool_name: powstream


Sample output with the --metadata-extended flag:

::

    source: perfsonar-latency-v4.esc.qmul.ac.uk
    destination: anl-owamp.es.net
    measurement_agent: anl-owamp.es.net
    input_source: perfsonar-latency.esc.qmul.ac.uk
    input_destination: anl-owamp.es.net
    tool_name: powstream
    ip_transport_protocol: udp
    sample_bucket_width: 0.0001
    sample_size: 600
    subject_type: point-to-point
    time_duration: 60
    time_interval: 0
    time_probe_interval: 0.1


esmond-ps-get
=============

Tool to pull smaller, more focused sets of data from a perfSONAR MA. This
requires a source/dest pair as well as a specific event type. Intended to
be more of a "quick look" at some data.  To gather more/larger amounts
of data, esmond-ps-get-bulk is intended for that.

esmond-ps-get-bulk
==================

Tool to pull non-trivial amounts of data from a perfSONAR esmond archive.

Iterates through the metadata matching the user query and makes incremental
data requests from the archive so as not to overwhelm the data store. When
all of the data for a given event type associated with a given metadata
has been gathered, it will be written to disc in either json or csv format,
with the format:

::

    <source>_<dest>_<event_type>_<start_time>_<end_time>.csv|.json


So one would end up with a set of output files that look like this:

::

    perfsonar.ascr.doe.gov_anl-owamp.es.net_failures_2015-03-15_2015-04-02.csv
    perfsonar.ascr.doe.gov_anl-owamp.es.net_histogram-owdelay_2015-03-15_2015-04-02.csv
    perfsonar.ascr.doe.gov_anl-owamp.es.net_histogram-ttl_2015-03-15_2015-04-02.csv
    perfsonar.ascr.doe.gov_anl-owamp.es.net_packet-count-lost_2015-03-15_2015-04-02.csv
    perfsonar.ascr.doe.gov_anl-owamp.es.net_packet-count-sent_2015-03-15_2015-04-02.csv
    perfsonar.ascr.doe.gov_anl-owamp.es.net_packet-duplicates_2015-03-15_2015-04-02.csv
    perfsonar.ascr.doe.gov_anl-owamp.es.net_packet-loss-rate_2015-03-15_2015-04-02.csv
    perfsonar.ascr.doe.gov_anl-owamp.es.net_time-error-estimates_2015-03-15_2015-04-02.csv


After the file for the metadata/event-type has been written, it will continue
to the next event-type or metadata as appropriate.  The "human readable"
output format is not available in this program.

While designed to not murder an MA with massive data queries, this command can
return a lot of data, so it is recommended to limit the scope of your query
by source, dest, event-type, etc.

General esmond-ps perfSONAR client usage
========================================

Core and/or required args
-------------------------

These args are common to all clients.  See the --help flag to get a
complete list of options.

--url
~~~~~

Required on all programs. Just the base protocol://host:port is required. When
querying a default perfSONAR install, it is not necessary to include the URI
as well.  For example given a MA access URL of:

::

    http://albq-owamp-v6.es.net:8085/esmond/perfsonar/archive


It is only necessary to provide:

::

    --url http://albq-owamp-v6.es.net:8085

--src and --dest
~~~~~~~~~~~~~~~~

Source and destination for the tests.  Both are required for some of the
clients.  This is input as raw IP addresses.

--start-time and --end-time
~~~~~~~~~~~~~~~~~~~~~~~~~~~

If these args are not included, it will default to grabbing data from the
previous 24 hours.  Arg input is parsed by the Python dateutil library
which will preform pretty intelligent guesses about incoming date formats.
It will understand structured things like ISO datetime formats, and more
organic ones like "January 1 2015" - if a time is not given, will default
00:00 am, etc.

See: https://dateutil.readthedocs.org/en/latest/examples.html#parse-examples
To see the variety of date formats that it will accept.

--event-type
~~~~~~~~~~~~

Requires a valid measurement event type.  The command line arg --list-events
can be used to give a list of valid event types.

Sometimes required.

Additional filtering args
-------------------------

There are additional args that can be used to filter results as well:

::

    --agent
    --tool
    --summary-type
    --summary-window


These should be fairly self-explanatory.

--filter
~~~~~~~~

An additional power user filter that takes the format:

::

    --filter key:value


This will add filters to the query string that goes to the MA. This
option can be used more than once to add multiple filters to the
query string, invalid filters will be ignored.

Output
------

--output-format
~~~~~~~~~~~~~~~

Select the desired output format from the choices 'human,' 'json' and
'csv.' Default is human readable for viewing in a terminal.  The human
and csv options are not allowed in all circumstances.

--output-directory
~~~~~~~~~~~~~~~~~~

Required by esmond-ps-get-bulk - specifies a directory to write output
files to.  Will default to the current working directory.

--ip
~~~~

By default in the output, IP addresses (source, dest, agent, etc) will be
converted to a human readable fully qualified domain name. Using the -ip
flag will stop this conversion and display all hostnames as raw IP addresses.

Example perfSONAR command line client usage
===========================================

esmond-ps-get-endpoints examples
--------------------------------

Get a list of all tests over the last 24 hours available in a given MA, show
src/dest as raw ip addresses:

::

    esmond-ps-get-endpoints --url http://nettest.lbl.gov/ --ip

Find all the powstream test data in a given MA since the beginning of the year:

::

    esmond-ps-get-endpoints --url http://nettest.lbl.gov/ --ip --start-time 'January 1' --tool powstream

esmond-ps-get-metadata examples
-------------------------------

Show all test metadata for a given destination over the last 24 hours,
displayed in CSV format:

::

    esmond-ps-get-metadata --url http://nettest.lbl.gov/ --dest 198.129.254.62 --output-format csv

Show more detailed metadata information from an MA for all bwctl/iperf3
tests involving a particular source since the beginning of the year,
showing extended test metadata like test duration, interval, etc
as a list of json objects:

::

    esmond-ps-get-metadata --url http://nettest.lbl.gov/ --tool bwctl/iperf3 --src 198.124.238.130 --metadata-extended --output-format json --start-time 'Jan 1'

esmond-ps-get examples
----------------------

Retrieve the past 24 hours of packet trace data for a src/dest pair:

::

    esmond-ps-get --url http://nettest.lbl.gov/ --src  131.243.24.11 --dest 198.129.254.62 --event-type packet-trace

Get throughput data starting at the beginning of the month (presuming the
month is April) for a src/dest pair:

::

    esmond-ps-get --url http://nettest.lbl.gov/ --src  131.243.24.11 --dest 198.129.254.114 --event-type throughput --start-time 'April 1'

esmond-ps-get-bulk examples
---------------------------

Pull all failures event-type information from an MA since the beginning
of the year and write out to current working directory as a set of json
files:

::

    esmond-ps-get-bulk --url http://anl-owamp.es.net:8085  --event-type failures --start-time 'January 1' --output-format json


Pull all data associated with a given source from the past 24 hours and write
to a custom directory in CSV format:

::

    esmond-ps-get-bulk --url http://anl-owamp.es.net:8085  --src 192.73.213.28 --output-format csv -D ~/Desktop/tmp


Pull data for all event types measured by the powstream tool since the start
of March and write to a custom directory in json format:

::

    esmond-ps-get-bulk --url http://anl-owamp.es.net:8085  --tool powstream --start-time 'March 1' --output-format json -D ~/Desktop/tmp


Pull all the data in an MA for the past 24 hours and output to current working
directory in json format:

::

    esmond-ps-get-bulk --url http://nettest.lbl.gov/ --output-format json

======================================
Esmond perfSONAR data loading programs
======================================

There are also client programs for writing data to an MA. This requires that the
user have write access to the esmond instance.

Core and/or required args
=========================

The following args are required/generally needed by all programs that write
data to an MA.

--user and --key
----------------

Both of these args are required. It is the username and api key string that
was generated on the MA to allow access to it.

--url
-----

The url of the MA. Format http://example.com:80 where http or https can be the
prefix. Just host and port information, no uri information. Defaults to
http://localhost:8080.

--script_alias
--------------

Used when the REST API has been deployed under Apache using a ScriptAlias
directive/prefix. This would commonly be set to 'esmond' since the canned
CentOS deployments use script alias of /esmond to allow other things to
run on the webserver (ie: so the REST API is not the root of the webserver).
The default value is '/' - which will not perform any prefixing.

esmond-ps-load-gridftp
======================

Utility to parse and load GridFTP data.

This will read the default gridftp logs, process the "Transfer stats" entries,
and upload the results to the pS esmond backend as metadata and either
throughput or failures event types. This has been expanded (using the --json
flag) to read the new json formatted gridftp logs that contain additional
event types like retransmits, iostat, etc.

The basic use case would that this script be run from cron periodically
over the day to parse and load data from the gridftp logs into an esmond
backend.  The scanning code will write out the contents of the record that
was last loaded as a python pickle file to disc.  This state file is used
to pick up from the point the last processing pass got to.

Basic usage: the following arguments are required for baseline operation:

::

    esmond-ps-load-gridftp -f ~/Desktop/gridftp.log -U http://localhost:8000 -u mgoode -k api_key_for_mgoode

In addition to the flags outlined above, required args
------------------------------------------------------

--file
~~~~~~

The path to the logfile to process.  The code will normalize the path,
so relative paths are fine.  No default.

Commonly used args
------------------

--json
~~~~~~

Specifies that the log indicate by the --file flag is the json-formatted
GridFTP files.

--pickle
~~~~~~~~

The path to the pickle file the scanning code uses to store the "state"
of the last record that has been processed.  Code uses this to know where
to pick up on subsequent scans.  This defaults to ./load_grid_ftp.pickle
or ./load_grid_ftp.json.pickle as appropriate - will probably want to
change this to a fully qualified path somewhere.

--dont_write
~~~~~~~~~~~~

Suppresses writing the pickle state file out when the file has been scanned.
This would be used when manually/etc processing one or more log files where
it is desired to just parse the contents of an entire static (ie: no longer
being written to) file.  Defaults to False - use this flag to suppress
writing the state file.

--log_dir
~~~~~~~~~

Can be used to specify a directory to write a log from the program to.
If this is not set (the default), then log output will go to stdout.

Optional content selection args
-------------------------------

The gridftp logs contain information on the user, the file being sent and
the volume being written to.  Since these might be considered to be sensitive
data, this information is not sent to the backend by default.  The following
flags can be set to send that information if desired:

::

    -F (--file_attr): send gridftp-file/value of FILE
    -N (--name_attr): send gridftp-user/value of USER (name)
    -V (--volume_attr): send gridftp-volume/value of VOLUME

Other/development args
----------------------

--single
~~~~~~~~

Will process a single value starting at the last record sent and stop.
This is mostly used for development/testing to "step through" a file
record by record.  It will set the pickle state file to the single
record sent before exiting.

Running from cron and dealing with rotated logs
-----------------------------------------------

When running from cron the script should be run with the required arguments
enumerated above and set the --pickle arg to a fully qualified path, and
the --file arg should point to the logfile.  It can be run at whatever
frequency the user desires as the code will pick up from the last record
that was processed.  When running from cron, the --log_dir arg should
be set so the logging output is written to a file rather than sent to
stdout.

Log rotation interfere with this if the code has not finished scanning
a log before it is rotated and renamed.  If the code is run on the "fresh"
log, it will not find the last record that was processed.   To deal with
this, this script should also be kicked off using the "prerotate" hook
that logrotated provides.

When running this as a prerotate job, the -D (--delete_state) flag should
also be used.  This will delete the pickle state file when the scan is
done with the log before it is rotated.  The state file is deleted so that
when the next cron job runs on the new "fresh" log, it will just start
scaning from the beginning and not try to search for a record that it
won't find.

Alternately if the user doesn't need the data to be periodically loaded,
one could opt to exclusively run this as a logrotated/prerotate job such
that the entire log is processed in one throw before it is rotated.  In that
case the --dont_write flag should be used.

esmond-ps-pipe
==============

Utility to take json-formatted output from bwctl (--parsable flag) and
load the data into an esmond MA.

Currently supported tool types:

* iperf3

Usage
-----

Primarily relies on the required command line args (--user, --key, etc)
outlined above and piped input from the bwctl command:

::

    bwctl -c lbl-pt1.es.net -s llnl-pt1.es.net -T iperf3 --parsable --verbose |& esmond-ps-pipe --user mgoode --key api_key_for_mgoode

The primary thing (other than using a -T <tool> that is supported) is that bwctl
**must** be run with both the --parsable flag (which generates the json output)
**and also** the --verbose flag. esmond-ps-pipe pulls important metadata from
the --verbose output, and uses it to identify the json part of the output.

If the program is unable to extract the necessary metadata and a valid json
payload from the piped input, it will log a fatal error and exit.

Shell redirection
-----------------
Note the "**|&**" that redirects the output from bwctl to esmond-ps-pipe - both stdout and stderr need to be piped to esmond-ps-pipe. That should work on Csh and current versions of Bash. This may vary from shell to shell - for example, older versions of Bash might need to use "**2>&1 |**" or something similar. The short of it is, the shell-specific way to redirect both stdout and stderr from bwctl is necessary.

If an error that looks something like this is generated:

::

    ts=2015-10-20 11:37:24,881 event=id_and_extract.error id=1445366244 could not extract tool_name
    ts=2015-10-20 11:37:24,881 event=id_and_extract.error id=1445366244 could not extract input_source
    ts=2015-10-20 11:37:24,881 event=id_and_extract.error id=1445366244 could not extract input_destination
    ts=2015-10-20 11:37:24,881 event=main.fatal id=1445366244 could not extract metadata and valid json from input
    ts=2015-10-20 11:37:24,882 event=main.fatal id=1445366244 exiting

It is likely that the redirection is not being executed properly because tool_name, input_source and input_destination are all read from the bwctl headers that are being written to stderr.

Optional args
-------------

--log_dir
~~~~~~~~~

Like esmond-ps-load-gridftp, this takes a --log_dir arg which specifies the
directory that logging output should be written to. If not specified, logging
output will got to stdout.

Event types
-----------

iperf3
~~~~~~

The following event types are extracted (as appropriate RE: TCP, UDP, streams,
etc) from the iperf3 data:

::

    throughput
    throughput-subintervals
    packet-retransmits-subintervals
    streams-packet-retransmits
    streams-packet-retransmits-subintervals
    streams-throughput
    streams-throughput-subintervals
    packet-retransmits
    packet-count-lost
    packet-count-sent
    packet-loss-rate



=======================================
API Client Libraries for perfSONAR data
=======================================

The pS data can be queried, retrieved and posted to the esmond/cassandra backend
via a REST interface.  This is streamlined by the following libraries::

    esmond.api.client.perfsonar.query
    esmond.api.client.perfsonar.post

Initializing the query interface
================================

The query libarary has two main "top level" classes: ApiFilters and ApiConnect.
ApiFilters lets the user, through a series of properties, set the primary query
criteria like time ranges, source, destination, etc.  The following criteria
properties can be set::

    destination
    input_destination
    input_source
    measurement_agent
    source
    tool_name
    time
    time_start
    time_end
    time_range
    verbose (for debugging/extended output)

After the query criteria have been set in the ApiFilters object, that is passed
to the ApiConnect object as one of the args.

The ApiConnect object takes the url of the REST interface as an argument, along
with the filters object, and optional username and api_key arguments if the user
is accessing restricted functionality of the REST interface (non-public data,
getting around throttling restrictions, etc).

A complete example of setting this up::

    from esmond.api.client.perfsonar.query import ApiConnect, ApiFilters

    filters = ApiFilters()

    filters.verbose = True
    filters.time_start = time.time() - 3600
    filters.time_end = time.time()
    filters.source = '198.129.254.30'
    filters.tool_name = 'bwctl/iperf3'

    conn = ApiConnect('http://localhost:8000/', filters)

NOTE: the default perfSONAR/esmond deployments use a WSGIScriptAlias of /esmond
prefixing the URI - this is set in Apache.  The client libraries default to
using this.  But if one is doing development against the django runserver dev
server, or if this has been set up differently, then the optional kwarg
"script_alias" will need to be set as well.  Against the dev server, it can
be set to script_alias=None since the Apache directive is not in place.

Retrieving the data
===================

The basic design of the returned data is a hierarchy of encapsulation objects
that return additioanl objects objects, etc.  All of the returned objects
have informative __repr__ methods defined, that might help when doing
initial development.

The top level call to the ApiConnect object is get_metadata().  This is an
iterator that will return a series of Metadata objects matching the criteria
given in the ApiFilters object.  At the top level, the Metadata object exposes
a series of properties giving additional information about the returned
metadata.  Example of this::

    for md in conn.get_metadata():
        print md # debug info in __repr__
        print md.destination
        print md.ip_packet_interval
        ...

The following top-level properties are exposed by the Metadata object::

    destination
    event_types (a list of event type names - more on this)
    input_destination
    input_source
    ip_packet_interval
    measurement_agent
    metadata_key
    sample_bucket_width
    source
    subject_type
    time_duration
    tool_name
    uri

The next in the data object hierarchy is fetching the event types that are
associated with the metadata.  This can be done by either using an interator
to access all of the event types::

    for et in md.get_all_event_types():
        print et.event_type
        ...

or fetching a single one by name::

    et = md.get_event_type('histogram-owdelay')

The top-level property "event_types" will return a list of valid event types
that can be passed as the argument to get_event_type.

The EventType objects expose the following top-level properties::

    base_uri
    event_type
    data_type
    summaries (a list of associated summaries - more on this)

The the actual underlying data are retrieved from the EventType objects by a call to the get_data() method, which returns a DataPayload object::

    dpay = et.get_data()

The DataPayload object expose the following top-level properties::

    data_type
    data

The data_type property returns the underlying data_type in the payload, and
the data property returns a list of DataPoint or DataHistogram objects as
is appropriate.  Both the DataPoint and DataHistogram objects expose the
following properties::

    ts (measurement timestamp as a UTC python datetime object)
    val (the measurement or hisogram dict)
    ts_epoch (the ts object expressed as UNIX time)

Putting it all together, to iterate throught all of the returned data::

    for et in md.get_all_event_types():
        dpay = et.get_data()
        print dpay.data_type
        for dp in dpay.data:
            print dp.ts, dp.val

Some event types have aggregated summaries associated with them.  Retrieving
the summaries from an EventType object is very similar to pulling event types
from a Metadata object.  The following properties/methods are analogous to the
ones that exist in the Metadata object::

    summaries

This returns a list of two-element tuples: (summary-type, summary-window). The
window is the time duration of the aggregation rollups.

The summary data can be retrieved by either using an iterator::

    for summ in et.get_all_summaries():
        ...

Or a single type can be fetched::

    summ = et.get_summary(summary-type, summary-window)

Like with the EventType object, the underlying data can be retrieved by
calling get_data() to get a DataPayload object and call the data property
on that to get a list of DataPoint objects.

Writing data to pS esmond/backend
=================================

The REST interface also supports adding metadata, event types and data if
the user is properly authenticated using a username and api_key that has
been generated by the admin of the system.  The following are presented as
an ordered process, but any single step of this can be done independently.
The functionality for POSTing date can be found in the following libarary::

    from esmond.api.client.perfsonar.post import MetadataPost, \
        EventTypePost, EventTypeBulkPost

First one needs to create a new metadata entry - this is accomplished
using the MetadataPost object.  It is initialized with a REST url,
username, api_key and a series of associated data - most required, a few
optional (the commented key/val pairs in the arg dict are optional)::

    args = {
        "subject_type": "point-to-point",
        "source": "10.10.0.1",
        "destination": "10.10.0.2",
        "tool_name": "bwctl/iperf3",
        "measurement_agent": "10.10.0.2",
        "input_source": "host1",
        "input_destination": "host2",
        # "time_duration": 30,
        # "ip_transport_protocol": "tcp"
    }

    mp = MetadataPost('http://localhost:8000/', username='pS_user',
        api_key='api-key-generated-by-auth-database', **args)

This will create the basic data associated with this metadata.  Then add
the event types and summaries associated with this metadata and post the
new information::

    mp.add_event_type('throughput')
    mp.add_event_type('time-error-estimates')
    mp.add_event_type('histogram-ttl')
    mp.add_event_type('packet-loss-rate')
    mp.add_summary_type('packet-count-sent', 'aggregation', [3600, 86400])

    new_meta = mp.post_metadata()

This writes the metadata information to the back end and returns the
associated "read only" Metadata object that was covered in the previous
section.  This is mostly necessary to get the newly generated metadata_key
property, it will be needed for other operations.

Next data can be added to the assocaited event types - the process is similar
for both numeric and histogram data.  Intialize an EventTypePost object
similarly to the MetadataPost object, but also using the appropriate
metadata_key and event_type to add the data to::

    et = EventTypePost('http://localhost:8000/', username='pS_user',
        api_key='api-key-generated-by-auth-database',
        metadata_key=new_meta.metadata_key,
        event_type='throughput')

Discrete data points can be added the process is similar for both numeric
data and histogram data - first arg is an integer timestamp in seconds and
the second is the value - and post it::

    et.add_data_point(1397075053, 23)
    et.add_data_point(1397075113, 55)

    (or in the case of histograms)

    et.add_data_point(1397075053, {28: 33})
    et.add_data_point(1397075113, {9: 12})

    et.post_data()

It is also possible to bulk post data for a variety of event types associated
with a single metadata using the EventTypeBulkPost interface.  Intialize in
a similar fashion minus the event_type arg::

    etb = EventTypeBulkPost('http://localhost:8000/', username='pS_user',
            api_key='api-key-generated-by-auth-database',
            metadata_key=new_meta.metadata_key)

Add a mix of data points specified by event type and post::

    etb.add_data_point('time-error-estimates', 1397075053, 23)
    etb.add_data_point('packet-loss-rate', 1397075053,
        {'numerator': 11, 'denominator': 33})

    etb.add_data_point('time-error-estimates', 1397075113, 55)
    etb.add_data_point('packet-loss-rate', 1397075113,
        {'numerator': 5, 'denominator': 8})

    etb.post_data()

NOTE: as noted in the previous section, the optional script_alias kwarg works
the same way with the POST interface.




