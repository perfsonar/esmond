#!/usr/bin/env python

import os
from setuptools import setup

def read(*paths):
    """Build a file path from *paths* and return the contents."""
    with open(os.path.join(*paths), 'r') as f:
        return f.read()

setup(
    name='esmond_client',
    version='1.3',
    description='API client libraries and command line tools for the ESnet Monitoring Daemon (esmond).',
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
