#!/usr/bin/env python
"""
Release notes:
*  Install pdoc3, wheel, twine
* Bump version in exchangelib/__init__.py
* Bump version in CHANGELOG.md
* Generate documentation:
    rm -r docs/exchangelib && pdoc3 --html exchangelib -o docs --force && pre-commit run end-of-file-fixer
* Commit and push changes
* Build package:
    rm -rf build dist exchangelib.egg-info && python setup.py sdist bdist_wheel
* Push to PyPI:
    twine upload dist/*
* Create release on GitHub
"""
from pathlib import Path

from setuptools import find_packages, setup


def version():
    for line in read("exchangelib/__init__.py").splitlines():
        if not line.startswith("__version__"):
            continue
        return line.split("=")[1].strip(" \"'\n")


def read(file_name):
    return (Path(__file__).parent / file_name).read_text()


setup(
    name="exchangelib",
    version=version(),
    author="Erik Cederstrand",
    author_email="erik@cederstrand.dk",
    description="Client for Microsoft Exchange Web Services (EWS)",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    license="BSD-2-Clause",
    keywords="ews exchange autodiscover microsoft outlook exchange-web-services o365 office365",
    install_requires=[
        'backports.zoneinfo;python_version<"3.9"',
        "cached_property",
        "defusedxml>=0.6.0",
        "dnspython>=2.2.0",
        "isodate",
        "lxml>3.0",
        "oauthlib",
        "pygments",
        "requests>=2.31.0",
        "requests_ntlm>=0.2.0",
        "requests_oauthlib",
        "tzdata",
        "tzlocal",
    ],
    extras_require={
        "kerberos": ["requests_gssapi"],
        "sspi": ["requests_negotiate_sspi"],  # Only for Win32 environments
        "complete": ["requests_gssapi", "requests_negotiate_sspi"],  # Only for Win32 environments
    },
    packages=find_packages(exclude=("tests", "tests.*")),
    python_requires=">=3.8",
    test_suite="tests",
    zip_safe=False,
    url="https://github.com/ecederstrand/exchangelib",
    project_urls={
        "Bug Tracker": "https://github.com/ecederstrand/exchangelib/issues",
        "Documentation": "https://ecederstrand.github.io/exchangelib/",
        "Source Code": "https://github.com/ecederstrand/exchangelib",
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Topic :: Communications",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3",
    ],
)
