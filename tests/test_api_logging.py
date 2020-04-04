from unittest import TestCase

import requests_mock

from exchangelib import Version, logging
from exchangelib.errors import TransportError
from exchangelib.version import EXCHANGE_2007, Build
from exchangelib.util import to_xml

from .common import TimedTestCase


class LoggingTest(TestCase):
    def test_logging(self):
        loggers = logging.loggers
        for lg in loggers:
            self.assertIsInstance(lg,logging)


    def test_default_api_version(self):
        # Test that a version gets a reasonable api_version value if we don't set one explicitly
        version = Version(build=Build(15, 1, 2, 3))
        self.assertEqual(version.api_version, 'Exchange2016')

    @requests_mock.mock()  # Just to make sure we don't make any requests
    def test_from_response(self, m):
        # Test fallback to suggested api_version value when there is a version mismatch and response version is fishy
        version = Version.from_soap_header(
            'Exchange2007',
            to_xml(b'''\
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1" Version="V2016_10_10"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>''')
        )
        self.assertEqual(version.api_version, EXCHANGE_2007.api_version())
        self.assertEqual(version.api_version, 'Exchange2007')
        self.assertEqual(version.build, Build(15, 1, 845, 22))

        # Test that override the suggested version if the response version is not fishy
        version = Version.from_soap_header(
            'Exchange2013',
            to_xml(b'''\
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1" Version="HELLO_FROM_EXCHANGELIB"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>''')
        )
        self.assertEqual(version.api_version, 'HELLO_FROM_EXCHANGELIB')

        # Test that we override the suggested version with the version deduced from the build number if a version is not
        # present in the response
        version = Version.from_soap_header(
            'Exchange2013',
            to_xml(b'''\
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>''')
        )
        self.assertEqual(version.api_version, 'Exchange2016')

        # Test that we use the version deduced from the build number when a version is not present in the response and
        # there was no suggested version.
        version = Version.from_soap_header(
            None,
            to_xml(b'''\
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>''')
        )
        self.assertEqual(version.api_version, 'Exchange2016')

        # Test various parse failures
        with self.assertRaises(TransportError):
            Version.from_soap_header(
                'Exchange2013',
                to_xml(b'''\
<s:Header>
</s:Header>''')
            )
        with self.assertRaises(TransportError):
            Version.from_soap_header(
                'Exchange2013',
                to_xml(b'''\
<s:Header>
    <h:ServerVersionInfo MajorBuildNumber="845" MajorVersion="15" Version="V2016_10_10"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>''')
            )
