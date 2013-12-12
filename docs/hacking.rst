==================
Hacking on esmond
==================


Setting up a development environment
------------------------------------

esmond comes with a script to set up a development environment.  Run the
`mkdevenv` script::

    ./mkdevenv

Every time you start a new shell you'll need to pull in the enviroment
variables it creates::

    source esmond.env

To setup the database and load the basic config data (OIDs, OIDSets, etc)::

    # this creates the database structure
    python esmond/manage.py syncdb

    # this loads the oidsets
    python esmond/manage.py loaddata oidsets.json

    # this loads the test devices
    python esmond/manage.py loaddata test_devices.json

To run tests do::

    # run all the tests in the api app
    python esmond/manage.py test api 

    # run all the tests in a file (esmond/api/tests/test_api.py)
    python esmond/manage.py test api.tests.test_api

    # run all the tests in a class in a file (DeviceAPITests)
    python esmond/manage.py test api.tests.test_api.DeviceAPITests

    # run just a specific test
    python esmond/manage.py test api.tests.test_api.DeviceAPITests.test_get_device_list

Note that the Django testing framework will create a separeate testing
database.  The fixtures attribute of the test classes specifies which fixtures
to load.  The fixtures are kept in ``esmond/api/fixtures`` in JSON format. We
are in the process of deprecating fixtures in favor of creating test objects in
code because it is simpler and less error prone.


Checking coverage of the tests
------------------------------

Coverage (http://nedbatchelder.com/code/coverage/) is a tool that can be 
used to see how much of the codebase is covered by the unit tests, or how 
much of a particular module is exercised by a script or piece of code.  
These are instructions on running against the test suite, but applies to 
other things like scripts.

To install::

    pip install coverage

To run against the test suite, change directory to the root of the esmond 
codebase and run the following command::

    coverage run esmond/manage.py test -v2 api.tests

This will run the entire test suite, one can tailor the "api.tests" bit 
to only run a subset of the tests.   

After this is complete, a data file called ".coverage" is created in that 
directory (it will be ignored by .hgignore) containing data from the most 
recent invocation.  This file is used to run the reporting features on.

To get a general coverage report::

    coverage report --include=esmond*

The --include arg will make it so it will only produce stats on the codebase 
instead of also the site-packages modules involved.  This will list all of the
modules that were hit by the test invocation and what percentage of the code 
in each was worked by the tests.  Modules not listed were not touched, and 
their absence can be used to determine additional tests to formulate.

To get a report that also lists the line numbers from each module that have 
been missed::

    coverage report --include=esmond* -m

That will display what lines have been missed.  Generally a single line of 
code is just part of a conditional statement and might not be super relevent.  
But sizable blocks of code (something like: 1104-1119) are candidates for 
inspection to see if additional tests need to be formulated to execute 
that block.

Profiling the persister
-----------------------

To profile the persister, set the "profile_persister = no" line in the config 
file to "yes."  Then run the persister for a while - do note that the 
profiler does put some drag on the processes.  After 20 minutes or so (or less depending on what you're checking), wait for the queues to drain from
whatever method you used to fill them (poller, data generatation script) and 
issue a clean shutdown signal to the persister.

Individual files with the cProfile information will be created in the 
directory indicated by the "traceback_dir" entry in the config file.  They 
will be of the following format::

    aluifref-1386882414.34.prof
    alusapref-1386882414.54.prof
    cassandra_1-1386882414.63.prof
    cassandra_2-1386882414.68.prof
    cassandra_3-1386882414.73.prof
    cassandra_4-1386882414.78.prof
    cassandra_5-1386882414.83.prof
    cassandra_6-1386882414.88.prof
    cassandra_7-1386882414.93.prof
    cassandra_8-1386882414.98.prof
    cassandra_9-1386882415.04.prof
    ifref-1386882414.45.prof
    infifref-1386882414.43.prof

They are named by the qname of the persister process that generated them and 
just a time.time() stamp to make the names unique over subsequent runs.

Don't forget to turn profiling back to "no" when you are done.

Be aware that unless you perfectly killed the persister at the precice moment 
it was done consuming things, the top process reported might be {time.sleep}. 
This is because of a tight loop when a persister process has nothing to do.

