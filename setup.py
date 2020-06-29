#!/usr/bin/env python3

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
        'Django==1.11.29',
        'web.py',
        'djangorestframework~=3.4.7',
        'drf-extensions==0.3.1',
        'djangorestframework-filters~=0.10.2',
        'django-filter~=1.1',
        'python-memcached>=1.57',
        'psycopg2>=2.7.7',
        'requests',
        'thrift==0.13.0'
    ],
    entry_points={
        'console_scripts': [
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
        'Programming Language :: Python :: 3',
        'Topic :: Internet',
        'Topic :: System :: Networking',
        'Topic :: Software Development :: Libraries',
    ],
)
