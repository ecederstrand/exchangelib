from __future__ import unicode_literals

from base64 import b64decode
from codecs import BOM_UTF8
import datetime
from decimal import Decimal
import io
import itertools
import logging
import re
import socket
import time
import xml.sax.expatreader
import xml.sax.handler

# Import _etree via defusedxml instead of directly from lxml.etree, to silence overly strict linters
from defusedxml.lxml import parse, tostring, GlobalParserTLS, RestrictedElement, _etree
from future.backports.misc import get_ident
from future.moves.urllib.parse import urlparse
from future.utils import PY2
import isodate
from pygments import highlight
from pygments.lexers.html import XmlLexer
from pygments.formatters.terminal import TerminalFormatter
import requests.exceptions
from six import text_type, string_types

from .errors import TransportError, RateLimitError, RedirectError, RelativeRedirect, CASError, UnauthorizedError, \
    ErrorInvalidSchemaVersionForMailboxVersion

time_func = time.time if PY2 else time.monotonic
log = logging.getLogger(__name__)


class ParseError(_etree.ParseError):
    # Wrap lxml ParseError in our own class
    pass


class ElementNotFound(Exception):
    def __init__(self, msg, data):
        super(ElementNotFound, self).__init__(msg)
        self.data = data


# Regex of UTF-8 control characters that are illegal in XML 1.0 (and XML 1.1)
_ILLEGAL_XML_CHARS_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]')

# XML namespaces
SOAPNS = 'http://schemas.xmlsoap.org/soap/envelope/'
MNS = 'http://schemas.microsoft.com/exchange/services/2006/messages'
TNS = 'http://schemas.microsoft.com/exchange/services/2006/types'
ENS = 'http://schemas.microsoft.com/exchange/services/2006/errors'

ns_translation = {
    's': SOAPNS,
    't': TNS,
    'm': MNS,
}
for item in ns_translation.items():
    _etree.register_namespace(*item)


def is_iterable(value, generators_allowed=False):
    """
    Checks if value is a list-like object. Don't match generators and generator-like objects here by default, because
    callers don't necessarily guarantee that they only iterate the value once. Take care to not match string types and
    bytes.

    :param value: any type of object
    :param generators_allowed: if True, generators will be treated as iterable
    :return: True or False
    """
    if generators_allowed:
        if not isinstance(value, string_types + (bytes,)) and hasattr(value, '__iter__'):
            return True
    else:
        if isinstance(value, (tuple, list, set)):
            return True
    return False


def chunkify(iterable, chunksize):
    """
    Splits an iterable into chunks of size ``chunksize``. The last chunk may be smaller than ``chunksize``.
    """
    from .queryset import QuerySet
    if hasattr(iterable, '__getitem__') and not isinstance(iterable, QuerySet):
        # tuple, list. QuerySet has __getitem__ but that evaluates the entire query greedily. We don't want that here.
        for i in range(0, len(iterable), chunksize):
            yield iterable[i:i + chunksize]
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
    """
    Checks if an iterable is empty and returns status and the rewinded iterable
    """
    from .queryset import QuerySet
    if isinstance(iterable, QuerySet):
        # QuerySet has __len__ but that evaluates the entire query greedily. We don't want that here. Instead, peek()
        # should be called on QuerySet.iterator()
        raise ValueError('Cannot peek on a QuerySet')
    if hasattr(iterable, '__len__'):
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
    """Serialize an XML tree. Returns unicode if 'encoding' is None. Otherwise, we return encoded 'bytes'."""
    if xml_declaration and not encoding:
        raise ValueError("'xml_declaration' is not supported when 'encoding' is None")
    if encoding:
        return tostring(tree, encoding=encoding, xml_declaration=True)
    return tostring(tree, encoding=text_type, xml_declaration=False)


def get_xml_attr(tree, name):
    elem = tree.find(name)
    if elem is None:  # Must compare with None, see XML docs
        return None
    return elem.text or None


def get_xml_attrs(tree, name):
    return [elem.text for elem in tree.findall(name) if elem.text is not None]


def value_to_xml_text(value):
    # We can't handle bytes in this function because str == bytes on Python2
    from .ewsdatetime import EWSTimeZone, EWSDateTime, EWSDate
    from .indexed_properties import PhoneNumber, EmailAddress
    from .properties import Mailbox, Attendee, ConversationId
    if isinstance(value, string_types):
        return safe_xml_value(value)
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, Decimal)):
        return text_type(value)
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
    raise NotImplementedError('Unsupported type: %s (%s)' % (type(value), value))


def xml_text_to_value(value, value_type):
    # We can't handle bytes in this function because str == bytes on Python2
    from .ewsdatetime import EWSDateTime
    return {
        bool: lambda v: True if v == 'true' else False if v == 'false' else None,
        int: int,
        Decimal: Decimal,
        datetime.timedelta: isodate.parse_duration,
        EWSDateTime: EWSDateTime.from_string,
        string_types[0]: lambda v: v
    }[value_type](value)


def set_xml_value(elem, value, version):
    from .ewsdatetime import EWSDateTime, EWSDate
    from .fields import FieldPath, FieldOrder
    from .folders import EWSElement
    from .version import Version
    if isinstance(value, string_types + (bool, bytes, int, Decimal, datetime.time, EWSDate, EWSDateTime)):
        elem.text = value_to_xml_text(value)
    elif isinstance(value, RestrictedElement):
        elem.append(value)
    elif is_iterable(value, generators_allowed=True):
        for v in value:
            if isinstance(v, (FieldPath, FieldOrder)):
                elem.append(v.to_xml())
            elif isinstance(v, EWSElement):
                if not isinstance(version, Version):
                    raise ValueError("'version' %r must be a Version instance" % version)
                elem.append(v.to_xml(version=version))
            elif isinstance(v, RestrictedElement):
                elem.append(v)
            elif isinstance(v, string_types):
                add_xml_child(elem, 't:String', v)
            else:
                raise ValueError('Unsupported type %s for list element %s on elem %s' % (type(v), v, elem))
    elif isinstance(value, (FieldPath, FieldOrder)):
        elem.append(value.to_xml())
    elif isinstance(value, EWSElement):
        if not isinstance(version, Version):
            raise ValueError("'version' %s must be a Version instance" % version)
        elem.append(value.to_xml(version=version))
    else:
        raise ValueError('Unsupported type %s for value %s on elem %s' % (type(value), value, elem))
    return elem


def safe_xml_value(value, replacement='?'):
    return text_type(_ILLEGAL_XML_CHARS_RE.sub(replacement, value))


def create_element(name, **attrs):
    # copy.deepcopy() is an order of magnitude faster than creating a new Element() every time
    if ':' in name:
        ns, name = name.split(':')
        name = '{%s}%s' % (ns_translation[ns], name)
    elem = RestrictedElement(**attrs)
    elem.tag = name
    return elem


def add_xml_child(tree, name, value):
    # We're calling add_xml_child many places where we don't have the version handy. Don't pass EWSElement or list of
    # EWSElement to this function!
    tree.append(set_xml_value(elem=create_element(name), value=value, version=None))


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


class StreamingBase64Parser(xml.sax.expatreader.ExpatParser):
    """A SAX parser that returns a generator of base64-decoded character content"""
    def __init__(self, *args, **kwargs):
        xml.sax.expatreader.ExpatParser.__init__(self, *args, **kwargs)
        self._namespaces = True
        self.buffer = None
        self.element_found = None

    def parse(self, source):
        raw_source = source.raw
        # Like upstream but yields the return value of self.feed()
        raw_source = xml.sax.expatreader.saxutils.prepare_input_source(raw_source)
        self.prepareParser(raw_source)
        file = raw_source.getByteStream()
        self.buffer = []
        self.element_found = False
        buffer = file.read(self._bufsize)
        collected_data = []
        while buffer:
            if not self.element_found:
                collected_data += buffer
            for data in self.feed(buffer):
                yield data
            buffer = file.read(self._bufsize)
        self.buffer = None
        source.close()
        self.close()
        if not self.element_found:
            if PY2:
                data = b''.join(collected_data)
            else:
                data = bytes(collected_data)
            raise ElementNotFound('The element to be streamed from was not found', data=data)

    def feed(self, data, isFinal=0):
        # Like upstream, but yields the current content of the character buffer
        xml.sax.expatreader.ExpatParser.feed(self, data=data, isFinal=isFinal)
        return self._decode_buffer()

    def _decode_buffer(self):
        remainder = ''
        for data in self.buffer:
            available = len(remainder) + len(data)
            overflow = available % 4
            if remainder:
                data = (remainder + data)
                remainder = ''
            if overflow:
                remainder, data = data[-overflow:], data[:-overflow]
            if data:
                yield b64decode(data)
        self.buffer = [remainder] if remainder else []


class ForgivingParser(GlobalParserTLS):
    parser_config = {
        'resolve_entities': False,
        'recover': True,  # This setting is non-default
    }


_forgiving_parser = ForgivingParser()


class BytesGeneratorIO(io.BytesIO):
    # A BytesIO that can produce bytes from a streaming HTTP request. Expects r.iter_content() as input
    def __init__(self, bytes_generator):
        self._bytes_generator = bytes_generator
        self._tell = 0
        super(BytesGeneratorIO, self).__init__()

    def getvalue(self):
        res = b''.join(self._bytes_generator)
        self._tell += len(res)
        return res

    def tell(self):
        return self._tell

    def read(self, size=-1):
        if size is None or size <= -1:
            res = b''.join(self._bytes_generator)
        else:
            res = b''.join(next(self._bytes_generator) for _ in range(size))
        self._tell += len(res)
        return res


def to_xml(bytes_content):
    # Converts bytes or a generator of bytes to an XML tree
    # Exchange servers may spit out the weirdest XML. lxml is pretty good at recovering from errors
    if isinstance(bytes_content, bytes):
        stream = io.BytesIO(bytes_content)
    else:
        stream = BytesGeneratorIO(bytes_content)
    forgiving_parser = _forgiving_parser.getDefaultParser()
    try:
        return parse(stream, parser=forgiving_parser)
    except AssertionError as e:
        raise ParseError(e.args[0], '<not from file>', -1, 0)
    except _etree.ParseError as e:
        if hasattr(e, 'position'):
            e.lineno, e.offset = e.position
        if not e.lineno:
            raise ParseError(text_type(e), '<not from file>', e.lineno, e.offset)
        try:
            stream.seek(0)
            offending_line = stream.read().splitlines()[e.lineno - 1]
        except IndexError:
            raise ParseError(text_type(e), '<not from file>', e.lineno, e.offset)
        else:
            offending_excerpt = offending_line[max(0, e.offset - 20):e.offset + 20]
            msg = '%s\nOffending text: [...]%s[...]' % (text_type(e), offending_excerpt)
            raise ParseError(msg, e.lineno, e.offset)
    except TypeError:
        stream.seek(0)
        raise ParseError('This is not XML: %r' % stream.read(), '<not from file>', -1, 0)


def is_xml(text):
    """
    Helper function. Lightweight test if response is an XML doc
    """
    # BOM_UTF8 is an UTF-8 byte order mark which may precede the XML from an Exchange server
    bom_len = len(BOM_UTF8)
    if text[:bom_len] == BOM_UTF8:
        return text[bom_len:bom_len + 5] == b'<?xml'
    return text[:5] == b'<?xml'


class PrettyXmlHandler(logging.StreamHandler):
    """A steaming log handler that prettifies log statements containing XML when output is a terminal"""
    @staticmethod
    def parse_bytes(xml_bytes):
        return parse(io.BytesIO(xml_bytes))

    @classmethod
    def prettify_xml(cls, xml_bytes):
        # Re-formats an XML document to a consistent style
        return tostring(
            cls.parse_bytes(xml_bytes),
            xml_declaration=True,
            encoding='utf-8',
            pretty_print=True
        ).replace(b'\t', b'    ').replace(b' xmlns:', b'\n    xmlns:')

    @staticmethod
    def highlight_xml(xml_str):
        # Highlights a string containing XML, using terminal color codes
        return highlight(xml_str, XmlLexer(), TerminalFormatter())

    def emit(self, record):
        """Pretty-print and syntax highlight a log statement if all these conditions are met:
           * This is a DEBUG message
           * We're outputting to a terminal
           * The log message args is a dict containing keys starting with 'xml_' and values as bytes
        """
        if record.levelno == logging.DEBUG and self.is_tty() and isinstance(record.args, dict):
            for key, value in record.args.items():
                if not key.startswith('xml_'):
                    continue
                if not isinstance(value, bytes):
                    continue
                if not is_xml(value):
                    continue
                try:
                    if PY2:
                        record.args[key] = self.highlight_xml(self.prettify_xml(value)).encode('utf-8')
                    else:
                        record.args[key] = self.highlight_xml(self.prettify_xml(value))
                except Exception as e:
                    # Something bad happened, but we don't want to crash the program just because logging failed
                    print('XML highlighting failed: %s' % e)
        return super(PrettyXmlHandler, self).emit(record)

    def is_tty(self):
        # Check if we're outputting to a terminal
        try:
            return self.stream.isatty()
        except AttributeError:
            return False


class AnonymizingXmlHandler(PrettyXmlHandler):
    """A steaming log handler that prettifies and anonymizes log statements containing XML when output is a terminal"""
    def __init__(self, forbidden_strings, *args, **kwargs):
        self.forbidden_strings = forbidden_strings
        super(AnonymizingXmlHandler, self).__init__(*args, **kwargs)

    def parse_bytes(self, xml_bytes):
        root = parse(io.BytesIO(xml_bytes))
        for elem in root.iter():
            for attr in set(elem.keys()) & {'RootItemId', 'ItemId', 'Id', 'RootItemChangeKey', 'ChangeKey'}:
                elem.set(attr, 'DEADBEEF=')
            for s in self.forbidden_strings:
                elem.text.replace(s, '[REMOVED]')
        return root


class DummyRequest(object):
    def __init__(self, headers):
        self.headers = headers


class DummyResponse(object):
    def __init__(self, url, headers, request_headers, content=b''):
        self.status_code = 503
        self.url = url
        self.headers = headers
        self.content = content
        self.text = content.decode('utf-8', errors='ignore')
        self.request = DummyRequest(headers=request_headers)

    def iter_content(self):
        return self.content


def get_domain(email):
    try:
        return email.split('@')[1].lower()
    except (IndexError, AttributeError):
        raise ValueError("'%s' is not a valid email" % email)


def split_url(url):
    parsed_url = urlparse(url)
    # Use netloc instead og hostname since hostname is None if URL is relative
    return parsed_url.scheme == 'https', parsed_url.netloc.lower(), parsed_url.path


def get_redirect_url(response, allow_relative=True, require_relative=False):
    # allow_relative=False throws RelativeRedirect error if scheme and hostname are equal to the request
    # require_relative=True throws RelativeRedirect error if scheme and hostname are not equal to the request
    redirect_url = response.headers.get('location', None)
    if not redirect_url:
        raise TransportError('HTTP redirect but no location header')
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
    if not redirect_path.startswith('/'):
        # The path is not top-level. Add response path
        redirect_path = (response_path or '/') + redirect_path
    redirect_url = '%s://%s%s' % ('https' if redirect_has_ssl else 'http', redirect_server, redirect_path)
    if redirect_url == request_url:
        # And some are mean enough to redirect to the same location
        raise TransportError('Redirect to same location: %s' % redirect_url)
    if not allow_relative and (request_has_ssl == response_has_ssl and request_server == redirect_server):
        raise RelativeRedirect(redirect_url)
    if require_relative and (request_has_ssl != response_has_ssl or request_server != redirect_server):
        raise RelativeRedirect(redirect_url)
    return redirect_url


MAX_REDIRECTS = 5  # Define a max redirection count. We don't want to be sent into an endless redirect loop

# A collection of error classes we want to handle as general connection errors
CONNECTION_ERRORS = (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError,
                     requests.exceptions.Timeout, socket.timeout)
if not PY2:
    # Python2 does not have ConnectionResetError
    CONNECTION_ERRORS += (ConnectionResetError,)

# A collection of error classes we want to handle as TLS verification errors
TLS_ERRORS = (requests.exceptions.SSLError,)
try:
    # If pyOpenSSL is installed, requests will use it and throw this class on TLS errors
    import OpenSSL.SSL
    TLS_ERRORS += (OpenSSL.SSL.Error,)
except ImportError:
    pass


def post_ratelimited(protocol, session, url, headers, data, allow_redirects=False, stream=False):
    """
    There are two error-handling policies implemented here: a fail-fast policy intended for stand-alone scripts which
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
        https://msdn.microsoft.com/en-us/library/office/jj945066(v=exchg.150).aspx#bk_ThrottlingBatch
    """
    thread_id = get_ident()
    wait = 10  # seconds
    retry = 0
    redirects = 0
    # In Python 2, we want this to be a 'str' object so logging doesn't break (all formatting arguments are 'str').
    # We activated 'unicode_literals' at the top of this file, so it would be a 'unicode' object unless we convert
    # to 'str' explicitly. This is a no-op for Python 3.
    log_msg = str('''\
Retry: %(retry)s
Waited: %(wait)s
Timeout: %(timeout)s
Session: %(session_id)s
Thread: %(thread_id)s
Auth type: %(auth)s
URL: %(url)s
HTTP adapter: %(adapter)s
Allow redirects: %(allow_redirects)s
Streaming: %(stream)s
Response time: %(response_time)s
Status code: %(status_code)s
Request headers: %(request_headers)s
Response headers: %(response_headers)s
Request data: %(xml_request)s
Response data: %(xml_response)s
''')
    log_vals = dict(
        retry=retry,
        wait=wait,
        timeout=protocol.TIMEOUT,
        session_id=session.session_id,
        thread_id=thread_id,
        auth=session.auth,
        url=url,
        adapter=session.get_adapter(url),
        allow_redirects=allow_redirects,
        stream=stream,
        response_time=None,
        status_code=None,
        request_headers=headers,
        response_headers=None,
        xml_request=data,
        xml_response=None,
    )
    try:
        while True:
            _back_off_if_needed(protocol.credentials.back_off_until)
            log.debug('Session %s thread %s: retry %s timeout %s POST\'ing to %s after %ss wait' % (session.session_id,
                      thread_id, retry, protocol.TIMEOUT, url, wait))
            d_start = time_func()
            # Always create a dummy response for logging purposes, in case we fail in the following
            r = DummyResponse(url=url, headers={}, request_headers=headers)
            try:
                r = session.post(url=url, headers=headers, data=data, allow_redirects=False, timeout=protocol.TIMEOUT,
                                 stream=stream)
            except CONNECTION_ERRORS as e:
                log.debug('Session %s thread %s: connection error POST\'ing to %s' % (session.session_id,
                                                                                      thread_id, url))
                r = DummyResponse(url=url, headers={'TimeoutException': e}, request_headers=headers)
            finally:
                log_vals.update(
                    retry=retry,
                    wait=wait,
                    session_id=session.session_id,
                    url=str(r.url),
                    response_time=time_func() - d_start,
                    status_code=r.status_code,
                    request_headers=r.request.headers,
                    response_headers=r.headers,
                    xml_response='[STREAMING]' if stream else r.content,
                )
            log.debug(log_msg, log_vals)
            if _may_retry_on_error(r, protocol, wait):
                log.info("Session %s thread %s: Connection error on URL %s (code %s). Cool down %s secs" %
                         (session.session_id, thread_id, r.url, r.status_code, wait))
                time.sleep(wait)  # Increase delay for every retry
                retry += 1
                wait *= 2
                session = protocol.renew_session(session)
                continue
            if r.status_code in (301, 302):
                if stream:
                    r.close()
                url, redirects = _redirect_or_fail(r, redirects, allow_redirects)
                continue
            break
    except (RateLimitError, RedirectError) as e:
        log.warning(e.value)
        protocol.retire_session(session)
        raise
    except Exception as e:
        # Let higher layers handle this. Add full context for better debugging.
        log.error(str('%s: %s\n%s'), e.__class__.__name__, str(e), log_msg % log_vals)
        protocol.retire_session(session)
        raise
    if r.status_code == 500 and r.content and is_xml(r.content):
        # Some genius at Microsoft thinks it's OK to send a valid SOAP response as an HTTP 500
        log.debug('Got status code %s but trying to parse content anyway' % r.status_code)
    elif r.status_code != 200:
        protocol.retire_session(session)
        try:
            _raise_response_errors(r, protocol, log_msg, log_vals)  # Always raises an exception
        finally:
            if stream:
                r.close()
    log.debug('Session %s thread %s: Useful response from %s' % (session.session_id, thread_id, url))
    return r, session


def _back_off_if_needed(back_off_until):
    if back_off_until:
        sleep_secs = (back_off_until - datetime.datetime.now()).total_seconds()
        # The back off value may have expired within the last few milliseconds
        if sleep_secs > 0:
            log.warning('Server requested back off until %s. Sleeping %s seconds' % (back_off_until, sleep_secs))
            time.sleep(sleep_secs)


def _may_retry_on_error(response, protocol, wait):
    # The genericerrorpage.htm/internalerror.asp is ridiculous behaviour for random outages. Redirect to
    # '/internalsite/internalerror.asp' or '/internalsite/initparams.aspx' is caused by e.g. TLS certificate
    # f*ckups on the Exchange server.
    if (response.status_code == 401) \
            or (response.headers.get('connection') == 'close') \
            or (response.status_code == 302 and response.headers.get('location', '').lower() ==
                '/ews/genericerrorpage.htm?aspxerrorpath=/ews/exchange.asmx') \
            or (response.status_code == 503):
        if response.status_code not in (301, 302, 401, 503):
            # Don't retry if we didn't get a status code that we can hope to recover from
            return False
        if protocol.credentials.fail_fast:
            return False
        if wait > protocol.credentials.max_wait:
            # We lost patience. Session is cleaned up in outer loop
            raise RateLimitError(
                'Max timeout reached', url=response.url, status_code=response.status_code, total_wait=wait)
        return True
    return False


def _redirect_or_fail(response, redirects, allow_redirects):
    # Retry with no delay. If we let requests handle redirects automatically, it would issue a GET to that
    # URL. We still want to POST.
    try:
        redirect_url = get_redirect_url(response=response, allow_relative=False)
    except RelativeRedirect as e:
        log.debug("'allow_redirects' only supports relative redirects (%s -> %s)" % (response.url, e.value))
        raise RedirectError(url=e.value)
    if not allow_redirects:
        raise TransportError('Redirect not allowed but we were redirected (%s -> %s)' % (response.url, redirect_url))
    log.debug('HTTP redirected to %s' % redirect_url)
    redirects += 1
    if redirects > MAX_REDIRECTS:
        raise TransportError('Max redirect count exceeded')
    return redirect_url, redirects


def _raise_response_errors(response, protocol, log_msg, log_vals):
    cas_error = response.headers.get('X-CasErrorCode')
    if cas_error:
        if cas_error.startswith('CAS error:'):
            # Remove unnecessary text
            cas_error = cas_error.split(':', 1)[1].strip()
        raise CASError(cas_error=cas_error, response=response)
    if response.status_code == 500 and (b'The specified server version is invalid' in response.content or
                                        b'ErrorInvalidSchemaVersionForMailboxVersion' in response.content):
        raise ErrorInvalidSchemaVersionForMailboxVersion('Invalid server version')
    if b'The referenced account is currently locked out' in response.content:
        raise TransportError('The service account is currently locked out')
    if response.status_code == 401 and protocol.credentials.fail_fast:
        # This is a login failure
        raise UnauthorizedError('Wrong username or password for %s' % response.url)
    if 'TimeoutException' in response.headers:
        raise response.headers['TimeoutException']
    # This could be anything. Let higher layers handle this. Add full context for better debugging.
    raise TransportError(str('Unknown failure\n') + log_msg % log_vals)
