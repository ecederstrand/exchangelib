import datetime
import io
import itertools
import logging
import re
import socket
import time
import xml.sax.handler  # nosec
from base64 import b64decode, b64encode
from codecs import BOM_UTF8
from contextlib import suppress
from decimal import Decimal
from functools import wraps
from threading import get_ident
from urllib.parse import urlparse

import isodate
import lxml.etree  # nosec
import requests.exceptions
from defusedxml.expatreader import DefusedExpatParser
from defusedxml.sax import _InputSource
from oauthlib.oauth2 import TokenExpiredError
from pygments import highlight
from pygments.formatters.terminal import TerminalFormatter
from pygments.lexers.html import XmlLexer
from requests_oauthlib import OAuth2Session

from .errors import ErrorInternalServerTransientError, ErrorTimeoutExpired, RelativeRedirect, TransportError

log = logging.getLogger(__name__)
xml_log = logging.getLogger(f"{__name__}.xml")


def require_account(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        if not self.account:
            raise ValueError(f"{self.__class__.__name__} must have an account")
        return f(self, *args, **kwargs)

    return wrapper


def require_id(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        if not self.account:
            raise ValueError(f"{self.__class__.__name__} must have an account")
        if not self.id:
            raise ValueError(f"{self.__class__.__name__} must have an ID")
        return f(self, *args, **kwargs)

    return wrapper


class ParseError(lxml.etree.ParseError):
    """Used to wrap lxml ParseError in our own class."""


class ElementNotFound(Exception):
    """Raised when the expected element was not found in a response stream."""

    def __init__(self, msg, data):
        super().__init__(msg)
        self.data = data


# Regex of UTF-8 control characters that are illegal in XML 1.0 (and XML 1.1).
# See https://stackoverflow.com/a/22273639/219640
_ILLEGAL_XML_CHARS_RE = re.compile("[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x84\x86-\x9F\uFDD0-\uFDDF\uFFFE\uFFFF]")
_ILLEGAL_XML_ESCAPE_CHARS_RE = re.compile(rb"&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?)")  # Could match the above better

# XML namespaces
SOAPNS = "http://schemas.xmlsoap.org/soap/envelope/"
MNS = "http://schemas.microsoft.com/exchange/services/2006/messages"
TNS = "http://schemas.microsoft.com/exchange/services/2006/types"
ENS = "http://schemas.microsoft.com/exchange/services/2006/errors"
ANS = "http://schemas.microsoft.com/exchange/2010/Autodiscover"
INS = "http://www.w3.org/2001/XMLSchema-instance"
WSA = "http://www.w3.org/2005/08/addressing"
AUTODISCOVER_BASE_NS = "http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006"
AUTODISCOVER_REQUEST_NS = "http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006"
AUTODISCOVER_RESPONSE_NS = "http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a"

ns_translation = {
    "s": SOAPNS,
    "m": MNS,
    "t": TNS,
    "a": ANS,
    "wsa": WSA,
    "xsi": INS,
}
for item in ns_translation.items():
    lxml.etree.register_namespace(*item)


def is_iterable(value, generators_allowed=False):
    """Check if value is a list-like object. Don't match generators and generator-like objects here by default, because
    callers don't necessarily guarantee that they only iterate the value once. Take care to not match string types and
    bytes.

    :param value: any type of object
    :param generators_allowed: if True, generators will be treated as iterable (Default value = False)

    :return: True or False
    """
    if generators_allowed:
        if not isinstance(value, (bytes, str)) and hasattr(value, "__iter__"):
            return True
    else:
        if isinstance(value, (tuple, list, set)):
            return True
    return False


def chunkify(iterable, chunksize):
    """Split an iterable into chunks of size ``chunksize``. The last chunk may be smaller than ``chunksize``.

    :param iterable:
    :param chunksize:
    :return:
    """
    from .queryset import QuerySet

    if hasattr(iterable, "__getitem__") and not isinstance(iterable, QuerySet):
        # tuple, list. QuerySet has __getitem__ but that evaluates the entire query greedily. We don't want that here.
        for i in range(0, len(iterable), chunksize):
            yield iterable[i : i + chunksize]
    else:
        # generator, set, map, QuerySet
        chunk = []
        for i in iterable:
            chunk.append(i)
            if len(chunk) == chunksize:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def peek(iterable):
    """Check if an iterable is empty and return status and the rewinded iterable.

    :param iterable:
    :return:
    """
    if hasattr(iterable, "__len__"):
        # tuple, list, set
        return not iterable, iterable
    # generator
    try:
        first = next(iterable)
    except StopIteration:
        return True, iterable
    # We can't rewind a generator. Instead, chain the first element and the rest of the generator
    return False, itertools.chain([first], iterable)


def xml_to_str(tree, encoding=None, xml_declaration=False):
    """Serialize an XML tree. Returns unicode if 'encoding' is None. Otherwise, we return encoded 'bytes'.

    :param tree:
    :param encoding:  (Default value = None)
    :param xml_declaration:  (Default value = False)
    :return:
    """
    if xml_declaration and not encoding:
        raise AttributeError("'xml_declaration' is not supported when 'encoding' is None")
    if encoding:
        return lxml.etree.tostring(tree, encoding=encoding, xml_declaration=True)
    return lxml.etree.tostring(tree, encoding=str, xml_declaration=False)


def get_xml_attr(tree, name):
    elem = tree.find(name)
    if elem is None:  # Must compare with None, see XML docs
        return None
    return elem.text or None


def get_xml_attrs(tree, name):
    return [elem.text for elem in tree.findall(name) if elem.text is not None]


def value_to_xml_text(value):
    from .ewsdatetime import EWSDate, EWSDateTime, EWSTimeZone
    from .indexed_properties import EmailAddress, PhoneNumber
    from .properties import AssociatedCalendarItemId, Attendee, ConversationId, Mailbox

    # We can't just create a map and look up with type(value) because we want to support subtypes
    if isinstance(value, str):
        return safe_xml_value(value)
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, bytes):
        return b64encode(value).decode("ascii")
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, EWSTimeZone):
        return value.ms_id
    if isinstance(value, EWSDateTime):
        return value.ewsformat()
    if isinstance(value, EWSDate):
        return value.ewsformat()
    if isinstance(value, PhoneNumber):
        return value.phone_number
    if isinstance(value, EmailAddress):
        return value.email
    if isinstance(value, Mailbox):
        return value.email_address
    if isinstance(value, Attendee):
        return value.mailbox.email_address
    if isinstance(value, ConversationId):
        return value.id
    if isinstance(value, AssociatedCalendarItemId):
        return value.id
    raise TypeError(f"Unsupported type: {type(value)} ({value})")


def xml_text_to_value(value, value_type):
    from .ewsdatetime import EWSDate, EWSDateTime

    if value_type == str:
        return value
    if value_type == bool:
        try:
            return {
                "true": True,
                "on": True,
                "false": False,
                "off": False,
            }[value.lower()]
        except KeyError:
            return None
    return {
        bytes: safe_b64decode,
        int: int,
        Decimal: Decimal,
        datetime.timedelta: isodate.parse_duration,
        EWSDate: EWSDate.from_string,
        EWSDateTime: EWSDateTime.from_string,
    }[value_type](value)


def set_xml_value(elem, value, version=None):
    from .ewsdatetime import EWSDate, EWSDateTime
    from .fields import FieldOrder, FieldPath
    from .properties import EWSElement

    if isinstance(value, (str, bool, bytes, int, Decimal, datetime.time, EWSDate, EWSDateTime)):
        elem.text = value_to_xml_text(value)
    elif isinstance(value, _element_class):
        elem.append(value)
    elif isinstance(value, (FieldPath, FieldOrder)):
        elem.append(value.to_xml())
    elif isinstance(value, EWSElement):
        elem.append(value.to_xml(version=version))
    elif is_iterable(value, generators_allowed=True):
        for v in value:
            set_xml_value(elem, v, version=version)
    else:
        raise ValueError(f"Unsupported type {type(value)} for value {value} on elem {elem}")
    return elem


def safe_xml_value(value, replacement="?"):
    return _ILLEGAL_XML_CHARS_RE.sub(replacement, value)


def sanitize_xml(data, replacement=b"?"):
    if not isinstance(data, bytes):
        # We may get data="" from some expatreader versions
        return data
    return _ILLEGAL_XML_ESCAPE_CHARS_RE.sub(replacement, data)


def create_element(name, attrs=None, nsmap=None):
    if ":" in name:
        ns, name = name.split(":")
        name = f"{{{ns_translation[ns]}}}{name}"
    elem = _forgiving_parser.makeelement(name, nsmap=nsmap)
    if attrs:
        # Try hard to keep attribute order, to ensure deterministic output. This simplifies testing.
        # Dicts in Python 3.6+ have stable ordering.
        for k, v in attrs.items():
            if isinstance(v, bool):
                v = "true" if v else "false"
            elif isinstance(v, int):
                v = str(v)
            elem.set(k, v)
    return elem


def add_xml_child(tree, name, value):
    # We're calling add_xml_child many places where we don't have the version handy. Don't pass EWSElement or list of
    # EWSElement to this function!
    tree.append(set_xml_value(elem=create_element(name), value=value))


class StreamingContentHandler(xml.sax.handler.ContentHandler):
    """A SAX content handler that returns a character data for a single element back to the parser. The parser must have
    a 'buffer' attribute we can append data to.
    """

    def __init__(self, parser, ns, element_name):
        xml.sax.handler.ContentHandler.__init__(self)
        self._parser = parser
        self._ns = ns
        self._element_name = element_name
        self._parsing = False

    def startElementNS(self, name, qname, attrs):
        if name == (self._ns, self._element_name):
            # we can expect element data next
            self._parsing = True
            self._parser.element_found = True

    def endElementNS(self, name, qname):
        if name == (self._ns, self._element_name):
            # all element data received
            self._parsing = False

    def characters(self, content):
        if not self._parsing:
            return
        self._parser.buffer.append(content)


def prepare_input_source(source):
    # Extracted from xml.sax.expatreader.saxutils.prepare_input_source
    f = source
    source = _InputSource()
    source.setByteStream(f)
    return source


def safe_b64decode(data):
    # Incoming base64-encoded data is not always padded to a multiple of 4. Python's parser is stricter and requires
    # padding. Add padding if it's needed.
    overflow = len(data) % 4
    if overflow:
        if isinstance(data, str):
            padding = "=" * (4 - overflow)
        else:
            padding = b"=" * (4 - overflow)
        data += padding
    return b64decode(data)


class StreamingBase64Parser(DefusedExpatParser):
    """A SAX parser that returns a generator of base64-decoded character content."""

    def __init__(self, *args, **kwargs):
        DefusedExpatParser.__init__(self, *args, **kwargs)
        self._namespaces = True
        self.buffer = None
        self.element_found = None

    def parse(self, r):
        raw_source = r.raw
        # Like upstream but yields the return value of self.feed()
        raw_source = prepare_input_source(raw_source)
        self.prepareParser(raw_source)
        file = raw_source.getByteStream()
        self.buffer = []
        self.element_found = False
        buffer = file.read(self._bufsize)
        collected_data = []
        while buffer:
            if not self.element_found:
                collected_data.extend(buffer)
            yield from self.feed(buffer)
            buffer = file.read(self._bufsize)
        # Any remaining data in self.buffer should be padding chars now
        self.buffer = None
        self.close()
        if not self.element_found:
            raise ElementNotFound("The element to be streamed from was not found", data=bytes(collected_data))

    def feed(self, data, isFinal=0):
        """Yield the current content of the character buffer. The input XML may contain illegal characters. The lxml
        parser handles this gracefully with the 'recover' option, but ExpatParser doesn't have this option. Remove
        illegal characters before parsing."""
        DefusedExpatParser.feed(self, data=sanitize_xml(data), isFinal=isFinal)
        return self._decode_buffer()

    def _decode_buffer(self):
        remainder = ""
        for data in self.buffer:
            available = len(remainder) + len(data)
            overflow = available % 4  # Make sure we always decode a multiple of 4
            if remainder:
                data = remainder + data
                remainder = ""
            if overflow:
                remainder, data = data[-overflow:], data[:-overflow]
            if data:
                yield b64decode(data)
        self.buffer = [remainder] if remainder else []


_forgiving_parser = lxml.etree.XMLParser(
    resolve_entities=False,  # This setting is recommended by lxml for safety
    recover=True,  # This setting is non-default
    huge_tree=True,  # This setting enables parsing huge attachments, mime_content and other large data
)
_element_class = _forgiving_parser.makeelement("x").__class__


class BytesGeneratorIO(io.RawIOBase):
    """A BytesIO that can produce bytes from a streaming HTTP request. Expects r.iter_content() as input
    lxml tries to be smart by calling `getvalue` when present, assuming that the entire string is in memory.
    Omitting `getvalue` forces lxml to stream the request through `read` avoiding the memory duplication.
    """

    def __init__(self, bytes_generator):
        self._bytes_generator = bytes_generator
        self._next = bytearray()
        self._tell = 0
        super().__init__()

    def readable(self):
        return not self.closed

    def tell(self):
        return self._tell

    def read(self, size=-1):
        # requests `iter_content()` auto-adjusts the number of bytes based on bandwidth
        # can't assume how many bytes next returns so stash any extra in `self._next`
        if self.closed:
            raise ValueError("read from a closed file")
        if self._next is None:
            return b""
        if size is None:
            size = -1

        res = self._next
        while size < 0 or len(res) < size:
            try:
                res.extend(next(self._bytes_generator))
            except StopIteration:
                self._next = None
                break

        if size > 0 and self._next is not None:
            self._next = res[size:]
            res = res[:size]

        self._tell += len(res)
        return bytes(res)

    def close(self):
        if not self.closed:
            self._bytes_generator.close()
        super().close()


class DocumentYielder:
    """Look for XML documents in a streaming HTTP response and yield them as they become available from the stream."""

    def __init__(self, content_iterator, document_tag="Envelope"):
        self._iterator = content_iterator
        self._document_tag = document_tag.encode()

    def _get_tag(self):
        """Iterate over the bytes until we have a full tag in the buffer. If there's a '>' in an attr value, then we'll
        exit on that, but it's OK because we just need the plain tag name later.
        """
        tag_buffer = [b"<"]
        while True:
            try:
                c = next(self._iterator)
            except StopIteration:
                break
            tag_buffer.append(c)
            if c == b">":
                break
        return b"".join(tag_buffer)

    @staticmethod
    def _normalize_tag(tag):
        """Returns the plain tag name given a range of tag formats:
        * <tag>
        * <ns:tag>
        * <ns:tag foo='bar'>
        * </ns:tag foo='bar'>
        """
        return tag.strip(b"<>/").split(b" ")[0].split(b":")[-1]

    def __iter__(self):
        """Consumes the content iterator, looking for start and end tags. Returns each document when we have fully
        collected it.
        """
        doc_started = False
        buffer = []
        try:
            while True:
                c = next(self._iterator)
                if not doc_started and c == b"<":
                    tag = self._get_tag()
                    if self._normalize_tag(tag) == self._document_tag:
                        # Start of document. Collect bytes from this point
                        buffer.append(tag)
                        doc_started = True
                elif doc_started and c == b"<":
                    tag = self._get_tag()
                    buffer.append(tag)
                    if self._normalize_tag(tag) == self._document_tag:
                        # End of document. Yield a valid document and reset the buffer
                        yield b"<?xml version='1.0' encoding='utf-8'?>\n" + b"".join(buffer)
                        doc_started = False
                        buffer = []
                elif doc_started:
                    buffer.append(c)
        except StopIteration:
            return


def to_xml(bytes_content):
    """Convert bytes or a generator of bytes to an XML tree."""
    # Exchange servers may spit out the weirdest XML. lxml is pretty good at recovering from errors
    if isinstance(bytes_content, bytes):
        stream = io.BytesIO(bytes_content)
    else:
        stream = BytesGeneratorIO(bytes_content)
    try:
        res = lxml.etree.parse(stream, parser=_forgiving_parser)  # nosec
    except AssertionError as e:
        raise ParseError(e.args[0], "<not from file>", -1, 0)
    except lxml.etree.ParseError as e:
        if hasattr(e, "position"):
            e.lineno, e.offset = e.position
        if not e.lineno:
            raise ParseError(str(e), "<not from file>", e.lineno, e.offset)
        try:
            stream.seek(0)
            offending_line = stream.read().splitlines()[e.lineno - 1]
        except (IndexError, io.UnsupportedOperation):
            raise ParseError(str(e), "<not from file>", e.lineno, e.offset)
        else:
            offending_excerpt = offending_line[max(0, e.offset - 20) : e.offset + 20]
            msg = f'{e}\nOffending text: [...]{offending_excerpt.decode("utf-8", errors="ignore")}[...]'
            raise ParseError(msg, "<not from file>", e.lineno, e.offset)
    except TypeError:
        with suppress(IndexError, io.UnsupportedOperation):
            stream.seek(0)
        raise ParseError(f"This is not XML: {stream.read()!r}", "<not from file>", -1, 0)

    if res.getroot() is None:
        try:
            stream.seek(0)
            msg = f"No root element found: {stream.read()!r}"
        except (IndexError, io.UnsupportedOperation):
            msg = "No root element found"
        raise ParseError(msg, "<not from file>", -1, 0)
    return res


def is_xml(text):
    """Lightweight test if response is an XML doc. It's better to be fast than correct here.

    :param text: The string to check
    :return:
    """
    # BOM_UTF8 is a UTF-8 byte order mark which may precede the XML from an Exchange server
    bom_len = len(BOM_UTF8)
    expected_prefixes = (b"<?xml", b"<s:Envelope")
    max_prefix_len = len(expected_prefixes[1])
    if text[:bom_len] == BOM_UTF8:
        prefix = text[bom_len : bom_len + max_prefix_len]
    else:
        prefix = text[:max_prefix_len]
    for expected_prefix in expected_prefixes:
        if prefix[: len(expected_prefix)] == expected_prefix:
            return True
    return False


class PrettyXmlHandler(logging.StreamHandler):
    """A steaming log handler that prettifies log statements containing XML when output is a terminal."""

    def parse_bytes(self, xml_bytes):
        return to_xml(xml_bytes)

    def prettify_xml(self, xml_bytes):
        """Re-format an XML document to a consistent style."""
        return (
            lxml.etree.tostring(self.parse_bytes(xml_bytes), xml_declaration=True, encoding="utf-8", pretty_print=True)
            .replace(b" xmlns:", b"\n    xmlns:")
            .expandtabs()
        )

    @staticmethod
    def highlight_xml(xml_str):
        """Highlight a string containing XML, using terminal color codes."""
        return highlight(xml_str, XmlLexer(), TerminalFormatter()).rstrip()

    def emit(self, record):
        """Pretty-print and syntax highlight a log statement if all these conditions are met:
           * This is a DEBUG message
           * We're outputting to a terminal
           * The log message args is a dict containing keys starting with 'xml_' and values as bytes

        :param record:
        """
        if record.levelno == logging.DEBUG and self.is_tty() and isinstance(record.args, dict):
            for key, value in record.args.items():
                if not key.startswith("xml_"):
                    continue
                if not isinstance(value, bytes):
                    continue
                if not is_xml(value):
                    continue
                try:
                    record.args[key] = self.highlight_xml(self.prettify_xml(value))
                except Exception as e:
                    # Something bad happened, but we don't want to crash the program just because logging failed
                    print(f"XML highlighting failed: {e}")
        return super().emit(record)

    def is_tty(self):
        """Check if we're outputting to a terminal."""
        try:
            return self.stream.isatty()
        except AttributeError:
            return False


class AnonymizingXmlHandler(PrettyXmlHandler):
    """A steaming log handler that prettifies and anonymizes log statements containing XML when output is a terminal."""

    PRIVATE_TAGS = {"RootItemId", "ItemId", "Id", "RootItemChangeKey", "ChangeKey"}

    def __init__(self, forbidden_strings, *args, **kwargs):
        self.forbidden_strings = forbidden_strings
        super().__init__(*args, **kwargs)

    def parse_bytes(self, xml_bytes):
        root = to_xml(xml_bytes)
        for elem in root.iter():
            # Anonymize element attribute values known to contain private data
            for attr in set(elem.keys()) & self.PRIVATE_TAGS:
                elem.set(attr, "DEADBEEF=")
            # Anonymize anything requested by the caller
            for s in self.forbidden_strings:
                if elem.text is not None:
                    elem.text = elem.text.replace(s, "[REMOVED]")
        return root


class DummyRequest:
    """A class to fake a requests Request object for functions that expect this."""

    def __init__(self, headers=None):
        self.headers = headers or {}


class DummyResponse:
    """A class to fake a requests Response object for functions that expect this."""

    def __init__(
        self, url=None, headers=None, request_headers=None, content=b"", status_code=503, streaming=False, history=None
    ):
        self.status_code = status_code
        self.url = url
        self.headers = headers or {}
        self.content = iter((bytes([b]) for b in content)) if streaming else content
        self.text = content.decode("utf-8", errors="ignore")
        self.request = DummyRequest(headers=request_headers)
        self.reason = ""
        self.history = history

    def iter_content(self):
        return self.content

    def close(self):
        pass


def get_domain(email):
    try:
        return email.split("@")[1].lower()
    except (IndexError, AttributeError):
        raise ValueError(f"{email!r} is not a valid email")


def split_url(url):
    parsed_url = urlparse(url)
    # Use netloc instead of hostname since hostname is None if URL is relative
    return parsed_url.scheme == "https", parsed_url.netloc.lower(), parsed_url.path


def get_redirect_url(response, allow_relative=True, require_relative=False):
    # allow_relative=False throws RelativeRedirect error if scheme and hostname are equal to the request
    # require_relative=True throws RelativeRedirect error if scheme and hostname are not equal to the request
    redirect_url = response.headers.get("location")
    if not redirect_url:
        raise TransportError("HTTP redirect but no location header")
    # At least some servers are kind enough to supply a new location. It may be relative
    redirect_has_ssl, redirect_server, redirect_path = split_url(redirect_url)
    # The response may have been redirected already. Get the original URL
    request_url = response.history[0] if response.history else response.url
    request_has_ssl, request_server, _ = split_url(request_url)
    response_has_ssl, response_server, response_path = split_url(response.url)

    if not redirect_server:
        # Redirect URL is relative. Inherit server and scheme from response URL
        redirect_server = response_server
        redirect_has_ssl = response_has_ssl
    if not redirect_path.startswith("/"):
        # The path is not top-level. Add response path
        redirect_path = (response_path or "/") + redirect_path
    redirect_url = f"{'https' if redirect_has_ssl else 'http'}://{redirect_server}{redirect_path}"
    if redirect_url == request_url:
        # And some are mean enough to redirect to the same location
        raise TransportError(f"Redirect to same location: {redirect_url}")
    if not allow_relative and (request_has_ssl == response_has_ssl and request_server == redirect_server):
        raise RelativeRedirect(redirect_url)
    if require_relative and (request_has_ssl != response_has_ssl or request_server != redirect_server):
        raise RelativeRedirect(redirect_url)
    return redirect_url


# A collection of error classes we want to handle as general connection errors
CONNECTION_ERRORS = (
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    socket.timeout,
    ConnectionResetError,
)

# A collection of error classes we want to handle as TLS verification errors
TLS_ERRORS = (requests.exceptions.SSLError,)
with suppress(ImportError):
    # If pyOpenSSL is installed, requests will use it and throw this class on TLS errors
    import OpenSSL.SSL

    TLS_ERRORS += (OpenSSL.SSL.Error,)


def post_ratelimited(protocol, session, url, headers, data, stream=False, timeout=None):
    """There are two error-handling policies implemented here: a fail-fast policy intended for stand-alone scripts which
    fails on all responses except HTTP 200. The other policy is intended for long-running tasks that need to respect
    rate-limiting errors from the server and paper over outages of up to 1 hour.

    Wrap POST requests in a try-catch loop with a lot of error handling logic and some basic rate-limiting. If a request
    fails, and some conditions are met, the loop waits in increasing intervals, up to 1 hour, before trying again. The
    reason for this is that servers often malfunction for short periods of time, either because of ongoing data
    migrations or other maintenance tasks, misconfigurations or heavy load, or because the connecting user has hit a
    throttling policy limit.

    If the loop exited early, consumers of this package that don't implement their own rate-limiting code could quickly
    swamp such a server with new requests. That would only make things worse. Instead, it's better if the request loop
    waits patiently until the server is functioning again.

    If the connecting user has hit a throttling policy, then the server will start to malfunction in many interesting
    ways, but never actually tell the user what is happening. There is no way to distinguish this situation from other
    malfunctions. The only cure is to stop making requests.

    The contract on sessions here is to return the session that ends up being used, or retiring the session if we
    intend to raise an exception. We give up on max_wait timeout, not number of retries.

    An additional resource on handling throttling policies and client back off strategies:
        https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/ews-throttling-in-exchange

    :param protocol:
    :param session:
    :param url:
    :param headers:
    :param data:
    :param stream:  (Default value = False)
    :param timeout:

    :return:
    """
    if not timeout:
        timeout = protocol.TIMEOUT
    thread_id = get_ident()
    log_msg = """\
Timeout: %(timeout)s
Session: %(session_id)s
Thread: %(thread_id)s
Auth type: %(auth)s
URL: %(url)s
HTTP adapter: %(adapter)s
Streaming: %(stream)s
Response time: %(response_time)s
Status code: %(status_code)s
Request headers: %(request_headers)s
Response headers: %(response_headers)s"""
    xml_log_msg = """\
Request XML: %(xml_request)s
Response XML: %(xml_response)s"""
    log_vals = dict(
        timeout=timeout,
        session_id=session.session_id,
        thread_id=thread_id,
        auth=session.auth,
        url=url,
        adapter=session.get_adapter(url),
        stream=stream,
        response_time=None,
        status_code=None,
        request_headers=headers,
        response_headers=None,
    )
    xml_log_vals = dict(
        xml_request=data,
        xml_response=None,
    )
    sleep_secs = _back_off_if_needed(protocol.retry_policy.back_off_until)
    if sleep_secs:
        # We may have slept for a long time. Renew the session.
        session = protocol.renew_session(session)
    log.debug(
        "Session %s thread %s timeout %s: POST'ing to %s after %ss sleep",
        session.session_id,
        thread_id,
        timeout,
        url,
        sleep_secs,
    )
    kwargs = dict(url=url, headers=headers, data=data, allow_redirects=False, timeout=timeout, stream=stream)
    if isinstance(session, OAuth2Session):
        # Fix token refreshing bug. Reported as https://github.com/requests/requests-oauthlib/issues/498
        kwargs.update(session.auto_refresh_kwargs)
    d_start = time.monotonic()
    try:
        r = session.post(**kwargs)
    except TLS_ERRORS as e:
        protocol.retire_session(session)
        # Don't retry on TLS errors. They will most likely be persistent.
        raise TransportError(str(e))
    except CONNECTION_ERRORS as e:
        protocol.retire_session(session)
        log.debug("Session %s thread %s: connection error POST'ing to %s", session.session_id, thread_id, url)
        raise ErrorTimeoutExpired(f"Reraised from {e.__class__.__name__}({e})")
    except TokenExpiredError:
        log.debug("Session %s thread %s: OAuth token expired; refreshing", session.session_id, thread_id)
        protocol.release_session(protocol.refresh_credentials(session))
        raise
    except KeyError as e:
        protocol.retire_session(session)
        if e.args[0] != "www-authenticate":
            raise
        # Server returned an HTTP error code during the NTLM handshake. Re-raise as internal server error
        log.debug("Session %s thread %s: auth headers missing from %s", session.session_id, thread_id, url)
        raise ErrorInternalServerTransientError(f"Reraised from {e.__class__.__name__}({e})")
    except Exception as e:
        # Let higher layers handle this. Add full context for better debugging.
        log.error("%s: %s\n%s\n%s", e.__class__.__name__, str(e), log_msg % log_vals, xml_log_msg % xml_log_vals)
        protocol.retire_session(session)
        raise
    log_vals.update(
        session_id=session.session_id,
        url=r.url,
        response_time=time.monotonic() - d_start,
        status_code=r.status_code,
        request_headers=r.request.headers,
        response_headers=r.headers,
    )
    xml_log_vals.update(
        xml_request=data,
        xml_response="[STREAMING]" if stream else r.content,
    )
    log.debug(log_msg, log_vals)
    xml_log.debug(xml_log_msg, xml_log_vals)

    try:
        protocol.retry_policy.raise_response_errors(r)
    except Exception:
        r.close()  # Release memory
        protocol.retire_session(session)
        raise

    log.debug("Session %s thread %s: Useful response from %s", session.session_id, thread_id, url)
    return r, session


def _back_off_if_needed(back_off_until):
    # Returns the number of seconds we slept
    if back_off_until:
        sleep_secs = (back_off_until - datetime.datetime.now()).total_seconds()
        # The back off value may have expired within the last few milliseconds
        if sleep_secs > 0:
            log.warning("Server requested back off until %s. Sleeping %s seconds", back_off_until, sleep_secs)
            time.sleep(sleep_secs)
            return sleep_secs
    return 0


def _get_retry_after(r):
    """Get Retry-After header, if it exists. We interpret the value as seconds to wait before sending next request."""
    try:
        val = int(r.headers.get("Retry-After", "0"))
    except ValueError:
        return None
    return val if val > 0 else None
