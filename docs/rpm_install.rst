****************
RPM Installation
****************

Summary
=======
This document describes how to install and configure esmond as an RPM on CentOS 6 using yum.

System Requirements
===================
The RPM currently MUST be installed with **yum** on a `CentOS 6 <https://www.centos.org>`_ system with an i386/i686 or x86_64 architecture. It may also work on other flavors of RedHat Linux but it is only tested on CentOS. It assumes a particular Python 2.7 package available for CentOS 6. Other operating systems should look at the instructions for installing from source.

Configuring Yum
===============
You will need to configure a few additional yum repositories on your target host to install the esmond RPM. This includes the yum repository containing esmond and a few others hosting its dependencies.

Configuring EPEL
----------------
`Extra Packages for Enterprise Linux (EPEL) <https://fedoraproject.org/wiki/EPEL>`_ is a repository run by Fedora containing additional packages commonly needed for systems. They provide an RPM for setting-up the yum repository. You can setup EPEL with the following:

#. Download the latest EPEL RPM. An architecture independent version of this RPM can be found on `this page <http://dl.fedoraproject.org/pub/epel/6/x86_64/repoview/epel-release.html>`_.
#. Install the RPM using `yum localinstall`. Example::

    yum localinstall epel-release-6-VERSION.noarch.rpm

Configuring Datastax
--------------------
Esmond also uses the `Cassandra Database <http://cassandra.apache.org>`_ as the backend for time-series data. Cassandra RPMs are maintained in the `Datastax <http://www.datastax.com>`_ yum repository. You can configure this repository by creating a file */etc/yum.repos.d/datastax.repo* with the following contents::

    [datastax]
    name= DataStax Repo for Apache Cassandra
    baseurl=http://rpm.datastax.com/community
    enabled=1
    gpgcheck=0


Configuring the perfSONAR Yum repository
----------------------------------------
The final repo you need to configure is the repository containing the perfSONAR packages. Esmond currently lives in a pre-release yum repository. It also contains Python 2.7 packages for i386/i686 architectures. You can configure that repository with the following:

#. Download the architecture independent RPM `here <http://software.internet2.edu/branches/release-3.4/rpms/el6/x86_64/RPMS.main/Internet2-repo-0.5-2.noarch.rpm>`_
#. Run the following command::
    
    yum localinstall Internet2-repo-0.5-2.noarch.rpm

Installing esmond
===================
After setting-up the yum repositories you can install esmond with the following::

    yum install esmond

.. note::

    Verify that the *python27-mod_wsgi* package is the one from the Internet2 repo as issues can occur if a different version is installed from another repo.
    
After the command completes logout and re-login so that certain environment variables will be set. You are now ready to begin configuration.


Configuration
=============
Now that esmond is installed you will need to do some configuration of esmond and supporting services such as Apache(httpd), Cassandra, and PostgreSQL.

#. First of all, enable *httpd*, *cassandra* and *postgresql* to start on system boot with the following commands::

    chkconfig --add cassandra
    chkconfig cassandra on
    chkconfig httpd on
    chkconfig postgresql on

#. Assuming this is the first time you have configured PostgreSQL, you will need to initialize PostgreSQL and create a user for esmond to access the database. *NOTE: If you had a PostgreSQL database prior to installing esmond the commands may be slightly different depending on your setup*. Initialize the database with the following commands (NOTE: Replace the password *changeit* with your password)::

    /sbin/service postgresql initdb
    /sbin/service postgresql start
    sudo -u postgres psql -c "CREATE USER esmond WITH PASSWORD 'changeit'"
    sudo -u postgres psql -c "CREATE DATABASE esmond"
    sudo -u postgres psql -c "GRANT ALL ON DATABASE esmond to esmond"

#. Next enable postgres password authentication by editing /var/lib/pgsql/data/pg_hba.conf and replacing all occurrences *ident* with *md5* (usually near the the bottom of the file). It should look something like the following when done::

    # TYPE  DATABASE    USER        CIDR-ADDRESS          METHOD

    # "local" is for Unix domain socket connections only
    local   all         all                               md5
    # IPv4 local connections:
    host    all         all         127.0.0.1/32          md5 
    # IPv6 local connections:
    host    all         all         ::1/128               md5

#. Restart postgresql with the following command::
    /sbin/service postgresql restart

#. Open **/etc/esmond/esmond.conf** in a text editor and set *sql_db_password* to the postgresql password set previously. For example::

    ...
    sql_db_password = changeit
    ...

#. Python 2.7 is required for the remaining configuration commands. Initialize the Python 2.7 virtualenv with the commands below (*NOTE: the commands below must be run from a bash shell*)::

    cd /usr/lib/esmond
    source /opt/rh/python27/enable
    /opt/rh/python27/root/usr/bin/virtualenv --prompt="(esmond)" .
    . bin/activate

#. Build the esmond databases and create an admin user for Django when prompted with the following command::

    python esmond/manage.py syncdb

#. Create a user that can write data to the MA. This may be used for things like the perfSONAR regular testing. Note the generated key::

    python esmond/manage.py add_api_key_user perfsonar

#. Finally, start cassandra and httpd::

    /sbin/service cassandra start
    /sbin/service httpd start

Verifying the Installation
==========================
#. You can verify esmond is running by opening *http://<your-host>/esmond/perfsonar/archive/?format=json* in your browser. If it is working you should just see an empty JSON array `[]`. If things are not working you will get a 500 error or similar. Useful logs are below:

    * /var/log/httpd/error_log.log
    * /var/log/esmond/esmond.log
    * /var/log/esmond/django.log
    
#. Verify you can login as a Django administrator by trying to open http://<your-host>/esmond/admin and logging-in with the username and password created when you ran `python esmond/manage.py syncdb` and were prompted. From this page you can manage API keys and user permissions for writing data.

Debugging Common Issues
=======================
* If cassandra refuses to start and the log contains the error ``Error: Exception thrown by the agent : java.net.MalformedURLException: Local host name unknown: java.net.UnknownHostException``, you may need to adjust your cassandra configuration. The easiest method for correcting this situation is to open */etc/cassandra/cassandra-env.sh* and comment out lines referencing `com.sun.management.jmxremote` by adding a # character at the start of the line. They commented out lines should look like the following::

    #JVM_OPTS="$JVM_OPTS -Dcom.sun.management.jmxremote.port=$JMX_PORT"
    #JVM_OPTS="$JVM_OPTS -Dcom.sun.management.jmxremote.rmi.port=$JMX_PORT"
    #JVM_OPTS="$JVM_OPTS -Dcom.sun.management.jmxremote.ssl=false"
    #JVM_OPTS="$JVM_OPTS -Dcom.sun.management.jmxremote.authenticate=false"
    #JVM_OPTS="$JVM_OPTS-Dcom.sun.management.jmxremote.password.file=/etc/cassandra/jmxremote.password"



