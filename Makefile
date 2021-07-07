PERFSONAR_AUTO_VERSION=4.4.0
#Need to set BRANCH in environment - Jenkins does this.

jenkins_rpms:
	git archive --format=tar --prefix=esmond-${PERFSONAR_AUTO_VERSION}/ remotes/${BRANCH} | gzip > /root/rpmbuild/SOURCES/esmond-${PERFSONAR_AUTO_VERSION}.tar.gz
	rpmbuild -bs rpm/esmond.spec 
	yum-builddep -y /root/rpmbuild/SRPMS/esmond*.src.rpm
	rpmbuild --rebuild /root/rpmbuild/SRPMS/esmond*.src.rpm
