*******************************
perfSONAR Client REST Interface
*******************************

This document describes the basics of reading and writing data from the perfSONAR measurement archive. The measurement archive implements a REST interface where clients can retrieve descriptions of measurements being run and the results of those measurements. It currently offers support for a range of measurements related to throughput, packet delay, packet loss, packet traces and more (with additional data types being added all the time). This document is intended to give developers a basic programming language-neutral understanding of how to interact with the archive.

Querying Data 
============== 

Getting Started 
---------------- 
Querying the measurement archive generally follows the two-step process below:
#. Find the measurements with the type of data you want
#. Retrieve the result data for the measurements you find

A quick example helps illustrate this process. First, let's say we we want to know about throughput for a particular set of measurements. In perfSONAR we call this the type of data we are interested-in the **event type**. Let's say we also only want throughput for measurements between two hosts where the host *host1.example.net* sends data to *host2.example.net*.  Since host1.example.net sends the data we consider it a **source** and since host2.example.net receives data we call it the **destination**. Assuming our measurement archive runs on archive.example.net we can send the following HTTP GET using curl to get the results we want:

::

    curl http://archive.example.net/esmond/perfsonar/archive/?event-type=throughput&source=host1.example.net&destination=host2.example.net


This returns the following JSON object:
::

    [
        {
            "source":"10.1.1.1",
            "destination":"10.1.1.2",
            "event-types":[
                {
                    "base-uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/packet-retransmits/base",
                    "event-type":"packet-retransmits",
                    "summaries":[],
                    "time-updated":1397482734
                },
                {
                    "base-uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base",
                    "event-type":"throughput",
                    "summaries":[
                        {
                        "summary-type":"average",
                        "summary-window":"86400",
                        "time-updated":1397482735,
                        "uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/averages/86400"
                        }
                    ],
                    "time-updated":1397482735
                },
                {
                    "base-uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/failures/base",
                    "event-type":"failures",
                    "summaries":[],
                    "time-updated":1397315930
                },
                {
                    "base-uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput-subintervals/base",
                    "event-type":"throughput-subintervals",
                    "summaries":[],
                    "time-updated":1397482735
                }
            ],
            "input-source":"host1.example.net",
            "input-destination":"host2.example.net",
            "ip-transport-protocol":"tcp",
            "measurement-agent":"10.1.1.1",
            "metadata-key":"f6b732e9f351487a96126f0c25e5e546",
            "subject-type":"point-to-point",
            "time-duration":"20",
            "time-duration":"14400",
            "tool-name":"bwctl/iperf3",
            "uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/"
        }
    ]


Notice we get back an array of objects. In the example above there is just one measurement that matches our search. Notice the source and destination are IP addresses. The archive always stores IP addresses for a measurement but will automatically do any required conversions if you provided DNS names in your search. Also notice there are multiple *event-types* where one of them matches our search. These other event-types are other data available for the measurement. We just want throughput so we look at the object where *event-type* is *throughput* and extract the **base-uri** field which is */esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base*. We can then query the last 24 hours (i.e. 86,400 seconds) of throughput measurements with the following HTTP GET request:
::

    curl http://archive.example.net/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base?time-range=86400


This returns the following list of datapoints where the *ts* is the time the measurement started and value is the throughput measured in bits per second:
::

    [
        {
            "ts":1397421672,
            "val":7016320000.0
        },
        {
            "ts":1397442692,
            "val":7225480000.0
        },
        {
            "ts":1397466492,
            "val":7095460000.0
        },
        {
            "ts":1397482700,
            "val":7042540000.0
        }
    ]


The example above glosses over many details and options, but outlines the normal workflow for querying data. See the remainder of this section for further details on more advanced queries and data types. 

Finding the right measurements 
------------------------------- 
Finding measurements with parameters relevant to the data you are seeking is the first step in querying the measurement archive. All searches of this type go to the top-level URL (usually /esmond/perfsonar/archive) and you can use HTTP GET parameters to filter the results. Almost any parameter in the measurement objects returned can be used as a search filter. If no results match your search you will get back an empty list. If one or more measurements match your search, you will get back a list of objects describing the measurements called **metadata**. This information includes URIs where you can get the measurement results. Fields and filters common to all measurement objects are listed in the table below:

+-------------------+------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Field name        | Type       | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
+-------------------+------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| source            | IP address | The sender in a point-to-point measurement represented as an IPv4 or IPv6 address. When searching you can provide a DNS name and the server will automatically map it to the correct IP address. See :ref:`psclient-rest-search` for more information.                                                                                                                                                                                                                                                                   |
+-------------------+------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| destination       | IP address | The receiver in a point-to-point measurement represented as an IPv4 or IPv6 address. When searching you can provide a DNS name and the server will automatically map it to the correct IP address. See :ref:`psclient-rest-search` for more information.                                                                                                                                                                                                                                                                 |
+-------------------+------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| measurement-agent | IP address | The host where the measurement was initiated represented as an IPv4 or IPv6 address. This may be the source, destination or a third-party host depending on the tool. When searching you can provide a DNS name and the server will automatically map it to the correct IP address. See :ref:`psclient-rest-search` for more information.                                                                                                                                                                                |
+-------------------+------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| input-source      | string     | A string indicating exactly how the source address is passed to the tool. **You SHOULD NOT search on this field, use the source instead.** This field is for informational purposes only to indicate whether the underlying tool running the measurement (e.g. bwctl, owping, ping) is passed a DNS name or IP when it runs. While searching is not strictly prohibited, you should almost never search on this field. The source is better since it will do DNS to IP mappings and will provide more consistent results.|
+-------------------+------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| input-destination | string     |  A string indicating exactly how the destination address is passed to the tool. **You SHOULD NOT search on this field, use the destination instead.**  See *input-source* above for a complete discussion.                                                                                                                                                                                                                                                                                                               |
+-------------------+------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| tool-name         | string     | A string indicating the name of the tool that produced the measurement. Examples include bwctl/iperf, bwctl/iperf or powstream.                                                                                                                                                                                                                                                                                                                                                                                          |
+-------------------+------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

In addition to the fields above, specific measurement types can have context-specific fields that are searchable. A list of these fields is available in the API `specification`_. Examples and more information on common searches are provided in the remainder of this section.

Listing all the measurements 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
Perhaps the simplest query one can perform is to list all the measurement metadata for which an archive has data. You can do this by querying the top level URI with no GET filters:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/"

.. _psclient-rest-search:

Searching by Endpoint 
^^^^^^^^^^^^^^^^^^^^^^ 
It is common to want to search by the endpoints of a point-to-point test. The archive provides two fields for this: **source** and **destination**. These fields are always stored as an IPv4 or IPv6 address depending on the type of address used in the actual measurement. If you provide just the source, all tests that send data from the given host will be returned. Likewise, if you provide just the destination the all hosts receiving data at the particular host will be returned. If both are provided, only tests between the given source and destination will be returned. Examples:

**Match all measurement metadata with source 10.1.1.1**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?source=10.1.1.1"


**Match all measurement metadata with destination 10.1.1.2**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?destination=10.1.1.2"


**Match all measurement metadata with source 10.1.1.1 AND destination 10.1.1.2**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?source=10.1.1.1&destination=10.1.1.2"


Furthermore, when providing a filter in the GET parameters you may provide a DNS name which the server will automatically convert to an IP address before performing the search. This is an enhancement over previous versions of the measurement archive where it was required to know exactly how an address was stored. The DNS name may be a CNAME or have A and/or AAAA records directly. For example, assume the hostname *host1.example.net* has an A record of 10.1.1.1. We can match all tests where 10.1.1.1 is the source with the following:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?source=host1.example.net"


There is also a special filter for controlling the behavior of the DNS lookups. By default, it will perform DNS lookups for both A and AAAA records. That means if you have two tests involving the same endpoint where one uses IPv4 addresses, the other uses IPv6 addresses AND you provide a hostname with both A and AAAA record, then you will both tests returned by your search. You can control this one of two ways:
#. Always search using the IP address in the form you wish to match. i.e. Searching with an IPv6 address will only return IPv6 results, searching with the IPv4 address returns only IPv4 results.
#. Use the special **dns-match-rule** filter in your GET parameters.
The **dns-match-rule** parameter controls what DNS lookups the server will perform and accepts the following options:

+-----------+-------------------------------------------------------------------------------------------------------------------------------------+
| Value     | Description                                                                                                                         |
+-----------+-------------------------------------------------------------------------------------------------------------------------------------+
| v4v6      | Default. Looks up both A and AAAA records and returns both the IPv4 and IPv6 tests it finds.                                        |
+-----------+-------------------------------------------------------------------------------------------------------------------------------------+
| only-v4   | Only performs a A record lookup for a given hostname and thus only returns results matching the IPv4 address.                       |
+-----------+-------------------------------------------------------------------------------------------------------------------------------------+
| only-v6   | Only performs a AAAA record lookup for a given hostname and thus only returns results matching the IPv6 address.                    |
+-----------+-------------------------------------------------------------------------------------------------------------------------------------+
| prefer-v4 | Tries an A lookup first but if that fails, tries a AAAA lookup. If the initial A lookup succeeds, only IPv4 results are returned.   |
+-----------+-------------------------------------------------------------------------------------------------------------------------------------+
| prefer-v6 | Tries an AAAA lookup first but if that fails, tries a A lookup. If the initial AAAA lookup succeeds, only IPv6 results are returned.|
+-----------+-------------------------------------------------------------------------------------------------------------------------------------+

A quick example that returns only results with a source that matches the AAAA record of host1.example.net is below:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?source=host1.example.net&dns-match-rule=v6-only"


Searching by Event Type 
^^^^^^^^^^^^^^^^^^^^^^^^ 
Another common desire is to search for only those measurements with a particular type of data. There is a special filter called **event-type** that returns this information. This will return any measurement metadata object that has an item in its *event-types* list where the *event-type* field equals the provided value. For example, to return only those measurements containing throughput data one could run:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?event-type=throughput"


Event types may also contain summaries. There are multiple types of summaries as described in :ref:`psclient-rest-basevsumm`. For example, an *average* summary may take the statistical average of all the measurements over a 24 hour period and post that value to a single data point. This allows for faster retrieval of long ranges of data by reducing the number of datapoints returned. A summary may perform some type of transformation such as a *statistics* summary that takes a histogram object and returns common statistical measures. There are two relevant fields for a summary: the **summary-type** (which is either *aggregation*, *average* or *statistics*) and **summary-window** which is the time range (in seconds) that is summarized. Summaries are defined when metadata is created so you can't expect all data to have summaries nor for a summary to be available for a particular time window unless it is explicitly listed in the metadata. For example, we can search for all one-way delay histogram (event type *histogram-owdelay*) with 24 hour statistical summaries as follows:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?event-type=histogram-owdelay&summary-type=statistics&summary-window=86400"


Summaries are explained in more detail in the section :ref:`psclient-rest-basevsumm`.

Searching by most recent result time 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
The previous examples will return all measurement metadata regardless of whether they have received any new data recently. In some cases this is fine, but its often useful to filter-out tests that have not been updated in a long time. For example if you have an old test that is no longer run and will not be updated again, but would like to keep the data around for historical purposes. You can filter measurement metadata based on time with the following special time filters:

+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Filter   | Description                                                                                                                                                                                                                                                                                                                                                                                                                                           |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time      | Match a measurement last updated at the exact time given as a UNIX timestamp                                                                                                                                                                                                                                                                                                                                                                          |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time-start|Match only measurements that were updated after the given time (inclusive). If time-end nor time-range is defined, then it will return all results from the start time to the current time. In UNIX timestamp format.                                                                                                                                                                                                                                  |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time-end  |Match only data that was measured before the given time (inclusive). If time-start nor time-range is provided, then will return all data stored in the archive up to and including the end time. In UNIX timestamp format.                                                                                                                                                                                                                             |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time-range| Only return results that have been updated in the given number of seconds in the past. If time-start nor end-time is defined, then it is the number of seconds in the past from the current time. If only time-start is defined then it is the number of seconds after time-start to search. If only time-end is provided it is the number of seconds before end time to search. If both time-start and time-end are defined, this value is ignored.  |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

Examples of various combinations of the parameters above are provided below:

**Match all measurement metadata updated since April 14, 2014 12:00GMT**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?time-start=1397476800"


**Match all measurement metadata updated before April 14, 2014 12:00GMT**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?time-end=1397476800"


**Match all measurement metadata updated at exactly April 14, 2014 12:00GMT**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?time=1397476800"


**Match all measurement metadata updated between April 14, 2014 12:00GMT and April 15, 2014 12:00GMT**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?time-start=1397476800&time-end=1397563200"


**Match all throughput metadata with source 10.1.1.1 AND destination 10.1.1.2 updated in the last 24 hours**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?time-range=86400&event-type=throughput&source=10.1.1.1&destination=10.1.1.2"


Limiting results returned 
^^^^^^^^^^^^^^^^^^^^^^^^^^ 
The following options are available to limit the results returned and do things like pagination of results:

+--------+-------------------------------------------------------------------------------------+
| Filter | Description                                                                         |
+--------+-------------------------------------------------------------------------------------+
|limit   | The maximum number of results to return. If not set then 1000 results are returned. |
+--------+-------------------------------------------------------------------------------------+
|offset  | The number of tests to skip. Useful for pagination.                                 |
+--------+-------------------------------------------------------------------------------------+

Examples of these options are provided below:

**Return the first 10 results**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?limit=10"


**Return the second 10 results**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?limit=10&offset=10"


**Ignore the first 10 results and return everything else**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/?offset=10"


Retrieving Measurement Results 
------------------------------- 

.. _psclient-rest-basevsumm:

Base Data vs Summaries 
^^^^^^^^^^^^^^^^^^^^^^^ 
Once you find the measurements with the parameters you want, you need to retrieve the actual results those measurements are collecting. The location of the data is provided by the list of objects in the **event-types** field. For reference, the *event-types* object looks something like the following:
::

    {
        "event-types":[
            {
                "base-uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/packet-retransmits/base",
                "event-type":"packet-retransmits",
                "summaries":[],
                "time-updated":1397482734
            },
            {
                "base-uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base",
                "event-type":"throughput",
                "summaries":[
                    {
                        "summary-type":"average",
                        "summary-window":"86400",
                        "time-updated":1397482735,
                        "uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/averages/86400"
                    }
                ],
                "time-updated":1397482735
            },
            {
                "base-uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/failures/base",
                "event-type":"failures",
                "summaries":[],
                "time-updated":1397315930
            },
            {
                "base-uri":"/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput-subintervals/base",
                "event-type":"throughput-subintervals",
                "summaries":[],
                "time-updated":1397482735
            }
        ]
    }


You will notice all of the objects have a **base-uri** field and a few have objects have a *summaries* list that also contain a URI. In the archive there are two types of data: **base data** and **summarized data**. Base data is exactly what is written to the archive when the measurement is performed, the server does not transform it in anyway. In contrast, summarized data is that which was transformed in some way by the server. All summarized data has a **summary type** and **summary window**. The summary window is the timeframe in seconds described by the summary. A summary window of 0 means it is a direct transformation of the base data (i.e. there should be a one-to-one mapping in the number of base data points and summary data points).  The summary type must be one of the following:

* **aggregation** - The data was combined in a context specific way. For example, if the underlying type is numeric it is the sum of all data points in the summary window. If its a histogram it is a union of the two histograms.
* **average** - The statistical average of a series of numbers
* **statistics** - Currently only applies to the histogram type, but contains common statistical measures of data over the summary window such as minimum, maximum, mean and median.

Summary data such as aggregation and average over large time windows can be a useful way to grab data over long periods of time as it should result in a smaller data set returned than the base data returned over the same timeframe. The *statistics* summary can be useful even on base data as it provides additional information about each data point. Querying base or summary data depends on the use case.

Retrieving time series data 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
Once you have decided whether you want base or statistical data, retrieving it is simply a matter of doing an HTTP GET to the provide URI. For example, to get all the base throughput data for a particular test, you can run:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base"


In general you will want to filter data based on time and you can do so with the following GET parameters (notice they have the same names and meaing as we used to search the measurement metadata):

+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Filter   | Description                                                                                                                                                                                                                                                                                                                                                                                                                                           |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time      | Match a result recorded at the exact time given (represented as a UNIX timestamp)                                                                                                                                                                                                                                                                                                                                                                     |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time-start|Match only results recorded after the given time (inclusive). If time-end nor time-range is defined, then it will return all results from the start time to the current time. In UNIX timestamp format.                                                                                                                                                                                                                                                |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time-end  |Match only data that was measured before the given time (inclusive). If time-start nor time-range is provided, then will return all data stored in the archive up to and including the end time. In UNIX timestamp format.                                                                                                                                                                                                                             |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time-range| Only return results that have been recorded in the given number of seconds in the past. If time-start nor end-time is defined, then it is the number of seconds in the past from the current time. If only time-start is defined then it is the number of seconds after time-start to search. If only time-end is provided it is the number of seconds before end time to search. If both time-start and time-end are defined, this value is ignored. |
+----------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

For example, you can get the last 24 hours of data with the following:

::

    curl "http://archive.example.net/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base?time-range=86400"


This will return an array of time series object with two fields: **ts** containing the unix timestamp when the measurement was run and **val** containing the result of the object. For example:
::

    [
        {
            "ts":1397421672,
            "val":7016320000.0
        },
        {
            "ts":1397442692,
            "val":7225480000.0
        },
        {
            "ts":1397466492,
            "val":7095460000.0
        },
        {
            "ts":1397482700,
            "val":7042540000.0
        }
    ]

The format of **val** depends on the event type (and in some cases the summary-type as well), some are numeric while others are JSON objects. The next section describes common event types and how to retrieve data.

Querying Throughput 
^^^^^^^^^^^^^^^^^^^^ 
**Event Type(s):** throughput

Throughput is a series of integer values always in bits per second. There may be average summaries but in general you will likely query the base data if the throughput tests only run a few times a day. You can do this with a query like the following to get the last 24 hours of throughput data:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/throughput/base?time-range=86400"


Results:
::

    [
        {
            "ts":1397421672,
            "val":7016320000.0
        },
        {
            "ts":1397442692,
            "val":7225480000.0
        },
        {
            "ts":1397466492,
            "val":7095460000.0
        },
        {
            "ts":1397482700,
            "val":7042540000.0
        }
    ]


Querying Delay/One-way Delay 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
**Event Type(s):** histogram-rtt, histogram-owdelay

Delay values are stored in a histogram where the histogram bucket is the number of milliseconds measured and the value is the number of packets that were measured to have that value. Delay in terms of the round trip time reported by ping is represented with the event-type **histogram-delay**. One-way delay is represented as "histogram-owdelay". The format of their histograms is exactly the same. Examples of query the 24 hours of base data are below:

**Ping Round Trip Time**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/2355e337a7214611ab1bc5db51e40424/histogram-rtt/base?time-range=86400"


**Owamp One-way Delay**
::

    curl "http://archive.example.net/esmond/perfsonar/archive/fce0483e51de49aaa7fcf8884d053134/histogram-owdelay/base?time-range=86400"


Results will look something like the following:
::

    [
        {
            "ts":1397504013,
            "val":{
                "34.4":506,
                "34.5":85,
                "34.6":5,
                "34.7":4
            }
        },
        {
            "ts":1397504052,
            "val":{
                "34.4":510,
                "34.5":80,
                "34.6":7,
                "34.7":3
            }
        },
        .....
    ]


You may interpret the results as for the packet sample starting at time 1397504013 there were 506 packets that took 34.4ms, 85 that took 34.5ms, 5 that too 34.6, etc. Delay tests can run rather frequently thus it can be very useful to use summarized data. Aggregation summaries combine all the histograms in a given time window. For example a histogram for 24 hours may look like the following:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/fce0483e51de49aaa7fcf8884d053134/histogram-owdelay/aggregations/86400"
    
::

    [
        {
            "ts":1396915200,
            "val":{
                "34.2":3,
                "34.3":38814,
                "34.4":114820,
                "34.5":54190,
                "34.6":7842,
                "34.7":9595,
                "34.8":741,
                "34.9":298,
                "35":185,
                "35.1":158,
                "35.2":112,
                "35.3":61,
                "35.4":40,
                "35.5":19,
            }
        },
        ...
    ]


Another useful summary for the delay histograms is **statistics**. This calculates common statistical measures of the data. An example of the statistical summaries for each base data point (i.e. summary-window equals 0) is as follows where the field names correspond to standard statistical measures:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/fce0483e51de49aaa7fcf8884d053134/histogram-owdelay/statistics/0"
    
::

    [
        {
            "ts":1397504795,
            "val":{
                "maximum":"34.4",
                "mean":34.4,
                "median":34.4,
                "minimum":"34.4",
                "mode":[
                "34.4"
                ],
                "percentile-25":34.4,
                "percentile-75":34.4,
                "percentile-95":34.4,
                "standard-deviation":0.0,
                "variance":0.0
            }
        },
        {
            "ts":1397504835,
            "val":{
                "maximum":"34.4",
                "mean":34.38233333333333,
                "median":34.4,
                "minimum":"34.3",
                "mode":[
                "34.4"
                ],
                "percentile-25":34.4,
                "percentile-75":34.4,
                "percentile-95":34.4,
                "standard-deviation":0.03813863599495395,
                "variance":0.001454555555555597
            }
        },
    ...
    ]


Querying Packet Loss 
^^^^^^^^^^^^^^^^^^^^^ 
**Event Type(s):** packet-loss-rate
Packet loss rate measures the number of packets lost over the number of packets sent. It is represented as a floating point number between 0 and 1 where 0 equals 0% packet loss and 1 equals 100% packet loss. You can query the base packet loss data using the packet-loss-rate event type such as in the request below:
::

    curl "http://archive.example.net/esmond/perfsonar/archive/fce0483e51de49aaa7fcf8884d053134/packet-loss-rate/base"

::

    [
        {
            "ts":1397555532,
            "val":0.04666666666666667
        },
        {
            "ts":1397555538,
            "val":0.06666666666666667
        },
        {
            "ts":1397555613,
            "val":0.0
        },
        {
            "ts":1397555619,
            "val":0.0
        }
    ]


Packet-loss can also have an *aggregation* summary that give the packet loss percentage over the given summary window. 


Querying Packet Traces 
^^^^^^^^^^^^^^^^^^^^^^^ 
**Event Type(s):** packet-trace
The results of a traceroute or tracepath measurement are stored under the packet-trace event type. The result is an array of objects describing the result of each traceroute or tracepath probe. For example:
::

    curl http://archive.example.net/esmond/perfsonar/archive/641860b2004c46a7b21fe26e5ffea9af/packet-trace/base?time-range=600

::

    [
        {
            "ts":1397566094,
            "val":[
                {
                    "error_message":null,
                    "ip":"198.124.238.65",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"0.246",
                    "success":1,
                    "ttl":"1"
                },
                {
                    "error_message":null,
                    "ip":"198.124.238.65",
                    "mtu":"9000",
                    "query":"2",
                    "rtt":"0.195",
                    "success":1,
                    "ttl":"1"
                },
                {
                    "error_message":null,
                    "ip":"134.55.38.77",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"22.159",
                    "success":1,
                    "ttl":"2"
                },
                {
                    "error_message":null,
                    "ip":"134.55.42.41",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"22.430",
                    "success":1,
                    "ttl":"3"
                },
                {
                    "error_message":null,
                    "ip":"134.55.43.82",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"33.548",
                    "success":1,
                    "ttl":"4"
                },
                {
                    "error_message":null,
                    "ip":"134.55.49.57",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"44.019",
                    "success":1,
                    "ttl":"5"
                },
                {
                    "error_message":null,
                    "ip":"134.55.50.201",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"65.203",
                    "success":1,
                    "ttl":"6"
                },
                {
                    "error_message":null,
                    "ip":"134.55.40.6",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"67.694",
                    "success":1,
                    "ttl":"7"
                },
                {
                    "error_message":null,
                    "ip":"134.55.49.2",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"68.914",
                    "success":1,
                    "ttl":"8"
                },
                {
                    "error_message":null,
                    "ip":"198.129.254.30",
                    "mtu":"9000",
                    "query":"1",
                    "rtt":"68.887",
                    "success":1,
                    "ttl":"9"
                }
            ]
        }
    ]

The object fields have the following meaning:

+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Field Name  | Description                                                                                                                                                            |
+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|error-message| A string indicating if an error occurred for the probe. It is null if *success* is 1 and should be populated if *success* is 0.                                        |
+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ip           | The IP address returned by the probe                                                                                                                                   |
+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|mtu          | The maximum transmission unit measured by the probe. This is only populated for tracepath tests and will be null if not measured.                                      |
+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|query        | For a given *ttl* a tool may send multiple probes. This distinguishes between probes with the same ttl.                                                                |
+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|rtt          |The round trip time measured by the probe in milliseconds.                                                                                                              |
+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|success      |A boolean indicating if the probe succeeded. If it did not, then further details can be found in *error_message*.                                                       |
+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ttl          |The time-to-live set in the IP headers of the probe. Traceroute and tracepath gradually increase this value to measure the path. The list will always be sorted by ttl. |
+-------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

There are no summaries supported for the packet-trace type currently.

Querying Subinterval Data 
^^^^^^^^^^^^^^^^^^^^^^^^^^ 
**Event Type(s):** throughput-subintervals, packet-retransmits-subintervals

Data such as throughput and packet retransmits is also available for subintervals of an individual test. No summarizations are avilable for this data type.
::

    curl "http://archive.example.net/esmond/perfsonar/archive/f6b732e9f351487a96126f0c25e5e546/packet-retransmits-subintervals/base?time-range=86400"


Results:
::

    [
       {
          "ts":1419471577,
          "val":[
             {
                "duration":"1.000000",
                "start":"0.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"1.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"2.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"3.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"4.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"5.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"6.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"7.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"8.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"9.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"10.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"11.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"12.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"13.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"14.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"15.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"16.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"17.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"18.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"19.000000",
                "val":0
             }
          ]
       },
       {
          "ts":1419493946,
          "val":[
             {
                "duration":"1.000000",
                "start":"0.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"1.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"2.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"3.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"4.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"5.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"6.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"7.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"8.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"9.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"10.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"11.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"12.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"13.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"14.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"15.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"16.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"17.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"18.000000",
                "val":0
             },
             {
                "duration":"1.000000",
                "start":"19.000000",
                "val":0
             }
          ]
       }
    ]



Publishing Data 
================ 

Getting Started 
---------------- 
The measurement archive defines a REST API for publishing data via HTTP POST requests. Much like querying data there are two steps to this process:

    #. Publish the measurement description and get the event-type URIs used for posting measurement results
    #. Using the URIs from step one, publish the measurement results

A quick example demonstrates this process. First we post a description of our measurement, called the measurement *metadata* with the following request:
::

    curl -X POST --dump-header - -H "Content-Type: application/json" -H "Authorization: ApiKey perfsonar:b3ba46b99e2ed8a267a409f3c4379238305ccaf2" --data '{"subject-type": "point-to-point", "source": "10.1.1.1", "destination": "10.1.1.2", "tool-name": "bwctl/iperf3", "measurement-agent": "110.1.1.1", "input-source": "host1.example.net","input-destination": "host2.example.net","time-duration": 30,"ip-transport-protocol": "tcp","event-types": [{"event-type": "throughput","summaries":[{"summary-type": "aggregation","summary-window": 3600},{"summary-type": "aggregation","summary-window": 86400}]},{"event-type": "packet-retransmits","summaries":[]}]}' http://archive.example.net/esmond/perfsonar/archive/

Notice we set the HTTP Authorization header since writing data generally will require some sort of authentication. See :ref:`psclient-rest-authn` for more details. The body is a JSON object describing the metadata. The result back is our metadata object with additional information such as the URIs where we can publish/retrieve information on the measurement and its results:
::

    {  
       "destination":"10.1.1.2",
       "event-types":[  
          {  
             "base-uri":"/esmond/perfsonar/archive/2ba58a26aee64a1e94cd2b5bacbb2cc6/packet-retransmits/base",
             "event-type":"packet-retransmits",
             "summaries":[  

             ],
             "time-updated":null
          },
          {  
             "base-uri":"/esmond/perfsonar/archive/2ba58a26aee64a1e94cd2b5bacbb2cc6/throughput/base",
             "event-type":"throughput",
             "summaries":[  
                {  
                   "summary-type":"aggregation",
                   "summary-window":"3600",
                   "time-updated":null,
                   "uri":"/esmond/perfsonar/archive/2ba58a26aee64a1e94cd2b5bacbb2cc6/throughput/aggregations/3600"
                },
                {  
                   "summary-type":"aggregation",
                   "summary-window":"86400",
                   "time-updated":null,
                   "uri":"/esmond/perfsonar/archive/2ba58a26aee64a1e94cd2b5bacbb2cc6/throughput/aggregations/86400"
                }
             ],
             "time-updated":null
          }
       ],
       "input-destination":"host2.example.net",
       "input-source":"host1.example.net",
       "ip-transport-protocol":"tcp",
       "measurement-agent":"110.1.1.1",
       "metadata-key":"2ba58a26aee64a1e94cd2b5bacbb2cc6",
       "source":"10.1.1.1",
       "subject-type":"point-to-point",
       "time-duration":"30",
       "tool-name":"bwctl/iperf3",
       "uri":"/esmond/perfsonar/archive/2ba58a26aee64a1e94cd2b5bacbb2cc6/"
    }


We can now publish a single data point to one of the URIs defined by a *base-uri* field (*NOTE: We can NOT publish to a summary URL as all summaries are performed by the server*). We send a simple time-series object with a UNIX timestamp indicating when the measurement was run and the value of the result:
::

    curl -X POST --dump-header - -H "Content-Type: application/json" -H "Authorization: ApiKey perfsonar:b3ba46b99e2ed8a267a409f3c4379238305ccaf2" --data '{"ts": "1392238294", "val": "1000000000"}' http://archive.example.net/esmond/perfsonar/archive/2ba58a26aee64a1e94cd2b5bacbb2cc6/throughput/base


Alternatively, we can publish measurement results from multiple times and with multiple event-types in the following bulk request:
::

    curl -X POST --dump-header - -H "Content-Type: application/json" -H "Authorization: ApiKey perfsonar:b3ba46b99e2ed8a267a409f3c4379238305ccaf2" --data '{"data": [{"ts": 1392238390, "val": [{"event-type": "throughput","val": 1000000000}, {"event-type": "packet-retransmits","val": 10}]}, {"ts": 1392238390, "val": [{"event-type": "throughput","val": 900000000}, {"event-type": "packet-retransmits","val": 5}]}]}' http://esmond-dev/perfsonar/archive/2ba58a26aee64a1e94cd2b5bacbb2cc6/

See the remainder of this section for more details one each of these steps.

.. _psclient-rest-authn:

Authentication and Authorization 
--------------------------------- 
Writing data generally requires some form of authentication and authorization. Currently the measurement archive supports the use of the HTTP Authorization header with an authorization string the form of ``ApiKey <username>:<api-key>`` where ``<username>`` and ``<api-key>`` are the authentication credentials. It is also recommended all requests be sent over HTTPS since otherwise these credentials will be sent in plain text.

Publishing the Measurement Description 
--------------------------------------- 
The first step to publishing data is to send a *metadata* object describing the measurement and the types of results it will collect. It looks very similar to the measurement descriptions returned by a query. When you register though, you do not provide the metadata-key nor any of the URIs as these will be generated by the server. All requests are sent as an HTTP POST to the top-level URL (usually ending with /esmond/perfsonar/archive). The metadata object MUST contain a *subject-type* field and a list of *event-types*. If the subject-type is *point-to-point* then the following fields are additionally required:

+-------------------+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Field name        | Type       | Description                                                                                                                                                                                                                                                                               |
+-------------------+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| source            | IP address | The sender in a point-to-point measurement represented as an IPv4 or IPv6 address. It MUST be in the form of an IP address when registering (unlike querying where you can search by DNS name as well)                                                                                    |
+-------------------+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| destination       | IP address | The receiver in a point-to-point measurement represented as an IPv4 or IPv6 address. It MUST be in the form of an IP address when registering (unlike querying where you can search by DNS name as well)                                                                                  |
+-------------------+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| measurement-agent | IP address | The host where the measurement was initiated represented as an IPv4 or IPv6 address. This may be the source, destination or a third-party host depending on the tool. It MUST be in the form of an IP address when registering (unlike querying where you can search by DNS name as well) |
+-------------------+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| input-source      | string     | A string indicating exactly how the source address is passed to the tool.                                                                                                                                                                                                                 |
+-------------------+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| input-destination | string     |  A string indicating exactly how the destination address is passed to the tool. .                                                                                                                                                                                                         |
+-------------------+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| tool-name         | string     | A string indicating the name of the tool that produced the measurement. Examples include bwctl/iperf, bwctl/iperf or powstream.                                                                                                                                                           |
+-------------------+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

The objects in the *event-types* array provided each have two fields:

+------------+--------------------------+-----------------------------------------------------------------------------------------------+
| Field name | Type                     | Description                                                                                   |
+------------+--------------------------+-----------------------------------------------------------------------------------------------+
| event-type | String                   | String indicating the type of data. See :ref:`psclient-rest-eventtypes`.                      |
+------------+--------------------------+-----------------------------------------------------------------------------------------------+
| summaries  | Array of Summary objects | The list of summaries to be performed. if no summaries than this can be an empty list.        |
+------------+--------------------------+-----------------------------------------------------------------------------------------------+

The summary objects have the following fields:

+----------------+---------+--------------------------------------------------------------------------------+
| Field name     | Type    | Description                                                                    |
+----------------+---------+--------------------------------------------------------------------------------+
| summary-type   | String  | The type of summary to be performed.                                           |
+----------------+---------+--------------------------------------------------------------------------------+
| summary-window | Integer | The number of seconds indicating the time period over which data is summarized |
+----------------+---------+--------------------------------------------------------------------------------+

After sending the request, the HTTP status code will indicate the result. If it succeed you will receive an HTTP 200 status code with the created metadata object including the generated *metadata-key* and URIs for each event-type. One feature of the Measurement Archive that can be useful is that if an existing measurement exactly matches one posted (i.e. same parameters and same even types) than that object is returned. This prevents the need of registration clients to keep local state of the URIs used to publish data. They can simply re-register the metadata each time and get back the existing metadata object if there is one. 

Publishing a Single Measurement Result 
--------------------------------------- 
You can publish a single measurement by sending a HTTP POST to one of the values in the event-type *base-uri* fields of the metadata object we created. This HTTP body contains a JSON object with two fields:

+-----------+-----------------------+------------------------------------------------------------------+
| Field name| Type                  | Description                                                      |
+-----------+-----------------------+------------------------------------------------------------------+
| ts        | UNIX Timestamp        | A UNIX timestamp of when the measurement was performed.          |
+-----------+-----------------------+------------------------------------------------------------------+
| val       | Depends on event-type | The value of the measurement whose type depends on the event-type|
+-----------+-----------------------+------------------------------------------------------------------+

The HTTP status code indicates success or failure. HTTP 200 means the measurement was published and there will be no JSON body. If the request fails for any reason, an non-200 status code is set and the cody will contain a JSON object with a single *error* field containing a message describing the error.  

Publishing Multiple Measurement Results 
---------------------------------------- 
It may be desirable to publish data points for multiple timestamps and/or multiple event types in the same request. This type of bulk request contains an object with a *data* field contain an array of the data to be published. The array contains a series of time-series objects with a *ts* and a *val* just like in the single-measurement case but the val of each object takes the following form:

+------------+-----------------------+------------------------------------------------------------------------------------------------------------------------------+
| Field name | Type                  | Description                                                                                                                  |
+------------+-----------------------+------------------------------------------------------------------------------------------------------------------------------+
| event-type | String                | The event-type of the measurement being published                                                                            |
+------------+-----------------------+------------------------------------------------------------------------------------------------------------------------------+
| val        | Depends on event-type | The value of the measurement whose type depends on the event-type. See :ref:`psclient-rest-eventtypes`.                      |
+------------+-----------------------+------------------------------------------------------------------------------------------------------------------------------+

A formatted example that registers *throughput* and *packet-retransmits* event types for two times is provided below:
::

    {
       "data":[
          {
             "ts":1392238390,
             "val":[
                {
                   "event-type":"throughput",
                   "val":1000000000
                },
                {
                   "event-type":"packet-retransmits",
                   "val":10
                }
             ]
          },
          {
             "ts":1392238390,
             "val":[
                {
                   "event-type":"throughput",
                   "val":900000000
                },
                {
                   "event-type":"packet-retransmits",
                   "val":5
                }
             ]
          }
       ]
    }

In the response, the HTTP status code indicates success or failure. HTTP 200 means the measurement was published and there will be no JSON body. If the request fails for any reason, an non-200 status code is set and the cody will contain a JSON object with a single *error* field containing a message describing the error.  

Examples 
--------- 
Publishing Throughput Data 
^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
An example of throughput metadata as published for BWCTL running iperf3 by the perfSONAR Regular Testing component:
::

    {  
       "tool-name":"bwctl/iperf3",
       "source":"10.1.1.1",
       "measurement-agent":"10.1.1.1",
       "destination":"10.1.1.2",
       "ip-transport-protocol":"tcp",
       "time-duration":"20",
       "event-types":[  
          {  
             "event-type":"failures"
          },
          {  
             "event-type":"packet-retransmits"
          },
          {  
             "event-type":"throughput",
             "summaries":[  
                {  
                   "summary-type":"average",
                   "summary-window":"86400"
                }
             ]
          },
          {  
             "event-type":"throughput-subintervals"
          }
       ],
       "bw-parallel-streams":"1",
       "subject-type":"point-to-point",
       "input-destination":"host1.example.net",
       "input-source":"host2.example.net"
    }


Example of publishing the measurement results to the bulk interface as done by the perfSONAR regular testing component:
::

    {
       "data":[
          {
             "ts":1397807404,
             "val":[
                {
                   "event-type":"packet-retransmits",
                   "val":"112"
                },
                {
                   "event-type":"throughput",
                   "val":"8446270000"
                },
                {
                   "event-type":"throughput-subintervals",
                   "val":[
                      {
                         "val":"47619700",
                         "duration":"1.034930",
                         "start":"0.000000"
                      },
                      {
                         "val":"584518000",
                         "duration":"0.972302",
                         "start":"1.034930"
                      },
                      {
                         "val":"5186490000",
                         "duration":"0.993889",
                         "start":"2.007230"
                      },
                      {
                         "val":"9970380000",
                         "duration":"0.999317",
                         "start":"3.001120"
                      },
                      {
                         "val":"9441540000",
                         "duration":"0.999761",
                         "start":"4.000440"
                      },
                      {
                         "val":"9181440000",
                         "duration":"0.999988",
                         "start":"5.000200"
                      },
                      {
                         "val":"9606770000",
                         "duration":"1.000250",
                         "start":"6.000190"
                      },
                      {
                         "val":"9770360000",
                         "duration":"0.999813",
                         "start":"7.000440"
                      },
                      {
                         "val":"9752390000",
                         "duration":"0.999935",
                         "start":"8.000250"
                      },
                      {
                         "val":"9726870000",
                         "duration":"1.000190",
                         "start":"9.000180"
                      },
                      {
                         "val":"9824500000",
                         "duration":"0.999853",
                         "start":"10.000400"
                      },
                      {
                         "val":"9851140000",
                         "duration":"1.000130",
                         "start":"11.000200"
                      },
                      {
                         "val":"9806560000",
                         "duration":"0.999972",
                         "start":"12.000400"
                      },
                      {
                         "val":"9754530000",
                         "duration":"1.000150",
                         "start":"13.000300"
                      },
                      {
                         "val":"9854340000",
                         "duration":"0.999805",
                         "start":"14.000500"
                      },
                      {
                         "val":"9809550000",
                         "duration":"1.000090",
                         "start":"15.000300"
                      },
                      {
                         "val":"9813970000",
                         "duration":"1.000070",
                         "start":"16.000400"
                      },
                      {
                         "val":"9001800000",
                         "duration":"0.999908",
                         "start":"17.000400"
                      },
                      {
                         "val":"9043970000",
                         "duration":"0.999884",
                         "start":"18.000400"
                      },
                      {
                         "val":"8886000000",
                         "duration":"1.002790",
                         "start":"19.000200"
                      },
                      {
                         "val":"9430650000",
                         "duration":"0.067380",
                         "start":"20.003000"
                      }
                   ]
                }
             ]
          }
       ]
    }


Publishing Delay/One-way Delay Data 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 
An example of delay metadata as published for BWCTL running ping by the perfSONAR Regular Testing component:
::

    {  
       "tool-name":"bwctl/ping",
       "source":"10.1.1.1",
       "measurement-agent":"10.1.1.1",
       "destination":"10.1.1.2",
       "ip-transport-protocol":"icmp",
       "time-probe-interval":1,
       "ip-packet-size":1000,
       "event-types":[  
          {  
             "event-type":"failures"
          },
          {  
             "event-type":"histogram-ttl-reverse",
             "summaries":[  
                {  
                   "summary-type":"statistics",
                   "summary-window":"0"
                }
             ]
          },
          {  
             "event-type":"packet-duplicates-bidir"
          },
          {  
             "event-type":"packet-loss-rate-bidir",
             "summaries":[  
                {  
                   "summary-type":"aggregation",
                   "summary-window":"3600"
                },
                {  
                   "summary-type":"aggregation",
                   "summary-window":"86400"
                }
             ]
          },
          {  
             "event-type":"packet-count-lost-bidir"
          },
          {  
             "event-type":"packet-count-sent"
          },
          {  
             "event-type":"histogram-rtt",
             "summaries":[  
                {  
                   "summary-type":"aggregation",
                   "summary-window":"86400"
                },
                {  
                   "summary-type":"statistics",
                   "summary-window":"86400"
                },
                {  
                   "summary-type":"statistics",
                   "summary-window":"0"
                }
             ]
          },
          {  
             "event-type":"packet-reorders-bidir"
          }
       ],
       "subject-type":"point-to-point",
       "input-destination":"host2.example.net",
       "sample-size":"100",
       "input-source":"host1.example.net"
    }


Similarly, metadata example for powstream as registered by the perfSONAR Regular Testing component (note the slightly different event types from ping since they actually measure different values):
::

    {
       "tool-name":"powstream",
       "source":"10.1.1.1",
       "measurement-agent":"10.1.1.1",
       "destination":"10.1.1.2",
       "ip-transport-protocol":"udp",
       "time-duration":60,
       "time-probe-interval":0.1,
       "sample-bucket-width":"0.0001",
       "event-types":[
          {
             "event-type":"failures"
          },
          {
             "event-type":"histogram-ttl",
             "summaries":[
                {
                   "summary-type":"statistics",
                   "summary-window":"0"
                }
             ]
          },
          {
             "event-type":"packet-duplicates"
          },
          {
             "event-type":"packet-loss-rate",
             "summaries":[
                {
                   "summary-type":"aggregation",
                   "summary-window":"3600"
                },
                {
                   "summary-type":"aggregation",
                   "summary-window":"86400"
                }
             ]
          },
          {
             "event-type":"packet-count-lost"
          },
          {
             "event-type":"packet-count-sent"
          },
          {
             "event-type":"histogram-owdelay",
             "summaries":[
                {
                   "summary-type":"aggregation",
                   "summary-window":"3600"
                },
                {
                   "summary-type":"statistics",
                   "summary-window":"3600"
                },
                {
                   "summary-type":"aggregation",
                   "summary-window":"86400"
                },
                {
                   "summary-type":"statistics",
                   "summary-window":"86400"
                },
                {
                   "summary-type":"statistics",
                   "summary-window":"0"
                }
             ]
          },
          {
             "event-type":"time-error-estimates"
          }
       ],
       "time-interval":0,
       "subject-type":"point-to-point",
       "input-destination":"host2.example.net",
       "sample-size":600,
       "input-source":"host1.example.net"
    }


Example of publishing the ping measurement results to the bulk interface as done by the perfSONAR regular testing component:
::

    {
       "data":[
          {
             "ts":1397804761,
             "val":[
                {
                   "event-type":"histogram-ttl-reverse",
                   "val":{
                      "59":100
                   }
                },
                {
                   "event-type":"packet-duplicates-bidir",
                   "val":0
                },
                {
                   "event-type":"packet-loss-rate-bidir",
                   "val":{
                      "denominator":"100",
                      "numerator":"0"
                   }
                },
                {
                   "event-type":"packet-count-lost-bidir",
                   "val":"0"
                },
                {
                   "event-type":"packet-count-sent",
                   "val":"100"
                },
                {
                   "event-type":"histogram-rtt",
                   "val":{
                      "41.00":99,
                      "41.10":1
                   }
                },
                {
                   "event-type":"packet-reorders-bidir",
                   "val":0
                }
             ]
          }
       ]
    }


Similarly an example of publishing the ping and powstream measurement results to the bulk interface as done by the perfSONAR regular testing component:
::

    {
       "data":[
          {
             "ts":1397807372,
             "val":[
                {
                   "event-type":"histogram-ttl",
                   "val":{
                      "59":"600"
                   }
                },
                {
                   "event-type":"packet-duplicates",
                   "val":"0"
                },
                {
                   "event-type":"packet-loss-rate",
                   "val":{
                      "denominator":"600",
                      "numerator":"0"
                   }
                },
                {
                   "event-type":"packet-count-lost",
                   "val":"0"
                },
                {
                   "event-type":"packet-count-sent",
                   "val":"600"
                },
                {
                   "event-type":"histogram-owdelay",
                   "val":{
                      "34.5":"30",
                      "34.3":"440",
                      "34.6":"7",
                      "34.4":"123"
                   }
                },
                {
                   "event-type":"time-error-estimates",
                   "val":"0.000124"
                }
             ]
          }
       ]
    }


Publishing Packet Loss 
^^^^^^^^^^^^^^^^^^^^^^^ 
A special note about packet loss: packet loss is currently published for multiple tools such as ping, UDP throughput tests, and owamp(powstream or owping). Packet loss is a percentage type and the MA provides a special format for registering such values to make summarization possible. Instead of registering the float value, you register the *numerator* and *denominator*, in this case packets lost and packets sent respectively. Below is the packet-loss portion extracted from one-way delay example above:
::

    ...
    {
        "event-type":"packet-loss-rate",
        "val":{
            "denominator":"600",
            "numerator":"0"
        }
    },
    ...



Publishing Packet Traces 
^^^^^^^^^^^^^^^^^^^^^^^^^ 
An example of packet trace metadata as published for BWCTL running tracepath by the perfSONAR Regular Testing component:
::

    {
       "tool-name":"bwctl/tracepath",
       "source":"10.1.1.1",
       "measurement-agent":"10.1.1.1",
       "destination":"10.1.1.2",
       "ip-transport-protocol":"icmp",
       "event-types":[
          {
             "event-type":"failures"
          },
          {
             "event-type":"packet-trace"
          },
          {
             "event-type":"path-mtu"
          }
       ],
       "subject-type":"point-to-point",
       "input-destination":"host1.example.net",
       "input-source":"host2.example.net"
    }


Similarly an example of publishing the BWCTL tracepath measurement results to the bulk interface as done by the perfSONAR regular testing component:
::

    {
       "data":[
          {
             "ts":1397804940,
             "val":[
                {
                   "event-type":"packet-trace",
                   "val":[
                      {
                         "success":1,
                         "error_message":null,
                         "ip":"10.1.1.1",
                         "query":"1",
                         "ttl":"1",
                         "rtt":"0.278",
                         "mtu":"9000"
                      },
                      {
                         "success":1,
                         "error_message":null,
                         "ip":"10.1.1.10",
                         "query":"1",
                         "ttl":"2",
                         "rtt":"22.243",
                         "mtu":"9000"
                      },
                      {
                         "success":1,
                         "error_message":null,
                         "ip":"10.1.1.12",
                         "query":"1",
                         "ttl":"3",
                         "rtt":"22.516",
                         "mtu":"9000"
                      },
                      {
                         "success":1,
                         "error_message":null,
                         "ip":"10.1.1.2",
                         "query":"1",
                         "ttl":"4",
                         "rtt":"33.562",
                         "mtu":"9000"
                      }
                   ]
                },
                {
                   "event-type":"path-mtu",
                   "val":"9000"
                }
             ]
          }
       ]
    }

.. _psclient-rest-eventtypes:

Full List of Event Types 
========================= 
A few of the common event types have been covered in previous sections, but a full list is provided below for reference (NOTE: See API `specification`_ for more formal definitions of each type):

+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Name                                  | Description                                                                                                                                                                                                                                                                         |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|failures                               |A record of test failures. A failure is any measurement that was scheduled to run but circumstances led to a state where it is unable to record a measurement. For example, being unable to connect to the remote endpoint. This is an object currently with one field named *error*.|
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|histogram-owdelay                      | A histogram describing the observed one-way delays over a time period. Buckets always in milliseconds.                                                                                                                                                                              |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|histogram-rtt                          |A histogram describing the observed packet round-trip times over a over a time period. Buckets always in milliseconds.                                                                                                                                                               |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|histogram-ttl                          |A histogram describing the observed number of hops (time-to-live) of packets over a time period from source to destination.                                                                                                                                                          |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|histogram-ttl-reverse                  |A histogram describing the observed number of hops (time-to-live) of packets over a time period from destination to source.                                                                                                                                                          |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ntp-delay                              |The round trip delay time to the NTP server in milliseconds.                                                                                                                                                                                                                         |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ntp-dispersion                         |The maximum error of the local clock relative to the NTP reference clock in milliseconds.                                                                                                                                                                                            |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ntp-jitter                             |Short-term variations in the clock frequency. The RMS deviation of the NTP offset in milliseconds.                                                                                                                                                                                   |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ntp-offset                             |The time difference between the system clock and the NTP reference clock in milliseconds.                                                                                                                                                                                            |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ntp-polling-interval                   |The NTP polling interval in seconds.                                                                                                                                                                                                                                                 |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ntp-reach                              |An integer representing the reachability register, which is technically an octal value. If all is well and NTP has been running for a while, this should read 377. It may be lower during startup or if the NTP servers is unreachable on some attempts.                             |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ntp-stratum                            |An integer indicating the NTP stratum of the local host (number of servers to a reference clock). 1=Primary (has a hardware clock), 2-15=Secondary reference (via NTP), 16=Unsynchronized                                                                                            |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|ntp-wander                             |Long-term variations in NTP RMS frequency jitter in PPM (parts per million) - a measure of long-term clock stability.                                                                                                                                                                |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-duplicates                      |The number of duplicate packets observed in a sample for a single direction.                                                                                                                                                                                                         |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-duplicates-bidir                |The number of duplicate packets observed for a complete packet round trip (from source to destination and then back to source)                                                                                                                                                       |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-loss-rate                       |The number of packets lost divided by the number of packets sent.                                                                                                                                                                                                                    |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-loss-rate-bidir                 |The number of packets lost in both directions divided by the number of packets sent over a given summarization window.                                                                                                                                                               |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-trace                           |The observed packet trace such as that returned by traceroute or tracepath.                                                                                                                                                                                                          |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-count-lost                      |The number of packets dropped in one direction. This is a raw count of packets and can be combined with packet­count­sent event type data to determine the rate of unidriectional loss.                                                                                              |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-count-lost-bidir                |The number of packets dropped in both directions. This is a raw count of packets and can be combined with packet­count­sent event type data to determine the rate of biidriectional loss.                                                                                            |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-count-sent                      |The number of packets sent in a sample. This is a raw count of packets and can be combined with packet-count-lost event type data to determine the rate of loss.                                                                                                                     |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-reorders                        |The number of packets received out of order for a unidirectional transfer                                                                                                                                                                                                            |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-reorders-bidir                  |The number of packets received out of order for a bidirectional transfer                                                                                                                                                                                                             |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-retransmits                     |The number of packets retransmitted for a transfer using reliable transport protocol such as TCP.                                                                                                                                                                                    |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|packet-retransmits-subintervals        |The number of packets retransmitted per subinterval of time                                                                                                                                                                                                                          |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|path-mtu                               |The maximum transmission unit of a path.                                                                                                                                                                                                                                             |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|streams-packet-retransmits             |For tests running multiple streams, the packet-retransmits for each individual stream. Each stream is represented as a position in an array. If other stream- stats collected, a stream will maintain the same position in each event type.                                          |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|streams-packet-retransmits-subintervals|For tests running multiple streams, the packet restransmit subintervals for each inividual stream. Each stream is represented as a position in an array. If other stream- stats collected, a stream will maintain the same position in each event type                               |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|streams-throughput                     |For tests running multiple streams, the throughput for each individual stream. Each stream is represented as a position in an array. If other stream- stats collected, a stream should maintain the same position in each event type.                                                |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|streams-throughput-subintervals        |For tests running multiple streams, the throughput subintervals for each inividual stream. Each stream is represented as a position in an array. If other stream- stats collected, a stream will maintain the same position in each event type                                       |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|throughput                             |The observed amount of data sent over a period of time. Throughput must be in bits per second(bps).                                                                                                                                                                                  |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|throughput-subintervals                |The throughput for individual subintervals of a throughput test                                                                                                                                                                                                                      |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
|time-error-estimates                   |An estimate of the clock error in a sample in milliseconds                                                                                                                                                                                                                           |
+---------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

Full API Specification
======================
* `Full API Specification <https://docs.google.com/document/d/1DFl4bgFxIQtRqYIZPHAT8xW4TACppKq2UeYK13ZsUDk/pub>`_

.. _specification: https://docs.google.com/document/d/1DFl4bgFxIQtRqYIZPHAT8xW4TACppKq2UeYK13ZsUDk/pub