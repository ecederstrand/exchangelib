import getpass
import sys
from collections import namedtuple
from types import MethodType
from unittest.mock import Mock, patch

import dns
import requests_mock

from exchangelib.account import Account, Identity
from exchangelib.autodiscover import clear_cache, close_connections
from exchangelib.autodiscover.cache import AutodiscoverCache, autodiscover_cache, shelve_filename
from exchangelib.autodiscover.discovery import Autodiscovery, SrvRecord, _select_srv_host
from exchangelib.autodiscover.protocol import AutodiscoverProtocol
from exchangelib.configuration import Configuration
from exchangelib.credentials import DELEGATE, Credentials, OAuth2LegacyCredentials
from exchangelib.errors import (
    AutoDiscoverCircularRedirect,
    AutoDiscoverFailed,
    ErrorInternalServerError,
    ErrorNonExistentMailbox,
    TransportError,
)
from exchangelib.properties import UserResponse
from exchangelib.protocol import FailFast, FaultTolerance
from exchangelib.transport import NTLM
from exchangelib.util import get_domain
from exchangelib.version import EXCHANGE_2013, Version

from .common import EWSTest, get_random_email, get_random_hostname, get_random_string


class AutodiscoverTest(EWSTest):
    def setUp(self):
        super().setUp()

        # Enable retries, to make tests more robust
        Autodiscovery.INITIAL_RETRY_POLICY = FaultTolerance(max_wait=5)
        AutodiscoverProtocol.RETRY_WAIT = 5

        # Each test should start with a clean autodiscover cache
        clear_cache()

        # Some mocking helpers
        self.domain = get_domain(self.account.primary_smtp_address)
        self.dummy_ad_endpoint = f"https://{self.domain}/autodiscover/autodiscover.svc"
        self.dummy_ews_endpoint = "https://expr.example.com/EWS/Exchange.asmx"
        self.dummy_ad_response = self.settings_xml(self.account.primary_smtp_address, self.dummy_ews_endpoint)

    @staticmethod
    def settings_xml(address, ews_url):
        return f"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:a="http://www.w3.org/2005/08/addressing">
  <s:Header>
    <h:ServerVersionInfo
    xmlns:h="http://schemas.microsoft.com/exchange/2010/Autodiscover"
    xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
      <h:MajorVersion>15</h:MajorVersion>
      <h:MinorVersion>20</h:MinorVersion>
      <h:MajorBuildNumber>5834</h:MajorBuildNumber>
      <h:MinorBuildNumber>15</h:MinorBuildNumber>
      <h:Version>Exchange2015</h:Version>
    </h:ServerVersionInfo>
  </s:Header>
  <s:Body>
    <GetUserSettingsResponseMessage xmlns="http://schemas.microsoft.com/exchange/2010/Autodiscover">
      <Response>
        <ErrorCode>NoError</ErrorCode>
        <ErrorMessage/>
        <UserResponses>
          <UserResponse>
            <ErrorCode>NoError</ErrorCode>
            <ErrorMessage>No error.</ErrorMessage>
            <RedirectTarget i:nil="true"/>
            <UserSettingErrors/>
            <UserSettings>
              <UserSetting i:type="StringSetting">
                <Name>AutoDiscoverSMTPAddress</Name>
                <Value>{address}</Value>
              </UserSetting>
              <UserSetting i:type="StringSetting">
                <Name>ExternalEwsUrl</Name>
                <Value>{ews_url}</Value>
              </UserSetting>
            </UserSettings>
          </UserResponse>
        </UserResponses>
      </Response>
    </GetUserSettingsResponseMessage>
  </s:Body>
</s:Envelope>""".encode()

    @staticmethod
    def redirect_address_xml(address):
        return f"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:a="http://www.w3.org/2005/08/addressing">
  <s:Header>
    <h:ServerVersionInfo
    xmlns:h="http://schemas.microsoft.com/exchange/2010/Autodiscover"
    xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
      <h:MajorVersion>15</h:MajorVersion>
      <h:MinorVersion>20</h:MinorVersion>
      <h:MajorBuildNumber>5834</h:MajorBuildNumber>
      <h:MinorBuildNumber>15</h:MinorBuildNumber>
      <h:Version>Exchange2015</h:Version>
    </h:ServerVersionInfo>
  </s:Header>
  <s:Body>
    <GetUserSettingsResponseMessage xmlns="http://schemas.microsoft.com/exchange/2010/Autodiscover">
      <Response>
        <ErrorCode>NoError</ErrorCode>
        <ErrorMessage/>
        <UserResponses>
          <UserResponse>
            <ErrorCode>RedirectAddress</ErrorCode>
            <ErrorMessage>Redirection address.</ErrorMessage>
            <RedirectTarget>{address}</RedirectTarget>
            <UserSettingErrors />
            <UserSettings />
          </UserResponse>
        </UserResponses>
      </Response>
    </GetUserSettingsResponseMessage>
  </s:Body>
</s:Envelope>""".encode()

    @staticmethod
    def redirect_url_xml(autodiscover_url):
        return f"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:a="http://www.w3.org/2005/08/addressing">
  <s:Header>
    <h:ServerVersionInfo
    xmlns:h="http://schemas.microsoft.com/exchange/2010/Autodiscover"
    xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
      <h:MajorVersion>15</h:MajorVersion>
      <h:MinorVersion>20</h:MinorVersion>
      <h:MajorBuildNumber>5834</h:MajorBuildNumber>
      <h:MinorBuildNumber>15</h:MinorBuildNumber>
      <h:Version>Exchange2015</h:Version>
    </h:ServerVersionInfo>
  </s:Header>
  <s:Body>
    <GetUserSettingsResponseMessage xmlns="http://schemas.microsoft.com/exchange/2010/Autodiscover">
      <Response>
        <ErrorCode>NoError</ErrorCode>
        <ErrorMessage/>
        <UserResponses>
          <UserResponse>
            <ErrorCode>RedirectUrl</ErrorCode>
            <ErrorMessage>Redirection URL.</ErrorMessage>
            <RedirectTarget>{autodiscover_url}</RedirectTarget>
            <UserSettingErrors />
            <UserSettings />
          </UserResponse>
        </UserResponses>
      </Response>
    </GetUserSettingsResponseMessage>
  </s:Body>
</s:Envelope>""".encode()

    @staticmethod
    def get_test_protocol(**kwargs):
        return AutodiscoverProtocol(
            config=Configuration(
                service_endpoint=kwargs.get("service_endpoint", "https://example.com/autodiscover/autodiscover.svc"),
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

    def test_autodiscover_empty_cache(self):
        # A live test of the entire process with an empty cache
        ad_response, protocol = Autodiscovery(
            email=self.account.primary_smtp_address,
            credentials=self.account.protocol.credentials,
        ).discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, self.account.primary_smtp_address)
        self.assertEqual(protocol.service_endpoint.lower(), self.account.protocol.service_endpoint.lower())

    def test_autodiscover_failure(self):
        # A live test that errors can be raised. Here, we try to autodiscover a non-existing email address
        if not self.settings.get("autodiscover_server"):
            self.skipTest(f"Skipping {self.__class__.__name__} - no 'autodiscover_server' entry in settings.yml")
        # Autodiscovery may take a long time. Prime the cache with the autodiscover server from the config file
        ad_endpoint = f"https://{self.settings['autodiscover_server']}/autodiscover/autodiscover.svc"
        cache_key = (self.domain, self.account.protocol.credentials)
        autodiscover_cache[cache_key] = self.get_test_protocol(
            service_endpoint=ad_endpoint,
            credentials=self.account.protocol.credentials,
            retry_policy=self.retry_policy,
        )
        with self.assertRaises(ErrorNonExistentMailbox):
            Autodiscovery(
                email="XXX." + self.account.primary_smtp_address,
                credentials=self.account.protocol.credentials,
            ).discover()

    def test_failed_login_via_account(self):
        with self.assertRaises(AutoDiscoverFailed):
            Account(
                primary_smtp_address=self.account.primary_smtp_address,
                access_type=DELEGATE,
                credentials=Credentials("john@example.com", "WRONG_PASSWORD"),
                autodiscover=True,
                locale="da_DK",
            )

    def test_autodiscover_with_delegate(self):
        if not self.settings.get("client_id") or not self.settings.get("username"):
            self.skipTest("This test requires delegate OAuth setup")

        self.skipTest(
            "Currently throws this error: Due to a configuration change made by your administrator, or because "
            "you moved to a new location, you must use multi-factor authentication to access '0000-aaa-bbb-0000'"
        )

        credentials = OAuth2LegacyCredentials(
            client_id=self.settings["client_id"],
            client_secret=self.settings["client_secret"],
            tenant_id=self.settings["tenant_id"],
            username=self.settings["username"],
            password=self.settings["password"],
            identity=Identity(smtp_address=self.settings["account"]),
        )
        ad_response, protocol = Autodiscovery(
            email=self.account.primary_smtp_address,
            credentials=credentials,
        ).discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, self.account.primary_smtp_address)
        self.assertEqual(protocol.service_endpoint.lower(), self.account.protocol.service_endpoint.lower())

    @requests_mock.mock(real_http=True)
    def test_get_user_settings(self, m):
        # Create a real Autodiscovery protocol instance
        ad = Autodiscovery(
            email=self.account.primary_smtp_address,
            credentials=self.account.protocol.credentials,
        )
        ad.discover()
        p = autodiscover_cache[ad._cache_key]

        # Test invalid settings
        with self.assertRaises(ValueError) as e:
            p.get_user_settings(user=None, settings=["XXX"])
        self.assertIn(
            "Setting 'XXX' is invalid. Valid options are:",
            e.exception.args[0],
        )

        # Test invalid email
        invalid_email = get_random_email()
        r = p.get_user_settings(user=invalid_email)
        self.assertIsInstance(r, UserResponse)
        self.assertEqual(r.error_code, "InvalidUser")
        self.assertIn(f"Invalid user '{invalid_email}'", r.error_message)

        # Test error response
        xml = """\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:a="http://www.w3.org/2005/08/addressing">
  <s:Body>
    <GetUserSettingsResponseMessage xmlns="http://schemas.microsoft.com/exchange/2010/Autodiscover">
      <Response>
        <ErrorCode>InvalidSetting</ErrorCode>
        <ErrorMessage>An error message</ErrorMessage>
      </Response>
    </GetUserSettingsResponseMessage>
  </s:Body>
</s:Envelope>""".encode()
        m.post(p.service_endpoint, status_code=200, content=xml)
        with self.assertRaises(TransportError) as e:
            p.get_user_settings(user="foo")
        self.assertEqual(
            e.exception.args[0],
            "Unknown ResponseCode in ResponseMessage: InvalidSetting (MessageText: An error message, MessageXml: None)",
        )
        xml = """\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:a="http://www.w3.org/2005/08/addressing">
  <s:Body>
    <GetUserSettingsResponseMessage xmlns="http://schemas.microsoft.com/exchange/2010/Autodiscover">
      <Response>
        <ErrorCode>InternalServerError</ErrorCode>
        <ErrorMessage>An internal error</ErrorMessage>
      </Response>
    </GetUserSettingsResponseMessage>
  </s:Body>
</s:Envelope>""".encode()
        m.post(p.service_endpoint, status_code=200, content=xml)
        with self.assertRaises(ErrorInternalServerError) as e:
            p.get_user_settings(user="foo")
        self.assertEqual(e.exception.args[0], "An internal error")

    @requests_mock.mock(real_http=False)  # Just make sure we don't issue any real HTTP here
    def test_close_autodiscover_connections(self, m):
        # Test that we can close TCP connections
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
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_cache(self, m, *args):
        # Mock the default endpoint that we test in step 1 of autodiscovery
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.dummy_ad_response)
        discovery = Autodiscovery(
            email=self.account.primary_smtp_address,
            credentials=self.account.protocol.credentials,
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
                self.account.protocol.credentials,
                True,
            ),
            autodiscover_cache,
        )
        # Poison the cache with a failing autodiscover endpoint. discover() must handle this and rebuild the cache
        p = self.get_test_protocol()
        autodiscover_cache[discovery._cache_key] = p
        m.post("https://example.com/autodiscover/autodiscover.svc", status_code=404)
        discovery.discover()
        self.assertIn(discovery._cache_key, autodiscover_cache)

        # Make sure that the cache is actually used on the second call to discover()
        _orig = discovery._step_1

        def _mock(slf, *args, **kwargs):
            raise NotImplementedError()

        discovery._step_1 = MethodType(_mock, discovery)
        discovery.discover()

        # Fake that another thread added the cache entry into the persistent storage, but we don't have it in our
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
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_from_account(self, m, *args):
        # Test that autodiscovery via account creation works
        # Mock the default endpoint that we test in step 1 of autodiscovery
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.dummy_ad_response)
        self.assertEqual(len(autodiscover_cache), 0)
        account = Account(
            primary_smtp_address=self.account.primary_smtp_address,
            config=Configuration(
                credentials=self.account.protocol.credentials,
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
        self.assertTrue((account.domain, self.account.protocol.credentials, True) in autodiscover_cache)
        # Test that autodiscover works with a full cache
        account = Account(
            primary_smtp_address=self.account.primary_smtp_address,
            config=Configuration(
                credentials=self.account.protocol.credentials,
                retry_policy=self.retry_policy,
            ),
            autodiscover=True,
            locale="da_DK",
        )
        self.assertEqual(account.primary_smtp_address, self.account.primary_smtp_address)
        # Test cache manipulation
        key = (account.domain, self.account.protocol.credentials, True)
        self.assertTrue(key in autodiscover_cache)
        del autodiscover_cache[key]
        self.assertFalse(key in autodiscover_cache)

    @requests_mock.mock(real_http=False)
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_redirect(self, m, *args):
        # Test various aspects of autodiscover redirection. Mock all HTTP responses because we can't force a live server
        # to send us into the correct code paths.
        # Mock the default endpoint that we test in step 1 of autodiscovery
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.dummy_ad_response)
        discovery = Autodiscovery(
            email=self.account.primary_smtp_address,
            credentials=self.account.protocol.credentials,
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
        self.assertEqual(ad_response.ews_url, f"https://redirected.{self.domain}/EWS/Exchange.asmx")

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
            f"https://{ews_hostname}/autodiscover/autodiscover.svc",
            status_code=200,
            content=self.settings_xml(redirect_email, ews_url),
        )
        ad_response, _ = discovery.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, redirect_email)
        self.assertEqual(ad_response.ews_url, ews_url)

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
        self.assertEqual(ad_response.ews_url, ews_url)

    @requests_mock.mock(real_http=False)
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_2_5(self, m, *args):
        # Test steps 1 -> 2 -> 5
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        ews_url = f"https://xxx.{self.domain}/EWS/Exchange.asmx"
        email = f"xxxd@{self.domain}"
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(
            f"https://autodiscover.{self.domain}/autodiscover/autodiscover.svc",
            status_code=200,
            content=self.settings_xml(email, ews_url),
        )
        ad_response, _ = d.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, email)
        self.assertEqual(ad_response.ews_url, ews_url)

    @requests_mock.mock(real_http=False)
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_2_3_invalid301_4(self, m, *args):
        # Test steps 1 -> 2 -> 3 -> invalid 301 URL -> 4
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=501)
        m.get(
            f"http://autodiscover.{self.domain}/autodiscover/autodiscover.svc",
            status_code=301,
            headers=dict(location="XXX"),
        )

        with self.assertRaises(AutoDiscoverFailed):
            # Fails in step 4 with invalid SRV entry
            ad_response, _ = d.discover()

    @requests_mock.mock(real_http=False)
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_2_3_no301_4(self, m, *args):
        # Test steps 1 -> 2 -> 3 -> no 301 response -> 4
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=501)
        m.get(f"http://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=200)

        with self.assertRaises(AutoDiscoverFailed):
            # Fails in step 4 with invalid SRV entry
            ad_response, _ = d.discover()

    @requests_mock.mock(real_http=False)
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_2_3_4_valid_srv_invalid_response(self, m, *args):
        # Test steps 1 -> 2 -> 3 -> 4 -> invalid response from SRV URL
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        redirect_srv = "httpbin.org"
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=501)
        m.get(f"http://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=200)
        m.head(f"https://{redirect_srv}/autodiscover/autodiscover.svc", status_code=501)
        m.post(f"https://{redirect_srv}/autodiscover/autodiscover.svc", status_code=501)

        tmp = d._get_srv_records
        d._get_srv_records = Mock(return_value=[SrvRecord(1, 1, 443, redirect_srv)])
        try:
            with self.assertRaises(AutoDiscoverFailed):
                # Fails in step 4 with invalid response
                ad_response, _ = d.discover()
        finally:
            d._get_srv_records = tmp

    @requests_mock.mock(real_http=False)
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_2_3_4_valid_srv_valid_response(self, m, *args):
        # Test steps 1 -> 2 -> 3 -> 4 -> 5
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        redirect_srv = "httpbin.org"
        ews_url = f"https://{redirect_srv}/EWS/Exchange.asmx"
        redirect_email = f"john@redirected.{redirect_srv}"
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=501)
        m.get(f"http://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=200)
        m.head(f"https://{redirect_srv}/autodiscover/autodiscover.svc", status_code=200)
        m.post(
            f"https://{redirect_srv}/autodiscover/autodiscover.svc",
            status_code=200,
            content=self.settings_xml(redirect_email, ews_url),
        )

        tmp = d._get_srv_records
        d._get_srv_records = Mock(return_value=[SrvRecord(1, 1, 443, redirect_srv)])
        try:
            ad_response, _ = d.discover()
            self.assertEqual(ad_response.autodiscover_smtp_address, redirect_email)
            self.assertEqual(ad_response.ews_url, ews_url)
        finally:
            d._get_srv_records = tmp

    @requests_mock.mock(real_http=False)
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_2_3_4_invalid_srv(self, m, *args):
        # Test steps 1 -> 2 -> 3 -> 4 -> invalid SRV URL
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        m.post(self.dummy_ad_endpoint, status_code=501)
        m.post(f"https://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=501)
        m.get(f"http://autodiscover.{self.domain}/autodiscover/autodiscover.svc", status_code=200)

        tmp = d._get_srv_records
        d._get_srv_records = Mock(return_value=[SrvRecord(1, 1, 443, get_random_hostname())])
        try:
            with self.assertRaises(AutoDiscoverFailed):
                # Fails in step 4 with invalid response
                ad_response, _ = d.discover()
        finally:
            d._get_srv_records = tmp

    @requests_mock.mock(real_http=False)
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_5_invalid_redirect_url(self, m, *args):
        # Test steps 1 -> -> 5 -> Invalid redirect URL
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        m.post(
            self.dummy_ad_endpoint,
            status_code=200,
            content=self.redirect_url_xml(f"https://{get_random_hostname()}/autodiscover/autodiscover.svc"),
        )
        m.post(
            f"https://autodiscover.{self.domain}/autodiscover/autodiscover.svc",
            status_code=200,
            content=self.redirect_url_xml(f"https://{get_random_hostname()}/autodiscover/autodiscover.svc"),
        )

        with self.assertRaises(AutoDiscoverFailed):
            # Fails in step 5 with invalid redirect URL
            ad_response, _ = d.discover()

    @requests_mock.mock(real_http=False)
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_5_valid_redirect_url_invalid_response(self, m, *args):
        # Test steps 1 -> -> 5 -> Invalid response from redirect URL
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        redirect_url = "https://httpbin.org/autodiscover/autodiscover.svc"
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.redirect_url_xml(redirect_url))
        m.head(redirect_url, status_code=501)
        m.post(redirect_url, status_code=501)

        with self.assertRaises(AutoDiscoverFailed):
            # Fails in step 5 with invalid response
            ad_response, _ = d.discover()

    @requests_mock.mock(real_http=False)
    @patch.object(Autodiscovery, "_ensure_valid_hostname")
    @patch("requests_oauthlib.OAuth2Session.fetch_token", return_value=None)
    def test_autodiscover_path_1_5_valid_redirect_url_valid_response(self, m, *args):
        # Test steps 1 -> 5 -> Valid response from redirect URL -> 5
        clear_cache()
        d = Autodiscovery(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        redirect_hostname = "httpbin.org"
        redirect_url = f"https://{redirect_hostname}/autodiscover/autodiscover.svc"
        ews_url = f"https://{redirect_hostname}/EWS/Exchange.asmx"
        email = f"john@redirected.{redirect_hostname}"
        m.post(self.dummy_ad_endpoint, status_code=200, content=self.redirect_url_xml(redirect_url))
        m.head(redirect_url, status_code=200)
        m.post(redirect_url, status_code=200, content=self.settings_xml(email, ews_url))

        ad_response, _ = d.discover()
        self.assertEqual(ad_response.autodiscover_smtp_address, email)
        self.assertEqual(ad_response.ews_url, ews_url)

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

    def test_srv_magic(self):
        hash(SrvRecord(priority=1, weight=2, port=3, srv="example.com"))

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

    def test_raise_errors(self):
        UserResponse().raise_errors()
        with self.assertRaises(ErrorNonExistentMailbox) as e:
            UserResponse(error_code="InvalidUser", error_message="Foo").raise_errors()
        self.assertEqual(e.exception.args[0], "Foo")
        with self.assertRaises(AutoDiscoverFailed) as e:
            UserResponse(error_code="InvalidRequest", error_message="FOO").raise_errors()
        self.assertEqual(e.exception.args[0], "InvalidRequest: FOO")
        with self.assertRaises(AutoDiscoverFailed) as e:
            UserResponse(user_settings_errors={"FOO": "BAR"}).raise_errors()
        self.assertEqual(e.exception.args[0], "User settings errors: {'FOO': 'BAR'}")

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

    def test_protocol_default_values(self):
        # Test that retry_policy, auth_type and max_connections always get values regardless of how we create an Account
        _max_conn = self.account.protocol.config.max_connections
        try:
            self.account.protocol.config.max_connections = 3
            a = Account(
                self.account.primary_smtp_address,
                autodiscover=True,
                config=self.account.protocol.config,
            )
            self.assertIsNotNone(a.protocol.auth_type)
            self.assertIsNotNone(a.protocol.retry_policy)
            self.assertEqual(a.protocol._session_pool_maxsize, 3)
        finally:
            self.account.protocol.config.max_connections = _max_conn

        a = Account(self.account.primary_smtp_address, autodiscover=True, credentials=self.account.protocol.credentials)
        self.assertIsNotNone(a.protocol.auth_type)
        self.assertIsNotNone(a.protocol.retry_policy)
        self.assertEqual(a.protocol._session_pool_maxsize, a.protocol.SESSION_POOLSIZE)
