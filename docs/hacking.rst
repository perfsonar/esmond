==================
Hacking on ESxSNMP
==================


Setting up a development environment
------------------------------------

ESxSNMP comes with a script to set up a development environment.  Run the
`mkdevenv` script::

    ./mkdevenv

Every time you start a new shell you'll need to pull in the enviroment
variables it creates::

    source esxsnmp.env

To setup the database and load the basic config data (OIDs, OIDSets, etc)::

    # this creates the database structure
    python esxsnmp/manage.py syncdb

    # this loads the oidsets
    python esxsnmp/manage.py loaddata oidsets.json

    # this loads the test devices
    python esxsnmp/manage.py loaddata test_devices.json

To run tests do::

    # run all the tests in the api app
    python esxsnmp/manage.py test api 

    # run just a specific test
    python esxsnmp/manage.py test api.TestIfRefPersister  

Note that the Django testing framework will create a separeate testing
database.  The fixtures attribute of the test classes specifies which fixtures
to load.  The fixtures are kept in ``esxsnmp/api/fixtures`` in JSON format.
