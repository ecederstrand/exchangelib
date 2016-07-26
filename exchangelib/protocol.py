"""
A protocol is an endpoint for EWS service connections. It contains all necessary information to make HTTPS connections.

Protocols should be accessed through an Account, and are either created from a default Configuration or autodiscovered
when creating an Account.
"""
import socket
import queue
from multiprocessing.pool import ThreadPool
import logging
from collections import defaultdict
from threading import Lock
from urllib import parse
import random

from requests import adapters, Session

from .credentials import Credentials
from .errors import TransportError
from .transport import get_auth_instance, get_service_authtype, get_docs_authtype, test_credentials
from .version import Version, API_VERSIONS

log = logging.getLogger(__name__)

# Used to cache version and auth types for visited servers
_server_cache = defaultdict(dict)
_server_cache_lock = Lock()

POOLSIZE = 4
TIMEOUT = 120


def close_connections():
    for cached_key, cached_values in _server_cache.items():
        server = cached_key[0]  # cached_key = server, username
        cached_protocol = Protocol('https://%s/EWS/Exchange.asmx' % server, True, Credentials('', ''))
        cached_protocol.close()


class Protocol:
    SESSION_POOLSIZE = 1

    def __init__(self, ews_url, has_ssl, credentials, ews_auth_type=None):
        assert isinstance(credentials, Credentials)
        self.server = parse.urlparse(ews_url).hostname.lower()
        self.has_ssl = has_ssl
        self.ews_url = ews_url
        scheme = 'https' if self.has_ssl else 'http'
        self.wsdl_url = '%s://%s/EWS/Services.wsdl' % (scheme, self.server)
        self.messages_url = '%s://%s/EWS/messages.xsd' % (scheme, self.server)
        self.types_url = '%s://%s/EWS/types.xsd' % (scheme, self.server)
        self.credentials = credentials
        self.timeout = TIMEOUT

        # Acquire lock to guard against multiple threads competing to cache information. Having a per-server lock is
        # overkill.
        log.debug('Waiting for _server_cache_lock')
        with _server_cache_lock:
            _server_cache_key = self.server, self.credentials.username
            if _server_cache_key in _server_cache:
                # Get cached version and auth types and session / thread pools
                log.debug("Cache hit for server '%s'", self.server)
                for k, v in _server_cache[_server_cache_key].items():
                    setattr(self, k, v)

                if ews_auth_type:
                    if ews_auth_type != self.ews_auth_type:
                        # Some Exchange servers just can't make up their mind
                        log.debug('Auth type mismatch on server %s. %s != %s' % (self.server, ews_auth_type,
                                                                                 self.ews_auth_type))
            else:
                log.debug("Cache miss. Adding server '%s', poolsize %s, timeout %s", self.server, POOLSIZE, TIMEOUT)
                # Autodetect authentication type if necessary
                self.ews_auth_type = ews_auth_type or get_service_authtype(server=self.server, has_ssl=self.has_ssl,
                                                                           ews_url=ews_url, versions=API_VERSIONS)
                self.docs_auth_type = get_docs_authtype(server=self.server, has_ssl=self.has_ssl, url=self.types_url)

                # Try to behave nicely with the Exchange server. We want to keep the connection open between requests.
                # We also want to re-use sessions, to avoid the NTLM auth handshake on every request.
                assert POOLSIZE > 0
                self._session_pool = queue.LifoQueue(maxsize=POOLSIZE)
                for i in range(POOLSIZE):
                    self._session_pool.put(self.create_session(), block=False)

                # Used by services to process service requests that are able to run in parallel. Thread pool should be
                # larger than connection the pool so we have time to process data without idling the connection.
                thread_poolsize = 4 * POOLSIZE
                self.thread_pool = ThreadPool(processes=thread_poolsize)

                # Needs auth objects and a working session pool
                self.version = Version.guess(self)

                # Cache results
                _server_cache[_server_cache_key] = dict(
                    version=self.version,
                    ews_auth_type=self.ews_auth_type,
                    docs_auth_type=self.docs_auth_type,
                    thread_pool=self.thread_pool,
                    _session_pool=self._session_pool,
                )
        log.debug('_server_cache_lock released')

    def close(self):
        log.debug('Server %s: Closing sessions', self.server)
        while True:
            try:
                self._session_pool.get(block=False).close_socket(self.ews_url)
            except queue.Empty:
                break

    def get_session(self):
        _timeout = 60  # Rate-limit messages about session starvation
        while True:
            try:
                log.debug('Server %s: Waiting for session', self.server)
                session = self._session_pool.get(timeout=_timeout)
                log.debug('Server %s: Got session %s', self.server, session.session_id)
                return session
            except queue.Empty:
                # This is normal when we have many worker threads starving for available sessions
                log.debug('Server %s: No sessions available for %s seconds', self.server, _timeout)

    def release_session(self, session):
        # This should never fail, as we don't have more sessions than the queue contains
        log.debug('Server %s: Releasing session %s', self.server, session.session_id)
        try:
            self._session_pool.put(session, block=False)
        except queue.Full:
            log.debug('Server %s: Session pool was already full %s', self.server, session.session_id)

    def retire_session(self, session):
        # The session is useless. Close it completely and place a fresh session in the pool
        log.debug('Server %s: Retiring session %s', self.server, session.session_id)
        session.close_socket(self.ews_url)
        del session
        self.release_session(self.create_session())

    def renew_session(self, session):
        # The session is useless. Close it completely and place a fresh session in the pool
        log.debug('Server %s: Renewing session %s', self.server, session.session_id)
        session.close_socket(self.ews_url)
        del session
        return self.create_session()

    def test(self):
        # We need the version for this
        try:
            socket.gethostbyname_ex(self.server)[2][0]
        except socket.gaierror as e:
            raise TransportError("Server '%s' does not exist" % self.server) from e
        return test_credentials(protocol=self)

    def __str__(self):
        return '''\
EWS url: %s
Product version (according to XSD): %s
Full name: %s
Build numbers: %s
EWS auth: %s
XSD auth: %s''' % (
            self.ews_url,
            self.version.api_version,
            self.version.fullname,
            self.version.build,
            self.ews_auth_type,
            self.docs_auth_type,
        )

    def create_session(self):
        session = EWSSession(self)
        session.auth = get_auth_instance(credentials=self.credentials, auth_type=self.ews_auth_type)
        # Leave this inside the loop because headers are mutable
        headers = {'Content-Type': 'text/xml; charset=utf-8', 'Accept-Encoding': 'compress, gzip'}
        session.headers.update(headers)
        scheme = 'https' if self.has_ssl else 'http'
        # We want just one connection per session. No retries, since we wrap all requests in our own retry handler
        assert self.SESSION_POOLSIZE > 0
        session.mount('%s://' % scheme, adapters.HTTPAdapter(pool_block=True, pool_connections=self.SESSION_POOLSIZE,
                                                             pool_maxsize=self.SESSION_POOLSIZE, max_retries=0))
        log.debug('Server %s: Created session %s', self.server, session.session_id)
        return session


class EWSSession(Session):
    def __init__(self, protocol):
        self.session_id = random.randint(1, 32767)  # Used for debugging messages in services
        self.protocol = protocol
        super().__init__()

    def close_socket(self, url):
        # Close underlying socket. This ensures we don't leave stray sockets around after program exit.
        adapter = self.get_adapter(url)
        pool = adapter.get_connection(url)
        for i in range(pool.pool.qsize()):
            conn = pool._get_conn()
            if conn.sock:
                log.debug('Closing socket %s', str(conn.sock.getsockname()))
                conn.sock.shutdown(socket.SHUT_RDWR)
                conn.sock.close()

    def __enter__(self):
        return super().__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.protocol.release_session(self)
        else:
            self.protocol.retire_session(self)
        # return super().__exit__()  # We don't want to close the session socket when we have used the session
