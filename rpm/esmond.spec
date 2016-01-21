# Make sure that unpackaged files are noticed
%define _unpackaged_files_terminate_build      1

# Don't create a debug package
%define debug_package %{nil}

%define install_base /opt/esmond

%define init_script_1 espolld
%define init_script_2 espersistd
 
Name:           esmond
Version:        2.0       
Release:        0.1.a1%{?dist}
Summary:        esmond
Group:          Development/Libraries
License:        New BSD License 
URL:            http://REPLACE
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
AutoReqProv:	no
 
BuildRequires:  python27
BuildRequires:  httpd
BuildRequires:  postgresql-devel
BuildRequires:  mercurial
BuildRequires:  gcc

Requires:       python27
Requires:       python27-mod_wsgi
Requires:       cassandra20
Requires:       httpd
Requires:       postgresql
Requires:       postgresql-server
Requires:       postgresql-devel
Requires:       sqlite
Requires:       sqlite-devel
Requires:       memcached
#java 1.7 needed for cassandra. dependency wrong in cassandra rpm.
Requires:       java-1.7.0-openjdk


%description
Esmond is a system for collecting and storing large sets of time-series data. Esmond
uses a hybrid model for storing data using TSDB for time series data and an SQL
database for everything else. All data is available via a REST style interface
(as JSON) allowing for easy integration with other tools.

%pre
# Create the 'esmond' user
/usr/sbin/groupadd esmond 2> /dev/null || :
/usr/sbin/useradd -g esmond -r -s /sbin/nologin -c "Esmond User" -d /tmp esmond 2> /dev/null || :

%prep
%setup -q -n %{name}-%{version}

%build

%install
# Copy and build in place so that we know what the path in the various files
# will be
rm -rf %{buildroot}/%{install_base}
mkdir -p %{buildroot}/%{install_base}
cp -Ra . %{buildroot}/%{install_base}
cd %{buildroot}/%{install_base}

# Get rid of any remnants of the buildroot directory
find %{buildroot}/%{install_base} -type f -exec sed -i "s|%{buildroot}||" {} \;

#Create bin directory. virtualenv files will leave here.
mkdir -p %{buildroot}/%{install_base}/bin/

# Move the default RPM esmond.conf into place
mv %{buildroot}/%{install_base}/rpm/config_files/esmond.conf %{buildroot}/%{install_base}/esmond.conf

# Move the config script into place
mv %{buildroot}/%{install_base}/rpm/scripts/configure_esmond %{buildroot}/%{install_base}/configure_esmond

# Move the default settings.py into place
mv %{buildroot}/%{install_base}/rpm/config_files/settings.py %{buildroot}/%{install_base}/esmond/settings.py

# Move the init scripts into place
mkdir -p %{buildroot}/etc/init.d
mv %{buildroot}/%{install_base}/rpm/init_scripts/%{init_script_1} %{buildroot}/etc/init.d/%{init_script_1}
mv %{buildroot}/%{install_base}/rpm/init_scripts/%{init_script_2} %{buildroot}/etc/init.d/%{init_script_2}

# Move the apache configuration into place
mkdir -p %{buildroot}/etc/httpd/conf.d/
mv %{buildroot}/%{install_base}/rpm/config_files/apache-esmond.conf %{buildroot}/etc/httpd/conf.d/apache-esmond.conf

# ENV files
mkdir -p %{buildroot}/etc/profile.d
mv %{buildroot}/%{install_base}/rpm/config_files/esmond.csh %{buildroot}/etc/profile.d/esmond.csh
mv %{buildroot}/%{install_base}/rpm/config_files/esmond.sh %{buildroot}/etc/profile.d/esmond.sh

# Get rid of the 'rpm' directory now that all the files have been moved into place
rm -rf %{buildroot}/%{install_base}/rpm

# Install python libs so don't rely on pip connectivity during RPM install
# NOTE: This part is why its not noarch
cd %{buildroot}/%{install_base}
rm -f .gitignore
source /opt/rh/python27/enable
/opt/rh/python27/root/usr/bin/virtualenv --prompt="(esmond)" .
. bin/activate
pip install --install-option="--prefix=%{buildroot}%{install_base}" -r requirements.txt
#not pretty but below is the best way I could find to remove references to buildroot
find bin -type f -exec sed -i "s|%{buildroot}%{install_base}|%{install_base}|g" {} \;
find lib -type f -exec sed -i "s|%{buildroot}%{install_base}|%{install_base}|g" {} \;

%clean
[ "%{buildroot}" != "/" ] && rm -rf %{buildroot}

%post
cd %{install_base}
source /opt/rh/python27/enable
/opt/rh/python27/root/usr/bin/virtualenv --prompt="(esmond)" .
. bin/activate

#handle database updates
if [ "$1" = "2" ]; then
    chmod 755 configure_esmond
    ./configure_esmond
fi

mkdir -p tsdb-data
touch tsdb-data/TSDB

#generate secret key
grep -q "SECRET_KEY =" esmond/settings.py || python util/gen_django_secret_key.py >> esmond/settings.py

# Create the logging directories
mkdir -p /var/log/esmond
mkdir -p /var/log/esmond/crashlog
touch /var/log/esmond/esmond.log
touch /var/log/esmond/django.log
chown -R apache:apache /var/log/esmond

# Create the TSDB directory
mkdir -p /var/lib/esmond
touch /var/lib/esmond/TSDB
chown -R esmond:esmond /var/lib/esmond

# Create the 'run' directory
mkdir -p /var/run/esmond
chown -R esmond:esmond /var/run/esmond

#create static files directory
mkdir -p /opt/esmond/staticfiles
django-admin collectstatic --clear --noinput


%files
%defattr(-,root,root,-)
%config(noreplace) %{install_base}/esmond.conf
%config(noreplace) %{install_base}/esmond/settings.py
%{install_base}/*
/etc/init.d/%{init_script_1}
/etc/init.d/%{init_script_2}
/etc/httpd/conf.d/apache-esmond.conf
/etc/profile.d/esmond.csh
/etc/profile.d/esmond.sh
 
%changelog
* Wed Mar 5 2014 Monte Goode <mmgoode@lbl.gov> .99-1
- Initial Esmond Spec File including perfsonar support

* Wed Apr 27 2011 Aaron Brown <aaron@internet2.edu> 1.0-1
- Initial Esmond Spec File
