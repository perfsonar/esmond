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

#Make sure there is something to migrate
if [ ! -d "$OLD_DATADIR" ] || [ ! "$(ls -A ${OLD_DATADIR})" ]; then
    echo "No old data to migrate in ${OLD_DATADIR}, init ${NEW_DATADIR}. "
    su -l postgres -c "${NEW_BINDIR}/initdb --pgdata='${NEW_DATADIR}' --auth='trust'"
    if [ $? != 0 ]; then
        exit 1
    fi
    exit 0
fi

##
# Make sure both old and new are stopped
/etc/init.d/postgresql stop
/etc/init.d/postgresql-9.5 stop
sleep 3

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

#Get encoding and locale
/etc/init.d/postgresql start
ENCODING=`su -l postgres -c "psql -wAt -c 'SHOW SERVER_ENCODING'"`
if [ $? != 0 ]; then
    ENCODING="sql_ascii"
fi
LOCALE=`su -l postgres -c "psql -wAt -c 'SHOW LC_COLLATE'"`
if [ $? != 0 ]; then
    LOCALE="C"
fi
echo "Using encoding $ENCODING and locale $LOCALE"
/etc/init.d/postgresql stop

##
# Init the new database with matching settings of old
su -l postgres -c "${NEW_BINDIR}/initdb  --locale='${LOCALE}' --encoding='${ENCODING}' --pgdata='${NEW_DATADIR}' --auth='trust'"
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
# Restore old config file
mv $OLD_HBA_BAK ${OLD_DATADIR}/pg_hba.conf
chown postgres:postgres ${OLD_DATADIR}/pg_hba.conf
chmod 600 ${OLD_DATADIR}/pg_hba.conf
