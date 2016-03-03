#! /usr/bin/env python

"""
Setup file for esmond_client distribution.
"""

import os
import sys
from setuptools import setup

if sys.version_info[0] == 2 and sys.version_info[1] < 7:
    sys.exit('Sorry, Python < 2.7 is not supported')


def read(*paths):
    """Build a file path from *paths* and return the contents."""
    with open(os.path.join(*paths), 'r') as fh:
        return fh.read()

setup(
    name='esmond_client',
    version='2.0',
    description='API client libraries and command line tools for the ESnet Monitoring Daemon (esmond).',  # pylint: disable=line-too-long
    long_description=(read('README.rst')),
    author='Monte M. Goode',
    author_email='MMGoode@lbl.gov',
    url='http://software.es.net/esmond/',
    packages=['esmond_client', 'esmond_client.perfsonar'],
    scripts=[
        'clients/esmond-ps-get',
        'clients/esmond-ps-get-bulk',
        'clients/esmond-ps-get-endpoints',
        'clients/esmond-ps-get-metadata',
        'clients/esmond-ps-load-gridftp',
        'clients/esmond-ps-pipe',
    ],
    install_requires=['requests', 'python-dateutil'],
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
