***************************
Registering GridFTP Results
***************************

Esmond includes a script capable of parsing GridFTP server transfer logs and registering data such as throughput and packet-retransmits to a central esmond server. This document describes how to install, configure and run this script. 

Preparing Your Environment
==========================


Preparing Your GridFTP Server(s)
--------------------------------
On the system you wish to install the script you will need the following software:

* GridFTP server 6.0 or newer
    * See the `Fasterdata GridFTP page <https://fasterdata.es.net/data-transfer-tools/gridftp/>`_ for install instructions
    
* Python 2.7 
    * Many modern OSes come with this pre-installed. CentOS 6/RHEL 6 users see :ref:`gridftp-install-centos-python27` for special instructions.

* The *esmond-client* Python package
    * See :ref:`gridftp-install-esmond-client`

* The load_gridftp.py script from esmond
    * See :ref:`gridftp-install-script`

.. _gridftp-prepare-ma:

Preparing Your Measurement Archive
----------------------------------
In addition you will need an esmond installation *on a different host* where you can store the results, often referred to as a Measurement Archive (MA). It needs to be on a different host to prevent conflicts with packages installed by GridFTP and esmond. The esmond installation that comes on the `perfSONAR Toolkit <http://www.perfsonar.net>`_ can serve this purpose. Likewise you can install a standalone esmond instance by following the instructions at :doc:`rpm_install`. 

Once you have a measurement archive, you will need to create credentials so that the GridFTP log parser can register data to it. The credentials take the form of a username and API key. If you have multiple GridFTP servers you may allow them to share the same credentials or create them each individual credentials. Sharing is simpler to manage and individual accounts make it easier to revoke access at a later date for an individual host. The decision is up to you and/or the MA administrator, but you may create an account by logging-in to the host running esmond and issuing the following commands (you may replace *gridftp* with the name of the user you want to add)::

    cd /opt/esmond
    source /opt/rh/python27/enable
    . bin/activate
    python esmond/manage.py add_ps_metadata_post_user gridftp
    python esmond/manage.py add_timeseries_post_user gridftp

The last two commands will output an API key that should be noted for later configuration steps.

.. note: You may re-run the commands in this section at any time if you forget the API key and they will output the existing key.  


Installation
============

.. _gridftp-install-centos-python27:

Installing Python 2.7 on CentOS 6/RHEL 6
-----------------------------------------

If you are running CentOS 6 or RHEL 6 then you do not have the required version (2.7) of python installed. Luckily, each provides a special Software Collections repository that makes his available. Below are the commands you can use to install and configure python 2.7::

    yum install centos-release-SCL
    yum clean all
    yum install python27 
    mkdir -p /opt/esmond-gridftp
    cd /opt/esmond-gridftp
    source /opt/rh/python27/enable
    /opt/rh/python27/root/usr/bin/virtualenv --prompt="(esmond-gridftp)" .

.. note:: Make sure you are using the `bash` shell when you run the commands above

.. _gridftp-install-esmond-client:

Installing esmond-client Python package
---------------------------------------
If you are running CentOS6/RHEL 6 run the following to get in your Python 2.7 environment::
    
    cd /opt/esmond-gridftp
    source /opt/rh/python27/enable
    . bin/activate


Run the following to install the package::

    pip install esmond-client

.. _gridftp-install-script:

Installing the Log Parser Script
--------------------------------
Run the following commands::

    mkdir -p /opt/esmond-gridftp
    cd /opt/esmond-gridftp
    wget --no-check-certificate https://raw.githubusercontent.com/esnet/esmond/develop/util/load_grid_ftp.py

Running the Log Parser
======================

Running Manually
----------------

Assuming you followed all the installation steps you should be able to run a set of commands similar to the following::

    cd /opt/esmond-gridftp
    source /opt/rh/python27/enable
    . bin/activate
    python /opt/esmond-gridftp/load_grid_ftp.py -f /var/log/gridftp-transfer.log -p /opt/esmond-gridftp/load_grid_ftp.pickle -l /var/log/load_grid_ftp.log -U https://archive.mydomain.net/esmond -u gridftp -k ABCDEF1234567890

.. note:: If you are not running CentOS 6 or RHEL 6 then you only need to run the last command

The `load_grid_ftp.py` script has a number of options but the most commonly used ones are in the example above. For a complete listing see the *-h* option of `load_grid_ftp.py`. A description of the options used in the example are as follows:

* *-f* is the path to the GridFTP log file to be parsed. In general it will be found at /var/log/gridftp-transfer.log but may be different depending on the system. You will know it's the correct log file if it has lines like the following::

    DATE=20150407145945.113944 HOST=lbl-diskpt1.es.net PROG=globus-gridftp-server NL.EVNT=FTP_INFO START=20150407145936.596363 USER=anonymous FILE=/data1/100M.dat BUFFER=87380 BLOCK=262144 NBYTES=100000000 VOLUME=/ STREAMS=5 STRIPES=1 DEST=[192.100.78.81] TYPE=RETR CODE=226 retrans=36,17,27,25,61

* *-p* is the path to a file used by the 'load_grid_ftp.py' script to keep track of what lines it has already parsed between runs. This file will be created if it doesn't already exist. If you delete this file, the script may complain about trying to register data that is already in the measurement archive. 

* *-l* is the log file where 'load_grid_ftp.py' logs its own progress and reports parsing errors, etc. This is NOT the GridFTP server log, so don't confuse it with *-f*. 

* *-U* is the URL of your esmond measurement archive. It should begin with *http://* or *https://* and end with /esmond usually. The hostname in between should be the name of the host where you want the data sent. 

* *-u* is the username used to authenticate to esmond. You should have set this up in :ref:`gridftp-prepare-ma`.

* *-k* is the API key used to authenticate to esmond. You should have set this up in :ref:`gridftp-prepare-ma`.


Running in Cron
---------------
Most likely you will not want to run that by hand, rather you'll want it to automatically register results over time. Currently the easiest way to do that is to create a new cron entry. If you are Running CentOS 6/RHEL 6 then you'll fist want to create a shell script since you'll need cron to use the correct python version each time. After that you can create the cron script. You may do this as follows:

#. Open a new file named */opt/esmond-gridftp/load_grid_ftp.sh*  with your favorite text editor and add the following (modifying the last line with the correct esmond URL (-U), username(-u) and API key (-k))::

    #!/bin/bash
    
    cd /opt/esmond-gridftp
    source /opt/rh/python27/enable
    . bin/activate
    python /opt/esmond-gridftp/load_grid_ftp.py -f /var/log/gridftp-transfer.log -p /opt/esmond-gridftp/load_grid_ftp.pickle -l /var/log/load_grid_ftp.log -U https://archive.mydomain.net/esmond -u gridftp -k ABCDEF1234567890

#. Run the following command to give it execute permissions::

    chmod 755 /opt/esmond-gridftp/load_grid_ftp.sh

#. Open a new file at */etc/cron.d/esmond-gridftp.cron* and add the following to parse the log every 15 minutes::

    */15 * * * * root /opt/esmond-gridftp/load_grid_ftp.sh &> /var/log/load_grid_ftp.out

.. note:: You may change the cron schedule above if you would like it to run more or less frequently just as you would any other cron job. The main consideration is giving adequate time so multiple runs of the script don't overlap and lead to unexpected results.


Using the Registered Data
==========================

What Information is Registered?
-------------------------------
Esmond breaks information into *metadata* and *data* as described in :doc:`perfsonar_client_rest`. The metadata describes the parameters of the GridFTP transfer. This includes the following (metadata field names in parentheses):

* The source IP address (*source*)
* The destination IP address (*destination*)
* The fact that the tool used was gridftp (*tool-name*)
* The number of parallel streams (*bw-parallel-streams*)
* The TCP window size if set (*tcp-window-size*)
* If file striping is used, the number of stripes (*bw-stripes*)
* The GridFTP program used such as globus-gridftp-server(*gridftp-program*)
* The block size used by GridFTP in the transfer(*gridftp-block-size*)
* If you give the log scraper the -F option, the name of the file transferred (*gridftp-file*)
* If you give the log scraper the -N option, the name of the user that made the transfer (*gridftp-user*)
* If you give the log scraper the -V option, the name of the volume used in the transfer (*gridftp-volume*)

Likewise it registers the following types of data (event-type in parentheses):

* Throughput (*throughput*)
* Per stream packet retransmits (*streams-packet-retransmits*)
* Error messages of failed transfers (*failures*)

If you want to learn more on how to search these values see :doc:`perfsonar_client_rest`.


Displaying Results in a Dashboard
---------------------------------

You may use `MaDDash <http://software.es.net/maddash>`_ to display and alert on throughput results reported by GridFTP. The process for doing so is the same a configuring MaDDash for BWCTL/iperf results since the event type is the same. See the MaDDash `configuration guide <http://software.es.net/maddash/config_server.html>`_ for more details.








