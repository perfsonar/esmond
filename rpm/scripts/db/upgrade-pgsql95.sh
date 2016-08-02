#!/bin/bash

################################################################################
# Script to upgrade an esmond postgresql 8.4 database to 9.5
################################################################################

# Variables
OLD_DATADIR=/var/lib/pgsql/data
NEW_DATADIR=/var/lib/pgsql/9.5/data
OLD_BINDIR=/usr/bin
NEW_BINDIR=/usr/pgsql-9.5/bin

# Make sure new data directory is clean
if [ "$(ls -A ${NEW_DATADIR})" ]; then
    echo "Database directory at ${NEW_DATADIR} is not empty, so nothing to do. "
    exit 0
fi

##
# Init the new database with matching settings of old
su -l postgres -c "${NEW_BINDIR}/initdb  --locale='C' --encoding='sql_ascii' --pgdata='${NEW_DATADIR}' --auth='trust'"
if [ $? != 0 ]; then
    exit 1
fi

##
# Make sure both old and new are stopped
/etc/init.d/postgresql stop
/etc/init.d/postgresql-9.5 stop
sleep 3
pkill -9 -f postgres

##
# Temporarily update auth on old DB to allow upgrade to proceed
##
OLD_HBA_BAK=`mktemp`
cp ${OLD_DATADIR}/pg_hba.conf $OLD_HBA_BAK
if [ $? != 0 ]; then
    exit 1
fi
cat >${OLD_DATADIR}/pg_hba.conf <<EOL
local   all         all                               trust 
host    all         all         127.0.0.1/32          trust
host    all         all         ::1/128               trust
EOL
if [ $? != 0 ]; then
    exit 1
fi

##
# Do the upgrade
su -l postgres -c "PGHOST=/tmp;export PGHOST;${NEW_BINDIR}/pg_upgrade --old-datadir ${OLD_DATADIR} --new-datadir ${NEW_DATADIR} --old-bindir ${OLD_BINDIR} --new-bindir ${NEW_BINDIR}"
if [ $? != 0 ]; then
    exit 1
fi

##
# Restore auth to md5 on both
mv $OLD_HBA_BAK ${OLD_DATADIR}/pg_hba.conf
chown postgres:postgres ${OLD_DATADIR}/pg_hba.conf
chmod 600 ${OLD_DATADIR}/pg_hba.conf
sed -i -e s/trust$/md5/g ${NEW_DATADIR}/pg_hba.conf
