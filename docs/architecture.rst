ESxSNMP subsystems
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
storage is either a TSDB database or a SQL database.

At present `espolld` and `espersistd` do not use `esdbd` for database
interactions but instead contacts the SQL and TSDB databases directly.  This
issue will be addressed in future versions of ESxSNMP.

`esdbd`
:::::::

`esdbd` provides a consistent interface to the ESxSNMP databases.  It provides
a front end service to query both the SQL and TSDB datastores.  `esdb` is
deprecated, see `newdbd`

`espersistd`
::::::::::::

`newdb`
:::::::

`newdb` provides a RESTful interface to the data.  It is typically run under
mod_wsgi inside Apache, however it can be run standalone.
