# coding=utf-8
from __future__ import unicode_literals

import logging
from xml.etree.ElementTree import ParseError

import requests.sessions
from future.utils import raise_from, python_2_unicode_compatible
from six import text_type

from .errors import UnauthorizedError, TransportError, EWSWarning
from .transport import TNS, SOAPNS, dummy_xml, get_auth_instance
from .util import is_xml, to_xml, post_ratelimited

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
        },
    }

    __slots__ = ('major_version', 'minor_version', 'major_build', 'minor_build')

    def __init__(self, major_version, minor_version, major_build=0, minor_build=0):
        self.major_version = major_version
        self.minor_version = minor_version
        self.major_build = major_build
        self.minor_build = minor_build
        if major_version < 8:
            raise ValueError("Exchange major versions below 8 don't support EWS (%s)", text_type(self))

    @classmethod
    def from_xml(cls, elem):
        keys = 'MajorVersion', 'MinorVersion', 'MajorBuildNumber', 'MinorBuildNumber'
        vals = []
        for k in keys:
            v = elem.get(k)
            if v is None:
                raise ValueError()
            vals.append(int(v))  # Also raises ValueError
        elem.clear()
        return cls(*vals)

    def api_version(self):
        if self.major_version == 15 and self.minor_version == 0 and self.major_build >= 847:
            return 'Exchange2013_SP1'
        return self.API_VERSION_MAP[self.major_version][self.minor_version]

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
        return '%s.%s.%s.%s' % (self.major_version, self.minor_version, self.major_build, self.minor_build)

    def __repr__(self):
        return self.__class__.__name__ \
               + repr((self.major_version, self.minor_version, self.major_build, self.minor_build))


# Helpers for comparison operations elsewhere in this package
EXCHANGE_2007 = Build(8, 0)
EXCHANGE_2010 = Build(14, 0)
EXCHANGE_2013 = Build(15, 0)


@python_2_unicode_compatible
class Version(object):
    """
    Holds information about the server version
    """

    def __init__(self, build, api_version):
        self.build = build
        self.api_version = api_version

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
        try:
            auth = get_auth_instance(credentials=protocol.credentials, auth_type=protocol.docs_auth_type)
            shortname = cls._get_shortname_from_docs(auth=auth, types_url=protocol.types_url,
                                                     verify_ssl=protocol.verify_ssl)
            log.debug('Shortname according to %s: %s', protocol.types_url, shortname)
        except (TransportError, UnauthorizedError) as e:
            log.info(text_type(e))
            shortname = None
        api_version = VERSIONS[shortname][0] if shortname else None
        return cls._guess_version_from_service(protocol=protocol, hint=api_version)

    @staticmethod
    def _get_shortname_from_docs(auth, types_url, verify_ssl):
        # Get the server version from types.xsd. We can't necessarily use the service auth type since it may not be the
        # same as the auth type for docs.
        log.debug('Getting %s with auth type %s', types_url, auth.__class__.__name__)
        # Some servers send an empty response if we send 'Connection': 'close' header
        with requests.sessions.Session() as s:
            r = s.get(url=types_url, auth=auth, allow_redirects=False, stream=False, verify=verify_ssl)
        log.debug('Request headers: %s', r.request.headers)
        log.debug('Response code: %s', r.status_code)
        log.debug('Response headers: %s', r.headers)
        if r.status_code == 401:
            raise UnauthorizedError('Wrong username or password for %s' % types_url)
        if r.status_code == 302:
            log.debug('We were redirected. Unable to get version info from docs')
            return None
        if r.status_code == 503:
            log.debug('Service is unavailable. Unable to get version info from docs')
            return None
        if r.status_code != 200:
            if 'The referenced account is currently locked out' in r.text:
                raise TransportError('The service account is currently locked out')
            raise TransportError('Unexpected HTTP status %s when getting %s (%s)' % (r.status_code, types_url, r.text))
        if not is_xml(r.text):
            raise TransportError('Unexpected result when getting %s. Maybe this is not an EWS server?%s' % (
                types_url,
                '\n\n%s[...]' % r.text[:200] if len(r.text) > 200 else '\n\n%s' % r.text if r.text else '',
            ))
        return to_xml(r.text, encoding=r.encoding).get('version')

    @classmethod
    def _guess_version_from_service(cls, protocol, hint=None):
        # Keep sending requests until we get a valid response. If we have a hint, start guessing that.
        if hint:
            api_versions = [hint] + [v for v in API_VERSIONS if v != hint]
        else:
            api_versions = API_VERSIONS
        for api_version in api_versions:
            try:
                return cls._get_version_from_service(protocol=protocol, api_version=api_version)
            except EWSWarning:
                continue
        raise TransportError('Unable to guess version')

    @classmethod
    def _get_version_from_service(cls, protocol, api_version):
        assert api_version
        xml = dummy_xml(version=api_version)
        # Create a minimal, valid EWS request to force Exchange into accepting the request and returning EWS xml
        # containing server version info. Some servers will only reply with their version if a valid POST is sent.
        session = protocol.get_session()
        log.debug('Test if service API version is %s using auth %s', api_version, session.auth.__class__.__name__)
        r, session = post_ratelimited(protocol=protocol, session=session, url=protocol.service_endpoint, headers=None,
                                      data=xml, timeout=protocol.TIMEOUT, verify=protocol.verify_ssl,
                                      allow_redirects=False)
        protocol.release_session(session)

        if r.status_code == 401:
            raise UnauthorizedError('Wrong username or password for %s' % protocol.service_endpoint)
        elif r.status_code == 302:
            log.debug('We were redirected. Unable to get version info from service')
            return None
        elif r.status_code == 503:
            log.debug('Service is unavailable. Unable to get version info from service')
            return None
        if r.status_code == 400:
            raise EWSWarning('Bad request')
        if r.status_code == 500 and ('The specified server version is invalid' in r.text or
                                             'ErrorInvalidSchemaVersionForMailboxVersion' in r.text):
            raise EWSWarning('Invalid server version')
        if r.status_code != 200:
            if 'The referenced account is currently locked out' in r.text:
                raise TransportError('The service account is currently locked out')
            raise TransportError('Unexpected HTTP status %s when getting %s (%s)' % (
                r.status_code, protocol.service_endpoint, r.text))
        log.debug('Response data: %s', r.text)
        try:
            header = to_xml(r.text, encoding=r.encoding).find('{%s}Header' % SOAPNS)
            if header is None:
                raise ParseError()
        except ParseError as e:
            raise_from(EWSWarning('Unknown XML response from %s (response: %s)' % (protocol.service_endpoint,
                                                                                   r.text)), e)
        info = header.find('{%s}ServerVersionInfo' % TNS)
        if info is None:
            raise TransportError('No ServerVersionInfo in response: %s' % r.text)

        version = cls.from_response(requested_api_version=api_version, response=r)
        log.debug('Service version is: %s', version)
        return version

    @classmethod
    def from_response(cls, requested_api_version, response):
        try:
            header = to_xml(response.text, encoding=response.encoding).find('{%s}Header' % SOAPNS)
            if header is None:
                raise ParseError()
        except ParseError as e:
            raise_from(EWSWarning('Unknown XML response from %s (response: %s)' % (response, response.text)), e)
        info = header.find('{%s}ServerVersionInfo' % TNS)
        if info is None:
            raise TransportError('No ServerVersionInfo in response: %s' % response.text)

        try:
            build = Build.from_xml(info)
        except ValueError:
            raise TransportError('Bad ServerVersionInfo in response: %s' % response.text)
        # Not all Exchange servers send the Version element
        api_version_from_server = info.get('Version') or build.api_version()
        if api_version_from_server != requested_api_version:
            if api_version_from_server.startswith('V2_') \
                    or api_version_from_server.startswith('V2015_') \
                    or api_version_from_server.startswith('V2016_'):
                # Office 365 is an expert in sending invalid API version strings...
                log.info('API version "%s" worked but server reports version "%s". Using "%s"', requested_api_version,
                         api_version_from_server, requested_api_version)
                api_version_from_server = requested_api_version
            else:
                # Work around a bug in Exchange that reports a bogus API version in the XML response. Trust server
                # response except 'V2_nn' or 'V201[5,6]_nn_mm' which is bogus
                log.info('API version "%s" worked but server reports version "%s". Using "%s"', requested_api_version,
                         api_version_from_server, api_version_from_server)
        return cls(build, api_version_from_server)

    def __repr__(self):
        return self.__class__.__name__ + repr((self.build, self.api_version))

    def __str__(self):
        return 'Build=%s, API=%s, Fullname=%s' % (self.build, self.api_version, self.fullname)
