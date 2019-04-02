# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  
  #For virtualbox set the memory
  config.vm.provider "virtualbox" do |v|
    v.memory = 1024
  end

  # Build an el7 machine as the default
  config.vm.define "esmond-el7", primary: true, autostart: true do |el7|
    
    # set box to official CentOS 7 image
    el7.vm.box = "centos/7"
    # explcitly set shared folder to virtualbox type. If not set will choose rsync 
    # which is just a one-way share that is less useful in this context
    el7.vm.synced_folder ".", "/vagrant", type: "virtualbox"
    # Set hostname
    el7.vm.hostname = "esmond-el7"
    
    # Enable IPv4. Cannot be directly before or after line that sets IPv6 address. Looks
    # to be a strange bug where IPv6 and IPv4 mixed-up by vagrant otherwise and one 
    #interface will appear not to have an address. If you look at network-scripts file
    # you will see a mangled result where IPv4 is set for IPv6 or vice versa
    el7.vm.network "private_network", ip: "10.0.0.201"
    
    # Setup port forwarding to apache
    el7.vm.network "forwarded_port", guest: 443, host: "20443", host_ip: "127.0.0.1"
    el7.vm.network "forwarded_port", guest: 80, host: "20080", host_ip: "127.0.0.1"
    
    # Enable IPv6. Currently only supports setting via static IP. Address below in the
    # reserved local address range for IPv6
    el7.vm.network "private_network", ip: "fdac:218a:75e5:69c8::201"
    
    #Disable selinux
    el7.vm.provision "shell", inline: <<-SHELL
        sed -i s/SELINUX=enforcing/SELINUX=permissive/g /etc/selinux/config
    SHELL
    
    #reload VM since selinux requires reboot. Requires `vagrant plugin install vagrant-reload`
    el7.vm.provision :reload
    
    #Install all requirements and perform initial setup
    el7.vm.provision "shell", inline: <<-SHELL
        # Create user and group
        /usr/sbin/groupadd esmond 2> /dev/null || :
        /usr/sbin/useradd -g esmond -r -s /sbin/nologin -c "Esmond User" -d /tmp esmond 2> /dev/null || :

        #env variables
        export ESMOND_ROOT=/usr/lib/esmond
        export ESMOND_CONF=/etc/esmond/esmond.conf
        export DJANGO_SETTINGS_MODULE=esmond.settings

        ## install yum dependencies
        yum install -y epel-release
        yum install -y  http://software.internet2.edu/rpms/el7/x86_64/RPMS.main/perfSONAR-repo-0.8-1.noarch.rpm
        yum clean all
        yum install -y perfSONAR-repo-staging perfSONAR-repo-nightly
        yum install -y https://yum.postgresql.org/9.6/redhat/rhel-7.6-x86_64/pgdg-redhat96-9.6-3.noarch.rpm
        yum clean all
        yum install -y gcc\
            kernel-devel\
            kernel-headers\
            dkms\
            make\
            bzip2\
            perl\
            pscheduler-bundle-full\
            python\
            python-virtualenv\
            httpd\
            mercurial\
            python2-mock\
            mod_wsgi\
            cassandra20\
            sqlite\
            sqlite-devel\
            memcached\
            java-1.7.0-openjdk\
            postgresql96\
            postgresql96-server\
            postgresql96-devel\
            postgresql96-contrib\
            postgresql96-plpython\
            https://timescalereleases.blob.core.windows.net/rpm/timescaledb-1.0.0-postgresql-9.6-0.x86_64.rpm
            
        ## setup shared folders and files
        if ! [ -d /vagrant/vagrant-data/esmond-el7/etc/esmond ]; then
            rm -rf /vagrant/vagrant-data/esmond-el7/etc/esmond
        fi
        if ! [ -L /etc/esmond ]; then
            rm -rf /etc/esmond
        fi
        if ! [ -L /usr/lib/esmond ]; then
            rm -rf /usr/lib/esmond
        fi
        mkdir -p /vagrant/vagrant-data/esmond-el7/etc/esmond
        cd /vagrant
        ln -fs /vagrant/vagrant-data/esmond-el7/etc/esmond /etc/esmond
        if ! [ -e /etc/esmond/esmond.conf ]; then
            cp rpm/config_files/esmond.conf /etc/esmond/esmond.conf
            chmod 644 /etc/esmond/esmond.conf
        fi
        ln -fs /vagrant /usr/lib/esmond
        cp -f /vagrant/rpm/config_files/tmpfiles.conf /usr/lib/tmpfiles.d/esmond.conf
        chmod 644 /usr/lib/tmpfiles.d/esmond.conf
        ln -fs /vagrant/util/esmond_manage /usr/sbin
        #have to copy so apache starts on boot
        cp -f /vagrant/rpm/config_files/apache-esmond.conf /etc/httpd/conf.d/apache-esmond.conf
        chmod 644 /etc/httpd/conf.d/apache-esmond.conf
        ln -fs /vagrant/rpm/config_files/esmond.csh /etc/profile.d/esmond.csh
        ln -fs /vagrant/rpm/config_files/esmond.sh /etc/profile.d/esmond.sh
        ln -fs /usr/pgsql-9.6/bin/pg_config /usr/sbin/pg_config
        
        ## Setup python environment
        virtualenv --prompt="(esmond)" .
        . bin/activate
        python -m pip install --install-option="--prefix=/vagrant" -r requirements.txt
        python -m pip install --install-option="--prefix=/vagrant" django-tastypie
        #need below for unittests
        python -m pip install --install-option="--prefix=/vagrant"  --upgrade setuptools
        python -m pip install --install-option="--prefix=/vagrant" mock
        ## Setup logging
        mkdir -p /var/run/cassandra/
        mkdir -p /var/log/esmond
        mkdir -p /var/log/esmond/crashlog
        touch /var/log/esmond/esmond.log
        touch /var/log/esmond/django.log
        touch /var/log/esmond/install.log
        chown -R apache:apache /var/log/esmond
        
        # initdb
        # Note: pscheduler inits postgresql-95. need to migrate to 9.6
        /usr/pgsql-9.6/bin/postgresql96-setup initdb
        # Check if upgrade possible
        su -l postgres -c "/usr/pgsql-9.6/bin/pg_upgrade --old-bindir=/usr/pgsql-9.5/bin/ --new-bindir=/usr/pgsql-9.6/bin/ --old-datadir=/var/lib/pgsql/9.5/data/ --new-datadir=/var/lib/pgsql/9.6/data/ --check"
        systemctl stop postgresql-9.5
        su -l postgres -c "/usr/pgsql-9.6/bin/pg_upgrade --old-bindir=/usr/pgsql-9.5/bin/ --new-bindir=/usr/pgsql-9.6/bin/ --old-datadir=/var/lib/pgsql/9.5/data/ --new-datadir=/var/lib/pgsql/9.6/data/"
        cp -f /var/lib/pgsql/9.5/data/pg_hba.conf /var/lib/pgsql/9.6/data/pg_hba.conf
        # add this to match with pscheduler-server.spec does anyways
        drop-in -n pscheduler - "/var/lib/pgsql/9.6/data/postgresql.conf" <<EOF
#
# pScheduler
#
max_connections = 500
EOF
        # Setup timescale
        drop-in -n esmond - "/var/lib/pgsql/9.6/data/postgresql.conf" <<EOF
#
# esmond
#
shared_preload_libraries = 'timescaledb'
timescaledb.telemetry_level=off
EOF
        # Start database so django can do its thing
        systemctl disable postgresql-9.5
        systemctl restart postgresql-9.6
        
        ## Finish Django setup
        #TODO: Handle this better
        cp -f rpm/config_files/settings.py esmond/settings.py
        grep -q "SECRET_KEY =" esmond/settings.py|| python util/gen_django_secret_key.py >> esmond/settings.py
        ./rpm/scripts/configure_esmond
        
        ## Configure DB
        USER_EXISTS=$(su -l postgres -c "psql -tAc \\"SELECT 1 FROM pg_roles WHERE rolname='esmond'\\"")
        if [ $? -ne 0 ]; then
            echo "Unable to connect to postgresql to check user. Your esmond database may not be initialized"
        fi
        if [ "$USER_EXISTS" != "1" ]; then
            DB_PASSWORD=$(< /dev/urandom tr -dc _A-Za-z0-9 | head -c32;echo;)
            su -l postgres -c "psql -c \\"CREATE USER esmond WITH PASSWORD '${DB_PASSWORD}'\\"" 
            su -l postgres -c "psql -c \\"CREATE DATABASE esmond\\"" 
            su -l postgres -c "psql -c \\"GRANT ALL ON DATABASE esmond to esmond\\"" 
            #need this for unit tests
            su -l postgres -c "psql -c \\"ALTER USER esmond CREATEDB\\"" 
            sed -i "s/sql_db_name = .*/sql_db_name = esmond/g" /etc/esmond/esmond.conf
            sed -i "s/sql_db_user = .*/sql_db_user = esmond/g" /etc/esmond/esmond.conf
            sed -i "s/sql_db_password = .*/sql_db_password = ${DB_PASSWORD}/g" /etc/esmond/esmond.conf
            drop-in -n -t esmond - /var/lib/pgsql/9.6/data/pg_hba.conf <<EOF
        #
        # esmond
        #
        # This user should never need to access the database from anywhere
        # other than locally.
        #
        local     esmond          esmond                            md5
        host      esmond          esmond     127.0.0.1/32           md5
        host      esmond          esmond     ::1/128                md5
        local     test_esmond     esmond                            md5
        host      test_esmond     esmond     127.0.0.1/32           md5
        host      test_esmond     esmond     ::1/128                md5
EOF
        fi
        
        ## Restart remaining services
        systemctl enable postgresql-9.6
        systemctl restart postgresql-9.6
        systemctl enable cassandra
        systemctl restart cassandra
        systemctl enable httpd
        systemctl restart httpd
        
        #build database
        python esmond/manage.py makemigrations --noinput
        python esmond/manage.py migrate --noinput
        
        # Create API key for testing
        KEY=`python esmond/manage.py add_api_key_user perfsonar 2> /dev/null | grep "Key:" | cut -f2 -d " "`
        mkdir -p /usr/share/pscheduler
        cat >/usr/share/pscheduler/psc-archiver-esmond.json <<EOF
{
    "archiver": "esmond",
    "data": {
        "url": "https://localhost/esmond/perfsonar/archive/",
        "_auth-token": "${KEY}"
    }
}
EOF
    SHELL
  end
end
