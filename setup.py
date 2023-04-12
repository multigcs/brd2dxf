#!/usr/bin/env python3
#
#

import os
from setuptools import setup

setup(
    name='brd2dxf',
    version='0.1.0',
    author='Oliver Dippel',
    author_email='o.dippel@gmx.de',
    packages=['brd2dxf'],
    scripts=['bin/brd2dxf'],
    url='https://github.com/multigcs/brd2dxf/',
    license='LICENSE',
    description='eagle-cad board (.brd) to dxf converter',
    long_description=open('README.md').read(),
    install_requires=['ezdxf', 'shapely', 'xmltodict'],
    include_package_data=True,
    data_files = []
)

