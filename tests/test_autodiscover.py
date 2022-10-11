import getpass
import sys
from collections import namedtuple
from types import MethodType
from unittest.mock import Mock, patch

import dns
import requests_mock

from exchangelib.account import Account
from exchangelib.autodiscover import (
    AutodiscoverCache,
    AutodiscoverProtocol,
    Autodiscovery,
    autodiscover_cache,
    clear_cache,
    close_connections,
    discover,
)
from exchangelib.autodiscover.cache import shelve_filename
from exchangelib.autodiscover.discovery import SrvRecord, _select_srv_host
from exchangelib.autodiscover.properties import Account as ADAccount
from exchangelib.autodiscover.properties import Autodiscover, Error, ErrorResponse, Response
from exchangelib.configuration import Configuration
from exchangelib.credentials import DELEGATE, Credentials, OAuth2Credentials
from exchangelib.errors import AutoDiscoverCircularRedirect, AutoDiscoverFailed, ErrorNonExistentMailbox
from exchangelib.protocol import FailFast, FaultTolerance
from exchangelib.transport import NOAUTH, NTLM
from exchangelib.util import ParseError, get_domain
from exchangelib.version import EXCHANGE_2013, Version

from .common import EWSTest, get_random_hostname, get_random_string


class AutodiscoverTest(EWSTest):
    def setUp(self):
        if isinstance(self.account.protocol.credentials, OAuth2Credentials):
            self.skipTest("OAuth authentication does not work with POX autodiscover")

        super().setUp()

        # Enable retries, to make tests more robust
        Autodiscovery.INITIAL_RETRY_POLICY = FaultTolerance(max_wait=5)
        Autodiscovery.RETRY_WAIT = 5

        # Each test should start with a clean autodiscover cache
        clear_cache()

        # Some mocking helpers
        self.domain = get_domain(self.account.primary_smtp_address)
        self.dummy_ad_endpoint = f"https://{self.domain}/Autodiscover/Autodiscover.xml"
        self.dummy_ews_endpoint = "https://expr.example.com/EWS/Exchange.asmx"
        self.dummy_ad_response = self.settings_xml(self.account.primary_smtp_address, self.dummy_ews_endpoint)

        self.pox_credentials = Credentials(username=self.settings["username"], password=self.settings["password"])

    @staticmethod
    def settings_xml(address, ews_url):
        return f"""\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>{address}</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <AccountType>email</AccountType>
            <Action>settings</Action>
            <Protocol>
                <Type>EXPR</Type>
                <EwsUrl>{ews_url}</EwsUrl>
            </Protocol>
        </Account>
    </Response>
</Autodiscover>""".encode()

    @staticmethod
    def redirect_address_xml(address):
        return f"""\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <Account>
            <Action>redirectAddr</Action>
            <RedirectAddr>{address}</RedirectAddr>
        </Account>
    </Response>
</Autodiscover>""".encode()

    @staticmethod
    def redirect_url_xml(ews_url):
        return f"""\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <Account>
            <Action>redirectUrl</Action>
            <RedirectURL>{ews_url}</RedirectURL>
        </Account>
    </Response>
</Autodiscover>""".encode()

    @staticmethod
    def get_test_protocol(**kwargs):
        return AutodiscoverProtocol(
            config=Configuration(
                service_endpoint=kwargs.get("service_endpoint", "https://example.com/Autodiscover/Autodiscover.xml"),
                credentials=kwargs.get("credentials", Credentials(get_random_string(8), get_random_string(8))),
                auth_type=kwargs.get("auth_type", NTLM),
                retry_policy=kwargs.get("retry_policy", FailFast()),
            )
        )

    @requests_mock.mock(real_http=False)  # Just make sure we don't issue any real HTTP here
    def test_magic(self, m):
        # Just test we don't fail when calling repr() and str(). Insert a dummy cache entry for testing
        p = self.get_test_protocol()
        autodiscover_cache[(p.config.server, p.config.credentials)] = p
        self.assertEqual(len(autodiscover_cache), 1)
        str(autodiscover_cache)
        repr(autodiscover_cache)
        for protocol in autodiscover_cache._protocols.values():
            str(protocol)
            repr(protocol)

    def test_response_properties(self):
        # Test edge cases of Response properties
        self.assertEqual(Response().redirect_address, None)
        self.assertEqual(Response(account=ADAccount(action=ADAccount.REDIRECT_URL)).redirect_address, None)
        self.assertEqual(Response().redirect_url, None)
        self.assertEqual(Response(account=ADAccount(action=ADAccount.SETTINGS)).redirect_url, None)
        self.assertEqual(Response().autodiscover_smtp_address, None)
        self.assertEqual(Response(account=ADAccount(action=ADAccount.REDIRECT_ADDR)).autodiscover_smtp_address, None)

    def test_autodiscover_empty_cache(self):
        # A live test of the entire process with an empty cache
        ad_response, protocol = discover(
            email=self.account.primary_smtp_address,
            credentials=self.pox_credentials,
            retry_policy=self.retry_policy,
        )
        self.assertEqual(ad_response.autodiscover_smtp_address, self.account.primary_smtp_address)
        self.assertEqual(ad_response.protocol.auth_type, self.account.protocol.auth_type)
        ad_response.protocol.auth_required = False
        self.assertEqual(ad_response.protocol.auth_type, NOAUTH)
        self.assertEqual(protocol.service_endpoint.lower(), self.account.protocol.service_endpoint.lower())
        self.assertEqual(protocol.version.build, self.account.protocol.version.build)

    def test_autodiscover_failure(self):
        # A live test that errors can be raised. Here, we try to autodiscover a non-existing email address
        if not self.settings.get("autodiscover_server"):
            self.skipTest(f"Skipping {self.__class__.__name__} - no 'autodiscover_server' entry in settings.yml")
        # Autodiscovery may take a long time. Prime the cache with the autodiscover server from the config file
        ad_endpoint = f"https://{self.settings['autodiscover_server']}/Autodiscover/Autodiscover.xml"
        cache_key = (self.domain, self.pox_credentials)
        autodiscover_cache[cache_key] = self.get_test_protocol(
            service_endpoint=ad_endpoint,
            credentials=self.pox_credentials,
            retry_policy=self.retry_policy,
        )
        with self.assertRaises(ErrorNonExistentMailbox):
            discover(
                email="XXX." + self.account.primary_smtp_address,
                credentials=self.pox_credentials,
                retry_policy=self.retry_policy,
            )

    def test_failed_login_via_account(self):
        with self.assertRaises(AutoDiscoverFailed):
            Account(
                primary_smtp_address=self.account.primary_smtp_address,
                access_type=DELEGATE,
                credentials=Credentials("john@example.com", "WRONG_PASSWORD"),
                autodiscover=True,
                locale="da_DK",
            )

    @requests_mock.mock(real_http=False)  # Just make sure we don't issue any real HTTP here
    def test_close_autodiscover_connections(self, m):
        # A live test that we can close TCP connections
        p = self.get_test_protocol()
        autodiscover_cache[(p.config.server, p.config.credentials)] = p
        self.assertEqual(len(autodiscover_cache), 1)
        close_connections()

    @requests_mock.mock(real_http=False)  # Just make sure we don't issue any real HTTP here
    def test_autodiscover_direct_gc(self, m):
        # Test garbage collection of the autodiscover cache
        p = self.get_test_protocol()
        autodiscover_cache[(p.config.server, p.config.credentials)] = p
        self.assertEqual(len(autodiscover_cache), 1)
        autodiscover_cache.__del__()  # Don't use del() because that would remove the global object

    @requests_mock.mock(real_http=False)
    def test_autodiscover_cache(self, m):
        # Mock the default endpoint that we test in step 1 of autodiscovery
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.dummy_ad_response)
        discovery = Autodiscovery(
            email=self.account.primary_smtp_address,
            credentials=self.pox_credentials,
        )
        # Not cached
        self.assertNotIn(discovery._cache_key, autodiscover_cache)
        discovery.discover()
        # Now it's cached
        self.assertIn(discovery._cache_key, autodiscover_cache)
        # Make sure the cache can be looked by value, not by id(). This is important for multi-threading/processing
        self.assertIn(
            (
                self.account.primary_smtp_address.split("@")[1],
                self.pox_credentials,
                True,
            ),
            autodiscover_cache,
        )
        # Poison the cache with a failing autodiscover endpoint. discover() must handle this and rebuild the cache
        p = self.get_test_protocol()
        autodiscover_cache[discovery._cache_key] = p
        m.post("https://example.com/Autodiscover/Autodiscover.xml", status_code=404)
        discovery.discover()
        self.assertIn(discovery._cache_key, autodiscover_cache)

        # Make sure that the cache is actually used on the second call to discover()
        _orig = discovery._step_1

        def _mock(slf, *args, **kwargs):
            raise NotImplementedError()

        discovery._step_1 = MethodType(_mock, discovery)
        discovery.discover()

        # Fake that another thread added the cache entry into the persistent storage but we don't have it in our
        # in-memory cache. The cache should work anyway.
        autodiscover_cache._protocols.clear()
        discovery.discover()
        discovery._step_1 = _orig

        # Make sure we can delete cache entries even though we don't have it in our in-memory cache
        autodiscover_cache._protocols.clear()
        del autodiscover_cache[discovery._cache_key]
        # This should also work if the cache does not contain the entry anymore
        del autodiscover_cache[discovery._cache_key]

    @requests_mock.mock(real_http=False)  # Just make sure we don't issue any real HTTP here
    def test_corrupt_autodiscover_cache(self, m):
        # Insert a fake Protocol instance into the cache and test that we can recover
        key = (2, "foo", 4)
        autodiscover_cache[key] = namedtuple("P", ["service_endpoint", "auth_type", "retry_policy"])(1, "bar", "baz")
        # Check that it exists. 'in' goes directly to the file
        self.assertTrue(key in autodiscover_cache)

        # Check that we can recover from a destroyed file
        file = autodiscover_cache._storage_file
        for f in file.parent.glob(f"{file.name}*"):
            f.write_text("XXX")
        self.assertFalse(key in autodiscover_cache)

        # Check that we can recover from an empty file
        for f in file.parent.glob(f"{file.name}*"):
            f.write_bytes(b"")
        self.assertFalse(key in autodiscover_cache)

    @requests_mock.mock(real_http=False)  # Just make sure we don't issue any real HTTP here
    def test_autodiscover_from_account(self, m):
        # Test that autodiscovery via account creation works
        # Mock the default endpoint that we test in step 1 of autodiscovery
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.dummy_ad_response)
        self.assertEqual(len(autodiscover_cache), 0)
        account = Account(
            primary_smtp_address=self.account.primary_smtp_address,
            config=Configuration(
                credentials=self.pox_credentials,
                retry_policy=self.retry_policy,
                version=Version(build=EXCHANGE_2013),
            ),
            autodiscover=True,
            locale="da_DK",
        )
        self.assertEqual(account.primary_smtp_address, self.account.primary_smtp_address)
        self.assertEqual(account.protocol.service_endpoint.lower(), self.dummy_ews_endpoint.lower())
        # Make sure cache is full
        self.assertEqual(len(autodiscover_cache), 1)
        self.assertTrue((account.domain, self.pox_credentials, True) in autodiscover_cache)
        # Test that autodiscover works with a full cache
        account = Account(
            primary_smtp_address=self.account.primary_smtp_address,
            config=Configuration(
                credentials=self.pox_credentials,
                retry_policy=self.retry_policy,
            ),
            autodiscover=True,
            locale="da_DK",
        )
        self.assertEqual(account.primary_smtp_address, self.account.primary_smtp_address)
        # Test cache manipulation
        key = (account.domain, self.pox_credentials, True)
        self.assertTrue(key in autodiscover_cache)
        del autodiscover_cache[key]
        self.assertFalse(key in autodiscover_cache)

    @requests_mock.mock(real_http=False)
    def test_autodiscover_redirect(self, m):
        # Test various aspects of autodiscover redirection. Mock all HTTP responses because we can't force a live server
        # to send us into the correct code paths.
        # Mock the default endpoint that we test in step 1 of autodiscovery
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.dummy_ad_response)
        discovery = Autodiscovery(
            email=self.account.primary_smtp_address,
            credentials=self.pox_credentials,
        )
        discovery.discover()

        # Make sure we discover a different return address
        m.post(
            self.dummy_ad_endpoint,
            status_code=200,
            content=self.settings_xml("john@example.com", "https://expr.example.com/EWS/Exchange.asmx"),
        )
        ad_response, _ = discovery.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, "john@example.com")

        # Make sure we discover an address redirect to the same domain. We have to mock the same URL with two different
        # responses. We do that with a response list.
        m.post(
            self.dummy_ad_endpoint,
            [
                dict(status_code=200, content=self.redirect_address_xml(f"redirect_me@{self.domain}")),
                dict(
                    status_code=200,
                    content=self.settings_xml(
                        f"redirected@{self.domain}", f"https://redirected.{self.domain}/EWS/Exchange.asmx"
                    ),
                ),
            ],
        )
        ad_response, _ = discovery.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, f"redirected@{self.domain}")
        self.assertEqual(ad_response.protocol.ews_url, f"https://redirected.{self.domain}/EWS/Exchange.asmx")

        # Test that we catch circular redirects on the same domain with a primed cache. Just mock the endpoint to
        # return the same redirect response on every request.
        self.assertEqual(len(autodiscover_cache), 1)
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.redirect_address_xml(f"foo@{self.domain}"))
        self.assertEqual(len(autodiscover_cache), 1)
        with self.assertRaises(AutoDiscoverCircularRedirect):
            discovery.discover()

        # Test that we also catch circular redirects when cache is empty
        clear_cache()
        self.assertEqual(len(autodiscover_cache), 0)
        with self.assertRaises(AutoDiscoverCircularRedirect):
            discovery.discover()

        # Test that we can handle being asked to redirect to an address on a different domain
        # Don't use example.com to redirect - it does not resolve or answer on all ISPs
        ews_hostname = "httpbin.org"
        redirect_email = f"john@redirected.{ews_hostname}"
        ews_url = f"https://{ews_hostname}/EWS/Exchange.asmx"
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.redirect_address_xml(f"john@{ews_hostname}"))
        m.post(
            f"https://{ews_hostname}/Autodiscover/Autodiscover.xml",
            status_code=200,
            content=self.settings_xml(redirect_email, ews_url),
        )
        ad_response, _ = discovery.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, redirect_email)
        self.assertEqual(ad_response.protocol.ews_url, ews_url)

        # Test redirect via HTTP 301
        clear_cache()
        redirect_url = f"https://{ews_hostname}/OtherPath/Autodiscover.xml"
        redirect_email = f"john@otherpath.{ews_hostname}"
        ews_url = f"https://xxx.{ews_hostname}/EWS/Exchange.asmx"
        discovery.email = self.account.primary_smtp_address
        m.post(self.dummy_ad_endpoint, status_code=301, headers=dict(location=redirect_url))
        m.post(redirect_url, status_code=200, content=self.settings_xml(redirect_email, ews_url))
        m.head(redirect_url, status_code=200)
        ad_response, _ = discovery.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, redirect_email)
        self.assertEqual(ad_response.protocol.ews_url, ews_url)

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_2_5(self, m):
        # Test steps 1 -> 2 -> 5
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        ews_url = f"https://xxx.{self.domain}/EWS/Exchange.asmx"
        email = f"xxxd@{self.domain}"
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(
            f"https://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml",
            status_code=200,
            content=self.settings_xml(email, ews_url),
        )
        ad_response, _ = d.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, email)
        self.assertEqual(ad_response.protocol.ews_url, ews_url)

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_2_3_invalid301_4(self, m):
        # Test steps 1 -> 2 -> 3 -> invalid 301 URL -> 4
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=501)
        m.get(
            f"http://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml",
            status_code=301,
            headers=dict(location="XXX"),
        )

        with self.assertRaises(AutoDiscoverFailed):
            # Fails in step 4 with invalid SRV entry
            ad_response, _ = d.discover()

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_2_3_no301_4(self, m):
        # Test steps 1 -> 2 -> 3 -> no 301 response -> 4
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=501)
        m.get(f"http://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=200)

        with self.assertRaises(AutoDiscoverFailed):
            # Fails in step 4 with invalid SRV entry
            ad_response, _ = d.discover()

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_2_3_4_valid_srv_invalid_response(self, m):
        # Test steps 1 -> 2 -> 3 -> 4 -> invalid response from SRV URL
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        redirect_srv = "httpbin.org"
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=501)
        m.get(f"http://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=200)
        m.head(f"https://{redirect_srv}/Autodiscover/Autodiscover.xml", status_code=501)
        m.post(f"https://{redirect_srv}/Autodiscover/Autodiscover.xml", status_code=501)

        tmp = d._get_srv_records
        d._get_srv_records = Mock(return_value=[SrvRecord(1, 1, 443, redirect_srv)])
        try:
            with self.assertRaises(AutoDiscoverFailed):
                # Fails in step 4 with invalid response
                ad_response, _ = d.discover()
        finally:
            d._get_srv_records = tmp

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_2_3_4_valid_srv_valid_response(self, m):
        # Test steps 1 -> 2 -> 3 -> 4 -> 5
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        redirect_srv = "httpbin.org"
        ews_url = f"https://{redirect_srv}/EWS/Exchange.asmx"
        redirect_email = f"john@redirected.{redirect_srv}"
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=501)
        m.get(f"http://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=200)
        m.head(f"https://{redirect_srv}/Autodiscover/Autodiscover.xml", status_code=200)
        m.post(
            f"https://{redirect_srv}/Autodiscover/Autodiscover.xml",
            status_code=200,
            content=self.settings_xml(redirect_email, ews_url),
        )

        tmp = d._get_srv_records
        d._get_srv_records = Mock(return_value=[SrvRecord(1, 1, 443, redirect_srv)])
        try:
            ad_response, _ = d.discover()
            self.assertEqual(ad_response.autodiscover_smtp_address, redirect_email)
            self.assertEqual(ad_response.protocol.ews_url, ews_url)
        finally:
            d._get_srv_records = tmp

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_2_3_4_invalid_srv(self, m):
        # Test steps 1 -> 2 -> 3 -> 4 -> invalid SRV URL
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=501)
        m.get(f"http://autodiscover.{self.domain}/Autodiscover/Autodiscover.xml", status_code=200)

        tmp = d._get_srv_records
        d._get_srv_records = Mock(return_value=[SrvRecord(1, 1, 443, get_random_hostname())])
        try:
            with self.assertRaises(AutoDiscoverFailed):
                # Fails in step 4 with invalid response
                ad_response, _ = d.discover()
        finally:
            d._get_srv_records = tmp

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_5_invalid_redirect_url(self, m):
        # Test steps 1 -> -> 5 -> Invalid redirect URL
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        m.post(
            self.dummy_ad_endpoint,
            status_code=200,
            content=self.redirect_url_xml(f"https://{get_random_hostname()}/EWS/Exchange.asmx"),
        )

        with self.assertRaises(AutoDiscoverFailed):
            # Fails in step 5 with invalid redirect URL
            ad_response, _ = d.discover()

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_5_valid_redirect_url_invalid_response(self, m):
        # Test steps 1 -> -> 5 -> Invalid response from redirect URL
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        redirect_url = "https://httpbin.org/Autodiscover/Autodiscover.xml"
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.redirect_url_xml(redirect_url))
        m.head(redirect_url, status_code=501)
        m.post(redirect_url, status_code=501)

        with self.assertRaises(AutoDiscoverFailed):
            # Fails in step 5 with invalid response
            ad_response, _ = d.discover()

    @requests_mock.mock(real_http=False)
    def test_autodiscover_path_1_5_valid_redirect_url_valid_response(self, m):
        # Test steps 1 -> -> 5 -> Valid response from redirect URL -> 5
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.pox_credentials)
        redirect_hostname = "httpbin.org"
        redirect_url = f"https://{redirect_hostname}/Autodiscover/Autodiscover.xml"
        ews_url = f"https://{redirect_hostname}/EWS/Exchange.asmx"
        email = f"john@redirected.{redirect_hostname}"
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.redirect_url_xml(redirect_url))
        m.head(redirect_url, status_code=200)
        m.post(redirect_url, status_code=200, content=self.settings_xml(email, ews_url))

        ad_response, _ = d.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, email)
        self.assertEqual(ad_response.protocol.ews_url, ews_url)

    def test_get_srv_records(self):
        ad = Autodiscovery("foo@example.com")
        # Unknown domain
        self.assertEqual(ad._get_srv_records("example.XXXXX"), [])
        # No SRV record
        self.assertEqual(ad._get_srv_records("example.com"), [])
        # Finding a real server that has a correct SRV record is not easy. Mock it
        _orig = dns.resolver.Resolver

        class _Mock1:
            @staticmethod
            def resolve(*args, **kwargs):
                class A:
                    @staticmethod
                    def to_text():
                        # Return a valid record
                        return "1 2 3 example.com."

                return [A()]

        dns.resolver.Resolver = _Mock1
        del ad.resolver
        # Test a valid record
        self.assertEqual(
            ad._get_srv_records("example.com."), [SrvRecord(priority=1, weight=2, port=3, srv="example.com")]
        )

        class _Mock2:
            @staticmethod
            def resolve(*args, **kwargs):
                class A:
                    @staticmethod
                    def to_text():
                        # Return malformed data
                        return "XXXXXXX"

                return [A()]

        dns.resolver.Resolver = _Mock2
        del ad.resolver
        # Test an invalid record
        self.assertEqual(ad._get_srv_records("example.com"), [])
        dns.resolver.Resolver = _orig
        del ad.resolver

    def test_select_srv_host(self):
        with self.assertRaises(ValueError):
            # Empty list
            _select_srv_host([])
        with self.assertRaises(ValueError):
            # No records with TLS port
            _select_srv_host([SrvRecord(priority=1, weight=2, port=3, srv="example.com")])
        # One record
        self.assertEqual(
            _select_srv_host([SrvRecord(priority=1, weight=2, port=443, srv="example.com")]), "example.com"
        )
        # Highest priority record
        self.assertEqual(
            _select_srv_host(
                [
                    SrvRecord(priority=10, weight=2, port=443, srv="10.example.com"),
                    SrvRecord(priority=1, weight=2, port=443, srv="1.example.com"),
                ]
            ),
            "10.example.com",
        )
        # Highest priority record no matter how it's sorted
        self.assertEqual(
            _select_srv_host(
                [
                    SrvRecord(priority=1, weight=2, port=443, srv="1.example.com"),
                    SrvRecord(priority=10, weight=2, port=443, srv="10.example.com"),
                ]
            ),
            "10.example.com",
        )

    def test_parse_response(self):
        # Test parsing of various XML responses
        with self.assertRaises(ParseError) as e:
            Autodiscover.from_bytes(b"XXX")  # Invalid response
        self.assertEqual(e.exception.args[0], "Response is not XML: b'XXX'")

        xml = b"""<?xml version="1.0" encoding="utf-8"?><foo>bar</foo>"""
        with self.assertRaises(ParseError) as e:
            Autodiscover.from_bytes(xml)  # Invalid XML response
        self.assertEqual(
            e.exception.args[0],
            'Unknown root element in XML: b\'<?xml version="1.0" encoding="utf-8"?><foo>bar</foo>\'',
        )

        # Redirect to different email address
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <Action>redirectAddr</Action>
            <RedirectAddr>foo@example.com</RedirectAddr>
        </Account>
    </Response>
</Autodiscover>"""
        self.assertEqual(Autodiscover.from_bytes(xml).response.redirect_address, "foo@example.com")

        # Redirect to different URL
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <Action>redirectUrl</Action>
            <RedirectURL>https://example.com/foo.asmx</RedirectURL>
        </Account>
    </Response>
</Autodiscover>"""
        self.assertEqual(Autodiscover.from_bytes(xml).response.redirect_url, "https://example.com/foo.asmx")

        # Select EXPR if it's there, and there are multiple available
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <AccountType>email</AccountType>
            <Action>settings</Action>
            <Protocol>
                <Type>EXCH</Type>
                <EwsUrl>https://exch.example.com/EWS/Exchange.asmx</EwsUrl>
            </Protocol>
            <Protocol>
                <Type>EXPR</Type>
                <EwsUrl>https://expr.example.com/EWS/Exchange.asmx</EwsUrl>
            </Protocol>
        </Account>
    </Response>
</Autodiscover>"""
        self.assertEqual(
            Autodiscover.from_bytes(xml).response.protocol.ews_url, "https://expr.example.com/EWS/Exchange.asmx"
        )

        # Select EXPR if EXPR is unavailable
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <AccountType>email</AccountType>
            <Action>settings</Action>
            <Protocol>
                <Type>EXCH</Type>
                <EwsUrl>https://exch.example.com/EWS/Exchange.asmx</EwsUrl>
            </Protocol>
        </Account>
    </Response>
</Autodiscover>"""
        self.assertEqual(
            Autodiscover.from_bytes(xml).response.protocol.ews_url, "https://exch.example.com/EWS/Exchange.asmx"
        )

        # Fail if neither EXPR nor EXPR are unavailable
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <AccountType>email</AccountType>
            <Action>settings</Action>
            <Protocol>
                <Type>XXX</Type>
                <EwsUrl>https://xxx.example.com/EWS/Exchange.asmx</EwsUrl>
            </Protocol>
        </Account>
    </Response>
</Autodiscover>"""
        with self.assertRaises(ValueError):
            _ = Autodiscover.from_bytes(xml).response.protocol.ews_url

    def test_raise_errors(self):
        with self.assertRaises(AutoDiscoverFailed) as e:
            Autodiscover().raise_errors()
        self.assertEqual(e.exception.args[0], "Unknown autodiscover error response: None")
        with self.assertRaises(AutoDiscoverFailed) as e:
            Autodiscover(error_response=ErrorResponse(error=Error(code="YYY", message="XXX"))).raise_errors()
        self.assertEqual(e.exception.args[0], "Unknown error YYY: XXX")
        with self.assertRaises(ErrorNonExistentMailbox) as e:
            Autodiscover(
                error_response=ErrorResponse(error=Error(message="The e-mail address cannot be found."))
            ).raise_errors()
        self.assertEqual(e.exception.args[0], "The SMTP address has no mailbox associated with it")

    def test_del_on_error(self):
        # Test that __del__ can handle exceptions on close()
        tmp = AutodiscoverCache.close
        cache = AutodiscoverCache()
        AutodiscoverCache.close = Mock(side_effect=Exception("XXX"))
        with self.assertRaises(Exception):
            cache.close()
        del cache
        AutodiscoverCache.close = tmp

    def test_shelve_filename(self):
        major, minor = sys.version_info[:2]
        self.assertEqual(shelve_filename(), f"exchangelib.2.cache.{getpass.getuser()}.py{major}{minor}")

    @patch("getpass.getuser", side_effect=KeyError())
    def test_shelve_filename_getuser_failure(self, m):
        # Test that shelve_filename can handle a failing getuser()
        major, minor = sys.version_info[:2]
        self.assertEqual(shelve_filename(), f"exchangelib.2.cache.exchangelib.py{major}{minor}")

    @requests_mock.mock(real_http=False)
    def test_redirect_url_is_valid(self, m):
        # This method is private but hard to get to otherwise
        a = Autodiscovery("john@example.com")

        # Already visited
        a._urls_visited.append("https://example.com")
        self.assertFalse(a._redirect_url_is_valid("https://example.com"))
        a._urls_visited.clear()

        # Max redirects exceeded
        a._redirect_count = 10
        self.assertFalse(a._redirect_url_is_valid("https://example.com"))
        a._redirect_count = 0

        # Must be secure
        self.assertFalse(a._redirect_url_is_valid("http://example.com"))

        # Does not resolve with DNS
        url = f"https://{get_random_hostname()}"
        m.head(url, status_code=200)
        self.assertFalse(a._redirect_url_is_valid(url))

        # Bad response from URL on valid hostname
        m.head(self.account.protocol.config.service_endpoint, status_code=501)
        self.assertTrue(a._redirect_url_is_valid(self.account.protocol.config.service_endpoint))

        # OK response from URL on valid hostname
        m.head(self.account.protocol.config.service_endpoint, status_code=200)
        self.assertTrue(a._redirect_url_is_valid(self.account.protocol.config.service_endpoint))
