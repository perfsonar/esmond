#!/usr/bin/env python

from distutils.core import setup

setup(name='ESxSNMP',
        version='0.9a1',
        description='ESnet eXtensible SNMP system.',
        author='Jon M. Dugan',
        author_email='jdugan@es.net',
        url='http://code.google.com/p/esxsnmp/',
        packages=['esxsnmp'],
        package_dir=['esxsnmp': 'src/python/esxsnmp'],
        install_requires=['tsdb', 'SQLAlchemy==0.5.2', 'web.py', 'simplejson'],
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
