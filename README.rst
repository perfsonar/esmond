.. image:: https://travis-ci.org/esnet/esmond.svg?branch=develop
    :target: https://travis-ci.org/esnet/esmond

.. image:: https://coveralls.io/repos/esnet/esmond/badge.png?branch=develop
   :target: https://coveralls.io/r/esnet/esmond?branch=develop

*******************************
esmond: ESnet Monitoring Daemon
*******************************

At this time esmond is only supported as part of the perfSONAR toolkit.
-----------------------------------------------------------------------

esmond is a system for collecting, storing, visualizing and analyzing large
sets of timeseries data. It was driven by the needs of the ESnet engineering team
but is likely useful to a much wider audience. esmond has a RESTful API which
allows easy access to the data which is collected. The original focus was on
collecting SNMP timeseries data which is still the system's forte, but there
is support for generalized timeseries data. The perfSONAR_ project has begun
using esmond to store timeseries of network measurements.

esmond uses a hybrid model for storing data. Timeseries data such as interface
counters is stored using Cassandra_. esmond will save the raw data, and create
summarizations similar to RRD_.  However, the system never discards data
through summarization, which distinguishes it from RRD_ (and whisper_/ceres_).
Metadata (such as interface description and interface types from SNMP) are
stored in an SQL database. Storing this data in an SQL database allows us to
use the full expressiveness of SQL to query this data. Since this data changes
relatively infrequently the demands placed on the SQL server are fairly
modest.  Our production server uses PostgreSQL_, but it's likely that SQLite_
would work just fine. Data can be visualized using Graphite_ or through custom
visualizations which can query the RESTful API.

The documentation_ has a lot more details.

.. _Cassandra: http://cassandra.apache.org/
.. _PostgreSQL: http://www.postgresql.org/
.. _RRD: http://oss.oetiker.ch/rrdtool/
.. _Graphite: https://github.com/graphite-project/graphite-web
.. _whisper: https://github.com/graphite-project/whisper
.. _ceres: https://github.com/graphite-project/ceres
.. _SQLite: https://sqlite.org/
.. _perfSONAR: http://www.perfsonar.net/
.. _SNMP: http://en.wikipedia.org/wiki/Simple_Network_Management_Protocol
.. _documentation: http://software.es.net/esmond/
