**********************
RPM Build Instructions
**********************

Summary
=======
This document describes how to build esmond as an RPM. It does NOT cover installation of the RPM by an end-user. It is intended for developers wishing to package esmond.

Build Environment
=================
The RPM currently supports CentOS 6 (http://centos.org). At a minimum you must have the rpmbuild tool installed but it is highly recommended you have mock (https://fedoraproject.org/wiki/Projects/Mock) installed as well. Mock creates clean environments for building RPMs and allows you to easily build RPMs for different architectures and platforms on the same build host. Installing and configuring mock is outside the scope of this document. See the mock documentation for more details. This document will assume you have mock installed and provide instruction accordingly.

Adding CentOS SCL Yum Repo
--------------------------
Open your epel-6 x86_64 profile and add the CentOS Software Collections (SCL) repo. This is required since esmond needs python 2.7 but CentOS ships with python 2.6. The SCL repo has newer versions that CentOS does not want to make a default but are largely popular with users. This repo is not available for i386 so only add it for x86_64. See the Other Packages section for notes on i386. Add the following to your epel6 x86_64 profile (e.g. /etc/mock/epel-6-x86_64.cfg)::

    [scl]
    name=CentOS-$releasever - SCL
    baseurl=http://mirror.centos.org/centos/6/SCL/x86_64/
    enabled=1
    failovermethod=priority

Running the Build
=================
1. Checkout a clean copy of the source code::

    git clone https://github.com/esnet/esmond.git ./esmond

1. Create a tarball (where VERSION is the major version to be built such as 1.0)::

    cd esmond
    git archive --format=tar --prefix=esmond-VERSION/ HEAD | gzip >$HOME/rpmbuild/SOURCES/esmond-VERSION.tar.gz

1. Copy the .spec file to your rpmbuild directory::

    cp esmond-VERSION/esmond.spec $HOME/rpmbuild/SPECS/

1. Build a source RPM::

    cd $HOME/rpmbuild
    rpmbuild -bs SPEC/esmond.spec

1. Build the RPM with mock::

    mock -r epel-6-x86_64 --resultdir=$HOME/mock-results/epel-6-x86_64/ --arch=x86_64 $HOME/rpmbuild/SRPMS/esmond-VERSION.el6.src.rpm 

1. You're done!

Other Packages
=================

mod_wsgi for python 2.7
----------------------------------------
Currently CentOS does not provide a version of mod_wsgi built against python2.7. This is true for both x86_64 and i386. See the SPEC file in the SRPM at http://software.internet2.edu/branches/release-3.4/rpms/el6/SRPMS/python27-mod_wsgi-3.2-3.el6.src.rpm for an example of the changes required to the default mod_wsgi RPM. Essentially the change boils down to the following:

1. Change the package name from mod_wsgi to python27-mod_wsgi

1. Add python27-python-devel and python27 to the BuildRequires.

1. Update %build section to link against python2.7::

    %build
    ...
    export LD_LIBRARY_PATH=/opt/rh/python27/root/usr/lib64/:/opt/rh/python27/root/usr/lib/:$   LD_LIBRARY_PATH
    %configure --enable-shared --with-python=/opt/rh/python27/root/usr/bin/python2.7

1. In the post section, make httpd aware of python 2.7::

    %post
    grep -q "source /opt/rh/python27/enable" /etc/sysconfig/httpd || echo "source /opt/rh/python27/enable" >> /etc/sysconfig/httpd 

python 2.7 for CentOS i386
----------------------------------------
The CentOS Software Collections only provide Python 2.7 for x86_64. For i386 architectures you will need to rebuild the python27 RPMs. Mock is required to rebuild these RPMs (at least if you want to keep your sanity). Assuming you have mock setup, follow the steps below to rebuild the RPMS.

1. Under the /rpm/mock_configs or the esmond source tree there are two files: epel-6-i386-scl.cfg and epel-6-i386-scl-python27.cfg. Move both of these files to /etc/mock of your build system. 

1. At the bottom of each file is a section called [holding-repo]. Update the path to point at a local holding repo on your system where you can install RPMs.

1. Download the following SRPMS from http://vault.centos.org/6.5/SCL/Source/SPackages/:
    * scl-utils 
 
    * python27
 
    * python27-python
 
    * python27-python-markupsafe
 
    * python27-python-simplejson
 
    * python27-python-sqlalchemy
 
1. Download the following RPMS and place them in your local holding-repo:
    * python27-python-setuptools
 
    * python27-python-nose
 
    * python27-python-sphinx
 
    * python27-python-jinja2
 
    * python27-python-babel
 
    * python27-python-pygments
 
    * python27-python-docutils
 
    * python27-python-virtualenv
 
    * python27-python-werkzeug

1. Rebuild the scl-utils SRPM for i386 and sign the result::

        mock -r epel-6-i386 --resultdir=$HOME/mock-results/epel-6-i386/ --arch=i386 $HOME/rpmbuild/SRPMS/scl-utils-*.el6.centos.alt.src.rpm 
        rpmsign --resign $HOME/mock-results/epel-6-i386/scl-utils-* 

1. Move the scl-utils RPMs you just created to your holding repo and rebuild it::

        cp $HOME/mock-results/epel-6-i386/scl-utils-\*.i386.rpm $HOME/mock-holding-repo/epel-6-i386/i386/RPMS/
        createrepo -d --update $HOME/mock-holding-repo/epel-6-i386/ 

1. Rebuild python27 using the scl profile and sign the result::

        mock -r epel-6-i386-scl --resultdir=$HOME/mock-results/epel-6-i386/ --arch=i386 $HOME/rpmbuild/SRPMS/python27-1-10.el6.centos.alt.src.rpm
        rpmsign --resign $HOME/mock-results/epel-6-i386/python27-* 

1. Move the python27 RPMs to your local holding repo and update it::

        cp $HOME/mock-results/epel-6-i386/python27-*.i386.rpm $HOME/mock-holding-repo/epel-6-i386/i386/RPMS/
        createrepo -d --update $HOME/mock-holding-repo/epel-6-i386/

1. Rebuild the remaining SRPMs downloaded earlier using the scl-python27 profile. Build them in the order below adding them to the local holding repo as you finish each::
    
        mock -r epel-6-i386-scl-python27 --resultdir=$HOME/mock-results/epel-6-i386/ --arch=i386 $HOME/rpmbuild/SRPMS/python27-python-2.7.5-7.el6.centos.alt.src.rpm 
        rpmsign --resign $HOME/mock-results/epel-6-i386/python27-* 
        cp $HOME/mock-results/epel-6-i386/python27-*.i386.rpm $HOME/mock-holding-repo/epel-6-i386/i386/RPMS/
        createrepo -d --update $HOME/mock-holding-repo/epel-6-i386/
        
        mock -r epel-6-i386-scl-python27 --resultdir=$HOME/mock-results/epel-6-i386/ --arch=i386 $HOME/rpmbuild/SRPMS/python27-python-markupsafe-0.11-11.el6.centos.alt.src.rpm
        rpmsign --resign $HOME/mock-results/epel-6-i386/python27-* 
        cp $HOME/mock-results/epel-6-i386/python27-*.i386.rpm  $HOME/mock-holding-repo/epel-6-i386/i386/RPMS/
        createrepo -d --update $HOME/mock-holding-repo/epel-6-i386/
        
        mock -r epel-6-i386-scl-python27 --resultdir=$HOME/mock-results/epel-6-i386/ --arch=i386 $HOME/rpmbuild/SRPMS/python27-python-simplejson-3.0.5-2.el6.centos.alt.src.rpm 
        rpmsign --resign $HOME/mock-results/epel-6-i386/python27-* 
        cp $HOME/mock-results/epel-6-i386/python27-*.i386.rpm  $HOME/mock-holding-repo/epel-6-i386/i386/RPMS/
        createrepo -d --update $HOME/mock-holding-repo/epel-6-i386/
        
        mock -r epel-6-i386-scl-python27 --resultdir=$HOME/mock-results/epel-6-i386/ --arch=i386 $HOME/rpmbuild/SRPMS/python27-python-sqlalchemy-0.7.9-2.el6.centos.alt.src.rpm  
        rpmsign --resign $HOME/mock-results/epel-6-i386/python27-* 
        cp $HOME/mock-results/epel-6-i386/python27-*.i386.rpm  $HOME/mock-holding-repo/epel-6-i386/i386/RPMS/
        createrepo -d --update $HOME/mock-holding-repo/epel-6-i386/
        
1. Finally rebuild python27-mod_wsgi using the SRPM from http://software.internet2.edu/branches/release-3.4/rpms/el6/SRPMS/ and sign the result::

        mock -r epel-6-i386 --resultdir=$HOME/mock-results/epel-6-i386/ --arch=i386 $HOME/rpmbuild/SRPMS/python27-mod_wsgi-3.2-3.el6.src.rpm 
        rpmsign --resign $HOME/mock-results/epel-6-i386/python27-* 

1. Upload the RPMs where you keep esmond. Esmond is noarch so you should not need to rebuild that separately for i386.
