#!/usr/bin/env python

"""Setup file for esmond."""

from distutils.core import setup

setup(
    name='esmond',
    version='0.9b1',
    description='ESnet Monitoring Daemon',
    author='Jon M. Dugan',
    author_email='jdugan@es.net',
    url='http://software.es.net/esmond/',
    packages=['esmond', 'esmond.api', 'esmond.api.client', 'esmond.admin'],
    install_requires=[
        'Django==1.5.1', 'django-tastypie==0.12.2', 'web.py==0.37',
        'python-memcached==1.57', 'pycassa==1.11.1', 'psycopg2==2.6.1',
        'python-mimeparse==0.1.4', 'requests==2.9.1', 'mock', 'nagiosplugin==1.2.3'
    ],
    entry_points={
        'console_scripts': [
            'espolld = esmond.poll:espolld',
            'espoll = esmond.poll:espoll',
            'espersistd = esmond.persist:espersistd',
            'espersistq = esmond.persist:espersistq',
            'esfetch = esmond.fetch:esfetch',
            'esdbd = esmond.newdb:esdb_standalone',
            'gen_ma_storefile = esmond.perfsonar:gen_ma_storefile',
            'esmanage = esmond.manage:esmanage',
        ]
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Telecommunications Industry',
        'Environment :: Console',
        'License :: OSI Approved :: BSD License',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 2',
        'Topic :: Internet',
        'Topic :: System :: Networking',
        'Topic :: Software Development :: Libraries',
    ],
)
