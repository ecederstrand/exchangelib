# coding=utf-8
from __future__ import unicode_literals

import logging

import requests.auth
import requests_ntlm
from requests_oauthlib import OAuth2

from .credentials import IMPERSONATION
from .errors import UnauthorizedError, TransportError, RedirectError, RelativeRedirect
from .util import create_element, add_xml_child, get_redirect_url, xml_to_str, ns_translation

log = logging.getLogger(__name__)

# Authentication method enums
NOAUTH = 'no authentication'
NTLM = 'NTLM'
BASIC = 'basic'
DIGEST = 'digest'
GSSAPI = 'gssapi'
OAUTH = 'OAuth 2.0'

AUTH_TYPE_MAP = {
    NTLM: requests_ntlm.HttpNtlmAuth,
    BASIC: requests.auth.HTTPBasicAuth,
    DIGEST: requests.auth.HTTPDigestAuth,
    OAUTH: OAuth2,
    NOAUTH: None,
}
try:
    import requests_kerberos
    AUTH_TYPE_MAP[GSSAPI] = requests_kerberos.HTTPKerberosAuth
except ImportError:
    # Kerberos auth is optional
    pass

DEFAULT_ENCODING = 'utf-8'
DEFAULT_HEADERS = {'Content-Type': 'text/xml; charset=%s' % DEFAULT_ENCODING, 'Accept-Encoding': 'gzip, deflate'}


def extra_headers(account):
    """
    Generate extra headers for impersonation requests. See
    https://blogs.msdn.microsoft.com/webdav_101/2015/05/11/best-practices-ews-authentication-and-access-issues/
    """
    if account and account.access_type == IMPERSONATION:
        return {'X-AnchorMailbox': account.primary_smtp_address}
    return None


def wrap(content, version, account=None):
    """
    Generate the necessary boilerplate XML for a raw SOAP request. The XML is specific to the server version.
    ExchangeImpersonation allows to act as the user we want to impersonate.
    """
    envelope = create_element('s:Envelope', nsmap=ns_translation)
    header = create_element('s:Header')
    requestserverversion = create_element('t:RequestServerVersion', Version=version)
    header.append(requestserverversion)
    if account:
        if account.access_type == IMPERSONATION:
            exchangeimpersonation = create_element('t:ExchangeImpersonation')
            connectingsid = create_element('t:ConnectingSID')
            add_xml_child(connectingsid, 't:PrimarySmtpAddress', account.primary_smtp_address)
            exchangeimpersonation.append(connectingsid)
            header.append(exchangeimpersonation)
        timezonecontext = create_element('t:TimeZoneContext')
        timezonedefinition = create_element('t:TimeZoneDefinition', Id=account.default_timezone.ms_id)
        timezonecontext.append(timezonedefinition)
        header.append(timezonecontext)
    envelope.append(header)
    body = create_element('s:Body')
    body.append(content)
    envelope.append(body)
    return xml_to_str(envelope, encoding=DEFAULT_ENCODING, xml_declaration=True)


def get_auth_instance(credentials, auth_type, client=None):
    """
    Returns an *Auth instance suitable for the requests package
    """
    model = AUTH_TYPE_MAP[auth_type]
    if model is None:
        return None
    username = credentials.username
    if auth_type == NTLM and credentials.type == credentials.EMAIL:
        username = '\\' + username
    elif auth_type == GSSAPI:
        # Kerberos auth relies on credentials supplied via a ticket available externally to this library
        return model()
    elif auth_type == OAUTH:
        return model(client=client)
    return model(username=username, password=credentials.password)


def get_autodiscover_authtype(service_endpoint, data):
    # First issue a HEAD request to look for a location header. This is the autodiscover HTTP redirect method. If there
    # was no redirect, continue trying a POST request with a valid payload.
    log.debug('Getting autodiscover auth type for %s', service_endpoint)
    from .autodiscover import AutodiscoverProtocol
    with AutodiscoverProtocol.raw_session() as s:
        r = s.head(url=service_endpoint, headers=DEFAULT_HEADERS.copy(), timeout=AutodiscoverProtocol.TIMEOUT,
                   allow_redirects=False)
        if r.status_code in (301, 302):
            try:
                redirect_url = get_redirect_url(r, require_relative=True)
                log.debug('Autodiscover HTTP redirect to %s', redirect_url)
            except RelativeRedirect as e:
                # We were redirected to a different domain or sheme. Raise RedirectError so higher-level code can
                # try again on this new domain or scheme.
                raise RedirectError(url=e.value)
            # Some MS servers are masters of messing up HTTP, issuing 302 to an error page with zero content.
            # Give this URL a chance with a POST request.
        r = s.post(url=service_endpoint, headers=DEFAULT_HEADERS.copy(), data=data,
                   timeout=AutodiscoverProtocol.TIMEOUT, allow_redirects=False)
    return _get_auth_method_from_response(response=r)


def get_docs_authtype(docs_url):
    # Get auth type by tasting headers from the server. Don't do HEAD requests. It's too error prone.
    log.debug('Getting docs auth type for %s', docs_url)
    from .protocol import BaseProtocol
    with BaseProtocol.raw_session() as s:
        r = s.get(url=docs_url, headers=DEFAULT_HEADERS.copy(), allow_redirects=True, timeout=BaseProtocol.TIMEOUT)
    return _get_auth_method_from_response(response=r)


def get_service_authtype(service_endpoint, versions, name):
    # Get auth type by tasting headers from the server. Only do POST requests. HEAD is too error prone, and some servers
    # are set up to redirect to OWA on all requests except POST to /EWS/Exchange.asmx
    log.debug('Getting service auth type for %s', service_endpoint)
    # We don't know the API version yet, but we need it to create a valid request because some Exchange servers only
    # respond when given a valid request. Try all known versions. Gross.
    from .protocol import BaseProtocol
    with BaseProtocol.raw_session() as s:
        for version in versions:
            data = dummy_xml(version=version, name=name)
            log.debug('Requesting %s from %s', data, service_endpoint)
            r = s.post(url=service_endpoint, headers=DEFAULT_HEADERS.copy(), data=data, allow_redirects=True,
                       timeout=BaseProtocol.TIMEOUT)
            try:
                auth_type = _get_auth_method_from_response(response=r)
                log.debug('Auth type is %s', auth_type)
                return auth_type
            except TransportError:
                continue
    raise TransportError('Failed to get auth type from service')


def _get_auth_method_from_response(response):
    # First, get the auth method from headers. Then, test credentials. Don't handle redirects - burden is on caller.
    log.debug('Request headers: %s', response.request.headers)
    log.debug('Response headers: %s', response.headers)
    if response.status_code == 200:
        return NOAUTH
    if response.status_code in (301, 302):
        # Some servers are set up to redirect to OWA on all requests except POST to EWS/Exchange.asmx
        try:
            redirect_url = get_redirect_url(response, allow_relative=False)
        except RelativeRedirect:
            raise TransportError('Redirect to same host when trying to get auth method')
        raise RedirectError(url=redirect_url)
    if response.status_code != 401:
        raise TransportError('Unexpected response: %s %s' % (response.status_code, response.reason))

    # Get auth type from headers
    for key, val in response.headers.items():
        if key.lower() == 'www-authenticate':
            # Requests will combine multiple HTTP headers into one in 'request.headers'
            vals = _tokenize(val.lower())
            for v in vals:
                if v.startswith('realm'):
                    realm = v.split('=')[1].strip('"')
                    log.debug('realm: %s', realm)
            # Prefer most secure auth method if more than one is offered. See discussion at
            # http://docs.oracle.com/javase/7/docs/technotes/guides/net/http-auth.html
            if 'digest' in vals:
                return DIGEST
            if 'ntlm' in vals:
                return NTLM
            if 'basic' in vals:
                return BASIC
    raise UnauthorizedError('Got a 401, but no compatible auth type was reported by server')


def _tokenize(val):
    # Splits cookie auth values
    auth_tokens = []
    auth_token = ''
    quote = False
    for c in val:
        if c in (' ', ',') and not quote:
            if auth_token not in ('', ','):
                auth_tokens.append(auth_token)
            auth_token = ''
            continue
        elif c == '"':
            auth_token += c
            if quote:
                auth_tokens.append(auth_token)
                auth_token = ''
            quote = not quote
            continue
        auth_token += c
    if auth_token:
        auth_tokens.append(auth_token)
    return auth_tokens


def dummy_xml(version, name):
    # Generate a minimal, valid EWS request
    from .services import ResolveNames  # Avoid circular import
    return wrap(content=ResolveNames(protocol=None).get_payload(
        unresolved_entries=[name],
        parent_folders=None,
        return_full_contact_data=False,
        search_scope=None,
        contact_data_shape=None,
    ), version=version)
