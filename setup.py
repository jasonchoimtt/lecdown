#!/usr/bin/env python3

from setuptools import setup

with open('requirements.txt') as f:
    reqs_str = f.read()
reqs = reqs_str.strip().split('\n')

setup(
    name='Lecdown',
    version='dev',
    description='Download lecture materials',
    author='Jason Choi',
    author_email='jasonchoi.mtt@gmail.com',
    url='https://github.com/jasonchoimtt/lecdown',
    scripts=['scripts/lecdown'],
    install_requires=reqs)
