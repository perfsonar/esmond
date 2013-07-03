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
