import io
import logging
from contextlib import suppress
from itertools import chain
from unittest.mock import patch

import requests
import requests_mock

import exchangelib.util
from exchangelib.errors import (
    CASError,
    RateLimitError,
    RedirectError,
    RelativeRedirect,
    TransportError,
    UnauthorizedError,
)
from exchangelib.protocol import FailFast, FaultTolerance
from exchangelib.util import (
    BOM_UTF8,
    CONNECTION_ERRORS,
    AnonymizingXmlHandler,
    DocumentYielder,
    ParseError,
    PrettyXmlHandler,
    chunkify,
    get_domain,
    get_redirect_url,
    is_xml,
    peek,
    post_ratelimited,
    safe_b64decode,
    to_xml,
    xml_to_str,
)

from .common import EWSTest, mock_post, mock_session_exception


class UtilTest(EWSTest):
    def test_chunkify(self):
        # Test tuple, list, set, range, map, chain and generator
        seq = [1, 2, 3, 4, 5]
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[1, 2], [3, 4], [5]])

        seq = (1, 2, 3, 4, 6, 7, 9)
        self.assertEqual(list(chunkify(seq, chunksize=3)), [(1, 2, 3), (4, 6, 7), (9,)])

        seq = {1, 2, 3, 4, 5}
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[1, 2], [3, 4], [5]])

        seq = range(5)
        self.assertEqual(list(chunkify(seq, chunksize=2)), [range(0, 2), range(2, 4), range(4, 5)])

        seq = map(int, range(5))
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[0, 1], [2, 3], [4]])

        seq = chain(*[[i] for i in range(5)])
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[0, 1], [2, 3], [4]])

        seq = (i for i in range(5))
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[0, 1], [2, 3], [4]])

    def test_peek(self):
        # Test peeking into various sequence types

        # tuple
        is_empty, seq = peek(())
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek((1, 2, 3))
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # list
        is_empty, seq = peek([])
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek([1, 2, 3])
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # set
        is_empty, seq = peek(set())
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek({1, 2, 3})
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # range
        is_empty, seq = peek(range(0))
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek(range(1, 4))
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # map
        is_empty, seq = peek(map(int, []))
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek(map(int, (1, 2, 3)))
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # generator
        is_empty, seq = peek((i for i in ()))
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek((i for i in (1, 2, 3)))
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

    @requests_mock.mock()
    def test_get_redirect_url(self, m):
        hostname = "httpbin.org"
        url = f"https://{hostname}/redirect-to"
        m.get(url, status_code=302, headers={"location": "https://example.com/"})
        r = requests.get(f"{url}?url=https://example.com/", allow_redirects=False)
        self.assertEqual(get_redirect_url(r), "https://example.com/")

        m.get(url, status_code=302, headers={"location": "http://example.com/"})
        r = requests.get(f"{url}?url=http://example.com/", allow_redirects=False)
        self.assertEqual(get_redirect_url(r), "http://example.com/")

        m.get(url, status_code=302, headers={"location": "/example"})
        r = requests.get(f"{url}?url=/example", allow_redirects=False)
        self.assertEqual(get_redirect_url(r), f"https://{hostname}/example")

        m.get(url, status_code=302, headers={"location": "https://example.com"})
        with self.assertRaises(RelativeRedirect):
            r = requests.get(f"{url}?url=https://example.com", allow_redirects=False)
            get_redirect_url(r, require_relative=True)

        m.get(url, status_code=302, headers={"location": "/example"})
        with self.assertRaises(RelativeRedirect):
            r = requests.get(f"{url}?url=/example", allow_redirects=False)
            get_redirect_url(r, allow_relative=False)

    def test_to_xml(self):
        to_xml(b'<?xml version="1.0" encoding="UTF-8"?><foo></foo>')
        to_xml(BOM_UTF8 + b'<?xml version="1.0" encoding="UTF-8"?><foo></foo>')
        to_xml(BOM_UTF8 + b'<?xml version="1.0" encoding="UTF-8"?><foo>&broken</foo>')
        with self.assertRaises(ParseError):
            to_xml(b"foo")

    @patch("lxml.etree.parse", side_effect=ParseError("", "", 1, 0))
    def test_to_xml_failure(self, m):
        # Not all lxml versions throw ParseError on the same XML, so we have to mock
        with self.assertRaises(ParseError) as e:
            to_xml(b"<t:Foo><t:Bar>Baz</t:Bar></t:Foo>")
        self.assertIn("Offending text: [...]<t:Foo><t:Bar>Baz</t[...]", e.exception.args[0])

    @patch("lxml.etree.parse", side_effect=AssertionError("XXX"))
    def test_to_xml_failure_2(self, m):
        # Not all lxml versions throw ParseError on the same XML, so we have to mock
        with self.assertRaises(ParseError) as e:
            to_xml(b"<t:Foo><t:Bar>Baz</t:Bar></t:Foo>")
        self.assertIn("XXX", e.exception.args[0])

    @patch("lxml.etree.parse", side_effect=TypeError(""))
    def test_to_xml_failure_3(self, m):
        # Not all lxml versions throw ParseError on the same XML, so we have to mock
        with self.assertRaises(ParseError) as e:
            to_xml(b"<t:Foo><t:Bar>Baz</t:Bar></t:Foo>")
        self.assertEqual(e.exception.args[0], "This is not XML: b'<t:Foo><t:Bar>Baz</t:Bar></t:Foo>'")

    def test_is_xml(self):
        self.assertEqual(is_xml(b'<?xml version="1.0" encoding="UTF-8"?><foo></foo>'), True)
        self.assertEqual(is_xml(BOM_UTF8 + b'<?xml version="1.0" encoding="UTF-8"?><foo></foo>'), True)
        self.assertEqual(is_xml(b"XXX"), False)

    def test_xml_to_str(self):
        with self.assertRaises(AttributeError):
            xml_to_str("XXX", encoding=None, xml_declaration=True)

    def test_anonymizing_handler(self):
        h = AnonymizingXmlHandler(forbidden_strings=("XXX", "yyy"))
        self.assertEqual(
            xml_to_str(
                h.parse_bytes(
                    b"""\
<Root>
  <t:ItemId Id="AQApA=" ChangeKey="AQAAAB"/>
  <Foo>XXX</Foo>
  <Foo><Bar>Hello yyy world</Bar></Foo>
</Root>"""
                )
            ),
            """\
<Root>
  <t:ItemId Id="DEADBEEF=" ChangeKey="DEADBEEF="/>
  <Foo>[REMOVED]</Foo>
  <Foo><Bar>Hello [REMOVED] world</Bar></Foo>
</Root>""",
        )

    def test_get_domain(self):
        self.assertEqual(get_domain("foo@example.com"), "example.com")
        with self.assertRaises(ValueError):
            get_domain("blah")

    def test_pretty_xml_handler(self):
        # Test that a normal, non-XML log record is passed through unchanged
        stream = io.StringIO()
        stream.isatty = lambda: True
        h = PrettyXmlHandler(stream=stream)
        self.assertTrue(h.is_tty())
        r = logging.LogRecord(
            name="baz", level=logging.INFO, pathname="/foo/bar", lineno=1, msg="hello", args=(), exc_info=None
        )
        h.emit(r)
        h.stream.seek(0)
        self.assertEqual(h.stream.read(), "hello\n")

        # Test formatting of an XML record. It should contain newlines and color codes.
        stream = io.StringIO()
        stream.isatty = lambda: True
        h = PrettyXmlHandler(stream=stream)
        r = logging.LogRecord(
            name="baz",
            level=logging.DEBUG,
            pathname="/foo/bar",
            lineno=1,
            msg="hello %(xml_foo)s",
            args=({"xml_foo": b'<?xml version="1.0" encoding="UTF-8"?><foo>bar</foo>'},),
            exc_info=None,
        )
        h.emit(r)
        h.stream.seek(0)
        self.assertEqual(
            h.stream.read(),
            "hello \x1b[36m<?xml version='1.0' encoding='utf-8'?>\x1b[39;49;00m\n\x1b[94m"
            "<foo\x1b[39;49;00m\x1b[94m>\x1b[39;49;00mbar\x1b[94m</foo>\x1b[39;49;00m\n",
        )

    def test_post_ratelimited(self):
        url = "https://example.com"

        protocol = self.account.protocol
        orig_policy = protocol.config.retry_policy
        RETRY_WAIT = exchangelib.util.RETRY_WAIT
        MAX_REDIRECTS = exchangelib.util.MAX_REDIRECTS

        session = protocol.get_session()
        try:
            # Make sure we fail fast in error cases
            protocol.config.retry_policy = FailFast()

            # Test the straight, HTTP 200 path
            session.post = mock_post(url, 200, {}, "foo")
            r, session = post_ratelimited(protocol=protocol, session=session, url="http://", headers=None, data="")
            self.assertEqual(r.content, b"foo")

            # Test exceptions raises by the POST request
            for err_cls in CONNECTION_ERRORS:
                session.post = mock_session_exception(err_cls)
                with self.assertRaises(err_cls):
                    r, session = post_ratelimited(
                        protocol=protocol, session=session, url="http://", headers=None, data=""
                    )

            # Test bad exit codes and headers
            session.post = mock_post(url, 401, {})
            with self.assertRaises(UnauthorizedError):
                r, session = post_ratelimited(protocol=protocol, session=session, url="http://", headers=None, data="")
            session.post = mock_post(url, 999, {"connection": "close"})
            with self.assertRaises(TransportError):
                r, session = post_ratelimited(protocol=protocol, session=session, url="http://", headers=None, data="")
            session.post = mock_post(
                url, 302, {"location": "/ews/genericerrorpage.htm?aspxerrorpath=/ews/exchange.asmx"}
            )
            with self.assertRaises(TransportError):
                r, session = post_ratelimited(protocol=protocol, session=session, url="http://", headers=None, data="")
            session.post = mock_post(url, 503, {})
            with self.assertRaises(TransportError):
                r, session = post_ratelimited(protocol=protocol, session=session, url="http://", headers=None, data="")

            # No redirect header
            session.post = mock_post(url, 302, {})
            with self.assertRaises(TransportError):
                r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data="")
            # Redirect header to same location
            session.post = mock_post(url, 302, {"location": url})
            with self.assertRaises(TransportError):
                r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data="")
            # Redirect header to relative location
            session.post = mock_post(url, 302, {"location": url + "/foo"})
            with self.assertRaises(RedirectError):
                r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data="")
            # Redirect header to other location and allow_redirects=False
            session.post = mock_post(url, 302, {"location": "https://contoso.com"})
            with self.assertRaises(TransportError):
                r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data="")
            # Redirect header to other location and allow_redirects=True
            exchangelib.util.MAX_REDIRECTS = 0
            session.post = mock_post(url, 302, {"location": "https://contoso.com"})
            with self.assertRaises(TransportError):
                r, session = post_ratelimited(
                    protocol=protocol, session=session, url=url, headers=None, data="", allow_redirects=True
                )

            # CAS error
            session.post = mock_post(url, 999, {"X-CasErrorCode": "AAARGH!"})
            with self.assertRaises(CASError):
                r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data="")

            # Allow XML data in a non-HTTP 200 response
            session.post = mock_post(url, 500, {}, '<?xml version="1.0" ?><foo></foo>')
            r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data="")
            self.assertEqual(r.content, b'<?xml version="1.0" ?><foo></foo>')

            # Bad status_code and bad text
            session.post = mock_post(url, 999, {})
            with self.assertRaises(TransportError):
                r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data="")

            # Test rate limit exceeded
            exchangelib.util.RETRY_WAIT = 1
            protocol.config.retry_policy = FaultTolerance(max_wait=0.5)  # Fail after first RETRY_WAIT
            session.post = mock_post(url, 503, {"connection": "close"})
            # Mock renew_session to return the same session so the session object's 'post' method is still mocked
            protocol.renew_session = lambda s: s
            with self.assertRaises(RateLimitError) as rle:
                r, session = post_ratelimited(protocol=protocol, session=session, url="http://", headers=None, data="")
            self.assertEqual(rle.exception.status_code, 503)
            self.assertEqual(rle.exception.url, url)
            self.assertRegex(
                str(rle.exception),
                r"Max timeout reached \(gave up after .* seconds. URL https://example.com returned status code 503\)",
            )
            self.assertTrue(1 <= rle.exception.total_wait < 2)  # One RETRY_WAIT plus some overhead

            # Test something larger than the default wait, so we retry at least once
            protocol.retry_policy.max_wait = 3  # Fail after second RETRY_WAIT
            session.post = mock_post(url, 503, {"connection": "close"})
            with self.assertRaises(RateLimitError) as rle:
                r, session = post_ratelimited(protocol=protocol, session=session, url="http://", headers=None, data="")
            self.assertEqual(rle.exception.status_code, 503)
            self.assertEqual(rle.exception.url, url)
            self.assertRegex(
                str(rle.exception),
                r"Max timeout reached \(gave up after .* seconds. URL https://example.com returned status code 503\)",
            )
            # We double the wait for each retry, so this is RETRY_WAIT + 2*RETRY_WAIT plus some overhead
            self.assertTrue(3 <= rle.exception.total_wait < 4, rle.exception.total_wait)
        finally:
            protocol.retire_session(session)  # We have patched the session, so discard it
            # Restore patched attributes and functions
            protocol.config.retry_policy = orig_policy
            exchangelib.util.RETRY_WAIT = RETRY_WAIT
            exchangelib.util.MAX_REDIRECTS = MAX_REDIRECTS

            with suppress(AttributeError):
                delattr(protocol, "renew_session")

    def test_safe_b64decode(self):
        # Test correctly padded string
        self.assertEqual(safe_b64decode("SGVsbG8gd29ybGQ="), b"Hello world")
        # Test incorrectly padded string
        self.assertEqual(safe_b64decode("SGVsbG8gd29ybGQ"), b"Hello world")
        # Test binary data
        self.assertEqual(safe_b64decode(b"SGVsbG8gd29ybGQ="), b"Hello world")
        # Test incorrectly padded binary data
        self.assertEqual(safe_b64decode(b"SGVsbG8gd29ybGQ"), b"Hello world")

    def test_document_yielder(self):
        self.assertListEqual(
            list(DocumentYielder(_bytes_to_iter(b"<b>a</b>"), "b")),
            [b"<?xml version='1.0' encoding='utf-8'?>\n<b>a</b>"],
        )
        self.assertListEqual(
            list(DocumentYielder(_bytes_to_iter(b"<b>a</b><b>c</b><b>b</b>"), "b")),
            [
                b"<?xml version='1.0' encoding='utf-8'?>\n<b>a</b>",
                b"<?xml version='1.0' encoding='utf-8'?>\n<b>c</b>",
                b"<?xml version='1.0' encoding='utf-8'?>\n<b>b</b>",
            ],
        )
        self.assertListEqual(
            list(DocumentYielder(_bytes_to_iter(b"<XXX></XXX>"), "XXX")),
            [b"<?xml version='1.0' encoding='utf-8'?>\n<XXX></XXX>"],
        )
        self.assertListEqual(
            list(DocumentYielder(_bytes_to_iter(b"<ns:XXX></ns:XXX>"), "XXX")),
            [b"<?xml version='1.0' encoding='utf-8'?>\n<ns:XXX></ns:XXX>"],
        )
        self.assertListEqual(
            list(DocumentYielder(_bytes_to_iter(b"<ns:XXX a='b'></ns:XXX>"), "XXX")),
            [b"<?xml version='1.0' encoding='utf-8'?>\n<ns:XXX a='b'></ns:XXX>"],
        )
        self.assertListEqual(
            list(DocumentYielder(_bytes_to_iter(b"<ns:XXX a='b' c='d'></ns:XXX>"), "XXX")),
            [b"<?xml version='1.0' encoding='utf-8'?>\n<ns:XXX a='b' c='d'></ns:XXX>"],
        )
        # Test 'dangerous' chars in attr values
        self.assertListEqual(
            list(DocumentYielder(_bytes_to_iter(b"<ns:XXX a='>b'></ns:XXX>"), "XXX")),
            [b"<?xml version='1.0' encoding='utf-8'?>\n<ns:XXX a='>b'></ns:XXX>"],
        )


def _bytes_to_iter(content):
    return iter((bytes([b]) for b in content))
