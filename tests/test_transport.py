from collections import namedtuple

import requests
import requests_mock

from exchangelib.account import DELEGATE, Identity
from exchangelib.errors import UnauthorizedError
from exchangelib.transport import BASIC, DIGEST, NOAUTH, NTLM, get_auth_method_from_response, wrap
from exchangelib.util import PrettyXmlHandler, create_element

from .common import TimedTestCase


class TransportTest(TimedTestCase):
    @requests_mock.mock()
    def test_get_auth_method_from_response(self, m):
        url = "http://example.com/noauth"
        m.get(url, status_code=200)
        r = requests.get(url)
        self.assertEqual(get_auth_method_from_response(r), NOAUTH)  # No authentication needed

        url = "http://example.com/redirect"
        m.get(url, status_code=302, headers={"location": "http://contoso.com"})
        r = requests.get(url, allow_redirects=False)
        with self.assertRaises(UnauthorizedError):
            get_auth_method_from_response(r)  # Redirect to another host

        url = "http://example.com/relativeredirect"
        m.get(url, status_code=302, headers={"location": "http://example.com/"})
        r = requests.get(url, allow_redirects=False)
        with self.assertRaises(UnauthorizedError):
            get_auth_method_from_response(r)  # Redirect to same host

        url = "http://example.com/internalerror"
        m.get(url, status_code=501)
        r = requests.get(url)
        with self.assertRaises(UnauthorizedError):
            get_auth_method_from_response(r)  # Non-401 status code

        url = "http://example.com/no_auth_headers"
        m.get(url, status_code=401)
        r = requests.get(url)
        with self.assertRaises(UnauthorizedError):
            get_auth_method_from_response(r)  # 401 status code but no auth headers

        url = "http://example.com/no_supported_auth"
        m.get(url, status_code=401, headers={"WWW-Authenticate": "FANCYAUTH"})
        r = requests.get(url)
        with self.assertRaises(UnauthorizedError):
            get_auth_method_from_response(r)  # 401 status code but no auth headers

        url = "http://example.com/basic_auth"
        m.get(url, status_code=401, headers={"WWW-Authenticate": "Basic"})
        r = requests.get(url)
        self.assertEqual(get_auth_method_from_response(r), BASIC)

        url = "http://example.com/basic_auth_empty_realm"
        m.get(url, status_code=401, headers={"WWW-Authenticate": 'Basic realm=""'})
        r = requests.get(url)
        self.assertEqual(get_auth_method_from_response(r), BASIC)

        url = "http://example.com/basic_auth_realm"
        m.get(url, status_code=401, headers={"WWW-Authenticate": 'Basic realm="some realm"'})
        r = requests.get(url)
        self.assertEqual(get_auth_method_from_response(r), BASIC)

        url = "http://example.com/digest"
        m.get(
            url,
            status_code=401,
            headers={
                "WWW-Authenticate": 'Digest realm="foo@bar.com", qop="auth,auth-int", nonce="mumble", opaque="bumble"'
            },
        )
        r = requests.get(url)
        self.assertEqual(get_auth_method_from_response(r), DIGEST)

        url = "http://example.com/ntlm"
        m.get(url, status_code=401, headers={"WWW-Authenticate": "NTLM"})
        r = requests.get(url)
        self.assertEqual(get_auth_method_from_response(r), NTLM)

        # Make sure we prefer the most secure auth method if multiple methods are supported
        url = "http://example.com/mixed"
        m.get(url, status_code=401, headers={"WWW-Authenticate": 'Basic realm="X1", Digest realm="X2", NTLM'})
        r = requests.get(url)
        self.assertEqual(get_auth_method_from_response(r), DIGEST)

    def test_wrap(self):
        # Test payload wrapper with both delegation, impersonation and timezones
        MockTZ = namedtuple("EWSTimeZone", ["ms_id"])
        MockAccount = namedtuple("Account", ["access_type", "identity", "default_timezone"])
        content = create_element("AAA")
        api_version = "BBB"
        account = MockAccount(access_type=DELEGATE, identity=None, default_timezone=MockTZ("XXX"))
        wrapped = wrap(content=content, api_version=api_version, timezone=account.default_timezone)
        self.assertEqual(
            PrettyXmlHandler().prettify_xml(wrapped),
            b"""<?xml version='1.0' encoding='utf-8'?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Header>
    <t:RequestServerVersion Version="BBB"/>
    <t:TimeZoneContext>
      <t:TimeZoneDefinition Id="XXX"/>
    </t:TimeZoneContext>
  </s:Header>
  <s:Body>
    <AAA/>
  </s:Body>
</s:Envelope>
""",
        )
        for attr, tag in (
            ("primary_smtp_address", "PrimarySmtpAddress"),
            ("upn", "PrincipalName"),
            ("sid", "SID"),
            ("smtp_address", "SmtpAddress"),
        ):
            val = f"{attr}@example.com"
            account = MockAccount(
                access_type=DELEGATE, identity=Identity(**{attr: val}), default_timezone=MockTZ("XXX")
            )
            wrapped = wrap(
                content=content,
                api_version=api_version,
                account_to_impersonate=account.identity,
                timezone=account.default_timezone,
            )
            self.assertEqual(
                PrettyXmlHandler().prettify_xml(wrapped),
                f"""<?xml version='1.0' encoding='utf-8'?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Header>
    <t:RequestServerVersion Version="BBB"/>
    <t:ExchangeImpersonation>
      <t:ConnectingSID>
        <t:{tag}>{val}</t:{tag}>
      </t:ConnectingSID>
    </t:ExchangeImpersonation>
    <t:TimeZoneContext>
      <t:TimeZoneDefinition Id="XXX"/>
    </t:TimeZoneContext>
  </s:Header>
  <s:Body>
    <AAA/>
  </s:Body>
</s:Envelope>
""".encode(),
            )
