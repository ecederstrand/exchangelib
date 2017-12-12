from __future__ import unicode_literals

from copy import deepcopy
from decimal import Decimal
import io
import itertools
import logging
from multiprocessing import Lock
import re
import socket
import time
from xml.etree.ElementTree import Element, fromstring, ParseError

from lxml.etree import XMLParser, parse, tostring
from future.moves.urllib.parse import urlparse
from future.moves._thread import get_ident
from future.utils import PY2
from pygments import highlight
from pygments.lexers import XmlLexer
from pygments.formatters import TerminalFormatter
import requests.exceptions
from six import text_type, string_types

from .errors import TransportError, RateLimitError, RedirectError, RelativeRedirect, CASError, UnauthorizedError, \
    ErrorInvalidSchemaVersionForMailboxVersion

time_func = time.time if PY2 else time.monotonic


log = logging.getLogger(__name__)

ElementType = type(Element('x'))  # Type is auto-generated inside cElementTree
string_type = string_types[0]

# Regex of UTF-8 control characters that are illegal in XML 1.0 (and XML 1.1)
_illegal_xml_chars_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]')
# UTF-8 byte order mark which may precede the XML from an Exchange server
BOM = '\xef\xbb\xbf'
BOM_LEN = len(BOM)


def is_iterable(value, generators_allowed=False):
    """
    Checks if value is a list-like object. Don't match generators and generator-like objects here by default, because
    callers don't necessarily guarantee that they only iterate the value once. Take care to not match string types.

    :param value: any type of object
    :param generators_allowed: if True, generators will be treated as iterable
    :return: True or False
    """
    if generators_allowed:
        if not isinstance(value, string_types) and hasattr(value, '__iter__'):
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
    assert not isinstance(iterable, QuerySet)
    if hasattr(iterable, '__len__'):
        # tuple, list, set
        return len(iterable) == 0, iterable
    else:
        # generator
        try:
            first = next(iterable)
        except StopIteration:
            return True, iterable
        # We can't rewind a generator. Instead, chain the first element and the rest of the generator
        return False, itertools.chain([first], iterable)


def xml_to_str(tree, encoding=None, xml_declaration=False):
    from xml.etree.ElementTree import ElementTree
    # tostring() returns bytecode unless encoding is 'unicode', and does not reliably produce an XML declaration. We
    # ALWAYS want bytecode so we can convert to unicode explicitly.
    if encoding is None:
        assert not xml_declaration
        if PY2:
            stream = io.BytesIO()
        else:
            stream = io.StringIO()
            encoding = 'unicode'
    else:
        stream = io.BytesIO()
        stream.write(('<?xml version="1.0" encoding="%s"?>' % encoding).encode(encoding))
    ElementTree(tree).write(stream, encoding=encoding, xml_declaration=False, method='xml')
    return stream.getvalue()


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
        EWSDateTime: EWSDateTime.from_string,
        string_type: lambda v: v
    }[value_type](value)


def set_xml_value(elem, value, version):
    from .fields import FieldPath, FieldOrder
    from .folders import EWSElement
    from .ewsdatetime import EWSDateTime, EWSDate
    if isinstance(value, string_types + (bool, bytes, int, Decimal, EWSDate, EWSDateTime)):
        elem.text = value_to_xml_text(value)
    elif is_iterable(value, generators_allowed=True):
        for v in value:
            if isinstance(v, (FieldPath, FieldOrder)):
                elem.append(v.to_xml())
            elif isinstance(v, EWSElement):
                assert version
                elem.append(v.to_xml(version=version))
            elif isinstance(v, ElementType):
                elem.append(v)
            elif isinstance(v, string_types):
                add_xml_child(elem, 't:String', v)
            else:
                raise ValueError('Unsupported type %s for list element %s on elem %s' % (type(v), v, elem))
    elif isinstance(value, (FieldPath, FieldOrder)):
        elem.append(value.to_xml())
    elif isinstance(value, EWSElement):
        assert version
        elem.append(value.to_xml(version=version))
    elif isinstance(value, ElementType):
        elem.append(value)
    else:
        raise ValueError('Unsupported type %s for value %s on elem %s' % (type(value), value, elem))
    return elem


def safe_xml_value(value, replacement='?'):
    return text_type(_illegal_xml_chars_RE.sub(replacement, value))


# Keeps a cache of Element objects to deepcopy
_deepcopy_cache = dict()
_deepcopy_cache_lock = Lock()


def create_element(name, **attrs):
    # copy.deepcopy() is an order of magnitude faster than creating a new Element() every time
    key = (name, tuple(attrs.items()))  # dict requires key to be immutable
    try:
        cached_elem = _deepcopy_cache[key]
    except KeyError:
        with _deepcopy_cache_lock:
            # Use setdefault() because another thread may have filled the cache while we were waiting for the lock
            cached_elem = _deepcopy_cache.setdefault(key, Element(name, **attrs))
    return deepcopy(cached_elem)


def add_xml_child(tree, name, value):
    # We're calling add_xml_child many places where we don't have the version handy. Don't pass EWSElement or list of
    # EWSElement to this function!
    tree.append(set_xml_value(elem=create_element(name), value=value, version=None))


def to_xml(text):
    try:
        if PY2:
            # On python2, fromstring expects an encoded string
            return fromstring((text[BOM_LEN:] if text.startswith(BOM) else text).encode('utf-8'))
        return fromstring(text[BOM_LEN:] if text.startswith(BOM) else text)
    except ParseError:
        # Exchange servers may spit out the weirdest XML. lxml is pretty good at recovering from errors
        log.warning('Fallback to lxml processing of faulty XML')
        magical_parser = XMLParser(recover=True)
        no_bom_text = text[BOM_LEN:] if text.startswith(BOM) else text
        root = parse(io.BytesIO(no_bom_text.encode('utf-8')), magical_parser)
        try:
            return fromstring(tostring(root))
        except ParseError as e:
            if hasattr(e, 'position'):
                e.lineno, e.offset = e.position
            if not e.lineno:
                raise ParseError('%s' % text_type(e))
            try:
                offending_line = no_bom_text.splitlines()[e.lineno - 1]
            except IndexError:
                raise ParseError('%s' % text_type(e))
            else:
                offending_excerpt = offending_line[max(0, e.offset - 20):e.offset + 20]
                raise ParseError('%s\nOffending text: [...]%s[...]' % (text_type(e), offending_excerpt))
        except TypeError:
            raise ParseError('This is not XML: %s' % text)


def is_xml(text):
    """
    Helper function. Lightweight test if response is an XML doc
    """
    if text.startswith(BOM):
        return text[BOM_LEN:BOM_LEN + 5] == '<?xml'
    return text[:5] == '<?xml'


class PrettyXmlHandler(logging.StreamHandler):
    """A steaming log handler that prettifies log statements containing XML when output is a terminal"""
    @staticmethod
    def prettify_xml(xml_bytes):
        # Re-formats an XML document to a consistent style
        return tostring(parse(
            io.BytesIO(xml_bytes)),
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
                if not is_xml(value[:10].decode('utf-8', errors='ignore')):
                    continue
                try:
                    if PY2:
                        record.args[key] = self.highlight_xml(self.prettify_xml(value)).encode('utf-8')
                    else:
                        record.args[key] = self.highlight_xml(self.prettify_xml(value))
                except Exception:
                    # Something bad happened, but we don't want to crash the program just because logging failed
                    pass
        return super(PrettyXmlHandler, self).emit(record)

    def is_tty(self):
        # Check if we're outputting to a terminal
        isatty = getattr(self.stream, 'isatty', None)
        return isatty and isatty()


class DummyRequest(object):
    def __init__(self, headers):
        self.headers = headers


class DummyResponse(object):
    def __init__(self, url, headers, request_headers):
        self.status_code = 503
        self.url = url
        self.headers = headers
        self.text = ''
        self.content = b''
        self.request = DummyRequest(headers=request_headers)


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
        raise TransportError('302 redirect but no location header')
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

# A collection of error classes we want to handle as SSL verification errors
SSL_ERRORS = (requests.exceptions.SSLError,)
try:
    # If pyOpenSSL is installed, requests will use it and throw this class on SSL errors
    import OpenSSL.SSL
    SSL_ERRORS += (OpenSSL.SSL.Error,)
except ImportError:
    pass


def post_ratelimited(protocol, session, url, headers, data, allow_redirects=False):
    """
    There are two error-handling policies implemented here: a fail-fast policy intended for stand-alone scripts which
    fails on all responses except HTTP 200. The other policy is intended for long-running tasks that need to respect
    rate-limiting errors from the server and paper over outages of up to 1 hour.

    Wrap POST requests in a try-catch loop with a lot of error handling logic and some basic rate-limiting. If a request
    fails, and some conditions are met, the loop waits in increasing intervals, up to 1 hour, before trying again. The
    reason for this is that servers often malfunction for short periods of time, either because of ongoing data
    migrations or other maintenance tasks, misconfigurations or heavy load, or because the connecting user has hit a
    throttling policy limit.

    If the loop exited early, consumers of exchangelib that don't implement their own rate-limiting code could quickly
    swamp such a server with new requests. That would only make things worse. Instead, it's better if the request loop
    waits patiently until the server is functioning again.

    If the connecting user has hit a throttling policy, then the server will start to malfunction in many interesting
    ways, but never actually tell the user what is happening. There is no way to distinguish this situation from other
    malfunctions. The only cure is to stop making requests.

    The contract on sessions here is to return the session that ends up being used, or retiring the session if we
    intend to raise an exception. We give up on max_wait timeout, not number of retries.

    An additional resource on handling throttling policies and client backoff strategies:
        https://msdn.microsoft.com/en-us/library/office/jj945066(v=exchg.150).aspx#bk_ThrottlingBatch
    """
    thread_id = get_ident()
    wait = 10  # seconds
    retry = 0
    redirects = 0
    log_msg = '''\
Retry: %(retry)s
Waited: %(wait)s
Timeout: %(timeout)s
Session: %(session_id)s
Thread: %(thread_id)s
Auth type: %(auth)s
URL: %(url)s
HTTP adapter: %(adapter)s
Allow redirects: %(allow_redirects)s
Response time: %(response_time)s
Status code: %(status_code)s
Request headers: %(request_headers)s
Response headers: %(response_headers)s
Request data: %(xml_request)s
Response data: %(xml_response)s
'''
    try:
        while True:
            log.debug('Session %s thread %s: retry %s timeout %s POST\'ing to %s after %ss wait', session.session_id,
                      thread_id, retry, protocol.TIMEOUT, url, wait)
            d_start = time_func()
            try:
                r = session.post(url=url, headers=headers, data=data, allow_redirects=False, timeout=protocol.TIMEOUT)
            except CONNECTION_ERRORS as e:
                log.debug('Session %s thread %s: connection error POST\'ing to %s', session.session_id, thread_id, url)
                r = DummyResponse(url=url, headers={'TimeoutException': e}, request_headers=headers)
            except:
                # Always create a dummy response for logging purposes, before re-raising
                r = DummyResponse(url=url, headers={}, request_headers=headers)
                raise
            finally:
                log_vals = dict(
                    retry=retry, wait=wait, timeout=protocol.TIMEOUT, session_id=session.session_id, thread_id=thread_id,
                    auth=session.auth, url=r.url, adapter=session.get_adapter(url), allow_redirects=allow_redirects,
                    response_time=time_func() - d_start, status_code=r.status_code, request_headers=r.request.headers,
                    response_headers=r.headers, xml_request=data, xml_response=r.content,
                )
            log.debug(log_msg, log_vals)
            if _may_retry_on_error(r, protocol, wait):
                log.info("Session %s thread %s: Connection error on URL %s (code %s). Cool down %s secs",
                         session.session_id, thread_id, r.url, r.status_code, wait)
                time.sleep(wait)  # Increase delay for every retry
                retry += 1
                wait *= 2
                session = protocol.renew_session(session)
                continue
            if r.status_code in (301, 302):
                url, redirects = _redirect_or_fail(r, redirects, allow_redirects)
                continue
            break
    except (RateLimitError, RedirectError) as e:
        log.warning(e.value)
        protocol.retire_session(session)
        raise
    except Exception as e:
        # Let higher layers handle this. Add full context for better debugging.
        log.error('%s: %s\n%s', e.__class__.__name__, text_type(e), log_msg % log_vals)
        protocol.retire_session(session)
        raise
    if r.status_code == 500 and r.text and is_xml(r.text):
        # Some genius at Microsoft thinks it's OK to send a valid SOAP response as an HTTP 500
        log.debug('Got status code %s but trying to parse content anyway', r.status_code)
    elif r.status_code != 200:
        protocol.retire_session(session)
        _raise_response_errors(r, protocol, log_msg, log_vals)  # Always raises an exception
    log.debug('Session %s thread %s: Useful response from %s', session.session_id, thread_id, url)
    return r, session


def _may_retry_on_error(r, protocol, wait):
    # The genericerrorpage.htm/internalerror.asp is ridiculous behaviour for random outages. Redirect to
    # '/internalsite/internalerror.asp' or '/internalsite/initparams.aspx' is caused by e.g. SSL certificate
    # f*ckups on the Exchange server.
    if (r.status_code == 401) \
            or (r.headers.get('connection') == 'close') \
            or (r.status_code == 302 and r.headers.get('location', '').lower() ==
                '/ews/genericerrorpage.htm?aspxerrorpath=/ews/exchange.asmx') \
            or (r.status_code == 503):
        # Maybe stale session. Get brand new one. But wait a bit, since the server may be rate-limiting us.
        # This can be 302 redirect to error page, 401 authentication error or 503 service unavailable
        if r.status_code not in (302, 401, 503):
            # Only retry if we didn't get a useful response
            return False
        if protocol.credentials.fail_fast:
            return False
        if wait > protocol.credentials.max_wait:
            # We lost patience. Session is cleaned up in outer loop
            raise RateLimitError('URL %s: Max timeout reached' % r.url)
        return True
    return False


def _redirect_or_fail(r, redirects, allow_redirects):
    # Retry with no delay. If we let requests handle redirects automatically, it would issue a GET to that
    # URL. We still want to POST.
    try:
        redirect_url = get_redirect_url(response=r, allow_relative=False)
    except RelativeRedirect as e:
        log.debug("'allow_redirects' only supports relative redirects (%s -> %s)", r.url, e.value)
        raise RedirectError(url=e.value)
    if not allow_redirects:
        raise TransportError('Redirect not allowed but we were redirected (%s -> %s)' % (r.url, redirect_url))
    log.debug('302 Redirected to %s', redirect_url)
    redirects += 1
    if redirects > MAX_REDIRECTS:
        raise TransportError('Max redirect count exceeded')
    return redirect_url, redirects


def _raise_response_errors(r, protocol, log_msg, log_vals):
    cas_error = r.headers.get('X-CasErrorCode')
    if cas_error:
        raise CASError(cas_error=cas_error, response=r)
    if r.status_code == 500 and ('The specified server version is invalid' in r.text or
                                 'ErrorInvalidSchemaVersionForMailboxVersion' in r.text):
        raise ErrorInvalidSchemaVersionForMailboxVersion('Invalid server version')
    if 'The referenced account is currently locked out' in r.text:
        raise TransportError('The service account is currently locked out')
    if r.status_code == 401 and protocol.credentials.fail_fast:
        # This is a login failure
        raise UnauthorizedError('Wrong username or password for %s' % r.url)
    if 'TimeoutException' in r.headers:
        raise r.headers['TimeoutException']
    # This could be anything. Let higher layers handle this. Add full context for better debugging.
    raise TransportError('Unknown failure\n' + log_msg % log_vals)
