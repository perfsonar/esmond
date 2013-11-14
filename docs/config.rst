*************
Configuration
*************

Environment Variables
=====================

``ESMOND_ROOT``
----------------

The standard root directory for all esmond configuration and data.  esmond
will not start unless ``ESMOND_ROOT`` is set.

``ESMOND_CONF``
----------------

This specifies the location of ``esmond.conf``.

``ESMOND_TESTING``
-------------------

Setting this environment variable will cause esmond to use SQLite for it's
SQL database instead of whatever is configured in ``esmond.conf``.

Config File
===========

.. todo::

    Probably should move this into the code that does the config to make it
    easier to keep it in sync.

esmond uses an INI style config file.  By default the config file is located
at ``${ESMOND_ROOT}/esmond.conf``.  The ``${ESMOND_CONF}`` enviroment
variable allows overriding the location of the config file.  The value of
``ESMOND_ROOT`` is available within the config file.

Here is an example ``esmond.conf`` file::

    [main]
    sql_db_engine = django.db.backends.postgresql_psycopg2
    sql_db_name = esmond
    sql_db_user = snmp
    tsdb_root = /ssd/esmond/data
    tsdb_chunk_prefixes = /ssd/esmond/data,/data/esmond/data
    mib_dirs = %(ESMOND_ROOT)s/etc/mibs
    mibs = JUNIPER-FIREWALL-MIB,JUNIPER-COS-MIB,INFINERA-PM-GIGECLIENTCTP-MIB
    syslog_facility = local7
    syslog_priority = debug
    traceback_dir = /data/esmond/crashlog
    pid_dir = %(ESMOND_ROOT)s/var/
    espersistd_uri = 127.0.0.1:11211
    espoll_persist_uri = MemcachedPersistHandler:127.0.0.1:11211
    htpasswd_file = /data/esmond/etc/htpasswd
    cassandra_servers = localhost:9160
    cassandra_user =
    cassandra_pass =
    api_anon_limit = 35
    [persist_map]
    FastPollHC = tsdb
    FastPoll = tsdb
    InfFastPollHC = tsdb
    JnxFirewall = tsdb
    JnxCOS = tsdb
    Errors = tsdb
    IfRefPoll = ifref
    [persist_queues]
    tsdb = TSDBPollPersister:8
    ifref = IfRefPollPersister:1

    
sql_db_*
--------

sql_db_engine, sql_db_host, sql_db_port, sql_db_user, sql_db_password,
sql_db_name are the same as their Django counterparts.

cassandra_*
-----------
Connection string info for cassandra backend.  cassandra_servers can be a 
comma-delimited list of servers if using a ring.

api_anon_limit
--------------
Limits the number of queries a non-authenticated client can request from the 
REST api /bulk/ data endpoint.

espoll_persist_uri
------------------

This tells `espolld` where to find the work queue for data persistence.  It is
of the form handler:ip_addr:port.  Currently the only handler implemented is
the MemcachedPersistHandler.  

esmond_root
------------

The root of the esmond installation.  This is used to find other important
resource.

htpasswd_file
-------------

This is location of the password file that is used by `newdb`

mib_dirs
--------

This is a comma separated list of directories additional MIBs can be found.  DLNetSNMP
automatically includes the system MIB dir in the MIB path.


mibs
----

This is a comma separated list of MIBs to load at startup time.

pid_dir
-------

Directory to store pid files in.

syslog_facility
---------------

Controls which syslog facility esmond uses for logging.

syslog_priority
---------------

Controls the verbosity of log messages sent to syslog.  Defaults to info.

traceback_dir
-------------

When an esmond daemon crashes the system makes an effort to save a traceback
for later fault analysis.  This controls where those files are logged.

tsdb_chunk_prefixes
-------------------

TSDB implements a simple union filesystem for data storage.  This is a comma
separated list of the directories to be used.

tsdb_root
---------

This is the path to the top (write) layer of the TSDB.  It should be the same
as the first component of of tsdb_chunk_prefixes.

persist_map and persist_queues
------------------------------

``persist_map`` specifies which queue(s) data from a given ``OIDSet`` is
placed in.  The queue names are comma separated.  ``persist_queues`` specifies
what persister is used to store the data put into that queue.

The default configuration should be fine for most situations.  Here is the
default config::

    [persist_map]
    FastPollHC = tsdb
    FastPoll = tsdb
    InfFastPollHC = tsdb
    JnxFirewall = tsdb
    JnxCOS = tsdb
    Errors = tsdb
    IfRefPoll = ifref
    [persist_queues]
    tsdb = TSDBPollPersister:8
    ifref = IfRefPollPersister:1

Creating the SQL Database
~~~~~~~~~~~~~~~~~~~~~~~~~
The database defined by the sql_db_* directives need to be loaded with the 
schema defined by the django models in esmond/api/models.py.

python esmond/manage.py syncdb

Configuring Collection
~~~~~~~~~~~~~~~~~~~~~~

Data collection is controlled by the configuration stored in the database.  A
`device` is any device from which data needs to be extracted.  Each device can
#be configured to have one or more `OIDSet` s collected.  An OIDSet is a list of
(generally) related `OID` s to collect together.

An initial set of OIDs and OIDSets is included in src/sql/testdata.sql.

To add a device to esmond you need to do:


   INSERT INTO device (name, begin_time, end_time, community, active)
       VALUES ('test-router', 'NOW', 'infinity', 'public', true);

name should be the DNS name of the device.  I certainly hope you aren't using
'public' for your community.

Once the device has been added you need to define some OIDSets to poll on that
device.  The OIDSets definied in testdata.sql are IfRefPoll, FastPoll and
FastPollHC.  IfRefPoll collects information about the interface such as it's
speed, it's description, etc.  FastPoll and FastPollHC collect
if{In,Out}Octets and ifHC{In,Out}Octets respectively.  To add a OIDSet to be
polled for a device do:

    INSERT INTO DeviceOIDSetMap (DeviceId, OIDSetId)
        VALUES (DeviceId, OIDSetId);

Testing Polling
:::::::::::::::

You can check to see what the results of polling a device would look like by
using the `espoll` tool.  For example:

    $ bin/espoll -f /path/to/esmond/conf router oidset

Start Data Collection
:::::::::::::::::::::

To start collection you need to start the polling and persistence daemons:

    $ bin/espersistd -f /path/to/esmond.conf
    $ bin/espolld -f /path/to/esmond.conf

To monitor the progress of the polling and persisting do:

    $ bin/espersistd -f /path/to/esmond.conf -r stats

You should also see messages in syslog.

Performance Tuning
::::::::::::::::::

Presently TSDB is very I/O intensive.  The current deployment at ESnet uses a
SSD as the top level storage.

Setting up `esdbd` standalone
::::::::::::::::::::::::::::::

   $ bin/esdbd -f /path/to/esmond.conf

Setting up `esdbd` with mod_wsgi
::::::::::::::::::::::::::::::::

To be written, there is a example wsgi wrapper in util.

Graphite Integration
::::::::::::::::::::

Use Store in esmond.graphite_store as the data store for Graphite.  This
section needs to be signficantly fleshed out.

Care and Feeding
::::::::::::::::

If you're using a two level data store take a look at migrate-tsdb-chunks in
util.   

