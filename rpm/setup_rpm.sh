#!/bin/sh

# Script that needs modification but shows what needs to
# be done to build the rpm.  Presumes the esmond source
# is in ~/esmond/esmond.  Consider it documentation.

cd ~/esmond/esmond
# I build on a clean VM so pull fresh source.
git pull
# Create a source tar. You will need to change the version
# to match the RPM. git archive will remove the .git files
git archive --format=tar --prefix=esmond-1.0/ HEAD | gzip > ~/rpmbuild/SOURCES/esmond-1.0.tar.gz

# This command will fail but will create the necessary
# rpmbuild hierarchy in your home directory
rpmbuild -bp esmond/rpm/esmond.spec
cd esmond/rpm/
sudo yum-builddep esmond.spec
# This will build the RPM - look in: ~/rpmbuild/RPMS/noarch/
rpmbuild -ba esmond.spec