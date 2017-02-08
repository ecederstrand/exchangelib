# coding=utf-8
from __future__ import unicode_literals

import logging
from xml.etree.ElementTree import tostring

from future.utils import raise_from
from six import text_type
import requests.sessions
import requests.auth
import requests_ntlm

from .credentials import IMPERSONATION
from .errors import UnauthorizedError, TransportError, RedirectError, RelativeRedirect
from .util import create_element, add_xml_child, is_xml, get_redirect_url

log = logging.getLogger(__name__)

# XML namespaces
SOAPNS = 'http://schemas.xmlsoap.org/soap/envelope/'
MNS = 'http://schemas.microsoft.com/exchange/services/2006/messages'
TNS = 'http://schemas.microsoft.com/exchange/services/2006/types'
ENS = 'http://schemas.microsoft.com/exchange/services/2006/errors'

# Authentication method enums
NOAUTH = 'no authentication'
NTLM = 'NTLM'
BASIC = 'basic'
DIGEST = 'digest'
UNKNOWN = 'unknown'

AUTH_TYPE_MAP = {
    NTLM: requests_ntlm.HttpNtlmAuth,
    BASIC: requests.auth.HTTPBasicAuth,
    DIGEST: requests.auth.HTTPDigestAuth,
    NOAUTH: None,
}

AUTH_CLASS_MAP = dict((v, k) for k, v in AUTH_TYPE_MAP.items())


def test_credentials(protocol):
    return _test_docs_credentials(protocol) and _test_service_credentials(protocol)


def _test_docs_credentials(protocol):
    log.debug("Trying auth type '%s' on '%s'", protocol.docs_auth_type, protocol.types_url)
    # Retrieve the result. We allow 401 errors to happen since the authentication type may be wrong, giving a 401
    # response.
    auth = get_auth_instance(credentials=protocol.credentials, auth_type=protocol.docs_auth_type)
    with requests.sessions.Session() as s:
        r = s.get(url=protocol.types_url, auth=auth, allow_redirects=False, verify=protocol.verify_ssl)
    return _test_response(auth=auth, response=r)


def _test_service_credentials(protocol):
    log.debug("Trying auth type '%s' on '%s'", protocol.auth_type, protocol.service_endpoint)
    # Retrieve the result. We allow 401 errors to happen since the authentication type may be wrong, giving a 401
    # response.
    headers = {'Content-Type': 'text/xml; charset=utf-8'}
    data = dummy_xml(version=protocol.version.api_version)
    auth = get_auth_instance(credentials=protocol.credentials, auth_type=protocol.auth_type)
    with requests.sessions.Session() as s:
        r = s.post(url=protocol.service_endpoint, headers=headers, data=data, auth=auth, allow_redirects=False,
                   verify=protocol.verify_ssl)
    return _test_response(auth=auth, response=r)


def _test_response(auth, response):
    log.debug('Response headers: %s', response.headers)
    resp = response.text
    log.debug('Response data: %s [...]', text_type(resp[:1000]))
    if is_xml(resp):
        log.debug('This is XML')
        # Assume that any XML response is good news
        return True
    elif _is_unauthorized(resp):
        # Exchange brilliantly sends an unauth message as a non-401 page. Clever.
        raise UnauthorizedError('Unauthorized (non-401)')
    elif isinstance(auth, HttpNtlmAuth) and not resp:
        # It seems the NTLM handler doesn't throw 401 errors. If the request is invalid, it doesn't bother
        # responding with anything. Even more clever.
        raise UnauthorizedError('Unauthorized (NTLM, empty response)')
    else:
        raise TransportError('Unknown response from Exchange:\n\n%s' % resp)


def _is_unauthorized(txt):
    """
    Helper function. Test if response contains an "Unauthorized" message
    """
    if txt.lower().count('unauthorized') > 0:
        return True
    return False


def wrap(content, version, account, ewstimezone=None, encoding='utf-8'):
    """
    Generate the necessary boilerplate XML for a raw SOAP request. The XML is specific to the server version.
    ExchangeImpersonation allows to act as the user we want to impersonate.
    """
    envelope = create_element('s:Envelope', **{
        'xmlns:s': SOAPNS,
        'xmlns:t': TNS,
        'xmlns:m': MNS,
    })
    header = create_element('s:Header')
    requestserverversion = create_element('t:RequestServerVersion', Version=version)
    header.append(requestserverversion)
    if account and account.access_type == IMPERSONATION:
        exchangeimpersonation = create_element('t:ExchangeImpersonation')
        connectingsid = create_element('t:ConnectingSID')
        add_xml_child(connectingsid, 't:PrimarySmtpAddress', account.primary_smtp_address)
        exchangeimpersonation.append(connectingsid)
        header.append(exchangeimpersonation)
    if ewstimezone:
        timezonecontext = create_element('t:TimeZoneContext')
        timezonedefinition = create_element('t:TimeZoneDefinition', Id=ewstimezone.ms_id)
        timezonecontext.append(timezonedefinition)
        header.append(timezonecontext)
    envelope.append(header)
    body = create_element('s:Body')
    body.append(content)
    envelope.append(body)
    return ('<?xml version="1.0" encoding="%s"?>' % encoding).encode(encoding) + tostring(envelope, encoding=encoding)


def get_auth_instance(credentials, auth_type):
    """
    Returns an *Auth instance suitable for the requests package
    """
    try:
        model = AUTH_TYPE_MAP[auth_type]
    except KeyError as e:
        raise_from(ValueError("Authentication type '%s' not supported" % auth_type), e)
    else:
        if model is None:
            return None
        username = credentials.username
        if auth_type == NTLM and credentials.type == credentials.EMAIL:
            username = '\\' + username
        return model(username=username, password=credentials.password)


def get_auth_type(auth):
    try:
        return AUTH_CLASS_MAP[auth.__class__]
    except KeyError as e:
        raise_from(ValueError("Authentication model '%s' not supported" % auth.__class__), e)


def get_autodiscover_authtype(service_endpoint, data, timeout, verify):
    # First issue a HEAD request to look for a location header. This is the autodiscover HTTP redirect method. If there
    # was no redirect, continue trying a POST request with a valid payload.
    log.debug('Getting autodiscover auth type for %s %s', service_endpoint, timeout)
    headers = {'Content-Type': 'text/xml; charset=utf-8'}
    with requests.sessions.Session() as s:
        r = s.head(url=service_endpoint, headers=headers, timeout=timeout, allow_redirects=False, verify=verify)
        if r.status_code == 302:
            try:
                redirect_url, redirect_server, redirect_has_ssl = get_redirect_url(r, require_relative=True)
                log.debug('Autodiscover HTTP redirect to %s', redirect_url)
            except RelativeRedirect as e:
                # We were redirected to a different domain or sheme. Raise RedirectError so higher-level code can
                # try again on this new domain or scheme.
                raise RedirectError(url=e.value)
            # Some MS servers are masters of messing up HTTP, issuing 302 to an error page with zero content.
            # Give this URL a chance with a POST request.
        r = s.post(url=service_endpoint, headers=headers, data=data, timeout=timeout, allow_redirects=False,
                   verify=verify)
    return _get_auth_method_from_response(response=r)


def get_docs_authtype(docs_url, verify):
    # Get auth type by tasting headers from the server. Don't do HEAD requests. It's too error prone.
    log.debug('Getting docs auth type for %s', docs_url)
    headers = {'Content-Type': 'text/xml; charset=utf-8'}
    with requests.sessions.Session() as s:
        r = s.get(url=docs_url, headers=headers, allow_redirects=True, verify=verify)
    return _get_auth_method_from_response(response=r)


def get_service_authtype(service_endpoint, versions, verify):
    # Get auth type by tasting headers from the server. Only do post requests. HEAD is too error prone, and some servers
    # are set up to redirect to OWA on all requests except POST to /EWS/Exchange.asmx
    log.debug('Getting service auth type for %s', service_endpoint)
    headers = {'Content-Type': 'text/xml; charset=utf-8'}
    # We don't know the API version yet, but we need it to create a valid request because some Exchange servers only
    # respond when given a valid request. Try all known versions. Gross.
    with requests.sessions.Session() as s:
        for version in versions:
            data = dummy_xml(version=version)
            log.debug('Requesting %s from %s', data, service_endpoint)
            r = s.post(url=service_endpoint, headers=headers, data=data, allow_redirects=True, verify=verify)
            auth_method = _get_auth_method_from_response(response=r)
            if auth_method != UNKNOWN:
                return auth_method
            raise ValueError("Authentication type '%s' not supported" % auth_method)


def _get_auth_method_from_response(response):
    # First, get the auth method from headers. Then, test credentials. Don't handle redirects - burden is on caller.
    log.debug('Request headers: %s', response.request.headers)
    log.debug('Response headers: %s', response.headers)
    if response.status_code == 200:
        log.debug('No authentication needed')
        return NOAUTH
    if response.status_code == 302:
        # Some servers are set up to redirect to OWA on all requests except POST to EWS/Exchange.asmx
        try:
            redirect_url, redirect_server, redirect_has_ssl = get_redirect_url(response, allow_relative=False)
        except RelativeRedirect:
            raise TransportError('Circular redirect')
        raise RedirectError(url=redirect_url)
    if response.status_code != 401:
        raise TransportError('Unexpected response: %s %s' % (response.status_code, response.reason))

    # Get auth type from headers
    for key, val in response.headers.items():
        if key.lower() == 'www-authenticate':
            vals = _tokenize(val.lower())
            for v in vals:
                if v.startswith('realm'):
                    realm = v.split('=')[1].strip('"')
                    log.debug('realm: %s', realm)
            # Prefer most secure auth method if more than one is offered. See discussion at
            # http://docs.oracle.com/javase/7/docs/technotes/guides/net/http-auth.html
            if 'digest' in vals:
                log.debug('Auth type is %s', DIGEST)
                return DIGEST
            if 'ntlm' in vals:
                log.debug('Auth type is %s', NTLM)
                return NTLM
            if 'basic' in vals:
                log.debug('Auth type is %s', BASIC)
                return BASIC
    raise UnauthorizedError('Got a 401, but no compatible auth type was reported by server')


def _tokenize(val):
    # Splits cookie auth values
    tokens = []
    token = ''
    quote = False
    for c in val:
        if c in (' ', ',') and not quote:
            if token not in ('', ','):
                tokens.append(token)
            token = ''
            continue
        elif c == '"':
            token += c
            if quote:
                tokens.append(token)
                token = ''
            quote = not quote
            continue
        token += c
    if token:
        tokens.append(token)
    return tokens


def dummy_xml(version):
    # Used as a minimal, valid EWS request to force Exchange into accepting the request and returning EWS XML
    # containing server version info.
    from .services import ResolveNames  # Avoid circular import
    return ResolveNames(protocol=None).payload(version=version, account=None, unresolved_entries=['DUMMY'])
