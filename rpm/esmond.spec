# Ignore unpackaged files
%define _unpackaged_files_terminate_build      0

%global __python %{python3}

%define postgresql_version_major  10
%define postgresql_version_minor  12
%define postgresql_version        %{postgresql_version_major}.%{postgresql_version_minor}
%define postgresql                postgresql%{postgresql_version_major}

# Don't create a debug package
%define debug_package %{nil}

%define install_base /usr/lib/esmond
%define config_base /etc/esmond
%define dbscript_base /usr/lib/esmond-database
%define perfsonar_auto_version 4.4.6
%define perfsonar_auto_relnum 0.a1.0
 
Name:           esmond
Version:        %{perfsonar_auto_version}
Release:        %{perfsonar_auto_relnum}%{?dist}
Summary:        esmond
Group:          Development/Libraries
License:        New BSD License 
URL:            http://software.es.net/esmond
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
AutoReqProv:    no

# NOTE:  This comes from pScheduler
BuildRequires:  postgresql-init
BuildRequires:  python3-devel
BuildRequires:  python3-memcached
BuildRequires:  python3-psycopg2
BuildRequires:  python3-pycassa
BuildRequires:  python3-requests
BuildRequires:  python3-thrift
BuildRequires:  python3-virtualenv
BuildRequires:  python36-astroid
BuildRequires:  python36-dateutil
BuildRequires:  python36-netaddr
BuildRequires:  python36-pylint
BuildRequires:  python36-pytz
BuildRequires:  python36-sphinx
BuildRequires:  python36-sphinx_rtd_theme
BuildRequires:  systemd
BuildRequires:  httpd
BuildRequires:  %{postgresql}-devel >= %{postgresql_version}
BuildRequires:  gcc


Requires:       postgresql-init
Requires:       python3
Requires:       python3-memcached
Requires:       python3-psycopg2
Requires:       python3-pycassa
Requires:       python3-requests
Requires:       python3-thrift
Requires:       python3-virtualenv
Requires:       python36-astroid
Requires:       python36-dateutil
Requires:       python36-netaddr
Requires:       python36-pytz
Requires:       mod_wsgi >= 4.6.5
Requires:       policycoreutils-python
%{?systemd_requires: %systemd_requires}
Requires:       cassandra20
Requires:       httpd
Requires:       mod_ssl
Requires:       esmond-database
Requires(post): esmond-database
Requires:       sqlite
Requires:       sqlite-devel
Requires:       memcached
Requires:       zip
#java 1.7 needed for cassandra. dependency wrong in cassandra rpm.
Requires:       java-1.7.0-openjdk


%description
Esmond is a system for collecting and storing large sets of time-series data. Esmond
uses a hybrid model for storing data using TSDB for time series data and an SQL
database for everything else. All data is available via a REST style interface
(as JSON) allowing for easy integration with other tools.

%package database-%{postgresql}
Summary:        Esmond PostgreSQL %{postgresql_version} Database Plugin
Group:          Development/Tools
Requires:       %{postgresql} >= %{postgresql_version}
Requires:       %{postgresql}-server >= %{postgresql_version}
Requires:       %{postgresql}-devel >= %{postgresql_version}
Requires(post): %{postgresql} >= %{postgresql_version}
Requires(post): %{postgresql}-server >= %{postgresql_version}
Requires(post): %{postgresql}-devel >= %{postgresql_version}
Requires(post): drop-in
Provides:       esmond-database
Obsoletes:      esmond-database-postgresql95

%description database-%{postgresql}
Installs Postgresql using one of the vendor RPMs.

%package compat
Summary:        Esmond Backward Compatibility
Group:          Development/Tools
Requires:       esmond >= 2.1
Requires:       esmond-database-%{postgresql}
Obsoletes:      esmond < 2.1

%description compat
Transitions esmond instances prior to the split of database modules to new version

%pre
# Create the 'esmond' user
/usr/sbin/groupadd -r esmond 2> /dev/null || :
/usr/sbin/useradd -g esmond -r -s /sbin/nologin -c "Esmond User" -d /tmp esmond 2> /dev/null || :

%pre database-%{postgresql}
# Create the 'esmond' user
/usr/sbin/groupadd -r esmond 2> /dev/null || :
/usr/sbin/useradd -g esmond -r -s /sbin/nologin -c "Esmond User" -d /tmp esmond 2> /dev/null || :

%prep
%setup -q -n %{name}-%{version}

%build

%install
# Copy and build in place so that we know what the path in the various files
# will be
rm -rf %{buildroot}/*
mkdir -p %{buildroot}/%{config_base}
mkdir -p %{buildroot}/%{install_base}
cp -Ra . %{buildroot}/%{install_base}
cd %{buildroot}/%{install_base}

# Get rid of any remnants of the buildroot directory
find %{buildroot}/%{install_base} -type f -exec sed -i "s|%{buildroot}||" {} \;

#Create bin directory. virtualenv files will leave here.
mkdir -p %{buildroot}/%{install_base}/bin/

#create systemd-tmpfiles config for cassandra since it doesn't do this right
mkdir -p %{buildroot}/%{_tmpfilesdir}
mv %{buildroot}/%{install_base}/rpm/config_files/tmpfiles.conf %{buildroot}/%{_tmpfilesdir}/esmond.conf

# Move the default RPM esmond.conf into place
mv %{buildroot}/%{install_base}/rpm/config_files/esmond.conf %{buildroot}/%{config_base}/esmond.conf

# Move the config script into place
mv %{buildroot}/%{install_base}/rpm/scripts/configure_esmond %{buildroot}/%{install_base}/configure_esmond

#install database scripts
mkdir -p %{buildroot}/%{dbscript_base}/
mv %{buildroot}/%{install_base}/rpm/scripts/db/* %{buildroot}/%{dbscript_base}/

# Move the default settings.py into place
mv %{buildroot}/%{install_base}/rpm/config_files/settings.py %{buildroot}/%{install_base}/esmond/settings.py

# Link the management script
mkdir -p %{buildroot}/usr/sbin
ln -s %{install_base}/util/esmond_manage %{buildroot}/usr/sbin

# Move the apache configuration into place
mkdir -p %{buildroot}/etc/httpd/conf.d/
mv %{buildroot}/%{install_base}/rpm/config_files/apache-esmond.conf %{buildroot}/etc/httpd/conf.d/apache-esmond.conf

# ENV files
mkdir -p %{buildroot}/etc/profile.d
mv %{buildroot}/%{install_base}/rpm/config_files/esmond.csh %{buildroot}/etc/profile.d/esmond.csh
mv %{buildroot}/%{install_base}/rpm/config_files/esmond.sh %{buildroot}/etc/profile.d/esmond.sh


cd %{buildroot}/%{install_base}
# Get rid of the development files and directories
rm -rf .git
rm -f .git*
rm -rf devel
rm -rf rpm
rm -rf rpms
rm -f mkdevenv
rm -f pylint.rc
rm -f Vagrantfile

# Install python libs so don't rely on pip connectivity during RPM install
# NOTE: This part is why its not noarch
# We don't want to use a PIP > 19.0.2 to avoid build errors in dependencies
virtualenv-3.6 --prompt="(esmond)" . --system-site-packages --no-pip
. bin/activate
curl https://bootstrap.pypa.io/pip/3.6/get-pip.py -o get-pip.py
python get-pip.py pip==18.1
#Invoking pip using 'python -m pip' to avoid 128 char shebang line limit that pip can hit in build envs like Jenkins
python3 -m pip install --install-option="--prefix=%{buildroot}%{install_base}" -r requirements.txt
#leave venv
deactivate
#not pretty but below is the best way I could find to remove references to buildroot
find bin -type f -exec sed -i "s|%{buildroot}%{install_base}|%{install_base}|g" {} \;
find lib -type f -exec sed -i "s|%{buildroot}%{install_base}|%{install_base}|g" {} \;
# Clean up after build
rm -f %{buildroot}%{install_base}/get-pip.py
rm -f %{buildroot}%{install_base}/pip-selfcheck.json
find %{buildroot}%{install_base} | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm -rf

%clean
[ "%{buildroot}" != "/" ] && rm -rf %{buildroot}

%post
cd %{install_base}
#create cassandra's pid directory since it doesn't do so on its own
mkdir -p /var/run/cassandra/
. bin/activate

#generate secret key
grep -q "SECRET_KEY =" esmond/settings.py || python3 util/gen_django_secret_key.py >> esmond/settings.py

# Create the logging directories
mkdir -p /var/log/esmond
mkdir -p /var/log/esmond/crashlog
touch /var/log/esmond/esmond.log
touch /var/log/esmond/django.log
touch /var/log/esmond/install.log
chown -R apache:apache /var/log/esmond
semanage fcontext -a -t httpd_log_t '/var/log/esmond(/.*)?'
restorecon -R /var/log/esmond
setsebool -P httpd_can_network_connect on

#run config script
chmod 755 configure_esmond
./configure_esmond $1

mkdir -p tsdb-data
touch tsdb-data/TSDB

# Create the TSDB directory
mkdir -p /var/lib/esmond
touch /var/lib/esmond/TSDB
chown -R esmond:esmond /var/lib/esmond

# Create the 'run' directory
mkdir -p /var/run/esmond
chown -R esmond:esmond /var/run/esmond

#fix any file permissions the pip packages mess-up 
find %{install_base}/lib -type f -perm 0666 -exec chmod 644 {} \;

#run database configuration scripts (dependent on esmond-database package installed)
%{dbscript_base}/configure-pgsql.sh %{postgresql_version_major}

# Remove problematic classes from cassandra (CVE-2022-23307)
zip -q -d /usr/share/cassandra/lib/log4j*.jar org/apache/log4j/chainsaw/* || :

#enable and start httpd and cassandra on fresh install
if [ "$1" = "1" ]; then
    systemctl enable cassandra
    systemctl restart cassandra
    systemctl enable httpd
    systemctl restart httpd
fi

%postun
if [ "$1" != "0" ]; then
    # An RPM upgrade
    systemctl restart httpd
fi

%files
%config(noreplace) %{config_base}/esmond.conf
%attr(0755,esmond,esmond) %{install_base}/bin/*
%attr(0755,esmond,esmond) %{install_base}/util/*
%attr(0755,esmond,esmond) %{install_base}/esmond_client/clients/*
%attr(0755,esmond,esmond) %{install_base}/configure_esmond
%{install_base}/AUTHORS
%{install_base}/COPYING
%{install_base}/ChangeLog
%{install_base}/INSTALL
%{install_base}/LICENSE
%{install_base}/README.rst
%{install_base}/TODO
# TODO: Not produced
# %{install_base}/__pycache__
%{install_base}/docs
%{install_base}/esmond.egg-info
%{install_base}/esmond
%{install_base}/esmond_client/README.rst
# TODO: Not produced
# %{install_base}/esmond_client/__pycache__
%{install_base}/esmond_client/esmond_client*
%{install_base}/esmond_client/setup*
%{install_base}/example_esmond.conf
%{install_base}/include
%{install_base}/lib
%{install_base}/lib64
%{install_base}/requirements.txt
%{install_base}/setup.py
%{install_base}/test_data
%config %{install_base}/esmond/settings.py
/usr/sbin/esmond_manage
%attr(0755,esmond,esmond) /etc/profile.d/esmond.csh
%attr(0755,esmond,esmond) /etc/profile.d/esmond.sh
/etc/httpd/conf.d/apache-esmond.conf
%{_tmpfilesdir}/esmond.conf

%files database-%{postgresql}
%defattr(0644,esmond,esmond,0755)
%attr(0755,esmond,esmond) %{dbscript_base}/configure-pgsql.sh

%files compat

%changelog
* Wed Mar 5 2014 Monte Goode <mmgoode@lbl.gov> .99-1
- Initial Esmond Spec File including perfsonar support

* Wed Apr 27 2011 Aaron Brown <aaron@internet2.edu> 1.0-1
- Initial Esmond Spec File
