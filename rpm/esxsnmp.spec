# Make sure that unpackaged files are noticed
%define _unpackaged_files_terminate_build      1

# Don't create a debug package
%define debug_package %{nil}

%define install_base /opt/esxsnmp

%define init_script_1 espolld
%define init_script_2 espersistd
 
Name:           esxsnmp
Version:        1.0        
Release:        1%{?dist}
Summary:        REPLACE
Group:          Development/Libraries
License:        REPLACE 
URL:            http://REPLACE
Source0:        http://REPLACE/%{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch
 
BuildRequires:  subversion
BuildRequires:  net-snmp
BuildRequires:  rrdtool
BuildRequires:  python26
BuildRequires:  python26-devel
BuildRequires:  python26-setuptools
BuildRequires:  httpd

Requires:       subversion
Requires:       net-snmp
Requires:       rrdtool
Requires:       python26
Requires:       python26-memcached
Requires:       python26-psycopg2
Requires:       python26-mod_wsgi
Requires:       httpd
 
%description
REPLACE
 
%prep
%setup -q -n %{name}-%{version}

%build
# Copy and build in place so that we know what the path in the various files
# will be
rm -rf %{buildroot}/%{install_base}
mkdir -p %{buildroot}/%{install_base}
cp -Ra . %{buildroot}/%{install_base}
cd %{buildroot}/%{install_base}

python26 bootstrap.py
bin/buildout -U || true # XXX: buildout fails the first time
bin/buildout -U

# Get rid of any remnants of the buildroot directory
find %{buildroot}/%{install_base} -type f -exec sed -i "s|%{buildroot}||" {} \;

# Move the default RPM esxsnmp.conf into place
mv %{buildroot}/%{install_base}/rpm/config_files/esxsnmp.conf %{buildroot}/%{install_base}/esxsnmp.conf

# Move the init scripts into place
mkdir -p %{buildroot}/etc/init.d
mv %{buildroot}/%{install_base}/rpm/init_scripts/%{init_script_1} %{buildroot}/etc/init.d/%{init_script_1}
mv %{buildroot}/%{install_base}/rpm/init_scripts/%{init_script_2} %{buildroot}/etc/init.d/%{init_script_2}

# Move the apache configuration into place
mkdir -p %{buildroot}/etc/httpd/conf.d/
mv %{buildroot}/%{install_base}/rpm/config_files/apache-esdb.conf %{buildroot}/etc/httpd/conf.d/apache-esdb.conf

# Move the apache mod_wsgi esdb CGI into place
mv %{buildroot}/%{install_base}/rpm/bin/esdb_wsgi %{buildroot}/%{install_base}/bin/

# Get rid of the 'rpm' directory now that all the files have been moved into place
rm -rf %{buildroot}/%{install_base}/rpm

# XXX: For some reason, the DLNetSNMP gets installed into a subdirectory of the
# egg
for i in %{buildroot}/%{install_base}/bin/*; do
    sed -i 's/DLNetSNMP-\(.*\).egg/DLNetSNMP-\1.egg\/DLNetSNMP/' $i
done

%install
 
%clean
[ "%{buildroot}" != "/" ] && rm -rf %{buildroot}

%post
# Create the 'esxsnmp' user
/usr/sbin/groupadd esxsnmp 2> /dev/null || :
/usr/sbin/useradd -g esxsnmp -r -s /sbin/nologin -c "ESxSNMP User" -d /tmp esxsnmp 2> /dev/null || :

# Create the logging directories
mkdir -p /var/log/esxsnmp
mkdir -p /var/log/esxsnmp/crashlog
chown -R esxsnmp:esxsnmp /var/log/esxsnmp

# Create the TSDB directory
mkdir -p /var/lib/esxsnmp
touch /var/lib/esxsnmp/TSDB
chown -R esxsnmp:esxsnmp /var/lib/esxsnmp

# Create the 'run' directory
mkdir -p /var/run/esxsnmp
chown -R esxsnmp:esxsnmp /var/run/esxsnmp

%files
%defattr(-,root,root,-)
%{install_base}/*
%{install_base}/.installed.cfg
/etc/init.d/%{init_script_1}
/etc/init.d/%{init_script_2}
/etc/httpd/conf.d
 
%changelog
* Wed Apr 27 2011 Aaron Brown <aaron@internet2.edu> 1.0-1
- Initial ESxSNMP Spec File
