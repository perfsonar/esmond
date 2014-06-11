#!/usr/bin/env python

from setuptools import setup

setup(
    name='esmond_client',
    version='1.0',
    description='Esmond API client libraries',
    author='Monte M. Goode',
    author_email='MMGoode@lbl.gov',
    url='https://github.com/esnet/esmond',
    packages=['esmond_client'],
    install_requires=['requests'],
)
