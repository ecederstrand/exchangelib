import logging
from urllib.parse import urlparse

import dns.name
import dns.resolver
from cached_property import threaded_cached_property

from ..configuration import Configuration
from ..errors import AutoDiscoverCircularRedirect, AutoDiscoverFailed, RedirectError, TransportError
from ..protocol import FailFast, Protocol
from ..transport import get_unauthenticated_autodiscover_response
from ..util import CONNECTION_ERRORS, get_domain, get_redirect_url
from .cache import autodiscover_cache
from .protocol import AutodiscoverProtocol

log = logging.getLogger(__name__)

DNS_LOOKUP_ERRORS = (
    dns.name.EmptyLabel,
    dns.resolver.LifetimeTimeout,
    dns.resolver.NXDOMAIN,
    dns.resolver.NoAnswer,
    dns.resolver.NoNameservers,
)


class SrvRecord:
    """A container for autodiscover-related SRV records in DNS."""

    def __init__(self, priority, weight, port, srv):
        self.priority = priority
        self.weight = weight
        self.port = port
        self.srv = srv

    def __hash__(self):
        return hash((self.priority, self.weight, self.port, self.srv))

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.__dict__)


def discover(email, credentials=None, auth_type=None, retry_policy=None):
    ad_response, protocol = Autodiscovery(email=email, credentials=credentials).discover()
    protocol.config.auth_typ = auth_type
    protocol.config.retry_policy = retry_policy
    return ad_response, protocol


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
    MAX_REDIRECTS = 10  # Maximum number of URL redirects before we give up
    DNS_RESOLVER_KWARGS = {}
    DNS_RESOLVER_ATTRS = {
        "timeout": AutodiscoverProtocol.TIMEOUT / 2.5,  # Timeout for query to a single nameserver
    }
    DNS_RESOLVER_LIFETIME = AutodiscoverProtocol.TIMEOUT  # Total timeout for a query in case of multiple nameservers
    URL_PATH = "autodiscover/autodiscover.svc"

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
                    ad = self._quick(protocol=ad_protocol)
                except AutoDiscoverFailed:
                    # Autodiscover no longer works with this domain. Clear cache and try again after releasing the lock
                    log.debug("AD request failure. Removing cache for key %s", cache_key)
                    del autodiscover_cache[cache_key]
                    ad = self._step_1(hostname=domain)
            else:
                # This will cache the result
                log.debug("Cache miss for key %s", cache_key)
                ad = self._step_1(hostname=domain)

        log.debug("Released autodiscover_cache_lock")
        if ad.redirect_address:
            log.debug("Got a redirect address: %s", ad.redirect_address)
            if ad.redirect_address.lower() in self._emails_visited:
                raise AutoDiscoverCircularRedirect("We were redirected to an email address we have already seen")

            # Start over, but with the new email address
            self.email = ad.redirect_address
            return self.discover()

        # We successfully received a response. Clear the cache of seen emails etc.
        self.clear()
        return self._build_response(ad_response=ad)

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
            ad_response.autodiscover_smtp_address = self.email

        protocol = Protocol(
            config=Configuration(
                service_endpoint=ad_response.ews_url,
                credentials=self.credentials,
                version=ad_response.version,
                # TODO: Detect EWS service auth type somehow
            )
        )
        return ad_response, protocol

    def _quick(self, protocol):
        try:
            user_response = protocol.get_user_settings(user=self.email)
        except TransportError as e:
            raise AutoDiscoverFailed(f"Response error: {e}")
        return self._step_5(ad=user_response)

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
        """Get response from server using the given HTTP method

        :param url:
        :return:
        """
        # We are connecting to untrusted servers here, so take necessary precautions.
        self._ensure_valid_hostname(url)

        protocol = AutodiscoverProtocol(
            config=Configuration(
                service_endpoint=url,
                retry_policy=self.INITIAL_RETRY_POLICY,
            )
        )
        return None, get_unauthenticated_autodiscover_response(protocol=protocol, method=method)

    def _attempt_response(self, url):
        """Return an (is_valid_response, response) tuple.

        :param url:
        :return:
        """
        self._urls_visited.append(url.lower())
        log.debug("Attempting to get a valid response from %s", url)

        try:
            self._ensure_valid_hostname(url)
        except TransportError:
            return False, None

        protocol = AutodiscoverProtocol(
            config=Configuration(
                service_endpoint=url,
                credentials=self.credentials,
                retry_policy=self.INITIAL_RETRY_POLICY,
            )
        )
        try:
            user_response = protocol.get_user_settings(user=self.email)
        except RedirectError as e:
            if self._redirect_url_is_valid(url=e.url):
                # The protocol does not specify this explicitly, but by looking at how testconnectivity.microsoft.com
                # works, it seems that we should follow this URL now and try to get a valid response.
                return self._attempt_response(url=e.url)
            log.debug("Invalid redirect URL: %s", e.url)
            return False, None
        except TransportError as e:
            log.debug("Failed to get a response: %s", e)
            return False, None
        except CONNECTION_ERRORS as e:
            log.debug("Failed to get a response: %s", e)
            return False, None

        # We got a valid response. Unless this is a URL redirect response, we cache the result
        if not user_response.redirect_url:
            cache_key = self._cache_key
            log.debug("Adding cache entry for key %s: %s", cache_key, protocol.service_endpoint)
            autodiscover_cache[cache_key] = protocol
        return True, user_response

    def _ensure_valid_hostname(self, url):
        hostname = urlparse(url).netloc
        log.debug("Checking if %s can be looked up in DNS", hostname)
        try:
            self.resolver.resolve(f"{hostname}.", "A", lifetime=self.DNS_RESOLVER_LIFETIME)
        except DNS_LOOKUP_ERRORS as e:
            log.debug("DNS A lookup failure: %s", e)
            # 'requests' is bad at reporting that a hostname cannot be resolved. Let's check this separately.
            # Don't retry on DNS errors. They will most likely be persistent.
            raise TransportError(f"{hostname!r} has no DNS entry")

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
        https://example.com/ and then does one of the following:
            * If the Autodiscover attempt succeeds, the client proceeds to step 5.
            * If the Autodiscover attempt fails, the client proceeds to step 2.

        :param hostname:
        :return:
        """
        url = f"https://{hostname}/{self.URL_PATH}"
        log.info("Step 1: Trying autodiscover on %r with email %r", url, self.email)
        is_valid_response, ad = self._attempt_response(url=url)
        if is_valid_response:
            return self._step_5(ad=ad)
        return self._step_2(hostname=hostname)

    def _step_2(self, hostname):
        """Perform step 2, where the client sends an Autodiscover request to
        https://autodiscover.example.com/ and then does one of the following:
            * If the Autodiscover attempt succeeds, the client proceeds to step 5.
            * If the Autodiscover attempt fails, the client proceeds to step 3.

        :param hostname:
        :return:
        """
        url = f"https://autodiscover.{hostname}/{self.URL_PATH}"
        log.info("Step 2: Trying autodiscover on %r with email %r", url, self.email)
        is_valid_response, ad = self._attempt_response(url=url)
        if is_valid_response:
            return self._step_5(ad=ad)
        return self._step_3(hostname=hostname)

    def _step_3(self, hostname):
        """Perform step 3, where the client sends an unauthenticated GET method request to
        http://autodiscover.example.com/ (Note that this is a non-HTTPS endpoint). The
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
        url = f"http://autodiscover.{hostname}/{self.URL_PATH}"
        log.info("Step 3: Trying autodiscover on %r with email %r", url, self.email)
        try:
            _, r = self._get_unauthenticated_response(url=url, method="get")
        except TransportError:
            pass
        else:
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
        redirect_url = f"https://{srv_host}/{self.URL_PATH}"
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
        # This is not explicit in the protocol, but let's raise any errors here
        ad.raise_errors()

        if ad.redirect_url:
            log.debug("Got a redirect URL: %s", ad.redirect_url)
            # We are diverging a bit from the protocol here. We will never get an HTTP 302 since earlier steps already
            # followed the redirects where possible. Instead, we handle redirect responses here.
            if self._redirect_url_is_valid(url=ad.redirect_url):
                is_valid_response, ad = self._attempt_response(url=ad.redirect_url)
                if is_valid_response:
                    return self._step_5(ad=ad)
                log.debug("Got invalid response")
                return self._step_6()
            log.debug("Invalid redirect URL")
            return self._step_6()
        # This could be an email redirect. Let outer layer handle this
        return ad

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
