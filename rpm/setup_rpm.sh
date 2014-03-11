#!/bin/sh

# Script that needs modification but shows what needs to
# be done to build the rpm.  Presumes the esmond source
# is in ~/esmond/esmond.  Consider it documentation.

cd ~/esmond/esmond
# I build on a clean VM so pull fresh source.
hg pull
hg update
cd ..
# This will eventually need to be changed to the 
# appropriate version listed in the spec file.
cp -r esmond/ esmond-0.99
# Strip out the mercurial stuff - also prevents
# an error when building the rpm.
rm -rf esmond-0.99/.hg*
tar cvf esmond-0.99.tar esmond-0.99/
gzip esmond-0.99.tar
# This command will fail but will create the necessary
# rpmbuild hierarchy in your home directory
rpmbuild -bp esmond/rpm/esmond.spec
cp esmond-0.99.tar.gz ~/rpmbuild/SOURCES/
cd esmond/rpm/
sudo yum-builddep esmond.spec
# This will build the RPM - look in: ~/rpmbuild/RPMS/noarch/
rpmbuild -ba esmond.spec