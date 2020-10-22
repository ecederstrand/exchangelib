#!/usr/bin/env python
"""
Release notes:
* Bump version in exchangelib/__init__.py
* Bump version in CHANGELOG.md
* Generate documentation: pdoc3 --html exchangelib -o docs --force
* Commit and push changes
* Build package: rm -rf dist/* && python setup.py sdist bdist_wheel
* Push to PyPI: twine upload dist/*
* Create release on GitHub
"""
import io
import os

from setuptools import setup, find_packages


__version__ = None
with io.open(os.path.join(os.path.dirname(__file__), 'exchangelib/__init__.py'), encoding='utf-8') as f:
    for l in f:
        if not l.startswith('__version__'):
            continue
        __version__ = l.split('=')[1].strip(' "\'\n')
        break


def read(file_name):
    with io.open(os.path.join(os.path.dirname(__file__), file_name), encoding='utf-8') as f:
        return f.read()


setup(
    name='exchangelib',
    version=__version__,
    author='Erik Cederstrand',
    author_email='erik@cederstrand.dk',
    description='Client for Microsoft Exchange Web Services (EWS)',
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    license='BSD-2-Clause',
    keywords='ews exchange autodiscover microsoft outlook exchange-web-services o365 office365',
    install_requires=[
        'backports-datetime-fromisoformat;python_version<"3.7"',
        'backports.zoneinfo;python_version<"3.9"',
        'cached_property',
        'defusedxml>=0.6.0',
        'dnspython>=2.0.0',
        'isodate',
        'lxml>3.0',
        'oauthlib',
        'pygments',
        'requests>=2.7',
        'requests_ntlm>=0.2.0',
        'requests_oauthlib',
        'tzdata',
        'tzlocal',
    ],
    extras_require={
        'kerberos': ['requests_kerberos'],
        'sspi': ['requests_negotiate_sspi'],  # Only for Win32 environments
        'complete': ['requests_kerberos', 'requests_negotiate_sspi'],  # Only for Win32 environments
    },
    packages=find_packages(exclude=('tests', 'tests.*')),
    tests_require=['flake8', 'psutil', 'python-dateutil', 'pytz', 'PyYAML', 'requests_mock'],
    python_requires=">=3.6",
    test_suite='tests',
    zip_safe=False,
    url='https://github.com/ecederstrand/exchangelib',
    project_urls={
        "Bug Tracker": "https://github.com/ecederstrand/exchangelib/issues",
        "Documentation": "https://ecederstrand.github.io/exchangelib/",
        "Source Code": "https://github.com/ecederstrand/exchangelib",
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Topic :: Communications',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3',
    ],
)
