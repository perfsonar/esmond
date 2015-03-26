*********************************
perfSONAR Python Client Libraries
*********************************

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

Additional notes
================

TBA


