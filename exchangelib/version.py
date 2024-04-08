import logging
import re

from .errors import InvalidTypeError, ResponseMessageError, TransportError
from .util import ANS, TNS, get_xml_attr, xml_to_str

log = logging.getLogger(__name__)


class Build:
    """Holds methods for working with build numbers."""

    __slots__ = "major_version", "minor_version", "major_build", "minor_build"

    def __init__(self, major_version, minor_version, major_build=0, minor_build=0):
        if not isinstance(major_version, int):
            raise InvalidTypeError("major_version", major_version, int)
        if not isinstance(minor_version, int):
            raise InvalidTypeError("minor_version", minor_version, int)
        if not isinstance(major_build, int):
            raise InvalidTypeError("major_build", major_build, int)
        if not isinstance(minor_build, int):
            raise InvalidTypeError("minor_build", minor_build, int)
        self.major_version = major_version
        self.minor_version = minor_version
        self.major_build = major_build
        self.minor_build = minor_build
        if major_version < 8:
            raise ValueError(f"Exchange major versions below 8 don't support EWS ({self})")

    @classmethod
    def from_xml(cls, elem):
        xml_elems_map = {
            "major_version": "MajorVersion",
            "minor_version": "MinorVersion",
            "major_build": "MajorBuildNumber",
            "minor_build": "MinorBuildNumber",
        }
        kwargs = {}
        for k, xml_elem in xml_elems_map.items():
            v = elem.get(xml_elem)
            if v is None:
                v = get_xml_attr(elem, f"{{{ANS}}}{xml_elem}")
                if v is None:
                    raise ValueError()
            kwargs[k] = int(v)  # Also raises ValueError
        return cls(**kwargs)

    def api_version(self):
        for build, api_version, _ in VERSIONS:
            if self.major_version != build.major_version or self.minor_version != build.minor_version:
                continue
            if self >= build:
                return api_version
        raise ValueError(f"API version for build {self} is unknown")

    def __cmp__(self, other):
        # __cmp__ is not a magic method in Python3. We'll just use it here to implement comparison operators
        c = (self.major_version > other.major_version) - (self.major_version < other.major_version)
        if c != 0:
            return c
        c = (self.minor_version > other.minor_version) - (self.minor_version < other.minor_version)
        if c != 0:
            return c
        c = (self.major_build > other.major_build) - (self.major_build < other.major_build)
        if c != 0:
            return c
        return (self.minor_build > other.minor_build) - (self.minor_build < other.minor_build)

    def __eq__(self, other):
        return self.__cmp__(other) == 0

    def __hash__(self):
        return hash(repr(self))

    def __ne__(self, other):
        return self.__cmp__(other) != 0

    def __lt__(self, other):
        return self.__cmp__(other) < 0

    def __le__(self, other):
        return self.__cmp__(other) <= 0

    def __gt__(self, other):
        return self.__cmp__(other) > 0

    def __ge__(self, other):
        return self.__cmp__(other) >= 0

    def __str__(self):
        return f"{self.major_version}.{self.minor_version}.{self.major_build}.{self.minor_build}"

    def __repr__(self):
        return self.__class__.__name__ + repr(
            (self.major_version, self.minor_version, self.major_build, self.minor_build)
        )


# Helpers for comparison operations elsewhere in this package
EXCHANGE_2007 = Build(8, 0)
EXCHANGE_2007_SP1 = Build(8, 1)
EXCHANGE_2007_SP2 = Build(8, 2)
EXCHANGE_2007_SP3 = Build(8, 3)
EXCHANGE_2010 = Build(14, 0)
EXCHANGE_2010_SP1 = Build(14, 1)
EXCHANGE_2010_SP2 = Build(14, 2)
EXCHANGE_2010_SP3 = Build(14, 3)
EXCHANGE_2013 = Build(15, 0)
EXCHANGE_2013_SP1 = Build(15, 0, 847)  # Major builds starting from 847 are Exchange2013_SP1
EXCHANGE_2015 = Build(15, 20)
EXCHANGE_2015_SP1 = Build(15, 20)
EXCHANGE_2016 = Build(15, 1)
EXCHANGE_2019 = Build(15, 2)
EXCHANGE_O365 = Build(15, 20)

# Legend for VERSIONS:
#   (build, API version, full name)
#
# 'API version' is the version name supplied in the RequestServerVersion element in SOAP headers and describes the EWS
# API version the server implements. Valid values for this element are described here:
#   https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/requestserverversion
#
# A list of build numbers and full version names is available here:
#   https://docs.microsoft.com/en-us/exchange/new-features/build-numbers-and-release-dates
#
# The list is sorted from newest to oldest build
VERSIONS = (
    (EXCHANGE_O365, "Exchange2016", "Microsoft Exchange Server Office365"),  # Not mentioned in list of build numbers
    (EXCHANGE_2019, "Exchange2016", "Microsoft Exchange Server 2019"),
    (EXCHANGE_2016, "Exchange2016", "Microsoft Exchange Server 2016"),
    (EXCHANGE_2015_SP1, "Exchange2015_SP1", "Microsoft Exchange Server 2015 SP1"),
    (EXCHANGE_2015, "Exchange2015", "Microsoft Exchange Server 2015"),
    (EXCHANGE_2013_SP1, "Exchange2013_SP1", "Microsoft Exchange Server 2013 SP1"),
    (EXCHANGE_2013, "Exchange2013", "Microsoft Exchange Server 2013"),
    (EXCHANGE_2010_SP3, "Exchange2010_SP2", "Microsoft Exchange Server 2010 SP3"),
    (EXCHANGE_2010_SP2, "Exchange2010_SP2", "Microsoft Exchange Server 2010 SP2"),
    (EXCHANGE_2010_SP1, "Exchange2010_SP1", "Microsoft Exchange Server 2010 SP1"),
    (EXCHANGE_2010, "Exchange2010", "Microsoft Exchange Server 2010"),
    (EXCHANGE_2007_SP3, "Exchange2007_SP1", "Microsoft Exchange Server 2007 SP3"),
    (EXCHANGE_2007_SP2, "Exchange2007_SP1", "Microsoft Exchange Server 2007 SP2"),
    (EXCHANGE_2007_SP1, "Exchange2007_SP1", "Microsoft Exchange Server 2007 SP1"),
    (EXCHANGE_2007, "Exchange2007", "Microsoft Exchange Server 2007"),
)


class Version:
    """Holds information about the server version."""

    __slots__ = "build", "api_version"

    def __init__(self, build, api_version=None):
        if api_version is None:
            if not isinstance(build, Build):
                raise InvalidTypeError("build", build, Build)
            self.api_version = build.api_version()
        else:
            if not isinstance(build, (Build, type(None))):
                raise InvalidTypeError("build", build, Build)
            if not isinstance(api_version, str):
                raise InvalidTypeError("api_version", api_version, str)
            self.api_version = api_version
        self.build = build

    @property
    def fullname(self):
        for build, api_version, full_name in VERSIONS:
            if self.build and (
                self.build.major_version != build.major_version or self.build.minor_version != build.minor_version
            ):
                continue
            if self.api_version == api_version:
                return full_name
        log.warning("Full name for API version %s build %s is unknown", self.api_version, self.build)
        return "UNKNOWN"

    @classmethod
    def guess(cls, protocol, api_version_hint=None):
        """Ask the server which version it has. We haven't set up an Account object yet, so we generate requests
        by hand. We only need a response header containing a ServerVersionInfo element.

        To get API version and build numbers from the server, we need to send a valid SOAP request. We can't do that
        without a valid API version. To solve this chicken-and-egg problem, we try all possible API versions that this
        package supports, until we get a valid response.

        :param protocol:
        :param api_version_hint:  (Default value = None)
        """
        from .properties import ENTRY_ID, EWS_ID, AlternateId
        from .services import ConvertId

        # The protocol doesn't have a version yet, so default to the latest supported version if we don't have a hint.
        api_version = api_version_hint or ConvertId.supported_api_versions()[0]
        log.debug("Asking server for version info using API version %s", api_version)
        # We don't know the build version yet. Hopefully, the server will report it in the SOAP header. Lots of
        # places expect a version to have a build, so this is a bit dangerous, but passing a fake build around is also
        # dangerous.
        protocol.config.version = Version(build=None, api_version=api_version)
        # Use ConvertId as a minimal request to the server to test if the version is correct. If not, ConvertId will
        # try to guess the version automatically. Make sure the call to ConvertId does not require a version build.
        try:
            list(ConvertId(protocol=protocol).call([AlternateId(id="DUMMY", format=EWS_ID, mailbox="DUMMY")], ENTRY_ID))
        except ResponseMessageError as e:
            # We may have survived long enough to get a new version
            if not protocol.config.version.build:
                raise TransportError(f"No valid version headers found in response ({e!r})")
        if not protocol.config.version.build:
            raise TransportError("No valid version headers found in response")
        return protocol.config.version

    @staticmethod
    def _is_invalid_version_string(version):
        # Check if a version string is bogus, e.g. V2_, V2015_ or V2018_
        return re.match(r"V[0-9]{1,4}_.*", version)

    @classmethod
    def from_soap_header(cls, requested_api_version, header):
        info = header.find(f"{{{TNS}}}ServerVersionInfo")
        if info is None:
            info = header.find(f"{{{ANS}}}ServerVersionInfo")
            if info is None:
                raise TransportError(f"No ServerVersionInfo in header: {xml_to_str(header)!r}")
        try:
            build = Build.from_xml(elem=info)
        except ValueError:
            raise TransportError(f"Bad ServerVersionInfo in response: {xml_to_str(header)!r}")
        # Not all Exchange servers send the Version element
        api_version_from_server = info.get("Version") or get_xml_attr(info, f"{{{ANS}}}Version") or build.api_version()
        if api_version_from_server != requested_api_version:
            if cls._is_invalid_version_string(api_version_from_server):
                # For unknown reasons, Office 365 may respond with an API version strings that is invalid in a request.
                # Detect these, so we can fall back to a valid version string.
                log.debug(
                    'API version "%s" worked but server reports version "%s". Using "%s"',
                    requested_api_version,
                    api_version_from_server,
                    requested_api_version,
                )
                api_version_from_server = requested_api_version
            else:
                # Trust API version from server response
                log.debug(
                    'API version "%s" worked but server reports version "%s". Using "%s"',
                    requested_api_version,
                    api_version_from_server,
                    api_version_from_server,
                )
        return cls(build=build, api_version=api_version_from_server)

    def copy(self):
        return self.__class__(build=self.build, api_version=self.api_version)

    @classmethod
    def all_versions(cls):
        # Return all supported versions, sorted newest to oldest
        return [cls(build=build, api_version=api_version) for build, api_version, _ in VERSIONS]

    def __hash__(self):
        return hash((self.build, self.api_version))

    def __eq__(self, other):
        if self.api_version != other.api_version:
            return False
        if self.build and not other.build:
            return False
        if other.build and not self.build:
            return False
        return self.build == other.build

    def __repr__(self):
        return self.__class__.__name__ + repr((self.build, self.api_version))

    def __str__(self):
        return f"Build={self.build}, API={self.api_version}, Fullname={self.fullname}"


class SupportedVersionClassMixIn:
    """Supports specifying the supported versions of services, fields, folders etc.

    For distinguished folders, a possibly authoritative source is:
    # https://github.com/OfficeDev/ews-managed-api/blob/master/Enumerations/WellKnownFolderName.cs
    """

    supported_from = None  # The Exchange build when this element was introduced
    deprecated_from = None  # The Exchange build when this element was deprecated

    @classmethod
    def __new__(cls, *args, **kwargs):
        _check(cls.supported_from, cls.deprecated_from)
        return super().__new__(cls)

    @classmethod
    def supports_version(cls, version):
        return _supports_version(cls.supported_from, cls.deprecated_from, version)


class SupportedVersionInstanceMixIn:
    """Like SupportedVersionClassMixIn but for class instances"""

    def __init__(self, supported_from=None, deprecated_from=None):
        _check(supported_from, deprecated_from)
        self.supported_from = supported_from
        self.deprecated_from = deprecated_from

    def supports_version(self, version):
        return _supports_version(self.supported_from, self.deprecated_from, version)


def _check(supported_from, deprecated_from):
    if supported_from is not None and not isinstance(supported_from, Build):
        raise InvalidTypeError("supported_from", supported_from, Build)
    if deprecated_from is not None and not isinstance(deprecated_from, Build):
        raise InvalidTypeError("deprecated_from", deprecated_from, Build)


def _supports_version(supported_from, deprecated_from, version):
    # 'version' is a Version instance, for convenience by callers
    if supported_from and version.build < supported_from:
        return False
    if deprecated_from and version.build >= deprecated_from:
        return False
    return True
