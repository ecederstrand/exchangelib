from __future__ import unicode_literals

import itertools
import logging
import re
import time
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from xml.etree.ElementTree import Element

from future.moves.urllib.parse import urlparse
from future.utils import PY2
from future.utils import raise_from
from six import text_type, string_types

from .errors import TransportError, RateLimitError, RedirectError, RelativeRedirect

if PY2:
    from thread import get_ident

    class ConnectionResetError(OSError):
        pass
else:
    from threading import get_ident


log = logging.getLogger(__name__)

ElementType = type(Element('x'))  # Type is auto-generated inside cElementTree
string_type = string_types[0]

# Regex of UTF-8 control characters that are illegal in XML 1.0 (and XML 1.1)
_illegal_xml_chars_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]')
# UTF-8 byte order mark which may precede the XML from an Exchange server
BOM = '\xef\xbb\xbf'


def chunkify(iterable, chunksize):
    """
    Splits an iterable into chunks of size ``chunksize``. The last chunk may be smaller than ``chunksize``.
    """
    from .queryset import QuerySet
    if hasattr(iterable, '__getitem__') and not isinstance(iterable, QuerySet):
        # list, tuple. QuerySet has __getitem__ but that evaluates the entire query greedily. We don't want that here.
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
    assert not isinstance(iterable, QuerySet)
    # QuerySet has __len__ but that evaluates the entire query greedily. We don't want that here. Instead, peek() should
    # be called on QuerySet.iterator()
    if hasattr(iterable, '__len__'):
        # list, tuple, set
        return len(iterable) == 0, iterable
    else:
        # generator
        try:
            first = next(iterable)
        except StopIteration:
            return True, iterable
        # We can't rewind a generator. Instead, chain the first element and the rest of the generator
        return False, itertools.chain([first], iterable)


def xml_to_str(tree, encoding='utf-8'):
    from xml.etree.ElementTree import tostring
    # tostring returns bytecode unless encoding is 'unicode'. We ALWAYS want bytecode so we can convert to unicode
    if encoding == 'unicode':
        encoding = 'utf-8'
    return tostring(tree, encoding=encoding).decode(encoding)


def get_xml_attr(tree, name):
    elem = tree.find(name)
    if elem is None:  # Must compare with None, see XML docs
        return None
    return  elem.text or None


def get_xml_attrs(tree, name):
    return [elem.text for elem in tree.findall(name) if elem.text is not None]


def value_to_xml_text(value):
    from .ewsdatetime import EWSDateTime
    from .folders import Attendee, Mailbox, EmailAddress, PhoneNumber
    if isinstance(value, string_types):
        return safe_xml_value(value)
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, Decimal)):
        return text_type(value)
    if isinstance(value, EWSDateTime):
        return value.ewsformat()
    if isinstance(value, PhoneNumber):
        return value.phone_number
    if isinstance(value, EmailAddress):
        return value.email
    if isinstance(value, Mailbox):
        return value.email_address
    if isinstance(value, Attendee):
        return value.mailbox.email_address
    raise ValueError('Unsupported type: %s (%s)' % (type(value), value))


def xml_text_to_value(value, field_type):
    if value is None:
        return None
    from .ewsdatetime import EWSDateTime
    from .folders import Choice, Email, AnyURI, Body, HTMLBody, MimeContent
    if field_type == string_type:
        # Return builtin str unprocessed
        return value
    if field_type in (Choice, Email, AnyURI, Body, HTMLBody, MimeContent):
        # Cast string-like values to their intended class
        return field_type(value)
    return {
        bool: lambda v: True if v == 'true' else False if v == 'false' else None,
        int: lambda v: int(v),
        Decimal: lambda v: Decimal(v),
        EWSDateTime: lambda v: EWSDateTime.from_string(v),
    }[field_type](value)


def set_xml_value(elem, value, version):
    from .folders import EWSElement
    from .ewsdatetime import EWSDateTime
    if isinstance(value, (string_types + (bool, int, Decimal, EWSDateTime))):
        elem.text = value_to_xml_text(value)
    elif isinstance(value, (tuple, list)):
        for v in value:
            if isinstance(v, EWSElement):
                assert version
                elem.append(v.to_xml(version=version))
            elif isinstance(v, ElementType):
                elem.append(v)
            elif isinstance(v, string_types):
                add_xml_child(elem, 't:String', v)
            else:
                raise AttributeError('Unsupported type %s for list value %s on elem %s' % (type(v), v, elem))
    elif isinstance(value, EWSElement):
        assert version
        elem.append(value.to_xml(version=version))
    elif isinstance(value, ElementType):
        elem.append(value)
    else:
        raise AttributeError('Unsupported type %s for value %s on elem %s' % (type(value), value, elem))
    return elem


def safe_xml_value(value, replacement='?'):
    return text_type(_illegal_xml_chars_RE.sub(replacement, value))


# Keeps a cache of Element objects to deepcopy
_deepcopy_cache = dict()


def create_element(name, **attrs):
    # copy.deepcopy() is an order of magnitude faster than creating a new Element() every time
    key = (name, tuple(attrs.items()))  # dict requires key to be immutable
    if name not in _deepcopy_cache:
        _deepcopy_cache[key] = Element(name, **attrs)
    return deepcopy(_deepcopy_cache[key])


def add_xml_child(tree, name, value):
    # We're calling add_xml_child many places where we don't have the version handy. Don't pass EWSElement or list of
    # EWSElement to this function!
    tree.append(set_xml_value(elem=create_element(name), value=value, version=None))


def to_xml(text, encoding):
    from xml.etree.ElementTree import fromstring, ParseError
    processed = text.lstrip(BOM).encode(encoding or 'utf-8')
    try:
        return fromstring(processed)
    except ParseError:
        from io import BytesIO
        from lxml.etree import XMLParser, parse, tostring
        # Exchange servers may spit out the weirdest XML. lxml is pretty good at recovering from errors
        log.warning('Fallback to lxml processing of faulty XML')
        magical_parser = XMLParser(encoding=encoding or 'utf-8', recover=True)
        root = parse(BytesIO(processed), magical_parser)
        try:
            return fromstring(tostring(root))
        except ParseError as e:
            line_no, col_no = e.lineno, e.offset
            try:
                offending_line = processed.splitlines()[line_no - 1]
            except IndexError:
                offending_line = ''
            offending_excerpt = offending_line[max(0, col_no - 20):col_no + 20].decode('ascii', 'ignore')
            raise_from(ParseError('%s\nOffending text: [...]%s[...]' % (text_type(e), offending_excerpt)), e)
        except  TypeError:
            raise ParseError('This is not XML: %s' % text)


def is_xml(text):
    """
    Helper function. Lightweight test if response is an XML doc
    """
    return text.lstrip(BOM)[0:5] == '<?xml'


class DummyRequest(object):
    headers = {}


class DummyResponse(object):
    status_code = 401
    headers = {}
    text = ''
    request = DummyRequest()


def get_domain(email):
    try:
        return email.split('@')[1].lower()
    except (IndexError, AttributeError) as e:
        raise_from(ValueError("'%s' is not a valid email" % email), e)


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
    request_has_ssl, request_server, request_path = split_url(request_url)
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
    return redirect_url, redirect_server, redirect_has_ssl


def post_ratelimited(protocol, session, url, headers, data, timeout=None, verify=True, allow_redirects=False):
    """
    There are two error-handling policies implemented here: a fail-fast policy intended for stnad-alone scripts which
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
    """
    from socket import timeout as SocketTimeout
    import requests.exceptions
    # The contract on sessions here is to return the session that ends up being used, or retiring the session if we
    # intend to raise an exception. We give up on max_wait timeout, not number of retries
    r = None
    wait = 10  # seconds
    max_wait = 3600  # seconds
    redirects = 0
    max_redirects = 5  # We don't want to be sent into an endless redirect loop
    log_msg = '''\
Retry: %(i)s
Waited: %(wait)s
Timeout: %(timeout)s
Session: %(session_id)s
Thread: %(thread_id)s
Auth type: %(auth)s
URL: %(url)s
Verify: %(verify)s
Allow redirects: %(allow_redirects)s
Response time: %(response_time)s
Status code: %(status_code)s
Request headers: %(request_headers)s
Response headers: %(response_headers)s'''
    log_vals = dict(i=0, wait=0, timeout=timeout, session_id=session.session_id, thread_id=get_ident(),
                    auth=session.auth, url=url, response_time=None, status_code=None, request_headers=headers,
                    response_headers=None, verify=verify, allow_redirects=allow_redirects)
    try:
        while True:
            log.debug('Session %(session_id)s thread %(thread_id)s: retry %(i)s timeout %(timeout)s POST\'ing to '
                      '%(url)s after %(wait)s s wait', log_vals)
            d1 = datetime.now()
            try:
                r = session.post(url=url, headers=headers, data=data, allow_redirects=False, timeout=timeout,
                                 verify=verify)
            except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError, ConnectionResetError,
                    requests.exceptions.Timeout, SocketTimeout):
                log.debug(
                    'Session %(session_id)s thread %(thread_id)s: timeout or connection error POST\'ing to %(url)s',
                    log_vals)
                r = DummyResponse()
                r.request.headers = headers
                r.headers = {'DummyResponseHeader': None}
            d2 = datetime.now()
            log_vals['response_time'] = text_type(d2 - d1)
            log_vals['status_code'] = r.status_code
            log_vals['request_headers'] = r.request.headers
            log_vals['response_headers'] = r.headers
            log.debug(log_msg, log_vals)
            log.debug('Request data: %s', data)
            log.debug('Response data: %s', getattr(r, 'text'))
            # The genericerrorpage.htm/internalerror.asp is ridiculous behaviour for random outages. Redirect to
            # '/internalsite/internalerror.asp' or '/internalsite/initparams.aspx' is caused by e.g. SSL certificate
            # f*ckups on the Exchange server.
            if (r.status_code == 401) \
                    or (r.headers.get('connection') == 'close') \
                    or (r.status_code == 302 and r.headers.get('location').lower() ==
                        '/ews/genericerrorpage.htm?aspxerrorpath=/ews/exchange.asmx') \
                    or (r.status_code == 503):
                # Maybe stale session. Get brand new one. But wait a bit, since the server may be rate-limiting us.
                # This can be 302 redirect to error page, 401 authentication error or 503 service unavailable
                if r.status_code not in (302, 401, 503):
                    # Only retry if we didn't get a useful response
                    break
                if not protocol.credentials.is_service_account:
                    break
                log_vals['i'] += 1
                log_vals['wait'] = wait  # We set it to 0 initially
                if wait > max_wait:
                    # We lost patience. Session is cleaned up in outer loop
                    raise RateLimitError(
                        'Session %(session_id)s URL %(url)s: Max timeout reached' % log_vals)
                log.info("Session %(session_id)s thread %(thread_id)s: Connection error on URL %(url)s "
                         "(code %(status_code)s). Cool down %(wait)s secs", log_vals)
                time.sleep(wait)  # Increase delay for every retry
                wait *= 2
                session = protocol.renew_session(session)
                log_vals['wait'] = wait
                log_vals['session_id'] = session.session_id
                continue
            if r.status_code == 302:
                # If we get a normal 302 redirect, requests will issue a GET to that URL. We still want to POST
                try:
                    redirect_url, server, has_ssl = get_redirect_url(response=r, allow_relative=False)
                except RelativeRedirect as e:
                    log.debug("'allow_redirects' only supports relative redirects (%s -> %s)", url, e.value)
                    raise RedirectError(url=e.value)
                if not allow_redirects:
                    raise TransportError('Redirect not allowed but we were redirected (%s -> %s)' % (url, redirect_url))
                url = redirect_url
                log_vals['url'] = url
                log.debug('302 Redirected to %s', url)
                redirects += 1
                if redirects > max_redirects:
                    raise TransportError('Max redirect count exceeded')
                continue
            break
    except (RateLimitError, RedirectError) as e:
        log.warning(e.value)
        protocol.retire_session(session)
        raise
    except Exception as e:
        # Let higher layers handle this. Add data for better debugging.
        log_msg = '%(exc_cls)s: %(exc_msg)s\n' + log_msg
        log_vals['exc_cls'] = e.__class__.__name__
        log_vals['exc_msg'] = text_type(e)
        log_msg += '\nRequest data: %(data)s'
        log_vals['data'] = data
        log_msg += '\nResponse data: %(text)s'
        try:
            log_vals['text'] = r.text
        except (NameError, AttributeError):
            log_vals['text'] = ''
        log.error(log_msg, log_vals)
        protocol.retire_session(session)
        raise
    if r.status_code != 200:
        if r.text and is_xml(r.text):
            # Some genius at Microsoft thinks it's OK to send 500 error messages with valid SOAP response
            log.debug('Got status code %s but trying to parse content anyway', r.status_code)
        else:
            # This could be anything. Let higher layers handle this
            protocol.retire_session(session)
            log_msg += '\nRequest data: %(data)s'
            log_vals['data'] = data
            try:
                log_msg += '\nResponse data: %(text)s'
                log_vals['text'] = r.text
            except (NameError, AttributeError):
                pass
            raise TransportError('Unknown failure\n' + log_msg % log_vals)
    log.debug('Session %(session_id)s thread %(thread_id)s: Useful response from %(url)s', log_vals)
    return r, session


def isanysubclass(cls, classinfos):
    try:
        iter(classinfos)
        return any([issubclass(cls, c) for c in classinfos])
    except TypeError:
        return issubclass(cls, classinfos)
