=================================================================
Client libraries and programs for esmond: ESnet Monitoring Daemon
=================================================================

Client programs
===============

esmond-ps-get-endpoints
-----------------------

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
----------------------

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
-------------

Tool to pull smaller, more focused sets of data from a perfSONAR MA. This 
requires a source/dest pair as well as a specific event type. Intended to 
be more of a "quick look" at some data.  To gather more/larger amounts 
of data, esmond-ps-get-bulk is intended for that.

esmond-ps-get-bulk
------------------

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

General esmond-ps client usage
===============================

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

Example command line usage
==========================

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

API Client Libraries
====================

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




