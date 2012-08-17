==================
Hacking on ESxSNMP
==================


Testing on a local machine
--------------------------

Run the mkdevenv script::

    ./mkdevenv

Every time you start a new shell you'll need to pull in the enviroment
variables it creates::

    source esxsnmp.env

To run tests do::

    python esxsnmp/manage.py test
    python esxsnmp/manage.py test api.TestIfRefPersister

