.. esmond documentation master file, created by
   sphinx-quickstart on Thu Aug 16 23:38:27 2012.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.


*******************************
esmond: ESnet Monitoring Daemon
*******************************

Summary
~~~~~~~

esmond is a system for collecting, storing, visualizing and analyzing large
sets of SNMP data. It was driven by the needs of the ESnet engineering team
but is likely useful to a much wider audience. esmond has a RESTful API which
allows easy access to the data which is collected.

esmond uses a hybrid model for storing data. Time series data such as
interface counters is stored using TSDB_. TSDB is a library for storing time
series data with no loss of information. TSDB optimizes the store of it's data
so that data which share similar timestamps is stored nearby on the disk
allowing very fast access to specific time ranges. Data such as interface
description and interface type are stored in an SQL database. Storing this
data in an SQL database allows us to use the full expressiveness of SQL to
query this data. Since this data changes relatively infrequently the demands
placed on the SQL server are fairly modest.  Our production server uses
PostgreSQL_, but it's likely that SQLite_ would work just fine.

.. _TSDB: http://code.google.com/p/tsdb/
.. _PostgreSQL: http://www.postgresql.org/
.. _SQLite: https://sqlite.org/

Contents:

.. toctree::
   :maxdepth: 2

   intro
   install
   config
   deployment_cookbook

   architecture

   api.client
   
   hacking
   api

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

