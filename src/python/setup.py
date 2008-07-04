#!/usr/bin/env python

from distutils.core import setup

setup(name='ESxSNMP',
        version='0.9a1',
        description='ESnet eXtensible SNMP system.',
        author='Jon M. Dugan',
        author_email='jdugan@es.net',
        url='http://code.google.com/p/esxsnmp/',
        packages=['esxsnmp'],
        install_requires=['tsdb', 'SQLAlchemy==0.4.6'],
        entry_points = {
            'console_scripts': [
                'espolld = esxsnmp.poll:espolld',
                'esdbd = esxsnmp.db:esdbd',
                'esfetch = esxsnmp.fetch:esfetch',
            ]
        }
    )
