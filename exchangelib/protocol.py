# coding=utf-8
"""
A protocol is an endpoint for EWS service connections. It contains all necessary information to make HTTPS connections.

Protocols should be accessed through an Account, and are either created from a default Configuration or autodiscovered
when creating an Account.
"""
from __future__ import unicode_literals

import logging
import random
import socket
from multiprocessing.pool import ThreadPool
from threading import Lock

import requests.adapters
import requests.sessions
from future.utils import with_metaclass, python_2_unicode_compatible
from future.moves.queue import LifoQueue, Empty, Full
from six import text_type

from .credentials import Credentials
from .errors import TransportError
from .services import GetServerTimeZones, GetRoomLists, GetRooms
from .transport import get_auth_instance, get_service_authtype, get_docs_authtype, AUTH_TYPE_MAP, DEFAULT_HEADERS
from .util import split_url
from .version import Version, API_VERSIONS

log = logging.getLogger(__name__)


def close_connections():
    CachingProtocol.clear_cache()


class BaseProtocol(object):
    # Base class for Protocol which implements the bare essentials

    # The maximum number of sessions (== TCP connections, see below) we will open to this service endpoint. Keep this
    # low unless you have an agreement with the Exchange admin on the receiving end to hammer the server and
    # rate-limiting policies have been disabled for the connecting user.
    SESSION_POOLSIZE = 4
    # We want only 1 TCP connection per Session object. We may have lots of different credentials hitting the server and
    # each credential needs its own session (NTLM auth will only send credentials once and then secure the connection,
    # so a connection can only handle requests for one credential). Having multiple connections ser Session could
    # quickly exhaust the maximum number of concurrent connections the Exchange server allows from one client.
    CONNECTIONS_PER_SESSION = 1
    # Timeout for HTTP requests
    TIMEOUT = 120

    def __init__(self, service_endpoint, credentials, auth_type, verify_ssl):
        assert isinstance(credentials, Credentials)
        if auth_type is not None:
            assert auth_type in AUTH_TYPE_MAP, 'Unsupported auth type %s' % auth_type
        self.has_ssl, self.server, _ = split_url(service_endpoint)
        self.credentials = credentials
        self.service_endpoint = service_endpoint
        self.auth_type = auth_type
        self.verify_ssl = verify_ssl
        self._session_pool = None  # Consumers need to fill the session pool themselves

    def __del__(self):
        # pylint: disable=bare-except
        try:
            self.close()
        except:
            # __del__ should never fail
            pass

    def close(self):
        log.debug('Server %s: Closing sessions', self.server)
        while True:
            try:
                self._session_pool.get(block=False).close_socket(self.service_endpoint)
            except (Empty, ReferenceError, AttributeError):
                break

    def get_session(self):
        _timeout = 60  # Rate-limit messages about session starvation
        while True:
            try:
                log.debug('Server %s: Waiting for session', self.server)
                session = self._session_pool.get(timeout=_timeout)
                log.debug('Server %s: Got session %s', self.server, session.session_id)
                return session
            except Empty:
                # This is normal when we have many worker threads starving for available sessions
                log.debug('Server %s: No sessions available for %s seconds', self.server, _timeout)

    def release_session(self, session):
        # This should never fail, as we don't have more sessions than the queue contains
        log.debug('Server %s: Releasing session %s', self.server, session.session_id)
        try:
            self._session_pool.put(session, block=False)
        except Full:
            log.debug('Server %s: Session pool was already full %s', self.server, session.session_id)

    def retire_session(self, session):
        # The session is useless. Close it completely and place a fresh session in the pool
        log.debug('Server %s: Retiring session %s', self.server, session.session_id)
        session.close_socket(self.service_endpoint)
        del session
        self.release_session(self.create_session())

    def renew_session(self, session):
        # The session is useless. Close it completely and place a fresh session in the pool
        log.debug('Server %s: Renewing session %s', self.server, session.session_id)
        session.close_socket(self.service_endpoint)
        del session
        return self.create_session()

    def create_session(self):
        session = EWSSession(self)
        session.auth = get_auth_instance(credentials=self.credentials, auth_type=self.auth_type)
        # Leave this inside the loop because headers are mutable
        session.headers.update(DEFAULT_HEADERS.copy())
        scheme = 'https' if self.has_ssl else 'http'
        # We want just one connection per session. No retries, since we wrap all requests in our own retry handler
        session.mount('%s://' % scheme, requests.adapters.HTTPAdapter(
            pool_block=True,
            pool_connections=self.CONNECTIONS_PER_SESSION,
            pool_maxsize=self.CONNECTIONS_PER_SESSION,
            max_retries=0
        ))
        log.debug('Server %s: Created session %s', self.server, session.session_id)
        return session

    def __repr__(self):
        return self.__class__.__name__ + repr((self.service_endpoint, self.credentials, self.auth_type,
                                               self.verify_ssl))


class CachingProtocol(type):
    _protocol_cache = {}
    _protocol_cache_lock = Lock()

    def __call__(cls, *args, **kwargs):
        # Cache Protocol instances that point to the same endpoint and use the same credentials. This ensures that we
        # re-use thread and connection pools etc. instead of flooding the remote server. This is a modified Singleton
        # pattern.
        #
        # We ignore auth_type from kwargs in the cache key. We trust caller to supply the correct auth_type - otherwise
        # __init__ will guess the correct auth type.

        # We may be using multiple different credentials and changing our minds on SSL verification. This key
        # combination should be safe.
        _protocol_cache_key = kwargs['service_endpoint'], kwargs['credentials'], kwargs['verify_ssl']

        protocol = cls._protocol_cache.get(_protocol_cache_key)
        if isinstance(protocol, Exception):
            # The input data leads to a TransportError. Re-throw
            raise protocol
        if protocol is not None:
            return protocol

        # Acquire lock to guard against multiple threads competing to cache information. Having a per-server lock is
        # probably overkill although it would reduce lock contention.
        log.debug('Waiting for _protocol_cache_lock')
        with cls._protocol_cache_lock:
            protocol = cls._protocol_cache.get(_protocol_cache_key)
            if isinstance(protocol, Exception):
                # Someone got ahead of us while holding the lock, but the input data leads to a TransportError. Re-throw
                raise protocol
            if protocol is not None:
                # Someone got ahead of us while holding the lock
                return protocol
            log.debug("Protocol __call__ cache miss. Adding key '%s'", str(_protocol_cache_key))
            try:
                protocol = super(CachingProtocol, cls).__call__(*args, **kwargs)
            except TransportError as e:
                # This can happen if, for example, autodiscover supplies us with a bogus EWS endpoint
                log.warning('Failed to create cached protocol with key %s: %s', _protocol_cache_key, e)
                cls._protocol_cache[_protocol_cache_key] = e
                raise e
            cls._protocol_cache[_protocol_cache_key] = protocol
        return protocol

    @classmethod
    def clear_cache(mcs):
        for key, protocol in mcs._protocol_cache.items():
            service_endpoint = key[0]
            log.debug("Service endpoint '%s': Closing sessions", service_endpoint)
            protocol.close()
            del protocol
        mcs._protocol_cache.clear()


@python_2_unicode_compatible
class Protocol(with_metaclass(CachingProtocol, BaseProtocol)):
    def __init__(self, *args, **kwargs):
        version = kwargs.pop('version', None)
        super(Protocol, self).__init__(*args, **kwargs)

        scheme = 'https' if self.has_ssl else 'https'
        self.wsdl_url = '%s://%s/EWS/Services.wsdl' % (scheme, self.server)
        self.messages_url = '%s://%s/EWS/messages.xsd' % (scheme, self.server)
        self.types_url = '%s://%s/EWS/types.xsd' % (scheme, self.server)

        # Autodetect authentication type if necessary
        if self.auth_type is None:
            self.auth_type = get_service_authtype(service_endpoint=self.service_endpoint, versions=API_VERSIONS,
                                                  verify=self.verify_ssl, name=self.credentials.username)

        # Default to the auth type used by the service. We only need this if 'version' is None
        self.docs_auth_type = self.auth_type

        # Try to behave nicely with the Exchange server. We want to keep the connection open between requests.
        # We also want to re-use sessions, to avoid the NTLM auth handshake on every request.
        self._session_pool = LifoQueue(maxsize=self.SESSION_POOLSIZE)
        for _ in range(self.SESSION_POOLSIZE):
            self._session_pool.put(self.create_session(), block=False)

        if version:
            isinstance(version, Version)
            self.version = version
        else:
            # Version.guess() needs auth objects and a working session pool
            try:
                # Try to get the auth_type of 'types.xsd' so we can fetch it and look at the version contained there
                self.docs_auth_type = get_docs_authtype(verify=self.verify_ssl, docs_url=self.types_url)
            except TransportError:
                pass
            self.version = Version.guess(self)

        # Used by services to process service requests that are able to run in parallel. Thread pool should be
        # larger than the connection pool so we have time to process data without idling the connection.
        # Create the pool as the last thing here, since we may fail in the version or auth type guessing, which would
        # leave open threads around to be garbage collected.
        thread_poolsize = 4 * self.SESSION_POOLSIZE
        self.thread_pool = ThreadPool(processes=thread_poolsize)

    def get_timezones(self):
        return GetServerTimeZones(protocol=self).call()

    def get_roomlists(self):
        return GetRoomLists(protocol=self).call()

    def get_rooms(self, roomlist):
        from .properties import RoomList
        return GetRooms(protocol=self).call(roomlist=RoomList(email_address=roomlist))

    def __str__(self):
        return '''\
EWS url: %s
Product name: %s
EWS API version: %s
Build number: %s
EWS auth: %s
XSD auth: %s''' % (
            self.service_endpoint,
            self.version.fullname,
            self.version.api_version,
            self.version.build,
            self.auth_type,
            self.docs_auth_type,
        )


class EWSSession(requests.sessions.Session):
    # A requests Session object that closes the underlying socket when we need it
    def __init__(self, protocol):
        self.session_id = random.randint(1, 32767)  # Used for debugging messages in services
        self.protocol = protocol
        super(EWSSession, self).__init__()

    def close_socket(self, url):
        # Close underlying socket. This ensures we don't leave stray sockets around after program exit.
        adapter = self.get_adapter(url)
        pool = adapter.get_connection(url)
        for _ in range(pool.pool.qsize()):
            conn = pool._get_conn()
            if conn.sock:
                log.debug('Closing socket %s', text_type(conn.sock.socket.getsockname()))
                conn.sock.socket.shutdown(socket.SHUT_RDWR)
                conn.sock.close()
