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

```
source: anl-owamp.es.net
destination: lsvn-owamp.es.net
measurement_agent: anl-owamp.es.net
tool_name: bwctl/tracepath,traceroute
event_type: packet-trace, failures, path-mtu
```

esmond-ps-get-metadata
----------------------

Similar to get-endpoints, but this will fetch the actual metadata test data 
from an esmond perfSONAR archive.  By default it will show the measurements 
that are common to all tests:

```
source
destination
measurement_agent
input_source
input_destination
tool_name
```

Including the --metadata-extended will also show the per-test measurements. 
This option can not be used with the CSV output option.

Sample default output:

```
source: perfsonar-latency-v4.esc.qmul.ac.uk
destination: anl-owamp.es.net
measurement_agent: anl-owamp.es.net
input_source: perfsonar-latency.esc.qmul.ac.uk
input_destination: anl-owamp.es.net
tool_name: powstream

```

Sample output with the --metadata-extended flag:

```
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
```

esmond-ps-get
-------------

TBA - we need to figure out what this is.

esmond-ps-get-bulk
------------------

Tool to pull non-trivial amounts of data from a perfSONAR esmond archive.

Iterates through the metadata matching the user query and makes incremental 
data requests from the archive so as not to overwhelm the data store. When 
all of the data for a given event type associated with a given metadata 
has been gathered, it will be written to disc in either json or csv format, 
with the format:

```
<source>_<dest>_<event_type>_<start_time>_<end_time>.csv|.json
```

So one would end up with a set of output files that look like this:

```
perfsonar.ascr.doe.gov_anl-owamp.es.net_failures_2015-03-15_2015-04-02.csv
perfsonar.ascr.doe.gov_anl-owamp.es.net_histogram-owdelay_2015-03-15_2015-04-02.csv
perfsonar.ascr.doe.gov_anl-owamp.es.net_histogram-ttl_2015-03-15_2015-04-02.csv
perfsonar.ascr.doe.gov_anl-owamp.es.net_packet-count-lost_2015-03-15_2015-04-02.csv
perfsonar.ascr.doe.gov_anl-owamp.es.net_packet-count-sent_2015-03-15_2015-04-02.csv
perfsonar.ascr.doe.gov_anl-owamp.es.net_packet-duplicates_2015-03-15_2015-04-02.csv
perfsonar.ascr.doe.gov_anl-owamp.es.net_packet-loss-rate_2015-03-15_2015-04-02.csv
perfsonar.ascr.doe.gov_anl-owamp.es.net_time-error-estimates_2015-03-15_2015-04-02.csv
```

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

```
http://albq-owamp-v6.es.net:8085/esmond/perfsonar/archive
```

It is only necessary to provide:

```
--url http://albq-owamp-v6.es.net:8085
```

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

```
--agent
--tool
--summary-type
--summary-window
```

These should be fairly self-explanatory.

--filter
~~~~~~~~

An additional power user filter that takes the format:

```
--filter key:value
```

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
~~~~~~~~~~~~~

Required by esmond-ps-get-bulk - specifies a directory to write output 
files to.  Will default to the current working directory.

--ip
~~~~

By default in the output, IP addresses (source, dest, agent, etc) will be 
converted to a human readable fully qualified domain name. Using the -ip 
flag will stop this conversion and display all hostnames as raw IP addresses.




