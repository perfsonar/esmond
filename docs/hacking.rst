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

To run tests do::

    # run all the tests in the api app
    python esxsnmp/manage.py test api 
    # run just a specific test
    python esxsnmp/manage.py test api.TestIfRefPersister  

