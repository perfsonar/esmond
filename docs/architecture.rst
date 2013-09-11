esmond subsystems
------------------

`espolld`
:::::::::

`espolld` is the process which polls the devices, correlates the data (if
necessary) and puts the data into a work queue which is consumed by
`espersistd`.

Operation
~~~~~~~~~

When `espolld` is started it will query the database for a list of currently
active devices and which OIDSets should be polled for each device.  `espolld`
has two threads of execution: a thread to perform the polling and a thread to
hand data off to `espersistd`.  

`espersistd` manages writing the collected data to disk.  Data collected by
`espolld` is placed into a work queue in `memcached`.  A worker `espersistd`
process removes data from the `memcached` work queue, performs the necessary
calculations on the data and writes it to persistent storage.  The persistent
storage is either a Cassandra database or a SQL database.

At present `espolld` and `espersistd` do not use `esdbd` for database
interactions but instead contacts the SQL and Cassandra databases directly.
This issue will be addressed in future versions of esmond.

`esdbd`
:::::::

`esdbd` provides a consistent interface to the esmond databases.  It provides
a front end service to query both the SQL and TSDB datastores.  `esdb` is
deprecated, see `newdbd`

`espersistd`
::::::::::::

`espersistd` is the process which consumes data from the work queue that is
 populated by `espolld`.  There is a manager process and a number of worker 
 processes.

Operation
~~~~~~~~~

When `espersistd` is started, the manager spawns a number of worker processes -
the number and type of which are defined in the [persist_queue] section of 
the configuration file.  The bulk of the incoming snmp data is being handled 
by the CassandraPollPersister class/worker processes so the bulk of this 
discussion will focus on that.

Data Flow
~~~~~~~~~

As the datum is pulled off of the work queue, it is distributed to the worker 
processes in a non-random way.  Data coming from a particular device is handed 
to the same worker process.  This is necessary for some of the calculations 
that is done to the data.  The entry point for the persister class that the 
worker proces is running is the store() method.  The incoming datum is first 
inserted into the raw_data table/column family.  

If the data for that particular oid (measurment) is to be aggregated (the 
bulk of the snmp data is), it is then passed to a method to caluculate a 
base rate.  A base rate is a "bin" of a certain time frequency (generally 
30 seconds) that can be the sum of more than one incoming raw data measurment. 
The incoming raw data is a monotonically increasing counter coming from the 
network devices.

Since the incoming values are these monotonic values, the first thing that 
is done is calculating a delta.  This is done by comparing the incoming value 
to the previously seen value from the same device/interface.  This is 
accomplished by maintaining an in-memory collection of metadata (essentially 
a python dictionary) and why the data from a given device is always 
distributed to the same worker process.  This way a worker can maintain its 
own internal state of device data.  If the internal metadata collection does 
not contain a value for a particular device/interface (due to a restart of 
the persister, etc), it will do a lookup on the raw data table/column family 
for the last value seen and the metadata for that device is initialized from 
there.

The delta is calculated and then is potentally fractionally split between 
two bins of the relevant frequency.  For example, if 30 second rate bins are 
being generated (one on the minute and one 30 seconds after the minute), a 
measurement coming in 10 seconds after the minute will be fractionally 
distributed between the two appropriate bins (see lines 510 to 518 of 
persist.py for an example of how this done).

Another thing that is determined when calculating the delta is the time since 
the last value for that device/interface was seen.  Ideally there will be a 
contiguous stream of data, but if not, one of two things will additionally 
occur.  If there is a particularly long gap between the current value and 
the previously seen one, then the persister will backtrack and fill the gap 
of bins with data that is marked as not valid.  This is how the client can 
differentiate between a "valid measurement of zero bytes" and a zero that 
is a corollary to a NULL value in a traditional relational database.
Alternately, if the gap is larger than "ideal" but not so large as to 
indicate a gap of no measurements (perhaps the device was offline), then 
additional fractional values are calculated distributed over this smaller 
gap.

After a valid delta is calculated and the base rates are calculated and 
stored on disc, then additional "higher level" aggregations are calculated 
and stored.  The frequencies of these aggregations are associated with 
a particular oidset's metadata - generally hourly and daily.  These higher 
level aggs are the minimum/maximum values seen during a particular time 
range, and also the values necessary to calculate the average over that 
hour/day/etc.  These higher level values are added to the backend, and 
then the worker process accepts the next datum for processing.

`cassandra`
:::::::::::

Apache Cassandra is a row-oriented datastore that has some things in 
common with a key-value store.  Data are stored with a unique row key 
pointing at a wide 'row' of 'columns' of data.  This was chosen because 
it is well suited for handling timeseries data - both the data model works 
well with that kind of data, and the read/write performance is suitable 
as well.  Data in a given row are written to contiguous disc locations, 
data ordering is handled internally by cassandra and the schema that 
is defined for a given column family (the cassandra corollary to a table 
in a traditional RDBMS) so it does not need to be sorted when it is read 
from the backend, and due to the nature of the row key/data model, data 
is not so much queried (where the engine needs to find the data) as it 
is merely retrieved based on the row key and time range.

Row Keys
~~~~~~~~

The core of storing and retrieving data from cassandra is the unique key 
that points at a row of data.  One does not 'query' the row keys, rather 
it is something that can be constructed by the client querying the data.

The row keys for the stored snmp data is of the following form:

router_a:FastPollHC:ifHCInOctets:xe-0_2_0:30000:2012

The components of the row key are:

device_name:oidset:oid:interface_name:data_frequency:year

The device name and interface names are self explanitory, the oidset is a 
grouping of a particular type of mesurement (like data traffic), the oid is 
the measurement itself (the direction of the data traffic), and the 
frequency is the is frequency of the measurements/bins of the measurement 
in milliseconds.  

The year is an artifical construct of how the data are stored.  Rows are 
divided up into a year's worth of data to keep a given row from growing 
arbitrarily wide.  A row of a year's worth of 30 second data is somewhere 
around 1.3 million columns long which is a nice healthy width for a row 
inside a cassandra store.  Cassandra rows should be wide to properly use 
the technology, but partitioning them by year makes for an nice easy cap 
on row width.  A querying client does not need to know the year 
segment of the row key because the query code in the cassandra.py module 
will automatically determine this from the time range specified for the 
query.  

Column Families
~~~~~~~~~~~~~~~

A column family is the cassandra corollary to a table in a RDBMS.  It is 
a collection of rows/columns defined by a 'strongly typed' schema, and the 
unique row keys that point to the rows.  They come in two varieties: a 
regular column family and a 'supercolumn.'  A regular column family is 
basically a row of key/value pairs.  A supercolumn is a row of keys that 
point to mulitple values (like a C struct for example) - one key, multiple 
values.  This will become more clear in the following examples on how the 
esmond cassandra keyspace is designed.

As noted before, the schema of a column family is what could be called 
strongly typed.  Row keys, row column headers, the associated value (or 
in the case of a supercolumn, associated values) are all defined in the 
schema of being of a given type like UTF-8 strings, LONG numbers, counters 
and etc.  Even though the structure of a supercolumn might look like a 
form of associative array, they contain a fixed and not arbitrary mix of 
data types.  There is also an internal sort order that is defined on a row 
as well so that the data are returned in a certain pre-defined order.

This is a perennially referenced (and appropriately titled) article
describing the nature of columns and more importanly supercolumns:

http://jayant7k.blogspot.com/2010/07/cassandra-data-model-wtf-is-supercolumn.html

Following are discussions of the structure of the column families the esmond 
data are stored in.  It has been said that this JSON-like representation of 
a column family structure isn't technically optimal, however, I don't think 
that someone has come up with a better way.

Raw Data cf
~~~~~~~~~~~

The raw data are stored in a regular column family with the following schema:

// regular col family
"raw_data" : {
    "router_a:FastPollHC:ifHCInOctets:xe-0_2_0:30000:2012" : {
        "1343955624" :   // long column name
        "16150333739148" // UTF-8 containing JSON for values.
    }
}

This is a regular column family - the column name is the timestamp and the 
value is the numeric value that came from the devices.  We were originaly 
storing the value as a numeric type, but it's been changed to UTF-8 in case 
in the future we want to start storing more arbitrary information in JSON 
blobs.  The sort order on this (and all the other esmond column families) is 
on the column name - all of the columns are ordered on the timestamp.

Base Rate cf
~~~~~~~~~~~~

// supercolumn
"base_rates" : {
    "router_a:FastPollHC:ifHCInOctets:xe-0_2_0:30000:2012" : {
        "1343955600" : {     // long column name.
            "val": "123",    // string key, counter type value.
            "is_valid" : "2" // zero or positive non-zero.
        }
    }
}

The base rates are stored in a supercolumn.  Column name is the timestamp, 
and the values in the supercol are a string 'key' and a counter type value. 
Counter types, and the name implies, is an i64 numeric data type that can be 
incremented and decremented.  They initialize to a zero value and inserting 
a number works like a += operation in a programming language.  

The 'val' counter is the actual value of the base rate delta and is the sum 
of multiple fractional values (a base rate bin may be made of more than just 
one delta).  The 'is_valid' element is also a counter type and all we care 
about is "does it have a value of zero or greater than zero?"  That element 
is incremented by 1 every time a delta is written to the bin which will 
generate a greater than zero value.  When the persister code is gap-filling 
a range of data where there is missing data, that element is set to zero. 
That way we can differentiate between a "valid measurement val of zero" or 
a "zero value that is basically a NULL."

Rate Aggregation cf
~~~~~~~~~~~~~~~~~~~

// supercolumn
"rate_aggregations" : {
    "router_a:FastPollHC:ifHCInOctets:xe-0_2_0:3600000:2012" : {
        "1343955600" : {   // long column name.
            "val": "1234", // string key, counter type.
            "30": "38"     // key of the 'non-val' column is freq of the base rate.
        }                  // the value of said is the count used in the average.
    }
}

This is one of two column families that contain the higher level 
aggregations.  This one is how we generate the aggregated averages.  It 
has the same basic structure as the base rate cf - timestamp column name, 
string element names and a counter type for the value.  And as before,the 
'val' element contains the actual aggregated delta sums.  The wrinkle is 
with the other element - in this example the element name is '30' and the 
value is '38.'  What's going on there is that the '30' (ie: the element name 
that is not 'val') is the frequency of the base rates that this aggregation 
is made of and the '38' is the number of of deltas that are summed to make 
up the 'val' element.  We need the sum, the base frequency and the number of 
sums to calculate the average.  To wit:

average = sum_value / ( sum_count * base_frequency )

Or in this case:

average = 1234 / ( 38 * 30 )

These calculations are masked/performed by the cassandra.py module when 
the data are retrieved, so it is transparent to the client.  But it is a 
point to note how the data are stored.

Stat Aggregation cf
~~~~~~~~~~~~~~~~~~~

// supercolumn
"stat_aggregations" : {
    "router_a:FastPollHC:ifHCInOctets:xe-0_2_0:86400000:2012" : {
        "1343955600" : { // long column name.
            "min": "0",  // string keys, long types.
            "max": "484140" 
        }
    }
}

This is different and somewhat more straightforward.  As usual, timestamp 
column name and the super column elements are just string names and 
numeric values.  This just stores the min/max rates over the given period. 
No calculations or other tomfoolery like in the last example.


`newdb`
:::::::

`newdb` provides a RESTful interface to the data.  It is typically run under
mod_wsgi inside Apache, however it can be run standalone.
