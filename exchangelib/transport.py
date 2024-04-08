import logging
from contextlib import suppress

import requests.auth
import requests_ntlm
import requests_oauthlib

from .errors import RateLimitError, TransportError, UnauthorizedError
from .util import CONNECTION_ERRORS, TLS_ERRORS, _back_off_if_needed

log = logging.getLogger(__name__)

# Authentication method enums
NOAUTH = "no authentication"
NTLM = "NTLM"
BASIC = "basic"
DIGEST = "digest"
GSSAPI = "gssapi"
SSPI = "sspi"
OAUTH2 = "OAuth 2.0"
CBA = "CBA"  # Certificate Based Authentication

# The auth types that must be accompanied by a credentials object
CREDENTIALS_REQUIRED = (NTLM, BASIC, DIGEST, OAUTH2)

AUTH_TYPE_MAP = {
    NTLM: requests_ntlm.HttpNtlmAuth,
    BASIC: requests.auth.HTTPBasicAuth,
    DIGEST: requests.auth.HTTPDigestAuth,
    OAUTH2: requests_oauthlib.OAuth2,
    CBA: None,
    NOAUTH: None,
}
with suppress(ImportError):
    # Kerberos auth is optional
    import requests_gssapi

    AUTH_TYPE_MAP[GSSAPI] = requests_gssapi.HTTPSPNEGOAuth
with suppress(ImportError):
    # SSPI auth is optional
    import requests_negotiate_sspi

    AUTH_TYPE_MAP[SSPI] = requests_negotiate_sspi.HttpNegotiateAuth

DEFAULT_ENCODING = "utf-8"
DEFAULT_HEADERS = {"Content-Type": f"text/xml; charset={DEFAULT_ENCODING}", "Accept-Encoding": "gzip, deflate"}


def get_auth_instance(auth_type, **kwargs):
    """Return an *Auth instance suitable for the requests package.

    :param auth_type:
    :param kwargs:
    """
    model = AUTH_TYPE_MAP[auth_type]
    if model is None:
        return None
    if auth_type == GSSAPI:
        # Kerberos auth relies on credentials supplied via a ticket available externally to this library
        return model()
    if auth_type == SSPI:
        # SSPI auth does not require credentials, but can have it
        return model(**kwargs)
    return model(**kwargs)


def get_service_authtype(protocol):
    # Get auth type by tasting headers from the server. Only do POST requests. HEAD is too error-prone, and some servers
    # are set up to redirect to OWA on all requests except POST to /EWS/Exchange.asmx
    #
    # We don't know the API version yet, but we need it to create a valid request because some Exchange servers only
    # respond when given a valid request. Try all known versions. Gross.
    from .services import ConvertId

    service_endpoint = protocol.service_endpoint
    retry_policy = protocol.retry_policy
    wait = protocol.RETRY_WAIT
    for api_version in ConvertId.supported_api_versions():
        protocol.api_version_hint = api_version
        data = protocol.dummy_xml()
        log.debug("Requesting %s from %s", data, service_endpoint)
        while True:
            _back_off_if_needed(retry_policy.back_off_until)
            log.debug("Trying to get service auth type for %s", service_endpoint)
            with protocol.raw_session(service_endpoint) as s:
                try:
                    r = s.post(
                        url=service_endpoint,
                        data=data,
                        allow_redirects=False,
                        timeout=protocol.TIMEOUT,
                    )
                    r.close()  # Release memory
                    break
                except CONNECTION_ERRORS as e:
                    # Don't retry on TLS errors. They will most likely be persistent.
                    log.info("Connection error on URL %s.", service_endpoint)
                    if not retry_policy.fail_fast:
                        retry_policy.back_off(wait)
                        continue
                    raise TransportError(str(e)) from e
                finally:
                    wait *= 2
        if r.status_code not in (200, 401):
            log.debug("Unexpected response: %s %s", r.status_code, r.reason)
            continue
        try:
            auth_type = get_auth_method_from_response(response=r)
            log.debug("Auth type is %s", auth_type)
            return auth_type
        except UnauthorizedError:
            continue
    raise TransportError("Failed to get auth type from service")


def get_autodiscover_authtype(protocol):
    data = protocol.dummy_xml()
    headers = {"X-AnchorMailbox": "DUMMY@example.com"}  # Required in case of OAuth
    r = get_unauthenticated_autodiscover_response(protocol=protocol, method="post", headers=headers, data=data)
    try:
        auth_type = get_auth_method_from_response(response=r)
        log.debug("Auth type is %s", auth_type)
        return auth_type
    except UnauthorizedError:
        raise TransportError("Failed to get autodiscover auth type from service")


def get_unauthenticated_autodiscover_response(protocol, method, headers=None, data=None):
    service_endpoint = protocol.service_endpoint
    retry_policy = protocol.retry_policy
    wait = protocol.RETRY_WAIT
    while True:
        _back_off_if_needed(retry_policy.back_off_until)
        log.debug("Trying to get response from %s", service_endpoint)
        with protocol.raw_session(service_endpoint) as s:
            try:
                r = getattr(s, method)(
                    url=service_endpoint,
                    headers=headers,
                    data=data,
                    allow_redirects=False,
                    timeout=protocol.TIMEOUT,
                )
                r.close()  # Release memory
                break
            except TLS_ERRORS as e:
                # Don't retry on TLS errors. But wrap, so we can catch later and continue with the next endpoint.
                raise TransportError(str(e))
            except CONNECTION_ERRORS as e:
                log.debug("Connection error on URL %s: %s", service_endpoint, e)
                if not retry_policy.fail_fast:
                    try:
                        retry_policy.back_off(wait)
                        continue
                    except RateLimitError:
                        pass
                raise TransportError(str(e)) from e
            finally:
                wait *= 2
    return r


def get_auth_method_from_response(response):
    # First, get the auth method from headers. Then, test credentials. Don't handle redirects - burden is on caller.
    log.debug("Request headers: %s", response.request.headers)
    log.debug("Response headers: %s", response.headers)
    if response.status_code == 200:
        return NOAUTH
    # Get auth type from headers
    for key, val in response.headers.items():
        if key.lower() == "www-authenticate":
            # Requests will combine multiple HTTP headers into one in 'request.headers'
            vals = _tokenize(val.lower())
            for v in vals:
                if v.startswith("realm"):
                    realm = v.split("=")[1].strip('"')
                    log.debug("realm: %s", realm)
            # Prefer most secure auth method if more than one is offered. See discussion at
            # http://docs.oracle.com/javase/7/docs/technotes/guides/net/http-auth.html
            if "digest" in vals:
                return DIGEST
            if "ntlm" in vals:
                return NTLM
            if "basic" in vals:
                return BASIC
        elif key.lower() == "ms-diagnostics-public" and "Modern Auth" in val:
            return OAUTH2
    raise UnauthorizedError("No compatible auth type was reported by server")


def _tokenize(val):
    # Splits cookie auth values
    auth_methods = []
    auth_method = ""
    quote = False
    for c in val:
        if c in (" ", ",") and not quote:
            if auth_method not in ("", ","):
                auth_methods.append(auth_method)
            auth_method = ""
            continue
        if c == '"':
            auth_method += c
            if quote:
                auth_methods.append(auth_method)
                auth_method = ""
            quote = not quote
            continue
        auth_method += c
    if auth_method:
        auth_methods.append(auth_method)
    return auth_methods
