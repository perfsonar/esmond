FROM centos:7
ENV container docker

#cleanup to enable systemd
RUN (cd /lib/systemd/system/sysinit.target.wants/; for i in *; do [ $i == \
    systemd-tmpfiles-setup.service ] || rm -f $i; done); \
    rm -f /lib/systemd/system/multi-user.target.wants/*;\
    rm -f /etc/systemd/system/*.wants/*;\
    rm -f /lib/systemd/system/local-fs.target.wants/*; \
    rm -f /lib/systemd/system/sockets.target.wants/*udev*; \
    rm -f /lib/systemd/system/sockets.target.wants/*initctl*; \
    rm -f /lib/systemd/system/basic.target.wants/*;\
    rm -f /lib/systemd/system/anaconda.target.wants/*;

#Install build environment dependencies
# NOTE: We point at the perfSONAR repo to grab nuttcp, owping and other tools.
RUN yum update -y && \
    yum install -y make spectool git which m4 epel-release rsyslog gcc python3-pip && \
    yum install -y http://linux.mirrors.es.net/perfsonar/el7/x86_64/4/packages/perfSONAR-repo-0.10-1.noarch.rpm && \
    yum install -y postgresql95-devel &&\
    pip3 install web.py &&\
    mkdir -p /root/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS} &&\
    echo '%_topdir %(echo $HOME)/rpmbuild' > /root/.rpmmacros &&\
    yum clean all

# Copy code to /app
# This would be a shared volume but can get permissions errors with read-only __pycache__ directories
COPY . /app

#shared volumes
VOLUME /sys/fs/cgroup

#Keep container running
#CMD tail -f /dev/null
CMD ["/usr/sbin/init"]
