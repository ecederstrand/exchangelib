import logging
import time
from urllib.parse import urlparse

import dns.name
import dns.resolver
from cached_property import threaded_cached_property

from ..configuration import Configuration
from ..errors import AutoDiscoverCircularRedirect, AutoDiscoverFailed, RedirectError, TransportError, UnauthorizedError
from ..protocol import FailFast, Protocol
from ..transport import AUTH_TYPE_MAP, DEFAULT_HEADERS, GSSAPI, NOAUTH, get_auth_method_from_response
from ..util import (
    CONNECTION_ERRORS,
    TLS_ERRORS,
    DummyResponse,
    ParseError,
    _back_off_if_needed,
    get_domain,
    get_redirect_url,
    post_ratelimited,
)
from .cache import autodiscover_cache
from .properties import Autodiscover
from .protocol import AutodiscoverProtocol

log = logging.getLogger(__name__)

DNS_LOOKUP_ERRORS = (
    dns.name.EmptyLabel,
    dns.resolver.NXDOMAIN,
    dns.resolver.NoAnswer,
    dns.resolver.NoNameservers,
)


def discover(email, credentials=None, auth_type=None, retry_policy=None):
    ad_response, protocol = Autodiscovery(email=email, credentials=credentials).discover()
    protocol.config.auth_typ = auth_type
    protocol.config.retry_policy = retry_policy
    return ad_response, protocol


class SrvRecord:
    """A container for autodiscover-related SRV records in DNS."""

    def __init__(self, priority, weight, port, srv):
        self.priority = priority
        self.weight = weight
        self.port = port
        self.srv = srv

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.__dict__)


class Autodiscovery:
    """Autodiscover is a Microsoft protocol for automatically getting the endpoint of the Exchange server and other
    connection-related settings holding the email address using only the email address, and username and password of the
    user.

    For a description of the protocol implemented, see "Autodiscover for Exchange ActiveSync developers":

    https://docs.microsoft.com/en-us/previous-versions/office/developer/exchange-server-interoperability-guidance/hh352638%28v%3dexchg.140%29

    Descriptions of the steps from the article are provided in their respective methods in this class.

    For a description of how to handle autodiscover error messages, see:

    https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/handling-autodiscover-error-messages

    A tip from the article:
    The client can perform steps 1 through 4 in any order or in parallel to expedite the process, but it must wait for
    responses to finish at each step before proceeding. Given that many organizations prefer to use the URL in step 2 to
    set up the Autodiscover service, the client might try this step first.

    Another possibly newer resource which has not yet been attempted is "Outlook 2016 Implementation of Autodiscover":
    https://support.microsoft.com/en-us/help/3211279/outlook-2016-implementation-of-autodiscover

    WARNING: The autodiscover protocol is very complicated. If you have problems autodiscovering using this
    implementation, start by doing an official test at https://testconnectivity.microsoft.com
    """

    # When connecting to servers that may not be serving the correct endpoint, we should use a retry policy that does
    # not leave us hanging for a long time on each step in the protocol.
    INITIAL_RETRY_POLICY = FailFast()
    RETRY_WAIT = 10  # Seconds to wait before retry on connection errors
    MAX_REDIRECTS = 10  # Maximum number of URL redirects before we give up
    DNS_RESOLVER_KWARGS = {}
    DNS_RESOLVER_ATTRS = {
        "timeout": AutodiscoverProtocol.TIMEOUT / 2.5,  # Timeout for query to a single nameserver
    }
    DNS_RESOLVER_LIFETIME = AutodiscoverProtocol.TIMEOUT  # Total timeout for a query in case of multiple nameservers

    def __init__(self, email, credentials=None):
        """

        :param email: The email address to autodiscover
        :param credentials: Credentials with authorization to make autodiscover lookups for this Account
            (Default value = None)
        """
        self.email = email
        self.credentials = credentials
        self._urls_visited = []  # Collects HTTP and Autodiscover redirects
        self._redirect_count = 0
        self._emails_visited = []  # Collects Autodiscover email redirects

    def discover(self):
        self._emails_visited.append(self.email.lower())

        # Check the autodiscover cache to see if we already know the autodiscover service endpoint for this email
        # domain. Use a lock to guard against multiple threads competing to cache information.
        log.debug("Waiting for autodiscover_cache lock")
        with autodiscover_cache:
            log.debug("autodiscover_cache lock acquired")
            cache_key = self._cache_key
            domain = get_domain(self.email)
            if cache_key in autodiscover_cache:
                ad_protocol = autodiscover_cache[cache_key]
                log.debug("Cache hit for key %s: %s", cache_key, ad_protocol.service_endpoint)
                try:
                    ad_response = self._quick(protocol=ad_protocol)
                except AutoDiscoverFailed:
                    # Autodiscover no longer works with this domain. Clear cache and try again after releasing the lock
                    log.debug("AD request failure. Removing cache for key %s", cache_key)
                    del autodiscover_cache[cache_key]
                    ad_response = self._step_1(hostname=domain)
            else:
                # This will cache the result
                log.debug("Cache miss for key %s", cache_key)
                ad_response = self._step_1(hostname=domain)

        log.debug("Released autodiscover_cache_lock")
        if ad_response.redirect_address:
            log.debug("Got a redirect address: %s", ad_response.redirect_address)
            if ad_response.redirect_address.lower() in self._emails_visited:
                raise AutoDiscoverCircularRedirect("We were redirected to an email address we have already seen")

            # Start over, but with the new email address
            self.email = ad_response.redirect_address
            return self.discover()

        # We successfully received a response. Clear the cache of seen emails etc.
        self.clear()
        return self._build_response(ad_response=ad_response)

    def clear(self):
        # This resets cached variables
        self._urls_visited = []
        self._redirect_count = 0
        self._emails_visited = []

    @property
    def _cache_key(self):
        # We may be using multiple different credentials and changing our minds on TLS verification. This key
        # combination should be safe for caching.
        domain = get_domain(self.email)
        return domain, self.credentials

    @threaded_cached_property
    def resolver(self):
        resolver = dns.resolver.Resolver(**self.DNS_RESOLVER_KWARGS)
        for k, v in self.DNS_RESOLVER_ATTRS.items():
            setattr(resolver, k, v)
        return resolver

    def _build_response(self, ad_response):
        if not ad_response.autodiscover_smtp_address:
            # Autodiscover does not always return an email address. In that case, the requesting email should be used
            ad_response.user.autodiscover_smtp_address = self.email

        protocol = Protocol(
            config=Configuration(
                service_endpoint=ad_response.protocol.ews_url,
                credentials=self.credentials,
                version=ad_response.version,
                auth_type=ad_response.protocol.auth_type,
            )
        )
        return ad_response, protocol

    def _quick(self, protocol):
        try:
            r = self._get_authenticated_response(protocol=protocol)
        except TransportError as e:
            raise AutoDiscoverFailed(f"Response error: {e}")
        if r.status_code == 200:
            try:
                ad = Autodiscover.from_bytes(bytes_content=r.content)
            except ParseError as e:
                raise AutoDiscoverFailed(f"Invalid response: {e}")
            else:
                return self._step_5(ad=ad)
        raise AutoDiscoverFailed(f"Invalid response code: {r.status_code}")

    def _redirect_url_is_valid(self, url):
        """Three separate responses can be “Redirect responses”:
        * An HTTP status code (301, 302) with a new URL
        * An HTTP status code of 200, but with a payload XML containing a redirect to a different URL
        * An HTTP status code of 200, but with a payload XML containing a different SMTP address as the target address

        We only handle the HTTP 302 redirects here. We validate the URL received in the redirect response to ensure that
        it does not redirect to non-SSL endpoints or SSL endpoints with invalid certificates, and that the redirect is
        not circular. Finally, we should fail after 10 redirects.

        :param url:
        :return:
        """
        if url.lower() in self._urls_visited:
            log.warning("We have already tried this URL: %s", url)
            return False

        if self._redirect_count >= self.MAX_REDIRECTS:
            log.warning("We reached max redirects at URL: %s", url)
            return False

        # We require TLS endpoints
        if not url.startswith("https://"):
            log.debug("Invalid scheme for URL: %s", url)
            return False

        # Quick test that the endpoint responds and that TLS handshake is OK
        try:
            self._get_unauthenticated_response(url, method="head")
        except TransportError as e:
            log.debug("Response error on redirect URL %s: %s", url, e)
            return False

        self._redirect_count += 1
        return True

    def _get_unauthenticated_response(self, url, method="post"):
        """Get auth type by tasting headers from the server. Do POST requests be default. HEAD is too error prone, and
        some servers are set up to redirect to OWA on all requests except POST to the autodiscover endpoint.

        :param url:
        :param method:  (Default value = 'post')
        :return:
        """
        # We are connecting to untrusted servers here, so take necessary precautions.
        hostname = urlparse(url).netloc
        if not self._is_valid_hostname(hostname):
            # 'requests' is really bad at reporting that a hostname cannot be resolved. Let's check this separately.
            # Don't retry on DNS errors. They will most likely be persistent.
            raise TransportError(f"{hostname!r} has no DNS entry")

        kwargs = dict(
            url=url, headers=DEFAULT_HEADERS.copy(), allow_redirects=False, timeout=AutodiscoverProtocol.TIMEOUT
        )
        if method == "post":
            kwargs["data"] = Autodiscover.payload(email=self.email)
        retry = 0
        t_start = time.monotonic()
        while True:
            _back_off_if_needed(self.INITIAL_RETRY_POLICY.back_off_until)
            log.debug("Trying to get response from %s", url)
            with AutodiscoverProtocol.raw_session(url) as s:
                try:
                    r = getattr(s, method)(**kwargs)
                    r.close()  # Release memory
                    break
                except TLS_ERRORS as e:
                    # Don't retry on TLS errors. They will most likely be persistent.
                    raise TransportError(str(e))
                except CONNECTION_ERRORS as e:
                    r = DummyResponse(url=url, request_headers=kwargs["headers"])
                    total_wait = time.monotonic() - t_start
                    if self.INITIAL_RETRY_POLICY.may_retry_on_error(response=r, wait=total_wait):
                        log.debug("Connection error on URL %s (retry %s, error: %s). Cool down", url, retry, e)
                        # Don't respect the 'Retry-After' header. We don't know if this is a useful endpoint, and we
                        # want autodiscover to be reasonably fast.
                        self.INITIAL_RETRY_POLICY.back_off(self.RETRY_WAIT)
                        retry += 1
                        continue
                    log.debug("Connection error on URL %s: %s", url, e)
                    raise TransportError(str(e))
        try:
            auth_type = get_auth_method_from_response(response=r)
        except UnauthorizedError:
            # Failed to guess the auth type
            auth_type = NOAUTH
        if r.status_code in (301, 302) and "location" in r.headers:
            # Make the redirect URL absolute
            try:
                r.headers["location"] = get_redirect_url(r)
            except TransportError:
                del r.headers["location"]
        return auth_type, r

    def _get_authenticated_response(self, protocol):
        """Get a response by using the credentials provided. We guess the auth type along the way.

        :param protocol:
        :return:
        """
        # Redo the request with the correct auth
        data = Autodiscover.payload(email=self.email)
        headers = DEFAULT_HEADERS.copy()
        session = protocol.get_session()
        if GSSAPI in AUTH_TYPE_MAP and isinstance(session.auth, AUTH_TYPE_MAP[GSSAPI]):
            # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/pox-autodiscover-request-for-exchange
            headers["X-ClientCanHandle"] = "Negotiate"
        try:
            r, session = post_ratelimited(
                protocol=protocol,
                session=session,
                url=protocol.service_endpoint,
                headers=headers,
                data=data,
            )
            protocol.release_session(session)
        except UnauthorizedError as e:
            # It's entirely possible for the endpoint to ask for login. We should continue if login fails because this
            # isn't necessarily the right endpoint to use.
            raise TransportError(str(e))
        except RedirectError as e:
            r = DummyResponse(url=protocol.service_endpoint, headers={"location": e.url}, status_code=302)
        return r

    def _attempt_response(self, url):
        """Return an (is_valid_response, response) tuple.

        :param url:
        :return:
        """
        self._urls_visited.append(url.lower())
        log.debug("Attempting to get a valid response from %s", url)
        try:
            auth_type, r = self._get_unauthenticated_response(url=url)
            ad_protocol = AutodiscoverProtocol(
                config=Configuration(
                    service_endpoint=url,
                    credentials=self.credentials,
                    auth_type=auth_type,
                    retry_policy=self.INITIAL_RETRY_POLICY,
                )
            )
            if auth_type != NOAUTH:
                r = self._get_authenticated_response(protocol=ad_protocol)
        except TransportError as e:
            log.debug("Failed to get a response: %s", e)
            return False, None
        if r.status_code in (301, 302) and "location" in r.headers:
            redirect_url = get_redirect_url(r)
            if self._redirect_url_is_valid(url=redirect_url):
                # The protocol does not specify this explicitly, but by looking at how testconnectivity.microsoft.com
                # works, it seems that we should follow this URL now and try to get a valid response.
                return self._attempt_response(url=redirect_url)
        if r.status_code == 200:
            try:
                ad = Autodiscover.from_bytes(bytes_content=r.content)
            except ParseError as e:
                log.debug("Invalid response: %s", e)
            else:
                # We got a valid response. Unless this is a URL redirect response, we cache the result
                if ad.response is None or not ad.response.redirect_url:
                    cache_key = self._cache_key
                    log.debug("Adding cache entry for key %s: %s", cache_key, ad_protocol.service_endpoint)
                    autodiscover_cache[cache_key] = ad_protocol
                return True, ad
        return False, None

    def _is_valid_hostname(self, hostname):
        log.debug("Checking if %s can be looked up in DNS", hostname)
        try:
            self.resolver.resolve(f"{hostname}.", "A", lifetime=self.DNS_RESOLVER_LIFETIME)
        except DNS_LOOKUP_ERRORS as e:
            log.debug("DNS A lookup failure: %s", e)
            return False
        return True

    def _get_srv_records(self, hostname):
        """Send a DNS query for SRV entries for the hostname.

        An SRV entry that has been formatted for autodiscovery will have the following format:

            canonical name = mail.example.com.
            service = 8 100 443 webmail.example.com.

        The first three numbers in the service line are: priority, weight, port

        :param hostname:
        :return:
        """
        log.debug("Attempting to get SRV records for %s", hostname)
        records = []
        try:
            answers = self.resolver.resolve(f"{hostname}.", "SRV", lifetime=self.DNS_RESOLVER_LIFETIME)
        except DNS_LOOKUP_ERRORS as e:
            log.debug("DNS SRV lookup failure: %s", e)
            return records
        for rdata in answers:
            try:
                vals = rdata.to_text().strip().rstrip(".").split(" ")
                # Raise ValueError if the first three are not ints, and IndexError if there are less than 4 values
                priority, weight, port, srv = int(vals[0]), int(vals[1]), int(vals[2]), vals[3]
                record = SrvRecord(priority=priority, weight=weight, port=port, srv=srv)
                log.debug("Found SRV record %s ", record)
                records.append(record)
            except (ValueError, IndexError):
                log.debug("Incompatible SRV record for %s (%s)", hostname, rdata.to_text())
        return records

    def _step_1(self, hostname):
        """Perform step 1, where the client sends an Autodiscover request to
        https://example.com/autodiscover/autodiscover.xml and then does one of the following:
            * If the Autodiscover attempt succeeds, the client proceeds to step 5.
            * If the Autodiscover attempt fails, the client proceeds to step 2.

        :param hostname:
        :return:
        """
        url = f"https://{hostname}/Autodiscover/Autodiscover.xml"
        log.info("Step 1: Trying autodiscover on %r with email %r", url, self.email)
        is_valid_response, ad = self._attempt_response(url=url)
        if is_valid_response:
            return self._step_5(ad=ad)
        return self._step_2(hostname=hostname)

    def _step_2(self, hostname):
        """Perform step 2, where the client sends an Autodiscover request to
        https://autodiscover.example.com/autodiscover/autodiscover.xml and then does one of the following:
            * If the Autodiscover attempt succeeds, the client proceeds to step 5.
            * If the Autodiscover attempt fails, the client proceeds to step 3.

        :param hostname:
        :return:
        """
        url = f"https://autodiscover.{hostname}/Autodiscover/Autodiscover.xml"
        log.info("Step 2: Trying autodiscover on %r with email %r", url, self.email)
        is_valid_response, ad = self._attempt_response(url=url)
        if is_valid_response:
            return self._step_5(ad=ad)
        return self._step_3(hostname=hostname)

    def _step_3(self, hostname):
        """Perform step 3, where the client sends an unauth'ed GET method request to
        http://autodiscover.example.com/autodiscover/autodiscover.xml (Note that this is a non-HTTPS endpoint). The
        client then does one of the following:
            * If the GET request returns a 302 redirect response, it gets the redirection URL from the 'Location' HTTP
            header and validates it as described in the "Redirect responses" section. The client then does one of the
            following:
                * If the redirection URL is valid, the client tries the URL and then does one of the following:
                    * If the attempt succeeds, the client proceeds to step 5.
                    * If the attempt fails, the client proceeds to step 4.
                * If the redirection URL is not valid, the client proceeds to step 4.
            * If the GET request does not return a 302 redirect response, the client proceeds to step 4.

        :param hostname:
        :return:
        """
        url = f"http://autodiscover.{hostname}/Autodiscover/Autodiscover.xml"
        log.info("Step 3: Trying autodiscover on %r with email %r", url, self.email)
        try:
            _, r = self._get_unauthenticated_response(url=url, method="get")
        except TransportError:
            r = DummyResponse(url=url)
        if r.status_code in (301, 302) and "location" in r.headers:
            redirect_url = get_redirect_url(r)
            if self._redirect_url_is_valid(url=redirect_url):
                is_valid_response, ad = self._attempt_response(url=redirect_url)
                if is_valid_response:
                    return self._step_5(ad=ad)
                log.debug("Got invalid response")
                return self._step_4(hostname=hostname)
            log.debug("Got invalid redirect URL")
            return self._step_4(hostname=hostname)
        log.debug("Got no redirect URL")
        return self._step_4(hostname=hostname)

    def _step_4(self, hostname):
        """Perform step 4, where the client performs a Domain Name System (DNS) query for an SRV record for
        _autodiscover._tcp.example.com. The query might return multiple records. The client selects only records that
        point to an SSL endpoint and that have the highest priority and weight. One of the following actions then
        occurs:
            * If no such records are returned, the client proceeds to step 6.
            * If records are returned, the application randomly chooses a record in the list and validates the endpoint
              that it points to by following the process described in the "Redirect Response" section. The client then
              does one of the following:
                * If the redirection URL is valid, the client tries the URL and then does one of the following:
                    * If the attempt succeeds, the client proceeds to step 5.
                    * If the attempt fails, the client proceeds to step 6.
                * If the redirection URL is not valid, the client proceeds to step 6.

        :param hostname:
        :return:
        """
        dns_hostname = f"_autodiscover._tcp.{hostname}"
        log.info("Step 4: Trying autodiscover on %r with email %r", dns_hostname, self.email)
        srv_records = self._get_srv_records(dns_hostname)
        try:
            srv_host = _select_srv_host(srv_records)
        except ValueError:
            srv_host = None
        if not srv_host:
            return self._step_6()
        redirect_url = f"https://{srv_host}/Autodiscover/Autodiscover.xml"
        if self._redirect_url_is_valid(url=redirect_url):
            is_valid_response, ad = self._attempt_response(url=redirect_url)
            if is_valid_response:
                return self._step_5(ad=ad)
            log.debug("Got invalid response")
            return self._step_6()
        log.debug("Got invalid redirect URL")
        return self._step_6()

    def _step_5(self, ad):
        """Perform step 5. When a valid Autodiscover request succeeds, the following sequence occurs:
            * If the server responds with an HTTP 302 redirect, the client validates the redirection URL according to
              the process defined in the "Redirect responses" and then does one of the following:
                * If the redirection URL is valid, the client tries the URL and then does one of the following:
                    * If the attempt succeeds, the client repeats step 5 from the beginning.
                    * If the attempt fails, the client proceeds to step 6.
                * If the redirection URL is not valid, the client proceeds to step 6.
            * If the server responds with a valid Autodiscover response, the client does one of the following:
                * If the value of the Action element is "Redirect", the client gets the redirection email address from
                  the Redirect element and then returns to step 1, using this new email address.
                * If the value of the Action element is "Settings", the client has successfully received the requested
                  configuration settings for the specified user. The client does not need to proceed to step 6.

        :param ad:
        :return:
        """
        log.info("Step 5: Checking response")
        if ad.response is None:
            # This is not explicit in the protocol, but let's raise errors here
            ad.raise_errors()

        ad_response = ad.response
        if ad_response.redirect_url:
            log.debug("Got a redirect URL: %s", ad_response.redirect_url)
            # We are diverging a bit from the protocol here. We will never get an HTTP 302 since earlier steps already
            # followed the redirects where possible. Instead, we handle redirect responses here.
            if self._redirect_url_is_valid(url=ad_response.redirect_url):
                is_valid_response, ad = self._attempt_response(url=ad_response.redirect_url)
                if is_valid_response:
                    return self._step_5(ad=ad)
                log.debug("Got invalid response")
                return self._step_6()
            log.debug("Invalid redirect URL")
            return self._step_6()
        # This could be an email redirect. Let outer layer handle this
        return ad_response

    def _step_6(self):
        """Perform step 6. If the client cannot contact the Autodiscover service, the client should ask the user for
        the Exchange server name and use it to construct an Exchange EWS URL. The client should try to use this URL for
        future requests.
        """
        raise AutoDiscoverFailed(
            f"All steps in the autodiscover protocol failed for email {self.email}. If you think this is an error, "
            f"consider doing an official test at https://testconnectivity.microsoft.com"
        )


def _select_srv_host(srv_records):
    """Select the record with the highest priority, that also supports TLS.

    :param srv_records:
    :return:
    """
    best_record = None
    for srv_record in srv_records:
        if srv_record.port != 443:
            log.debug("Skipping SRV record %r (no TLS)", srv_record)
            continue
        # Assume port 443 will serve TLS. If not, autodiscover will probably also be broken for others.
        if best_record is None or best_record.priority < srv_record.priority:
            best_record = srv_record
    if not best_record:
        raise ValueError("No suitable records")
    return best_record.srv
