************
Introduction
************

Summary
=======

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

Desgin Goals
============

esmond was designed to meet the needs of the Network Engineering group at
ESnet_.  The key design goals were:

  * data collection should be very reliable
  * data visualization should be very reliable but not at the expense of data
    collection
  * raw data should never be discarded
  * new interfaces should be detected automatically
  * automate as much as possible
  * provide a clean interface for programatic control

.. _ESnet: http://www.es.net/

