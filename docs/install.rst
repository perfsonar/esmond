************
Installation
************

Prerequisites
=============

ESxSNMP relies on the following software:

  * Python_, version 2.7 or greater
  * Net-SNMP_
  * PostgreSQL_, verson 8.0 or greater
  * memcached_

In addition, it uses the following Python libraries:

  * DLNetSNMP_, with ESnet mods
  * psycopg2_
  * Django_
  * web.py_ 
  * TSDB_
  * memcached_

.. _Python: http://www.python.org/
.. _Net-SNMP: http://www.net-snmp.org/
.. _PostgreSQL: http://www.postgresql.org/
.. _memcached: http://memcached.org/
.. _DLNetSNMP: http://bitbucket.org/jdugan/dlnetsnmp
.. _psycopg2: http://www.initd.org/pub/software/psycopg/PSYCOPG-2-0/
.. _Django: http://www.djangoproject.com/
.. _web.py: http://webpy.org/
.. _TSDB: http://code.google.com/p/tsdb/
.. _memcached: http://www.memcached.org/

Installation
============

virtualenv
----------

buildout, or more specifically zc.buildout, is a tool for creating an isolated
Python environment and installing packages inside it.  It is used in some
parts of the Python community to manage deployments and is currently the most
convienent way to install ESxSNMP.  At some point in the future this may
change. buildout includes a bootstrap script that has a single dependency
which is Python.

1. Install the prerequisites

    You will need to install Python, Net-SNMP and PostgreSQL using your normal
    method for installing software.  These packages are very common and are
    supported by most Linux distributions, BSD systems, OS X and others.

1. Obtain the code

    Currently there is no release tarball so we'll use a version checked out
    from the Subversion repo.

    The directory you install ESxSNMP into will be referred to as ESXSNMP.

        $ cd $ESXSNMP
        $ svn checkout http://esxsnmp.googlecode.com/svn/trunk/ esxsnmp

    Note that this creates a subdirectory called esxsnmp, so if you have
    $ESXSNMP set to /opt/esxsnmp, the code will be in /opt/esxsnmp/esxsnmp/

1. Perform the buildout

    Buildout is a tool that allows the construction of an isolated environment
    for running Python programs.  It will take care of fetching the Python
    dependencies and installing them in this isolated environement.  To do the
    buildout run the following commands:

       $ cd $ESXSNMP/esxsnmp
       $ python bootstrap.py
       $ bin/buildout

    Note that all of the programs will be installed in $ESXSNMP/esxsnmp/bin.
    So to run the polling daemon for example you'd run
    $ESXSNMP/esxsnmp/bin/espolld.
   
Other installation methods
--------------------------

Currently virtualenv is the only documented install method.  There is an RPM
under development.  If you'd like a copy of the RPM contact the author.

