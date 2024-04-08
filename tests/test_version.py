import requests_mock

from exchangelib.errors import TransportError
from exchangelib.util import to_xml
from exchangelib.version import EXCHANGE_2007, Build, Version

from .common import TimedTestCase


class VersionTest(TimedTestCase):
    def test_magic(self):
        hash(Version(Build(15, 1, 2, 3)))

    def test_invalid_version_args(self):
        with self.assertRaises(TypeError) as e:
            Version(build="XXX")
        self.assertEqual(e.exception.args[0], "'build' 'XXX' must be of type <class 'exchangelib.version.Build'>")
        with self.assertRaises(TypeError) as e:
            Version(build="XXX", api_version="XXX")
        self.assertEqual(e.exception.args[0], "'build' 'XXX' must be of type <class 'exchangelib.version.Build'>")
        with self.assertRaises(TypeError) as e:
            Version(build=Build(15, 1, 2, 3), api_version=999)
        self.assertEqual(e.exception.args[0], "'api_version' 999 must be of type <class 'str'>")

    def test_invalid_build_args(self):
        with self.assertRaises(TypeError) as e:
            Build("XXX", 2, 3, 4)
        self.assertEqual(e.exception.args[0], "'major_version' 'XXX' must be of type <class 'int'>")
        with self.assertRaises(TypeError) as e:
            Build(1, "XXX", 3, 4)
        self.assertEqual(e.exception.args[0], "'minor_version' 'XXX' must be of type <class 'int'>")
        with self.assertRaises(TypeError) as e:
            Build(1, 2, "XXX", 4)
        self.assertEqual(e.exception.args[0], "'major_build' 'XXX' must be of type <class 'int'>")
        with self.assertRaises(TypeError) as e:
            Build(1, 2, 3, "XXX")
        self.assertEqual(e.exception.args[0], "'minor_build' 'XXX' must be of type <class 'int'>")

    def test_comparison(self):
        self.assertEqual(Version(Build(15, 1, 2, 3)), Version(Build(15, 1, 2, 3)))
        self.assertNotEqual(Version(Build(15, 1, 2, 3)), Version(Build(15, 1)))
        self.assertNotEqual(Version(Build(15, 1, 2, 3), api_version="XXX"), Version(None, api_version="XXX"))
        self.assertNotEqual(Version(None, api_version="XXX"), Version(Build(15, 1, 2), api_version="XXX"))
        self.assertEqual(Version(Build(15, 1, 2, 3), "XXX"), Version(Build(15, 1, 2, 3), "XXX"))
        self.assertNotEqual(Version(Build(15, 1, 2, 3), "XXX"), Version(Build(15, 1, 2, 3), "YYY"))
        self.assertNotEqual(Version(Build(15, 1, 2, 3), "XXX"), Version(Build(99, 88), "XXX"))
        self.assertNotEqual(Version(Build(15, 1, 2, 3), "XXX"), Version(Build(99, 88), "YYY"))

    def test_default_api_version(self):
        # Test that a version gets a reasonable api_version value if we don't set one explicitly
        version = Version(build=Build(15, 1, 2, 3))
        self.assertEqual(version.api_version, "Exchange2016")

    @requests_mock.mock()  # Just to make sure we don't make any requests
    def test_from_response(self, m):
        # Test fallback to suggested api_version value when there is a version mismatch and response version is fishy
        version = Version.from_soap_header(
            "Exchange2007",
            to_xml(
                b"""\
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1" Version="V2016_10_10"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>"""
            ),
        )
        self.assertEqual(version.api_version, EXCHANGE_2007.api_version())
        self.assertEqual(version.api_version, "Exchange2007")
        self.assertEqual(version.build, Build(15, 1, 845, 22))

        # Test that override the suggested version if the response version is not fishy
        version = Version.from_soap_header(
            "Exchange2013",
            to_xml(
                b"""\
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1" Version="HELLO_FROM_EXCHANGELIB"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>"""
            ),
        )
        self.assertEqual(version.api_version, "HELLO_FROM_EXCHANGELIB")

        # Test that we override the suggested version with the version deduced from the build number if a version is not
        # present in the response
        version = Version.from_soap_header(
            "Exchange2013",
            to_xml(
                b"""\
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>"""
            ),
        )
        self.assertEqual(version.api_version, "Exchange2016")

        # Test that we use the version deduced from the build number when a version is not present in the response and
        # there was no suggested version.
        version = Version.from_soap_header(
            None,
            to_xml(
                b"""\
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>"""
            ),
        )
        self.assertEqual(version.api_version, "Exchange2016")

        # Test various parse failures
        with self.assertRaises(TransportError) as e:
            Version.from_soap_header(
                "Exchange2013",
                to_xml(
                    b"""\
<s:Header>
    <foo/>
</s:Header>"""
                ),
            )
        self.assertIn("No ServerVersionInfo in header", e.exception.args[0])
        with self.assertRaises(TransportError) as e:
            Version.from_soap_header(
                "Exchange2013",
                to_xml(
                    b"""\
<s:Header>
    <h:ServerVersionInfo MajorBuildNumber="845" MajorVersion="15" Version="V2016_10_10"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>"""
                ),
            )
        self.assertIn("Bad ServerVersionInfo in response", e.exception.args[0])
