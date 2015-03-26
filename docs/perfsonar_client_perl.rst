*******************************
perfSONAR Perl Client Libraries
*******************************

This document describes the basics of reading and writing data from the perfSONAR measurement archive using the PERL API. The measurement archive implements a REST interface where clients can retrieve descriptions of measurements being run and the results of those measurements. It currently offers support for a range of measurements related to throughput, packet delay, packet loss, packet traces and more (with additional data types being added all the time). This document gives developers information on how to interact with the API using the Perl library.

Where to get the API 
===================== 
The API can currently be found in the perfsonar shared `perl source tree <https://github.com/perfsonar/perl-shared>`_. You will find the client libraries under `lib/perfSONAR_PS/Client/Esmond`. You may add these as a git submodule to your own project. Assuming you keep your Perl files under `lib` you can include them as follows::

    git submodule add https://github.com/perfsonar/perl-shared shared
    mkdir -p lib/perfSONAR_PS/Client/Esmond
    cd lib/perfSONAR_PS/Client/Esmond
    ln -s ../../../../shared/lib/perfSONAR_PS/Client/Esmond/* .

Querying Data 
============== 

Quickstart 
----------- 
::

    # Define filters
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->source("host1.example.net");
    $filters->destination("host2.example.net");
    $filters->time_range(86400);
    $filters->event_type('throughput');
    
    # Connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata();
    die $client->error if($client->error); #check for errors
    #loop through all measurements
    foreach my $m(@{$md}){
        # get data of a particular event type
        my $et = $m->get_event_type("throughput");
        my $data = $et->get_data();
        die $et->error if($et->error); #check for errors
        #print all data
        foreach my $d(@{$data}){
            print "Time: " . $d->datetime . ", Value: " . $d->val . "\n";
        }
    }


.. _psclient-perl-filters:

Defining filters 
----------------- 
The first step to querying the measurement archive is to define a set of filters. If you want a listing of all the measurements run by a measurement archive using default HTTP connection parameters then you can skip this step. The library allows you to filter measurements using the **perfSONAR_PS::Client::Esmond::ApiFilters** module. The class has a a set of well-known filters available as specific functions and also allows the setting of custom filters with direct access to the *metadata_filters* hash. It also allows you to define various settings related to the HTTP connection. In general, you can call the constructor without any options as follows:
::

    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();


You can optionally pass the following values to the ApiFilters constructor when creating a new object:

+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Property Name**       | **Description**                                                                                                                                           |
+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **auth_username**       | String with the username to pass in the HTTP Authorization header. Not required for querying data, but may be required to write data.                     |
+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **auth_apikey**         | String with the API key to pass in the HTTP Authorization header. Not required for querying data, but may be required to write data.                      |
+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **ca_certificate_file** | For HTTPS connections only, the absolute path to a file containing a certificate file used to verify the server certificate                               |
+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **ca_certificate_path** | For HTTPS connections only, the absolute path to a directory containing one or more certificate files to be used to verify the server                     |
+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **timeout**             | The timeout in seconds to wait before terminating the HTTP request. Defaults to 60 seconds.                                                               |
+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **verify_hostname**     |For HTTPS connections only, a boolean indicating whether the hostname must match the common name in the subject of the certificate presented by the server.|
+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------+

After creating the filters object, you can set various parameters that will limit the results returned by the search by using a set of accessor methods. The methods accept an optional argument containing the value to set. If no argument is provided, it simply returns the value of the field. The full set of methods available for setting common values is provided below:

+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Method Name**                   | **Description**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **source(ip)**                    |An IP address or hostname matching against the sender in a measurement. Hostnames will automatically get mapped to IP addresses by the server, so no need to match the form in which things are stored on the backend.                                                                                                                                                                                                                                                                                           |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **destination(ip)**               |An IP address or hostname matching against the receiver in a measurement. Hostnames will automatically get mapped to IP addresses by the server, so no need to match the form in which things are stored on the backend.                                                                                                                                                                                                                                                                                         |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **measurement_agent(ip)**         |An IP address or hostname matching against the host that initiated a test. Could either be the source, destination or in some cases a third-party host. Hostnames will automatically get mapped to IP addresses by the server, so no need to match the form in which things are stored on the backend.                                                                                                                                                                                                           |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **tool_name(string)**             | The name of the tool used for the measurement. Examples include *bwctl/iperf3* and *powstream*.                                                                                                                                                                                                                                                                                                                                                                                                                 |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **event_type(string)**            |Matches only metadata with a certain type for data (e.g. *throughput*, *packet-loss-rate*)                                                                                                                                                                                                                                                                                                                                                                                                                       |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **summary_type(string)**          |Matches only metadata doing certain summaries(e.g. *statistics*, *average*, *aggregation*)                                                                                                                                                                                                                                                                                                                                                                                                                       |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **summary_window(seconds)**       |Matches only metadata with event-types that have summaries over a certain windows (in seconds).                                                                                                                                                                                                                                                                                                                                                                                                                  |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **time(timestamp)**               | Match metadata last updated at the exact time given as a UNIX timestamp.                                                                                                                                                                                                                                                                                                                                                                                                                                        |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **time_start(timestamp)**         |Match only measurements that were updated after the given time (inclusive). If time_end nor time_range is defined, then it will return all results from the start time to the current time. In UNIX timestamp format.                                                                                                                                                                                                                                                                                            |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **time_end(timestamp)**           |Match only data that was measured before the given time (inclusive). If time-start nor time-range is provided, then will return all data stored in the archive up to and including the end time. In UNIX timestamp format.                                                                                                                                                                                                                                                                                       |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **time_range(seconds)**           |Only return results that have been updated in the given number of seconds in the past. If time_start nor time-end is defined, then it is the number of seconds in the past from the current time. If only time_start is defined then it is the number of seconds after time_start to search. If only time_end is provided it is the number of seconds before end time to search. If both time_start and time_end are defined, this value is ignored.                                                             |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **input_source(string)**          |A string indicating exactly how the source address is passed to the tool. **You SHOULD NOT search on this field, use the source instead.** This field is for informational purposes only to indicate whether the underlying tool running the measurement (e.g. bwctl, owping, ping) is passed a DNS name or IP when it runs. While searching is not strictly prohibited, you should almost never search on this field. The source is better since it will do DNS to IP mappings and will provide more consistent |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **input_destination(string)**     | A string indicating exactly how the destination address is passed to the tool. **You SHOULD NOT search on this field, use the destination instead.**  See *input-source* above for a complete discussion.                                                                                                                                                                                                                                                                                                       |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **dns_match_rule(string)**        |A string indicating how to handle DNS lookups on fields such as *source*, *destination* and *measurement_agent* where the server maps DNS names to IP addresses. See :ref:`psclient-rest-search` for valid values. Also see the ``dns_match_**`` subroutines below for convenience functions that set this same field to specific values.                                                                                                                                                                        |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **dns_match_only_v4()**           |Alias for ``dns_match_rule('only-v4')``. Only maps given DNS names to their A records when searching                                                                                                                                                                                                                                                                                                                                                                                                             |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **dns_match_only_v6()**           |Alias for ``dns_match_rule('only-v6')``. Only maps given DNS names to their AAAA records when searching                                                                                                                                                                                                                                                                                                                                                                                                          |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **dns_match_prefer_v4()**         |Alias for ``dns_match_rule('prefer-v4')``. Maps given DNS names to their A record if they have one, otherwise tries AAAA record                                                                                                                                                                                                                                                                                                                                                                                  |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **dns_match_prefer_v6()**         |Alias for ``dns_match_rule('prefer-v6')``. Maps given DNS names to their AAAA record if they have one, otherwise tries A record                                                                                                                                                                                                                                                                                                                                                                                  |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **dns_match_all()**               |Alias for ``dns_match_rule('v4v6')``. Maps DNS names to both A and AAAA records when searching. This is the default behavior if * dns_match_rule* is unspecified                                                                                                                                                                                                                                                                                                                                                 |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **limit()**                       |An integer indicating the maximum number of metadata objects to return. If not set, all results will be returned.                                                                                                                                                                                                                                                                                                                                                                                                |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **offset()**                      |An integer indicating the number of results to skip in the metadata search. This can be combined with the *limit* filter to support pagination. See :ref:`psclient-perl-pagination` for more details.                                                                                                                                                                                                                                                                                                            |
+-----------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

Finally, you can set context-specific parameters that don't have a function by accessing the *metadata``_``filters* hash directly:
::

    $filters->metadata_filters->{'ip-transport-protocol'} = 'tcp';

.. _psclient-perl-connect:

Connecting to the API
--------------------- 

Once the filters are defined, you create an instance of **perfSONAR_PS::Client::Esmond::ApiConnect** as follows:
::

    ...
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );


You MUST provide the *url* parameter with the base URL of the measurement archive (usually ending with */esmond/perfsonar/archive*) in the constructor. You may optionally define the *filters* field in the constructor with an instance of **perfSONAR_PS::Client::Esmond::ApiFilters**. If none is provided, all metadata will be returned and default HTTP connection settings will be used. After constructing the ApiConnect object, there is one method, **get_metadata()**, that accepts no arguments available to call:
::

    ...
    my $md = $client->get_metadata();

The **get_metadata()** call returns an ArrayRef to a list of **perfSONAR_PS::Client::Esmond::Metadata** objects as described in :ref:`psclient-perl-metadata`. After making a call to **get_metadata()** you can check the **error** property to see if any errors occurred since **get_metadata()** leads to an HTTP GET request. For example:
::

    ...
    my $md = $client->get_metadata();
    die $client->error if($client->error); #check for errors

.. _psclient-perl-metadata:

Working with Measurement Metadata
--------------------------------- 
As discussed in :ref:`psclient-perl-connect` you can retrieve an ArrayRef to a list of **perfSONAR_PS::Client::Esmond::Metadata** objects. These objects describe tests and have the following property methods to retrieve common metadata parameters:

+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **Method Name**         | **Description**                                                                                             |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **source()**            |An IP address representing the sender in a point-to-point measurement                                        |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **destination()**       |An IP address representing the receiver in a point-to-point measurement                                      |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **measurement_agent()** |The IP address of the host that initiated the measurement                                                    |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **metadata_key()**      |The key used to identify this metadata_object.                                                               |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **input_source**        |A string representing the source address exactly as it is passed to the underlying measurement tool.         |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **input_destination()** |A string representing the destination address exactly as it is passed to the underlying measurement tool.    |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **subject_type()**      |Indicates the type of parameters to expect in the metadata. In general will always be *point-to-point*.      |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **tool_name()**         | The name of the tool used to run the underlying measurement.                                                |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **uri()**               |The URI to this individual metadata object                                                                   |
+-------------------------+-------------------------------------------------------------------------------------------------------------+
| **event_types()**       |Returns an ArrayRef of strings indicating the event type available. e.g. ['throughput', 'packet-count-sent'] |
+-------------------------+-------------------------------------------------------------------------------------------------------------+

Additionally, you can retrieve context-specific metadata parameters with the **get_field** call which accepts the field name as a parameter:
::

    ...
    foreach my $m(@{$md}){
        print $m->get_field('ip-transport-protocol') . "\n";
    }


Finally, there are a special set of methods to work with event types and will act as the gateway to accessing the results. The methods are as follows:

+------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Method Name**              | **Description**                                                                                                                                                             |
+------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **get_all_event_types()**    |Accepts no arguments and returns an ArrayRef of **perfSONAR_PS::Client::Esmond::EventType** objects                                                                          |
+------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **get_event_type(string)**   |Accepts a single argument indicating the type of data you want (e.g.'throughput'). Returns a single **perfSONAR_PS::Client::Esmond::EventType** object or undef if none match|
+------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

An example of each:
::

    ...
    #print the base uri for every event type
    foreach my $et(@{$m->get_all_event_types()}){
        print $et->base_uri() . "\n";
    }
    
    #grab a single throughput event type
    my $throughput_et = $m->get_event_type("throughput");

.. _psclient-perl-query-base:

Querying Base Measurement Results
--------------------------------- 
The **perfSONAR_PS::Client::Esmond::EventType** is the gateway object to pulling down actual results. It provides the following methods:

+------------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Method Name**        | **Description**                                                                                                                                                                                            |
+------------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **base_uri()**         |Returns the URI where you can get the base data for the event type. See :ref:`psclient-rest-basevsumm` for more details on base and summary data.                                                           |
+------------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **event_type()**       | The type of data such as *throughput* or *packet-loss-rate*.                                                                                                                                               |
+------------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **time_updated()**     |A Unix timestamp indicating when the event type was last updated. A value of undef means it has never been updated.                                                                                         |
+------------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **datetime_updated()** |A DateTime object indicating when the event type was last updated. The same as *time_updated()* but returns a DateTime object instead of a UNIX timestamp.                                                  |
+------------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **summaries()**        | An ArrayRef of tuples. The first item in each tuple is the summary type, the second is the summary window.                                                                                                 |
+------------------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

It provides a single **get_data()** method that accepts no arguments for pulling down data. It also provides an **error** property for checking if the **get_data()** call failed. If **get_data()** succeeds it returns an ArrayRef of **perfSONAR_PS::Client::Esmond::DataPayload** objects. **perfSONAR_PS::Client::Esmond::DataPayload** objects have the following properties:

+-------------------+------------------------------------------------------------------------------------------------------------------------+
| **Property Name** | **Description**                                                                                                        |
+-------------------+------------------------------------------------------------------------------------------------------------------------+
| **ts**            |The UNIX timestamp of when the measurement was run                                                                      |
+-------------------+------------------------------------------------------------------------------------------------------------------------+
| **val**           | The value of the measurement. The type depends on the event type. It will either be a primitive type or a Perl HashRef.|
+-------------------+------------------------------------------------------------------------------------------------------------------------+

It also contains the following method:

+-----------------+-----------------------------------------------+
| **Method Name** | **Description**                               |
+-----------------+-----------------------------------------------+
| **datetime()**  |Returns a DateTime version of the *ts* property|
+-----------------+-----------------------------------------------+

A full example is shown below:
::

    ...
    my $data = $et->get_data();
    die $et->error if($et->error); #check for errors
    #print all data
    foreach my $d(@{$data}){
        print "Time: " . $d->datetime . ", Value: " . $d->val . "\n";
    }


Querying Summary Measurement Results
------------------------------------ 
The **perfSONAR_PS::Client::Esmond::EventType** contains two more methods for geting summary data:


+--------------------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **get_all_summaries()**              |Returns an ArrayRef of **perfSONAR_PS::Client::Esmond::Summary** objects. Returns an empty list if there are no summaries.|
+--------------------------------------+--------------------------------------------------------------------------------------------------------------------------+
| **get_summary(string, seconds)**     |Returns a a single **perfSONAR_PS::Client::Esmond::Summary** of a given type and summary window.                          |
+--------------------------------------+--------------------------------------------------------------------------------------------------------------------------+

The **perfSONAR_PS::Client::Esmond::Summary** module has the following methods:

+------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Method Name**        | **Description**                                                                                                                                       |
+------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
| **uri()**              |Returns the URI where you can get the summary data.                                                                                                    |
+------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
| **summary_type()**     | The type of summary such as *aggregation*, *average* or *statistics*.                                                                                 |
+------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
| **summary_window()**   |The time in seconds over which the data is summarized.                                                                                                 |
+------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
| **time_updated()**     |A Unix timestamp indicating when the summary was last updated. A value of undef means it has never been updated.                                       |
+------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+
| **datetime_updated()** |A DateTime object indicating when the summary was last updated. The same as *time_updated()* but returns a DateTime object instead of a UNIX timestamp.|
+------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------+

The **perfSONAR_PS::Client::Esmond::Summary** module also has a **get_data()** method that accepts no arguments and returns an ArrayRef of **perfSONAR_PS::Client::Esmond::DataPayload** objects. It also has an **error** property that gets populated if the library is unable to retrieve the summary. These methods follow the exact same format as the **perfSONAR_PS::Client::Esmond::EventType** module. An example of querying summary data below:
::

    #get 24 hour summaries
    my $agg_summ = $et->get_summary('aggregation', 86400);
    die "No summary found" unless($agg_summ);
    my $agg_data = $agg_summ->get_data();
    die $agg_summ->error if($agg_summ->error);
    foreach my $agg_d(@{$agg_data}){
        print "Time: " . $agg_d->datetime . ", Val: " . $agg_d->val . "\n";
    }


Advanced Time Filter Usage
-------------------------- 
It's important to note an important behavior of the time filters when working with a metadata request versus a data request. When you create a **perfSONAR_PS::Client::Esmond::ApiFilters** object, pass it to a **perfSONAR_PS::Client::Esmond::ApiConnect**, and the call to get_metadata() it will match the *last updated* time of the metadata. When making a data request, it will only return results *recorded in that time range*. This is a subtle but important difference. For example, let's say you have a metadata object that was last updated 1 minute ago but you ultimately want data from between 2 hours and 1 hour ago. You might be tempted to try something like this:
::

    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    my $now = time;
    $filters->time_start($now - 7200); # 2 hours ago
    $filters->time_end($now - 3600); #1 hour ago
    
    # Connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata(); # this returns empty results


The above returns empty results because the above is saying *give me all metadata object last updated between 2 hours and 1 hour ago* but we have already stated that our metadata was updated more recently. This does not mean there is no data in that time range, just that more recent data exists. Instead we need to adjust the time filters before we query the data. Below will give the results we want:
::

    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    my $now = time;
    $filters->time_start($now - 7200); # return anything updated in the last 2 hours
    
    # Connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata(); # this returns empty results
    foreach my $m(@{$md}){
        # get data of a particular event type
        my $et = $m->get_event_type("throughput");
        $et->filters->time_end($now - 3600); #add the end filter so we only get data up to an hour ago
        my $data = $et->get_data();
        die $et->error if($et->error); #check for errors
        #print all data
        foreach my $d(@{$data}){
            print "Time: " . $d->datetime . ", Value: " . $d->val . "\n";
        }
    }

.. _psclient-perl-pagination:

Pagination of Metadata Search Results 
-------------------------------------- 

For measurement archives hosting a large number of tests, it may be desirable to limit the number of metadata search results returned. This can be done using the *limit* and *offset* filters as follows:

::

    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->limit(10); #return up to 10 results
    $filters->offset(0); # return the first results you find
    
    # Connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata(); # returns first 10 results
    ...
    $filters->offset(10); # skip the first 10 results
    $md = $client->get_metadata(); # returns the second 10 results
    


As the example shows you can use these options to implement pagination. This is done by keeping the limit option constant and incrementing the offset by the size of limit for each page until you reach the last page. To aid in common calculations like the last page, current page, and the next/previous offset the **perfSONAR_PS::Client::Esmond::Paginator** class is provided. After you define your filters and query your metadata, you can create a **perfSONAR_PS::Client::Esmond::Paginator** instance as follows:
::

    my $paginator = new perfSONAR_PS::Client::Esmond::Paginator(
        'metadata' => $mds,
        'filters' => $filters,
    );


As shown in the example the constructor requires the properties below:

+-------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Property Name** | **Description**                                                                                                                                                          |
+-------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **metadata**      | An ArrayRef of **perfSONAR_PS::Client::Esmond::Metadata** objects (such as the results returned by a get_metadata call).                                                 |
+-------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **filters**       | The **perfSONAR_PS::Client::Esmond::ApiFilters** object used in the query. It is recommended the *limit* and *offset* filters are defined for the paginator to be useful.|
+-------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

Once you have created your paginator, the following methods are available:


+--------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Method Name**                | **Description**                                                                                                                                          |
+--------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **current_page()**             | Returns the current page number based on the offset and limit. Page count starts at 1.                                                                   |
+--------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **last_page()**                | Returns the last page number based on the offset and limit. Page count starts at 1.                                                                      |
+--------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **next_offset()**              | Calculates the value to pass to the offset to get next page of data. Returns undef if the current page is the last page.                                 |
+--------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **prev_offset()**              |  Calculates the value to pass to the offset to get previous page of data. Returns undef if the current page is the last page.                            |
+--------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------+
| **page_offset(page_number)**   |  Calculates the value to pass to the offset for the given page number (starting at 1). If the page number is bigger than the last page undef is returned.|
+--------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------+

A full example that grabs all the metadata in chunks of 10 and prints the page number is shown below:
::

    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->limit(10);
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://esmond-dev/perfsonar/archive',
        filters => $filters
    );
    my $next = 0;
    while(defined $next){
        $filters->offset($next);
        my $mds = $client->get_metadata();
        my $paginator = new perfSONAR_PS::Client::Esmond::Paginator(
            'metadata' => $mds,
            'filters' => $filters,
        );
        print "Current page is " . $paginator->current_page() . " of " . $paginator->last_page() . "\n";
        $next = $paginator->next_offset();
    }
    





Querying Data by URI 
--------------------- 
In some cases you will already have the URI for the summary or base data that you want to request. For example, if you have a web page that first presents the list of tests available as returned by a metadata search, then upon user interaction you return data from a selected result of that search. There is no point in querying the metadata a second time since you should have all the URIs you need from the first request. You can request the data directly by URI with the **get_data(*uri*)** call from **perfSONAR_PS::Client::Esmond::ApiConnect**. For example:
::

    ...
    use CGI;
    my $cgi = new CGI;
    my $uri = $cgi->param('data-uri');
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->time_range(86400);
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    my $data = $client->get_data($uri);
    die $client->error if($client->error);
    foreach my $d(@{$data}){
        print "Time: " . $d->datetime . ", Value: " . $d->val . "\n";
    }




Examples
-------- 
Querying Throughput
^^^^^^^^^^^^^^^^^^^ 
::

    # Define filters
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->source("host1.example.net");
    $filters->destination("host2.example.net");
    $filters->time_range(86400);
    $filters->event_type('throughput');
    
    # Connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata();
    die $client->error if($client->error); #check for errors
    #loop through all measurements
    foreach my $m(@{$md}){
        # get data of a particular event type
        my $et = $m->get_event_type("throughput");
        my $data = $et->get_data();
        die $et->error if($et->error); #check for errors
        #print all data
        foreach my $d(@{$data}){
            print "Time: " . $d->datetime . ", Value: " . $d->val . "\n";
        }
    }


Querying Delay/One-way Delay
^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
::

    # define filters
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->source("host1.example.net");
    $filters->destination("host2.example.net");
    $filters->time_range(86400);
    
    # connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata();
    die $client->error if($client->error); #check for errors
    foreach my $m(@{$md}){
        my $et = $m->get_event_type("histogram-owdelay");
        my $data = $et->get_data();
        die $et->error if($et->error); #check for errors
        #base data
        foreach my $d(@{$data}){
            print "Time: " . $d->datetime . "\n";
            foreach my $bucket(keys %{$d->val}){
                print "\t${bucket}ms: " . $d->val->{$bucket} . "\n";
            }
        }
    
        #get histogram statistics summary for base data
        my $stats_summ = $et->get_summary('statistics', 0);
        next unless($stats_summ);
        my $stats_data = $stats_summ->get_data();
        die $stats_summ->error if($stats_summ->error);
        foreach my $stats_d(@{$stats_data}){
            print "Time: " . $stats_d->datetime . ", Median:" . $stats_d->{val}->{median}. "\n";
        }
    
        #get 24 hour summaries
        my $agg_summ = $et->get_summary('aggregation', 86400);
        next unless($agg_summ);
        my $agg_data = $agg_summ->get_data();
        return $agg_summ->error if($agg_summ->error);
        foreach my $agg_d(@{$agg_data}){
            foreach my $agg_bucket(keys %{$agg_d->val}){
                print "\t${agg_bucket}ms: " . $agg_d->val->{$agg_bucket}. "\n";
            }
        }
    }


Querying Packet Loss
^^^^^^^^^^^^^^^^^^^^ 
::

    #define filters
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->source("host1.example.net");
    $filters->destination("host2.example.net");
    $filters->time_range(86400);
    
    # connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata();
    die $client->error if($client->error); #check for errors
    foreach my $m(@{$md}){
        my $et = $m->get_event_type("packet-loss-rate");
        my $data = $et->get_data();
        die $et->error if($et->error); #check for errors
        #base data
        foreach my $d(@{$data}){
            print "Time: " . $d->datetime . ", Loss: " . $d->val*100.0 . "%\n";
        }
    
        #get 24 hour summaries
        my $agg_summ = $et->get_summary('aggregation', 86400);
        next unless($agg_summ);
        my $agg_data = $agg_summ->get_data();
        return $agg_summ->error if($agg_summ->error);
        foreach my $agg_d(@{$agg_data}){
            print "Time: " . $agg_d->datetime . ", Loss: " . $agg_d->val*100.0 . "%\n";
        }
    }


Querying Packet Traces
^^^^^^^^^^^^^^^^^^^^^^ 
::

    #define filters
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->source("host1.example.net");
    $filters->destination("host2.example.net");
    $filters->time_range(86400);
    
    # connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata();
    die $client->error if($client->error); #check for errors
    foreach my $m(@{$md}){
        my $et = $m->get_event_type("packet-trace");
        my $data = $et->get_data();
        die $et->error if($et->error); #check for errors
        #base data
        foreach my $d(@{$data}){
            print "Time: " . $d->datetime . "\n";
            foreach my $hop(@{$d->val}){
                print "ttl=" . $hop->ttl . ",query=" . $hop->query;
                if($hop->{success}){
                    print ",ip=" . $hop->{ip} . ",rtt=" . $hop->{rtt} . ",mtu=" . $hop->{mtu} . "\n"; 
                }else{
                    print ",error=" . $hop->{error} . "\n"; 
                }
            }
        }
    }


Querying Subintervals
^^^^^^^^^^^^^^^^^^^^^ 
::

    # Define filters
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters();
    $filters->source("host1.example.net");
    $filters->destination("host2.example.net");
    $filters->time_range(86400);
    $filters->event_type('packet-retransmits-subintervals');
    
    # Connect to api
    my $client = new perfSONAR_PS::Client::Esmond::ApiConnect(
        url => 'http://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    
    #get measurements matching filters
    my $md = $client->get_metadata();
    die $client->error if($client->error); #check for errors
    #loop through all measurements
    foreach my $m(@{$md}){
        # get data of a particular event type
        my $et = $m->get_event_type("packet-retransmits-subintervals");
        my $data = $et->get_data();
        die $et->error if($et->error); #check for errors
        #print all data
        foreach my $d(@{$data}){
            print "Time: " . $d->datetime . "\n";
            foreach my $subint(@{$d->val}){
                print "\tstart=" . $subint->{start} . ",duration=" . $subint->{duration} . ",value=" . $subint->{val} . "\n";
            }
        }
    }


Publishing Data 
================ 

Quickstart 
----------- 
::

    #define filters with authentication information
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters(
        'auth_username' => 'perfsonar', 
        'auth_apikey' => '8208b9ad15dbda8e91cb086b0d228857de99fa25',
        'ca_certificate_file' => '/etc/pki/tls/bundle.crt'
    );
    
    #Post measurement metadata
    my $metadata = new perfSONAR_PS::Client::Esmond::Metadata(
        url => 'https://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    $metadata->subject_type('point-to-point');
    $metadata->source('10.1.1.1');
    $metadata->destination('10.1.1.2');
    $metadata->input_source('host1.example.net');
    $metadata->input_destination('host2.example.net');
    $metadata->tool_name('bwctl/iperf3');
    $metadata->measurement_agent('10.1.1.1');
    $metadata->set_field('time-interval', 21600);
    $metadata->set_field('time-duration', 20);
    $metadata->add_event_type('throughput');
    $metadata->add_summary_type('throughput', 'average', 86400);
    $metadata->add_event_type('packet-retransmits');
    $metadata->post_metadata();
    die $metadata->error() if $metadata->error();
    
    #post data to single event type
    my $et = $metadata->get_event_type('throughput');
    my $data = new perfSONAR_PS::Client::Esmond::DataPayload('ts' => time. '', 'val' => 1000000000);
    $et->post_data($data);
    die $et->error() if $et->error();
    
    #post multiple time series to multiple event types
    my $bulk_post = $metadata->generate_event_type_bulk_post();
    my $ts = time;
    $bulk_post->add_data_point('throughput', $ts, 2000000000);
    $bulk_post->add_data_point('packet-retransmits', $ts, 10);
    $bulk_post->add_data_point('throughput', $ts-1800, 1000000000);
    $bulk_post->add_data_point('packet-retransmits', $ts-1800, 9);
    $bulk_post->post_data();
    die $bulk_post->error() if $bulk_post->error();
    


Authentication and Authorization 
--------------------------------- 
Writing data generally requires authentication and authorization. You can define authentication-related parameters using the options defined in the first table under :ref:`psclient-perl-filters`. Specifically the option **auth_username** and **auth_apikey** are important for setting your user credentials. It is also highly recommended you send the message over HTTPS so the credentials are not sent plain-text (especially when sending to an external host). You may control HTTPS settings with the options **ca_certificate_file**, **ca_certificate_path** and/or **verify_hostname**. For example:
::

    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters(
        'auth_username' => 'perfsonar', 
        'auth_apikey' => '8208b9ad15dbda8e91cb086b0d228857de99fa25',
        'ca_certificate_file' => '/etc/pki/tls/bundle.crt'
    );


.. _psclient-perl-publish-metadata:

Publishing the Measurement Description 
--------------------------------------- 
Publishing a new description of a measurement's parameters requires the instantiation of a new *perfSONAR_PS::Client::Esmond::Metadata* object. Notice this is the same object returned when querying as described in :ref:`psclient-perl-metadata`. This also means if you want to post data to an existing test, you can use the Metadata object returned directly. Assuming you are using a completely new object though, the object provides a number of setters for common fields:


+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **Method Name**                 | **Description**                                                                                         |
+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **source(ip)**                  |An IP address representing the sender in a point-to-point measurement                                    |
+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **destination(ip)**             |An IP address representing the receiver in a point-to-point measurement                                  |
+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **measurement_agent(ip)**       |The IP address of the host that initiated the measurement                                                |
+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **metadata_key(string)**        |The key used to identify this metadata_object.                                                           |
+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **input_source(string)**        |A string representing the source address exactly as it is passed to the underlying measurement tool.     |
+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **input_destination(string)**   |A string representing the destination address exactly as it is passed to the underlying measurement tool.|
+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **subject_type(string)**        |Indicates the type of parameters to expect in the metadata. In general will always be *point-to-point*.  |
+---------------------------------+---------------------------------------------------------------------------------------------------------+
| **tool_name(string)**           | The name of the tool used to run the underlying measurement.                                            |
+---------------------------------+---------------------------------------------------------------------------------------------------------+

In addition you may set context-specific fields with the *set_field* subroutine that accepts the field name and the value to assign (*NOTE: The value must be a primitive type such as a number or string*):
::

    $metadata->set_field('time-interval', 21600);


There are a few special methods for adding new event types and summaries:

+----------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **Method Name**                                                      | **Description**                                                                                                                                                    |
+----------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **add_event_type(event-type)**                                       |Accepts a string with the event type (e.g. *throughput*, *histogram-owdelay*, *packet-loss-rate*) and adds it to the metadata.                                      |
+----------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **add_summary_type(event-type, summary-type, summary-window)**       |Adds a summary of the given *summary-type* (e.g. *average*. *aggregation*, or *statistics*) over the given *summary_window* (in seconds) for the given *event-type*.|
+----------------------------------------------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------+

An example of these methods is provided below:
::

    $metadata->add_event_type('throughput');
    $metadata->add_summary_type('throughput', 'average', 86400);
    $metadata->add_event_type('packet-retransmits');


The final step of creating the new metadata is to call the *post_metadata()* method:
::

    $metadata->post_metadata();


This sends an HTTP POST request to the server. If the request fails for any reason, there will be an error message returned by a call to the *error()* method. If it succeeds, the Metadata object will contain the resulting URIs and metadata_key in addition to the parameters already set. Also remember that if the server determines there is a metadata object that exactly matches, it will return the existing result instead of creating a duplicate. The resulting object can also be used to post measurement results as described in the next few sections.

Publishing a Single Measurement Result 
--------------------------------------- 
Once you have the Metadata object by either creating your own as described in :ref:`psclient-perl-publish-metadata` or querying an existing one as described in :ref:`psclient-perl-metadata`, you can then retrieve a *perfSONAR_PS::Client::Esmond::EventType* object with the following:
::

    my $et = $metadata->get_event_type('throughput');


You can then post to this event type by creating a new *perfSONAR_PS::Client::Esmond::DataPayload* with a *ts* field indicating the time the measurement was performed and a *val* indicating the result. The *perfSONAR_PS::Client::Esmond::DataPayload* module is described in detail in :ref:`psclient-perl-query-base` but an example is below:
::

    my $data = new perfSONAR_PS::Client::Esmond::DataPayload('ts' => time. '', 'val' => 1000000000);


We then publish the result with the following call to *post_data* that accepts a single *perfSONAR_PS::Client::Esmond::DataPayload* parameter:
::

    $et->post_data($data);


If the request succeeds then the *error()* method will return an empty result. The error() method will contain a message describing the problem if something goes wrong. See an example that kills the running program if an error is encountered:
::

    die $et->error() if $et->error();


Publishing Multiple Measurement Results 
---------------------------------------- 
In addition to publishing single measurements, you may also perform bulk requests for multiple event types and multiple timestamps. All bulk requests go to the same Metadata object. As with the single result case, we must first :ref:`create <psclient-perl-publish-metadata>` or :ref:`retrieve <psclient-perl-metadata>` a Metadata object. We can do this be asking the metadata object to generate a *perfSONAR_PS::Client::Esmond::EventTypeBulkPost* instance (*NOTE: Do not construct perfSONAR_PS::Client::Esmond::EventTypeBulkPost directly, retrieve it from the Metadata object*):
::

    my $bulk_post = $metadata->generate_event_type_bulk_post();


You can then add multiple data points with the *add_data_point* subroutine:

+----------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------+
| **Method Name**                                          | **Description**                                                                                                                              |
+----------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------+
| **add_data_point(event-type, timestamp, value)**         |Adds a new data point to publish for the given event-type string (*event-type*) at the given UNIX timestamp(*ts*) with the given value (*val*)|
+----------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------+

For example:
::

    my $ts = time;
    $bulk_post->add_data_point('throughput', $ts, 2000000000);
    $bulk_post->add_data_point('packet-retransmits', $ts, 10);
    $bulk_post->add_data_point('throughput', $ts-1800, 1000000000);
    $bulk_post->add_data_point('packet-retransmits', $ts-1800, 9);


Finally, you can send the result and check for errors from the server with the *post_data()* and *error()* functions as shown below:
::

    $bulk_post->post_data();
    die $bulk_post->error() if $bulk_post->error();



Examples 
--------- 

Publishing Throughput Data 
^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
::

    #Define filters with authentication information
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters(
        'auth_username' => 'perfsonar', 
        'auth_apikey' => '8208b9ad15dbda8e91cb086b0d228857de99fa25',
        'ca_certificate_file' => '/etc/pki/tls/bundle.crt'
    );
    
    #Post measurement metadata
    my $metadata = new perfSONAR_PS::Client::Esmond::Metadata(
        url => 'https://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    $metadata->subject_type('point-to-point');
    $metadata->source('10.1.1.1');
    $metadata->destination('10.1.1.2');
    $metadata->input_source('host1.example.net');
    $metadata->input_destination('host2.example.net');
    $metadata->tool_name('bwctl/iperf3');
    $metadata->measurement_agent('10.1.1.1');
    $metadata->set_field('ip-transport-protocol', 'tcp');
    $metadata->set_field('time-duration', 20);
    $metadata->set_field('time-interval', 21600);
    $metadata->set_field('bw-parallel-streams', 1);
    $metadata->add_event_type('throughput');
    $metadata->add_summary_type('throughput', 'average', 86400);
    $metadata->add_event_type('failures');
    $metadata->add_event_type('packet-retransmits');
    $metadata->post_metadata();
    die $metadata->error() . "\n" if $metadata->error();
    
    #Bulk post data
    my $bulk_post = $metadata->generate_event_type_bulk_post();
    my $ts = time;
    $bulk_post->add_data_point('throughput', $ts, 2000000000);
    $bulk_post->add_data_point('packet-retransmits', $ts, 10);
    $bulk_post->post_data();
    die $bulk_post->error() if($bulk_post->error());
    


Publishing Delay(Ping) Data 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
::

    #define filters with authentication information
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters(
        'auth_username' => 'perfsonar', 
        'auth_apikey' => '8208b9ad15dbda8e91cb086b0d228857de99fa25',
        'ca_certificate_file' => '/etc/pki/tls/bundle.crt'
    );
    
    #Post measurement metadata
    my $metadata = new perfSONAR_PS::Client::Esmond::Metadata(
        url => 'https://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    $metadata->subject_type('point-to-point');
    $metadata->source('10.1.1.1');
    $metadata->destination('10.1.1.2');
    $metadata->input_source('host1.example.net');
    $metadata->input_destination('host2.example.net');
    $metadata->tool_name('bwctl/ping');
    $metadata->measurement_agent('10.1.1.1');
    $metadata->set_field('ip-transport-protocol', 'icmp');
    $metadata->set_field('ip-packet-size', 1000);
    $metadata->set_field('time-interval', 600);
    $metadata->set_field('time-probe-interval', 1);
    $metadata->set_field('sample-size', 100);
    $metadata->add_event_type('histogram-rtt');
    $metadata->add_summary_type('histogram-rtt', 'aggregation', 86400);
    $metadata->add_summary_type('histogram-rtt', 'statistics', 0);
    $metadata->add_summary_type('histogram-rtt', 'statistics', 86400);
    $metadata->add_event_type('packet-loss-rate-bidir');
    $metadata->add_summary_type('packet-loss-rate-bidir', 'aggregation', 3600);
    $metadata->add_summary_type('packet-loss-rate-bidir', 'aggregation', 86400);
    $metadata->add_event_type('histogram-ttl-reverse');
    $metadata->add_summary_type('histogram-ttl-reverse', 'statistics', 0);
    $metadata->add_event_type('packet-count-lost-bidir');
    $metadata->add_event_type('packet-count-sent');
    $metadata->add_event_type('packet-duplicates-bidir');
    $metadata->add_event_type('packet-reorders-bidir');
    $metadata->add_event_type('failures');
    $metadata->post_metadata();
    die $metadata->error() . "\n" if $metadata->error();
    
    #bulk post data
    my $bulk_post = $metadata->generate_event_type_bulk_post();
    my $ts = time;
    $bulk_post->add_data_point('histogram-rtt', $ts, { '41.00'=> 99, '41.10'=> 1 });
    $bulk_post->add_data_point('packet-loss-rate', $ts, {'numerator'=> 0, 'denominator'=> 100});
    $bulk_post->add_data_point('histogram-ttl', $ts, { '59'=> 100 });
    $bulk_post->add_data_point('packet-count-lost', $ts, 0);
    $bulk_post->add_data_point('packet-count-sent', $ts, 100);
    $bulk_post->add_data_point('packet-duplicates', $ts, 0);
    $bulk_post->add_data_point('packet-reorders', $ts, 0);
    $bulk_post->post_data();
    die $bulk_post->error() if($bulk_post->error());
    


Publishing One-way Delay(OWAMP) Data 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
::

    #define filters with authentication information
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters(
        'auth_username' => 'perfsonar', 
        'auth_apikey' => '8208b9ad15dbda8e91cb086b0d228857de99fa25',
        'ca_certificate_file' => '/etc/pki/tls/bundle.crt'
    );
    
    #Post measurement metadata
    my $metadata = new perfSONAR_PS::Client::Esmond::Metadata(
        url => 'https://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    $metadata->subject_type('point-to-point');
    $metadata->source('10.1.1.1');
    $metadata->destination('10.1.1.2');
    $metadata->input_source('host1.example.net');
    $metadata->input_destination('host2.example.net');
    $metadata->tool_name('powstream');
    $metadata->measurement_agent('10.1.1.1');
    $metadata->set_field('ip-transport-protocol', 'udp');
    $metadata->set_field('ip-packet-size', 100);
    $metadata->set_field('time-interval', 0);
    $metadata->set_field('time-probe-interval', .1);
    $metadata->set_field('sample-size', 600);
    $metadata->set_field('sample-bucket-width', .0001);
    $metadata->add_event_type('histogram-owdelay');
    $metadata->add_summary_type('histogram-owdelay', 'aggregation', 3600);
    $metadata->add_summary_type('histogram-owdelay', 'aggregation', 86400);
    $metadata->add_summary_type('histogram-owdelay', 'statistics', 0);
    $metadata->add_summary_type('histogram-owdelay', 'statistics', 3600);
    $metadata->add_summary_type('histogram-owdelay', 'statistics', 86400);
    $metadata->add_event_type('packet-loss-rate');
    $metadata->add_summary_type('packet-loss-rate', 'aggregation', 3600);
    $metadata->add_summary_type('packet-loss-rate', 'aggregation', 86400);
    $metadata->add_event_type('histogram-ttl');
    $metadata->add_summary_type('histogram-ttl', 'statistics', 0);
    $metadata->add_event_type('packet-count-lost');
    $metadata->add_event_type('packet-count-sent');
    $metadata->add_event_type('packet-duplicates');
    $metadata->add_event_type('time-error-estimates');
    $metadata->add_event_type('failures');
    $metadata->post_metadata();
    die $metadata->error() . "\n" if $metadata->error();
    
    #bulk post data
    my $bulk_post = $metadata->generate_event_type_bulk_post();
    my $ts = time;
    $bulk_post->add_data_point('histogram-owdelay', $ts, { '34.5'=> 30, '34.3'=> 440, '34.6' => 7, '34.4' => 123 });
    $bulk_post->add_data_point('packet-loss-rate', $ts, {'numerator'=> 0, 'denominator'=> 600});
    $bulk_post->add_data_point('histogram-ttl', $ts, { '59'=> 600 });
    $bulk_post->add_data_point('packet-count-lost', $ts, 0);
    $bulk_post->add_data_point('packet-count-sent', $ts, 600);
    $bulk_post->add_data_point('packet-duplicates', $ts, 0);
    $bulk_post->add_data_point('time-error-estimates', $ts, 0.000124);
    $bulk_post->post_data();
    die $bulk_post->error() if($bulk_post->error());


Publishing Packet Loss
^^^^^^^^^^^^^^^^^^^^^^ 
Note that *packet-loss-rate* is a special percentage type and thus is not registered as a simple float. It is registered as an object with a *numerator* and a *denominator* so that it is easier to summarize. Packet loss is measured by tools such as owamp  (packet-loss-rate) and ping (packet-loss-rate-bidir), but the data registration portion is repeated below to highlight this difference:
::

    ...
    $bulk_post->add_data_point('packet-loss-rate', $ts, {'numerator'=> 0, 'denominator'=> 100});
    ...


Publishing Packet Traces 
^^^^^^^^^^^^^^^^^^^^^^^^^ 
::

    #define filters with authentication information
    my $filters = new perfSONAR_PS::Client::Esmond::ApiFilters(
        'auth_username' => 'perfsonar', 
        'auth_apikey' => '8208b9ad15dbda8e91cb086b0d228857de99fa25',
        'ca_certificate_file' => '/etc/pki/tls/bundle.crt'
    );
    
    #Post measurement metadata
    my $metadata = new perfSONAR_PS::Client::Esmond::Metadata(
        url => 'https://archive.example.net/esmond/perfsonar/archive',
        filters => $filters
    );
    $metadata->subject_type('point-to-point');
    $metadata->source('10.1.1.1');
    $metadata->destination('10.1.1.2');
    $metadata->input_source('host1.example.net');
    $metadata->input_destination('host2.example.net');
    $metadata->tool_name('bwctl/tracepath');
    $metadata->measurement_agent('10.1.1.1');
    $metadata->set_field('ip-transport-protocol', 'icmp');
    $metadata->set_field('time-interval', 600);
    $metadata->add_event_type('failures');
    $metadata->add_event_type('packet-trace');
    $metadata->add_event_type('path-mtu');
    $metadata->post_metadata();
    die $metadata->error() . "\n" if $metadata->error();
    
    #bulk post data
    my $bulk_post = $metadata->generate_event_type_bulk_post();
    my $ts = time;
    $bulk_post->add_data_point('packet-trace', $ts,[
        {
        "success" => 1,
        "error_message" => undef,
        "ip" => "10.1.1.1",
        "query" => "1",
        "ttl" => "1",
        "rtt" => "0.278",
        "mtu" => "9000"
        },
        {
        "success" => 1,
        "error_message" => undef,
        "ip" => "10.1.1.10",
        "query" => "1",
        "ttl" => "2",
        "rtt" => "22.243",
        "mtu" => "9000"
        },
        {
        "success" => 1,
        "error_message" => undef,
        "ip" => "10.1.1.12",
        "query" => "1",
        "ttl" => "3",
        "rtt" => "22.516",
        "mtu" => "9000"
        },
        {
        "success" => 1,
        "error_message" => undef,
        "ip" => "10.1.1.2",
        "query" => "1",
        "ttl" => "4",
        "rtt" => "68.931",
        "mtu" => "9000"
        }
    ]);
    $bulk_post->add_data_point('path-mtu', $ts, 9000);
    $bulk_post->post_data();
    die $bulk_post->error() if($bulk_post->error());
