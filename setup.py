#!/usr/bin/env python

from distutils.core import setup

setup(name='esxsnmp',
        version='0.9a1',
        description='ESnet eXtensible SNMP system.',
        author='Jon M. Dugan',
        author_email='jdugan@es.net',
        url='http://code.google.com/p/esxsnmp/',
        packages=['esxsnmp', 'esxsnmp.api', 'esxsnmp.admin'],
        install_requires=['tsdb', 'Django==1.4.1', 'web.py', 'simplejson', 'python-memcached', 'pymongo', 'pysqlite'],
        entry_points = {
            'console_scripts': [
                'espolld = esxsnmp.poll:espolld',
                'espoll = esxsnmp.poll:espoll',
                'espersistd = esxsnmp.persist:espersistd',
                'esfetch = esxsnmp.fetch:esfetch',
                'esdbd = esxsnmp.newdb:esdb_standalone',
                'gen_ma_storefile = esxsnmp.perfsonar:gen_ma_storefile',
            ]
        }
    )
