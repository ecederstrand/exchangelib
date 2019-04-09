# coding=utf-8
from __future__ import unicode_literals

import logging
import re

from future.utils import python_2_unicode_compatible, PY2
from six import text_type

from .errors import TransportError, ErrorInvalidSchemaVersionForMailboxVersion, ErrorInvalidServerVersion, \
    ResponseMessageError
from .transport import get_auth_instance
from .util import is_xml, to_xml, TNS, SOAPNS, ParseError

log = logging.getLogger(__name__)

# Legend for dict:
#   Key: shortname
#   Values: (EWS API version ID, full name)

# 'shortname' comes from types.xsd and is the official version of the server, corresponding to the version numbers
# supplied in SOAP headers. 'API version' is the version name supplied in the RequestServerVersion element in SOAP
# headers and describes the EWS API version the server implements. Valid values for this element are described here:
#    http://msdn.microsoft.com/en-us/library/bb891876(v=exchg.150).aspx

VERSIONS = {
    'Exchange2007': ('Exchange2007', 'Microsoft Exchange Server 2007'),
    'Exchange2007_SP1': ('Exchange2007_SP1', 'Microsoft Exchange Server 2007 SP1'),
    'Exchange2007_SP2': ('Exchange2007_SP1', 'Microsoft Exchange Server 2007 SP2'),
    'Exchange2007_SP3': ('Exchange2007_SP1', 'Microsoft Exchange Server 2007 SP3'),
    'Exchange2010': ('Exchange2010', 'Microsoft Exchange Server 2010'),
    'Exchange2010_SP1': ('Exchange2010_SP1', 'Microsoft Exchange Server 2010 SP1'),
    'Exchange2010_SP2': ('Exchange2010_SP2', 'Microsoft Exchange Server 2010 SP2'),
    'Exchange2010_SP3': ('Exchange2010_SP2', 'Microsoft Exchange Server 2010 SP3'),
    'Exchange2013': ('Exchange2013', 'Microsoft Exchange Server 2013'),
    'Exchange2013_SP1': ('Exchange2013_SP1', 'Microsoft Exchange Server 2013 SP1'),
    'Exchange2015': ('Exchange2015', 'Microsoft Exchange Server 2015'),
    'Exchange2015_SP1': ('Exchange2015_SP1', 'Microsoft Exchange Server 2015 SP1'),
    'Exchange2016': ('Exchange2016', 'Microsoft Exchange Server 2016'),
    'Exchange2019': ('Exchange2019', 'Microsoft Exchange Server 2019'),
}

# Build a list of unique API versions, used when guessing API version supported by the server.  Use reverse order so we
# get the newest API version supported by the server.
API_VERSIONS = sorted({v[0] for v in VERSIONS.values()}, reverse=True)


@python_2_unicode_compatible
class Build(object):
    """
    Holds methods for working with build numbers
    """

    # List of build numbers here: https://technet.microsoft.com/en-gb/library/hh135098(v=exchg.150).aspx
    API_VERSION_MAP = {
        8: {
            0: 'Exchange2007',
            1: 'Exchange2007_SP1',
            2: 'Exchange2007_SP1',
            3: 'Exchange2007_SP1',
        },
        14: {
            0: 'Exchange2010',
            1: 'Exchange2010_SP1',
            2: 'Exchange2010_SP2',
            3: 'Exchange2010_SP2',
        },
        15: {
            0: 'Exchange2013',  # Minor builds starting from 847 are Exchange2013_SP1, see api_version()
            1: 'Exchange2016',
            2: 'Exchange2019',
            20: 'Exchange2016',  # This is Office365. See issue #221
        },
    }

    __slots__ = ('major_version', 'minor_version', 'major_build', 'minor_build')

    def __init__(self, major_version, minor_version, major_build=0, minor_build=0):
        self.major_version = major_version
        self.minor_version = minor_version
        self.major_build = major_build
        self.minor_build = minor_build
        if major_version < 8:
            raise ValueError("Exchange major versions below 8 don't support EWS (%s)" % text_type(self))

    @classmethod
    def from_xml(cls, elem):
        xml_elems_map = {
            'major_version': 'MajorVersion',
            'minor_version': 'MinorVersion',
            'major_build': 'MajorBuildNumber',
            'minor_build': 'MinorBuildNumber',
        }
        kwargs = {}
        for k, xml_elem in xml_elems_map.items():
            v = elem.get(xml_elem)
            if v is None:
                raise ValueError()
            kwargs[k] = int(v)  # Also raises ValueError
        return cls(**kwargs)

    def api_version(self):
        if EXCHANGE_2013_SP1 <= self < EXCHANGE_2016:
            return 'Exchange2013_SP1'
        try:
            return self.API_VERSION_MAP[self.major_version][self.minor_version]
        except KeyError:
            raise ValueError('API version for build %s is unknown' % self)

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

    if PY2:
        def __getstate__(self):
            return {k: getattr(self, k) for k in self.__slots__}

        def __setstate__(self, state):
            for k in self.__slots__:
                setattr(self, k, state.get(k))

    def __str__(self):
        return '%s.%s.%s.%s' % (self.major_version, self.minor_version, self.major_build, self.minor_build)

    def __repr__(self):
        return self.__class__.__name__ \
               + repr((self.major_version, self.minor_version, self.major_build, self.minor_build))


# Helpers for comparison operations elsewhere in this package
EXCHANGE_2007 = Build(8, 0)
EXCHANGE_2007_SP1 = Build(8, 1)
EXCHANGE_2010 = Build(14, 0)
EXCHANGE_2010_SP1 = Build(14, 1)
EXCHANGE_2010_SP2 = Build(14, 2)
EXCHANGE_2013 = Build(15, 0)
EXCHANGE_2013_SP1 = Build(15, 0, 847)
EXCHANGE_2016 = Build(15, 1)
EXCHANGE_2019 = Build(15, 2)


@python_2_unicode_compatible
class Version(object):
    """
    Holds information about the server version
    """
    __slots__ = ('build', 'api_version')

    def __init__(self, build, api_version=None):
        self.build = build
        self.api_version = api_version
        if self.build is not None and self.api_version is None:
            self.api_version = build.api_version()

    @property
    def fullname(self):
        return VERSIONS[self.api_version][1]

    @classmethod
    def guess(cls, protocol):
        """
        Tries to ask the server which version it has. We haven't set up an Account object yet, so we generate requests
        by hand. We only need a response header containing a ServerVersionInfo element.

        The types.xsd document contains a 'shortname' value that we can use as a key for VERSIONS to get the API version
        that we need in SOAP headers to generate valid requests. Unfortunately, the Exchagne server may be misconfigured
        to either block access to types.xsd or serve up a wrong version of the document. Therefore, we only use
        'shortname' as a hint, but trust the SOAP version returned in response headers.

        To get API version and build numbers from the server, we need to send a valid SOAP request. We can't do that
        without a valid API version. To solve this chicken-and-egg problem, we try all possible API versions that this
        package supports, until we get a valid response. If we managed to get a 'shortname' previously, we try the
        corresponding API version first.
        """
        log.debug('Asking server for version info')
        # We can't use a session object from the protocol pool for docs because sessions are created with service auth.
        auth = get_auth_instance(credentials=protocol.credentials, auth_type=protocol.docs_auth_type)
        try:
            shortname = cls._get_shortname_from_docs(auth=auth, types_url=protocol.types_url)
            log.debug('Shortname according to %s: %s', protocol.types_url, shortname)
        except (TransportError, ParseError) as e:
            log.info(text_type(e))
            shortname = None
        api_version = VERSIONS[shortname][0] if shortname else None
        return cls._guess_version_from_service(protocol=protocol, hint=api_version)

    @staticmethod
    def _get_shortname_from_docs(auth, types_url):
        # Get the server version from types.xsd. We can't necessarily use the service auth type since it may not be the
        # same as the auth type for docs.
        log.debug('Getting %s with auth type %s', types_url, auth.__class__.__name__)
        # Some servers send an empty response if we send 'Connection': 'close' header
        from .protocol import BaseProtocol
        with BaseProtocol.raw_session() as s:
            r = s.get(url=types_url, auth=auth, allow_redirects=False, stream=False)
        log.debug('Request headers: %s', r.request.headers)
        log.debug('Response code: %s', r.status_code)
        log.debug('Response headers: %s', r.headers)
        log.debug('Response data: %s', r.content[:1000])
        if r.status_code != 200:
            raise TransportError('Unexpected HTTP %s when getting %s (%r)' % (r.status_code, types_url, r.content))
        if not is_xml(r.content):
            raise TransportError('Unexpected result when getting %s. Maybe this is not an EWS server?%s' % (
                types_url,
                '\n\n%r[...]' % r.content[:200] if len(r.content) > 200 else '\n\n%r' % r.content if r.content else '',
            ))
        return to_xml(r.content).getroot().get('version')

    @classmethod
    def _guess_version_from_service(cls, protocol, hint=None):
        # The protocol doesn't have a version yet, so add one with our hint, or default to latest supported version.
        # Use ResolveNames as a minimal request to the server to test if the version is correct. If not, ResolveNames
        # will try to guess the version automatically.
        from .services import ResolveNames
        protocol.version = Version(build=None, api_version=hint or API_VERSIONS[-1])
        try:
            list(ResolveNames(protocol=protocol).call(unresolved_entries=[protocol.credentials.username]))
        except (ErrorInvalidSchemaVersionForMailboxVersion, ErrorInvalidServerVersion):
            raise TransportError('Unable to guess version')
        except ResponseMessageError:
            # We survived long enough to get a new version
            pass
        return protocol.version

    @staticmethod
    def _is_invalid_version_string(version):
        # Check if a version string is bogus, e.g. V2_, V2015_ or V2018_
        return re.match(r'V[0-9]{1,4}_.*', version)

    @classmethod
    def from_response(cls, requested_api_version, bytes_content):
        try:
            header = to_xml(bytes_content).find('{%s}Header' % SOAPNS)
            if header is None:
                raise TransportError('No header in XML response (%r)' % bytes_content)
        except ParseError:
            raise TransportError('Unknown XML response (%r)' % bytes_content)

        info = header.find('{%s}ServerVersionInfo' % TNS)
        if info is None:
            raise TransportError('No ServerVersionInfo in response: %r' % bytes_content)
        try:
            build = Build.from_xml(elem=info)
        except ValueError:
            raise TransportError('Bad ServerVersionInfo in response: %r' % bytes_content)
        # Not all Exchange servers send the Version element
        api_version_from_server = info.get('Version') or build.api_version()
        if api_version_from_server != requested_api_version:
            if cls._is_invalid_version_string(api_version_from_server):
                # For unknown reasons, Office 365 may respond with an API version strings that is invalid in a request.
                # Detect these so we can fallback to a valid version string.
                log.info('API version "%s" worked but server reports version "%s". Using "%s"', requested_api_version,
                         api_version_from_server, requested_api_version)
                api_version_from_server = requested_api_version
            else:
                # Work around a bug in Exchange that reports a bogus API version in the XML response. Trust server
                # response except 'V2_nn' or 'V201[5,6]_nn_mm' which is bogus
                log.info('API version "%s" worked but server reports version "%s". Using "%s"', requested_api_version,
                         api_version_from_server, api_version_from_server)
        return cls(build, api_version_from_server)

    if PY2:
        def __getstate__(self):
            return {k: getattr(self, k) for k in self.__slots__}

        def __setstate__(self, state):
            for k in self.__slots__:
                setattr(self, k, state.get(k))

    def __repr__(self):
        return self.__class__.__name__ + repr((self.build, self.api_version))

    def __str__(self):
        return 'Build=%s, API=%s, Fullname=%s' % (self.build, self.api_version, self.fullname)
