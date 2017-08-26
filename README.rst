.. image:: https://travis-ci.org/esnet/esmond.svg?branch=develop
    :target: https://travis-ci.org/esnet/esmond

.. image:: https://coveralls.io/repos/esnet/esmond/badge.png?branch=develop
   :target: https://coveralls.io/r/esnet/esmond?branch=develop

*******************************
esmond: ESnet Monitoring Daemon
*******************************

At this time esmond is only supported as part of the perfSONAR toolkit.
-----------------------------------------------------------------------

esmond is a system for collecting, storing, visualizing and analyzing large
sets of timeseries data. It was driven by the needs of the ESnet engineering team
but is likely useful to a much wider audience. esmond has a RESTful API which
allows easy access to the data which is collected. The original focus was on
collecting SNMP timeseries data which is still the system's forte, but there
is support for generalized timeseries data. The perfSONAR_ project has begun
using esmond to store timeseries of network measurements.

esmond uses a hybrid model for storing data. Timeseries data such as interface
counters is stored using Cassandra_. esmond will save the raw data, and create
summarizations similar to RRD_.  However, the system never discards data
through summarization, which distinguishes it from RRD_ (and whisper_/ceres_).
Metadata (such as interface description and interface types from SNMP) are
stored in an SQL database. Storing this data in an SQL database allows us to
use the full expressiveness of SQL to query this data. Since this data changes
relatively infrequently the demands placed on the SQL server are fairly
modest.  Our production server uses PostgreSQL_, but it's likely that SQLite_
would work just fine. Data can be visualized using Graphite_ or through custom
visualizations which can query the RESTful API.

The documentation_ has a lot more details.

Development Environment
-----------------------
This repository allows you to use Vagrant_ to create a VM on VirtualBox_ with the necessary components installed. The default VM is based on CentOS 7 and creates a shared folder in the VM that points at the top-level of your checked-out copy. This allows you to edit files on your base system and have the changes automatically appear in the VM.

Installation
=============
#. Install VirtualBox_ according the the instructions on their site for your system. 
#. Install Vagrant_ according the the instructions on their site for your system. 
#. Install the vagrant-vbguest and vagrant-reload plugins with the following commands::

    vagrant plugin install vagrant-vbguest
    vagrant plugin install vagrant-reload

Starting the VM
=================
#. Clone the esmond github repo::

    git clone https://github.com/esnet/esmond
#. Start the VM with ``vagrant up``. The first time you do this it will take awhile to create the initial VM.

Using the VM
=============
* The VM sets-up port forwarding by default so you can access esmond from the host system. You can test esmond runs on HTTP and HTTPS as follows::

    curl "http://127.0.0.1:20080/esmond/perfsonar/archive/"
    curl -k "https://127.0.0.1:20443/esmond/perfsonar/archive/"
* Any changes you make to the checked-out code on your host system get reflected in the host VM under the `/vagrant` directory
* The following symlinks are setup to files in the git copy of the code:
    
    * /etc/esmond -> /vagrant/vagrant-data/esmond-el7/etc/esmond
    * /usr/lib/esmond -> /vagrant
    * /usr/sbin/esmond_manage -> /vagrant/util/esmond_manage
    * /etc/profile.d/esmond.csh -> /vagrant/rpm/config_files/esmond.csh
    * /etc/profile.d/esmond.sh -> /vagrant/rpm/config_files/esmond.sh
* You must run ``systemctl restart httpd`` whenever you make a code change
* Run ``vagrant reload`` to restart the VM
* Run ``vagrant suspend`` to freeze the VM. Running ``vagrant up`` again will restore the state it was in when you suspended it.
* Run ``vagrant halt`` to shutdown the VM. Running ``vagrant up`` again will run through the normal boot process.
* Run ``vagrant destory`` to completely delete the VM. Running again ``vagrant up`` will build a brand new VM.

.. _Cassandra: http://cassandra.apache.org/
.. _PostgreSQL: http://www.postgresql.org/
.. _RRD: http://oss.oetiker.ch/rrdtool/
.. _Graphite: https://github.com/graphite-project/graphite-web
.. _whisper: https://github.com/graphite-project/whisper
.. _ceres: https://github.com/graphite-project/ceres
.. _SQLite: https://sqlite.org/
.. _perfSONAR: http://www.perfsonar.net/
.. _SNMP: http://en.wikipedia.org/wiki/Simple_Network_Management_Protocol
.. _Vagrant: https://www.vagrantup.com
.. _VirtualBox: https://www.virtualbox.org
.. _documentation: http://software.es.net/esmond/
