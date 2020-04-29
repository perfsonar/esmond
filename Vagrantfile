# -*- mode: ruby -*-
# vi: set ft=ruby shiftwidth=4 :

Vagrant.configure("2") do |config|
    # Disable audio and get reasonable specs
    config.vm.provider "virtualbox" do |vb|
        vb.customize ["modifyvm", :id, "--audio", "none"]
        vb.cpus = 2
        vb.memory = 2048
    end
    # Skip VB Gest Additions update
    if Vagrant.has_plugin?("vagrant-vbguest")
        config.vbguest.auto_update = false
    end
    # Build an el7 machine as the default
    config.vm.define "esmond-el7-py3", primary: true, autostart: true do |el7|
        # set box to official CentOS 7 image
        el7.vm.box = "bento/centos-7"
        # explcitly set shared folder to virtualbox type. If not set will choose rsync 
        # which is just a one-way share that is less useful in this context
        el7.vm.synced_folder ".", "/vagrant", type: "virtualbox"
        # Set hostname
        el7.vm.hostname = "esmond-el7-py3"
        el7.vm.provider "virtualbox" do |v|
            # Prevent VirtualBox from interfering with host audio stack
            v.customize ["modifyvm", :id, "--audio", "none"]
        end

        # Enable IPv4. Cannot be directly before or after line that sets IPv6 address. Looks
        # to be a strange bug where IPv6 and IPv4 mixed-up by vagrant otherwise and one 
        #interface will appear not to have an address. If you look at network-scripts file
        # you will see a mangled result where IPv4 is set for IPv6 or vice versa
        el7.vm.network "private_network", ip: "10.0.0.203"

        # Setup port forwarding to apache
        el7.vm.network "forwarded_port", guest: 443, host: "21443", host_ip: "127.0.0.1"
        el7.vm.network "forwarded_port", guest: 80, host: "21080", host_ip: "127.0.0.1"

        # Enable IPv6. Currently only supports setting via static IP. Address below in the
        # reserved local address range for IPv6
        el7.vm.network "private_network", ip: "fdac:218a:75e5:69c8::203"

        #Disable selinux
        el7.vm.provision "shell", inline: <<-SHELL
        sed -i s/SELINUX=enforcing/SELINUX=permissive/g /etc/selinux/config
        SHELL

        #reload VM since selinux requires reboot. Requires `vagrant plugin install vagrant-reload`
        el7.vm.provision :reload

        #Install all requirements and perform initial setup
        el7.vm.provision "shell", inline: <<-SHELL

        #env variables
        export ESMOND_ROOT=/usr/lib/esmond
        export ESMOND_CONF=/etc/esmond/esmond.conf
        export DJANGO_SETTINGS_MODULE=esmond.settings

        ## install yum dependencies
        yum install -y epel-release
        yum install -y centos-release-scl
        yum install -y http://software.internet2.edu/rpms/el7/x86_64/4/packages/perfSONAR-repo-0.9-1.noarch.rpm
        yum clean all
        yum install -y gcc\
            kernel-devel\
            kernel-headers\
            dkms\
            make\
            bzip2\
            perl\
            pscheduler-bundle-full\
            python3\
            python3-virtualenv\
            httpd\
            python3-mock\
            python3-memcached\
            python3-psycopg2\
            python3-requests\
            python3-thrift\
            rh-python36-mod_wsgi\
            cassandra20\
            sqlite\
            sqlite-devel\
            memcached\
            java-1.7.0-openjdk\
            postgresql95\
            postgresql95-server\
            postgresql95-devel

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
        ln -fs /usr/pgsql-9.5/bin/pg_config /usr/sbin/pg_config

        ## Setup python environment
        virtualenv-3 --prompt="(esmond)" .
        . bin/activate
        python3 -m pip install --install-option="--prefix=/vagrant" -r requirements.txt
        python3 -m pip install --install-option="--prefix=/vagrant" django-tastypie
        #need below for unittests
        python3 -m pip install --install-option="--prefix=/vagrant"  --upgrade setuptools
        python3 -m pip install --install-option="--prefix=/vagrant" mock
        ## Setup logging
        mkdir -p /var/run/cassandra/
        mkdir -p /var/log/esmond
        mkdir -p /var/log/esmond/crashlog
        touch /var/log/esmond/esmond.log
        touch /var/log/esmond/django.log
        touch /var/log/esmond/install.log
        chown -R apache:apache /var/log/esmond

        ## Finish Django setup
        #TODO: Handle this better
        cp -f rpm/config_files/settings.py esmond/settings.py
        grep -q "SECRET_KEY =" esmond/settings.py|| python3 util/gen_django_secret_key.py >> esmond/settings.py
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
            drop-in -n -t esmond - /var/lib/pgsql/9.5/data/pg_hba.conf <<EOF
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
local     postgres        esmond                            md5
host      postgres        esmond     127.0.0.1/32           md5
host      postgres        esmond     ::1/128                md5
EOF
        fi

        ## Restart remaining services
        systemctl enable postgresql-9.5
        systemctl restart postgresql-9.5
        systemctl enable cassandra
        systemctl restart cassandra
        systemctl enable httpd
        systemctl restart httpd

        #build database
        ./rpm/scripts/configure_esmond 2
        SHELL
    end

    # Runs on all hosts before they are provisioned independent of OS
    config.vm.provision "shell", inline: <<-SHELL
    /usr/sbin/groupadd -r esmond 2> /dev/null || :
    /usr/sbin/useradd -g esmond -r -s /sbin/nologin -c "Esmond User" -d /tmp esmond 2> /dev/null || :
    SHELL
end
