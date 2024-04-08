"""
A protocol is an endpoint for EWS service connections. It contains all necessary information to make HTTPS connections.

Protocols should be accessed through an Account, and are either created from a default Configuration or autodiscovered
when creating an Account.
"""

import abc
import datetime
import logging
import random
from contextlib import suppress
from queue import Empty, LifoQueue
from threading import Lock

import requests.adapters
import requests.sessions
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from .credentials import BaseOAuth2Credentials
from .errors import (
    CASError,
    ErrorInternalServerTransientError,
    ErrorInvalidSchemaVersionForMailboxVersion,
    ErrorServerBusy,
    InvalidTypeError,
    MalformedResponseError,
    RateLimitError,
    RedirectError,
    RelativeRedirect,
    SessionPoolMaxSizeReached,
    SessionPoolMinSizeReached,
    TransportError,
    UnauthorizedError,
)
from .properties import (
    ENTRY_ID,
    EWS_ID,
    AlternateId,
    DLMailbox,
    FreeBusyViewOptions,
    MailboxData,
    RoomList,
    TimeWindow,
    TimeZone,
)
from .services import (
    ConvertId,
    ExpandDL,
    GetRoomLists,
    GetRooms,
    GetSearchableMailboxes,
    GetServerTimeZones,
    GetUserAvailability,
    ResolveNames,
)
from .transport import CREDENTIALS_REQUIRED, DEFAULT_HEADERS, NTLM, OAUTH2, get_auth_instance, get_service_authtype
from .util import _get_retry_after, get_redirect_url, is_xml
from .version import Version

log = logging.getLogger(__name__)


def close_connections():
    CachingProtocol.clear_cache()


class BaseProtocol:
    """Base class for Protocol which implements the bare essentials."""

    # The maximum number of sessions (== TCP connections, see below) we will open to this service endpoint. Keep this
    # low unless you have an agreement with the Exchange admin on the receiving end to hammer the server and
    # rate-limiting policies have been disabled for the connecting user. Changing this setting only makes sense if
    # you are using threads to run multiple concurrent workers in this process.
    SESSION_POOLSIZE = 1
    # We want only 1 TCP connection per Session object. We may have lots of different credentials hitting the server and
    # each credential needs its own session (NTLM auth will only send credentials once and then secure the connection,
    # so a connection can only handle requests for one credential). Having multiple connections per Session could
    # quickly exhaust the maximum number of concurrent connections the Exchange server allows from one client.
    CONNECTIONS_PER_SESSION = 1
    # The number of times a session may be reused before creating a new session object. 'None' means "infinite".
    # Discarding sessions after a certain number of usages may limit memory leaks in the Session object.
    MAX_SESSION_USAGE_COUNT = None
    # Timeout for HTTP requests
    TIMEOUT = 120
    RETRY_WAIT = 10  # Seconds to wait before retry on connection errors

    # The adapter class to use for HTTP requests. Override this if you need e.g. proxy support or specific TLS versions
    HTTP_ADAPTER_CLS = requests.adapters.HTTPAdapter

    # The User-Agent header to use for HTTP requests. Override this to set an app-specific one
    USERAGENT = None

    def __init__(self, config):
        self.config = config

        self._session_pool_size = 0
        self._session_pool_maxsize = config.max_connections or self.SESSION_POOLSIZE

        # Try to behave nicely with the remote server. We want to keep the connection open between requests.
        # We also want to re-use sessions, to avoid the NTLM auth handshake on every request. We must know the
        # authentication method to create sessions.
        self._session_pool = LifoQueue()
        self._session_pool_lock = Lock()

    @property
    def service_endpoint(self):
        return self.config.service_endpoint

    @abc.abstractmethod
    def get_auth_type(self):
        """Autodetect authentication type"""

    @property
    def auth_type(self):
        # Autodetect authentication type if necessary
        if self.config.auth_type is None:
            self.config.auth_type = self.get_auth_type()
        return self.config.auth_type

    @property
    def credentials(self):
        return self.config.credentials

    @credentials.setter
    def credentials(self, value):
        # We are updating credentials, but that doesn't automatically propagate to the session objects. The simplest
        # solution is to just kill the sessions in the pool.
        with self._session_pool_lock:
            self.config._credentials = value
            self.close()

    @property
    def max_connections(self):
        return self._session_pool_maxsize

    @max_connections.setter
    def max_connections(self, value):
        with self._session_pool_lock:
            self._session_pool_maxsize = value or self.SESSION_POOLSIZE

    @property
    def retry_policy(self):
        return self.config.retry_policy

    @property
    def server(self):
        return self.config.server

    def __getstate__(self):
        # The session pool and lock cannot be pickled
        state = self.__dict__.copy()
        del state["_session_pool"]
        del state["_session_pool_lock"]
        return state

    def __setstate__(self, state):
        # Restore the session pool and lock
        self.__dict__.update(state)
        self._session_pool = LifoQueue()
        self._session_pool_lock = Lock()

    def __del__(self):
        # pylint: disable=bare-except
        try:
            self.close()
        except Exception:  # nosec
            # __del__ should never fail
            pass

    def close(self):
        log.debug("Server %s: Closing sessions", self.server)
        while True:
            try:
                session = self._session_pool.get(block=False)
                self.close_session(session)
                self._session_pool_size -= 1
            except Empty:
                break

    @classmethod
    def get_adapter(cls):
        # We want just one connection per session. No retries, since we wrap all requests in our own retry handler
        return cls.HTTP_ADAPTER_CLS(
            pool_block=True,
            pool_connections=cls.CONNECTIONS_PER_SESSION,
            pool_maxsize=cls.CONNECTIONS_PER_SESSION,
            max_retries=0,
        )

    @property
    def session_pool_size(self):
        return self._session_pool_size

    def increase_poolsize(self):
        """Increases the session pool size. We increase by one session per call."""
        # Create a single session and insert it into the pool. We need to protect this with a lock while we are changing
        # the pool size variable, to avoid race conditions. We must not exceed the pool size limit.
        if self._session_pool_size >= self._session_pool_maxsize:
            raise SessionPoolMaxSizeReached("Session pool size cannot be increased further")
        with self._session_pool_lock:
            if self._session_pool_size >= self._session_pool_maxsize:
                log.debug("Session pool size was increased in another thread")
                return
            log.debug(
                "Server %s: Increasing session pool size from %s to %s",
                self.server,
                self._session_pool_size,
                self._session_pool_size + 1,
            )
            self._session_pool.put(self.create_session(), block=False)
            self._session_pool_size += 1

    def decrease_poolsize(self):
        """Decreases the session pool size in response to error messages from the server requesting to rate-limit
        requests. We decrease by one session per call.
        """
        # Take a single session from the pool and discard it. We need to protect this with a lock while we are changing
        # the pool size variable, to avoid race conditions. We must keep at least one session in the pool.
        if self._session_pool_size <= 1:
            raise SessionPoolMinSizeReached("Session pool size cannot be decreased further")
        with self._session_pool_lock:
            if self._session_pool_size <= 1:
                log.debug("Session pool size was decreased in another thread")
                return
            log.warning(
                "Server %s: Decreasing session pool size from %s to %s",
                self.server,
                self._session_pool_size,
                self._session_pool_size - 1,
            )
            session = self.get_session()
            self.close_session(session)
            self._session_pool_size -= 1

    def get_session(self):
        # Try to get a session from the queue. If the queue is empty, try to add one more session to the queue. If the
        # queue is already at its max, wait until a session becomes available.
        _timeout = 60  # Rate-limit messages about session starvation
        try:
            session = self._session_pool.get(block=False)
            log.debug("Server %s: Got session immediately", self.server)
        except Empty:
            with suppress(SessionPoolMaxSizeReached):
                self.increase_poolsize()
            while True:
                try:
                    log.debug("Server %s: Waiting for session", self.server)
                    session = self._session_pool.get(timeout=_timeout)
                    break
                except Empty:
                    # This is normal when we have many worker threads starving for available sessions
                    log.debug("Server %s: No sessions available for %s seconds", self.server, _timeout)
        log.debug("Server %s: Got session %s", self.server, session.session_id)
        session.usage_count += 1
        return session

    def release_session(self, session):
        # This should never fail, as we don't have more sessions than the queue contains
        log.debug("Server %s: Releasing session %s", self.server, session.session_id)
        if self.MAX_SESSION_USAGE_COUNT and session.usage_count >= self.MAX_SESSION_USAGE_COUNT:
            log.debug("Server %s: session %s usage exceeded limit. Discarding", self.server, session.session_id)
            session = self.renew_session(session)
        self._session_pool.put(session, block=False)

    def close_session(self, session):
        if isinstance(self.credentials, BaseOAuth2Credentials) and isinstance(
            self.credentials.client, BackendApplicationClient
        ):
            # Reset access token
            with self.credentials.lock:
                self.credentials.access_token = None
        session.close()
        del session

    def retire_session(self, session):
        # The session is useless. Close it completely and place a fresh session in the pool
        log.debug("Server %s: Retiring session %s", self.server, session.session_id)
        self.close_session(session)
        self.release_session(self.create_session())

    def renew_session(self, session):
        # The session is useless. Close it completely and place a fresh session in the pool
        log.debug("Server %s: Renewing session %s", self.server, session.session_id)
        self.close_session(session)
        return self.create_session()

    def refresh_credentials(self, session):
        # Credentials need to be refreshed, probably due to an OAuth
        # access token expiring. If we've gotten here, it's because the
        # application didn't provide an OAuth client secret, so we can't
        # handle token refreshing for it.
        with self.credentials.lock:
            if self.credentials.sig() == session.credentials_sig:
                # Credentials have not been refreshed by another thread:
                # they're the same as the session was created with. If
                # this isn't the case, we can just go ahead with a new
                # session using the already-updated credentials.
                self.credentials.refresh(session=session)
        return self.renew_session(session)

    def create_session(self):
        if self.credentials is None:
            if self.auth_type in CREDENTIALS_REQUIRED:
                raise ValueError(f"Auth type {self.auth_type!r} requires credentials")
            session = self.raw_session(self.service_endpoint)
            session.auth = get_auth_instance(auth_type=self.auth_type)
        else:
            if isinstance(self.credentials, BaseOAuth2Credentials):
                with self.credentials.lock:
                    session = self.create_oauth2_session()
                    # Keep track of the credentials used to create this session. If and when we need to renew
                    # credentials (for example, refreshing an OAuth access token), this lets us easily determine whether
                    # the credentials have already been refreshed in another thread by the time this session tries.
                    session.credentials_sig = self.credentials.sig()
            else:
                if self.auth_type == NTLM and self.credentials.type == self.credentials.EMAIL:
                    username = "\\" + self.credentials.username
                else:
                    username = self.credentials.username
                session = self.raw_session(self.service_endpoint)
                session.auth = get_auth_instance(
                    auth_type=self.auth_type, username=username, password=self.credentials.password
                )

        # Add some extra info
        session.session_id = random.randint(10000, 99999)  # Used for debugging messages in services
        session.usage_count = 0
        log.debug("Server %s: Created session %s", self.server, session.session_id)
        return session

    def create_oauth2_session(self):
        session = self.raw_session(
            self.service_endpoint,
            oauth2_client=self.credentials.client,
            oauth2_session_params=self.credentials.session_params(),
            oauth2_token_endpoint=self.credentials.token_url,
        )
        if not session.token:
            # Fetch the token explicitly -- it doesn't occur implicitly
            token = session.fetch_token(
                token_url=self.credentials.token_url,
                client_id=self.credentials.client_id,
                client_secret=self.credentials.client_secret,
                scope=self.credentials.scope,
                timeout=self.TIMEOUT,
                **self.credentials.token_params(),
            )
            # Allow the credentials object to update its copy of the new token, and give the application an opportunity
            # to cache it.
            self.credentials.on_token_auto_refreshed(token)
        session.auth = get_auth_instance(auth_type=OAUTH2, client=self.credentials.client)

        return session

    @classmethod
    def raw_session(cls, prefix, oauth2_client=None, oauth2_session_params=None, oauth2_token_endpoint=None):
        if oauth2_client:
            session = OAuth2Session(client=oauth2_client, **(oauth2_session_params or {}))
        else:
            session = requests.sessions.Session()
        session.headers.update(DEFAULT_HEADERS)
        session.headers["User-Agent"] = cls.USERAGENT
        session.mount(prefix, adapter=cls.get_adapter())
        if oauth2_token_endpoint:
            session.mount(oauth2_token_endpoint, adapter=cls.get_adapter())
        return session

    def __repr__(self):
        return self.__class__.__name__ + repr((self.service_endpoint, self.credentials, self.auth_type))


class CachingProtocol(type):
    """A metaclass for Protocol that caches Protocol instances based on a server+username key."""

    _protocol_cache = {}
    _protocol_cache_lock = Lock()

    def __call__(cls, *args, **kwargs):
        # Cache Protocol instances that point to the same endpoint and use the same credentials. This ensures that we
        # re-use thread and connection pools etc. instead of flooding the remote server. This is a modified Singleton
        # pattern.
        #
        # We ignore auth_type from kwargs in the cache key. We trust caller to supply the correct auth_type - otherwise
        # __init__ will guess the correct auth type.
        config = kwargs["config"]
        from .configuration import Configuration

        if not isinstance(config, Configuration):
            raise InvalidTypeError("config", config, Configuration)
        if not config.service_endpoint:
            raise AttributeError("'config.service_endpoint' must be set")
        _protocol_cache_key = cls._cache_key(config)

        try:
            protocol, _ = cls._protocol_cache[_protocol_cache_key]
        except KeyError:
            pass
        else:
            if isinstance(protocol, Exception):
                # The input data leads to a TransportError. Re-throw
                raise protocol
            return protocol

        # Acquire lock to guard against multiple threads competing to cache information. Having a per-server lock is
        # probably overkill, although it would reduce lock contention.
        log.debug("Waiting for _protocol_cache_lock")
        with cls._protocol_cache_lock:
            try:
                protocol, _ = cls._protocol_cache[_protocol_cache_key]
            except KeyError:
                pass
            else:
                if isinstance(protocol, Exception):
                    # We already tried this combination, possibly in a different competing thread, but the input
                    # data leads to a TransportError.
                    raise protocol
                return protocol

            log.debug("Protocol __call__ cache miss. Adding key '%s'", str(_protocol_cache_key))
            try:
                protocol = super().__call__(*args, **kwargs)
            except TransportError as e:
                # This can happen if, for example, autodiscover supplies us with a bogus EWS endpoint
                log.warning("Failed to create cached protocol with key %s: %s", _protocol_cache_key, e)
                cls._protocol_cache[_protocol_cache_key] = e, datetime.datetime.now()
                raise e
            cls._protocol_cache[_protocol_cache_key] = protocol, datetime.datetime.now()
        return protocol

    @staticmethod
    def _cache_key(config):
        # We may be using multiple different credentials for the same service endpoint. This key combination should be
        # safe.
        return config.service_endpoint, config.credentials

    def __getitem__(cls, config):
        return cls._protocol_cache[cls._cache_key(config)]

    def __delitem__(cls, config):
        del cls._protocol_cache[cls._cache_key(config)]

    @classmethod
    def clear_cache(mcs):
        with mcs._protocol_cache_lock:
            for key, (protocol, _) in mcs._protocol_cache.items():
                if isinstance(protocol, Exception):
                    continue
                service_endpoint = key[0]
                log.debug("Service endpoint '%s': Closing sessions", service_endpoint)
                with protocol._session_pool_lock:
                    protocol.close()
            mcs._protocol_cache.clear()


class Protocol(BaseProtocol, metaclass=CachingProtocol):
    """A class to handle all the low-level communication with an Exchange server. Contains a session pool, knows how to
    negotiate the authentication type of the server, refresh credentials, etc. Also contains methods for calling EWS
    services that are not tied to an account.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._version_lock = Lock()
        self.api_version_hint = None

    def get_auth_type(self):
        # Autodetect authentication type. We also set 'self.api_version_hint' here.
        return get_service_authtype(protocol=self)

    @property
    def version(self):
        # Make sure only one thread does the guessing.
        if not self.config.version or not self.config.version.build:
            log.debug("Waiting for _version_lock")
            with self._version_lock:
                if not self.config.version or not self.config.version.build:
                    # Version.guess() needs auth objects and a working session pool
                    self.config.version = Version.guess(self, api_version_hint=self.api_version_hint)
        return self.config.version

    def get_timezones(self, timezones=None, return_full_timezone_data=False):
        """Get timezone definitions from the server.

        :param timezones: A list of EWSDateTime instances. If None, fetches all timezones from server
          (Default value = None)
        :param return_full_timezone_data: If true, also returns periods and transitions (Default value = False)

        :return: A generator of TimeZoneDefinition objects
        """
        return GetServerTimeZones(protocol=self).call(
            timezones=timezones, return_full_timezone_data=return_full_timezone_data
        )

    def get_free_busy_info(self, accounts, start, end, merged_free_busy_interval=30, requested_view="DetailedMerged"):
        """Return free/busy information for a list of accounts.

        :param accounts: A list of (account, attendee_type, exclude_conflicts) tuples, where account is either an
          Account object or a string, attendee_type is a MailboxData.attendee_type choice, and exclude_conflicts is a
          boolean.
        :param start: The start datetime of the request
        :param end: The end datetime of the request
        :param merged_free_busy_interval: The interval, in minutes, of merged free/busy information (Default value = 30)
        :param requested_view: The type of information returned. Possible values are defined in the
          FreeBusyViewOptions.requested_view choices. (Default value = 'DetailedMerged')

        :return: A generator of FreeBusyView objects
        """
        from .account import Account

        tz_definition = list(self.get_timezones(timezones=[start.tzinfo], return_full_timezone_data=True))[0]
        return GetUserAvailability(self).call(
            mailbox_data=[
                MailboxData(
                    email=account.primary_smtp_address if isinstance(account, Account) else account,
                    attendee_type=attendee_type,
                    exclude_conflicts=exclude_conflicts,
                )
                for account, attendee_type, exclude_conflicts in accounts
            ],
            timezone=TimeZone.from_server_timezone(tz_definition=tz_definition, for_year=start.year),
            free_busy_view_options=FreeBusyViewOptions(
                time_window=TimeWindow(start=start, end=end),
                merged_free_busy_interval=merged_free_busy_interval,
                requested_view=requested_view,
            ),
        )

    def get_roomlists(self):
        return GetRoomLists(protocol=self).call()

    def get_rooms(self, roomlist):
        return GetRooms(protocol=self).call(room_list=RoomList(email_address=roomlist))

    def resolve_names(self, names, parent_folders=None, return_full_contact_data=False, search_scope=None, shape=None):
        """Resolve accounts on the server using partial account data, e.g. an email address or initials.

        :param names: A list of identifiers to query
        :param parent_folders: A list of contact folders to search in
        :param return_full_contact_data: If True, returns full contact data (Default value = False)
        :param search_scope: The scope to perform the search. Must be one of SEARCH_SCOPE_CHOICES (Default value = None)
        :param shape: (Default value = None)

        :return: A list of Mailbox items or, if return_full_contact_data is True, tuples of (Mailbox, Contact) items
        """
        return list(
            ResolveNames(protocol=self).call(
                unresolved_entries=names,
                parent_folders=parent_folders,
                return_full_contact_data=return_full_contact_data,
                search_scope=search_scope,
                contact_data_shape=shape,
            )
        )

    def expand_dl(self, distribution_list):
        """Expand distribution list into its members.

        :param distribution_list: SMTP address of the distribution list to expand, or a DLMailbox representing the list

        :return: List of Mailbox items that are members of the distribution list
        """
        if isinstance(distribution_list, str):
            distribution_list = DLMailbox(email_address=distribution_list, mailbox_type="PublicDL")
        return list(ExpandDL(protocol=self).call(distribution_list=distribution_list))

    def get_searchable_mailboxes(self, search_filter=None, expand_group_membership=False):
        """Call the GetSearchableMailboxes service to get mailboxes that can be searched.

        This method is only available to users who have been assigned the Discovery Management RBAC role. See
        https://docs.microsoft.com/en-us/exchange/permissions-exo/permissions-exo

        :param search_filter: If set, must be a single email alias (Default value = None)
        :param expand_group_membership: If True, returned distribution lists are expanded (Default value = False)

        :return: a list of SearchableMailbox, FailedMailbox or Exception instances
        """
        return list(
            GetSearchableMailboxes(protocol=self).call(
                search_filter=search_filter,
                expand_group_membership=expand_group_membership,
            )
        )

    def convert_ids(self, ids, destination_format):
        """Convert item and folder IDs between multiple formats.

        :param ids: a list of AlternateId, AlternatePublicFolderId or AlternatePublicFolderItemId instances
        :param destination_format: A string

        :return: a generator of AlternateId, AlternatePublicFolderId or AlternatePublicFolderItemId instances
        """
        return ConvertId(protocol=self).call(items=ids, destination_format=destination_format)

    def dummy_xml(self):
        # Generate a minimal, valid EWS request
        svc = ConvertId(protocol=self)
        return svc.wrap(
            content=svc.get_payload(
                items=[AlternateId(id="DUMMY", format=EWS_ID, mailbox="DUMMY")],
                destination_format=ENTRY_ID,
            ),
            api_version=self.api_version_hint,
        )

    def __getstate__(self):
        # The lock cannot be pickled
        state = super().__getstate__()
        del state["_version_lock"]
        return state

    def __setstate__(self, state):
        # Restore the lock
        super().__setstate__(state)
        self._version_lock = Lock()

    def __str__(self):
        # Don't trigger version guessing here just for the sake of printing
        if self.config.version:
            fullname, api_version, build = self.version.fullname, self.version.api_version, self.version.build
        else:
            fullname, api_version, build = "[unknown]", "[unknown]", "[unknown]"

        return f"""\
EWS url: {self.service_endpoint}
Product name: {fullname}
EWS API version: {api_version}
Build number: {build}
EWS auth: {self.auth_type}"""


class NoVerifyHTTPAdapter(requests.adapters.HTTPAdapter):
    """An HTTP adapter that ignores TLS validation errors. Use at own risk."""

    def cert_verify(self, conn, url, verify, cert):
        # pylint: disable=unused-argument
        # We're overriding a method, so we have to keep the signature
        super().cert_verify(conn=conn, url=url, verify=False, cert=cert)


class TLSClientAuth(requests.adapters.HTTPAdapter):
    """An HTTP adapter that implements Certificate Based Authentication (CBA)."""

    cert_file = None

    def init_poolmanager(self, *args, **kwargs):
        kwargs["cert_file"] = self.cert_file
        return super().init_poolmanager(*args, **kwargs)


class RetryPolicy(metaclass=abc.ABCMeta):
    """Stores retry logic used when faced with errors from the server."""

    @property
    @abc.abstractmethod
    def fail_fast(self):
        """Used to choose the error handling policy. When True, a fault-tolerant policy is used. False, a fail-fast
        policy is used."""

    @property
    @abc.abstractmethod
    def back_off_until(self):
        """Return a datetime to back off until"""

    @back_off_until.setter
    @abc.abstractmethod
    def back_off_until(self, value):
        """Setter for back off values"""

    @abc.abstractmethod
    def back_off(self, seconds):
        """Set a new back off until value"""

    def raise_response_errors(self, response):
        if response.status_code == 200:
            # Response is OK
            return
        if response.status_code == 500 and response.content and is_xml(response.content):
            # Some genius at Microsoft thinks it's OK to send a valid SOAP response as an HTTP 500
            log.debug("Got status code %s but trying to parse content anyway", response.status_code)
            return
        cas_error = response.headers.get("X-CasErrorCode")
        if cas_error:
            if cas_error.startswith("CAS error:"):
                # Remove unnecessary text
                cas_error = cas_error.split(":", 1)[1].strip()
            raise CASError(cas_error=cas_error, response=response)
        if response.status_code == 500 and (
            b"The specified server version is invalid" in response.content
            or b"ErrorInvalidSchemaVersionForMailboxVersion" in response.content
        ):
            # Another way of communicating invalid schema versions
            raise ErrorInvalidSchemaVersionForMailboxVersion("Invalid server version")
        if response.headers.get("connection") == "close":
            # Connection closed. OK to retry.
            raise ErrorServerBusy("Caused by closed connection")
        if (
            response.status_code == 302
            and response.headers.get("location", "").lower()
            == "/ews/genericerrorpage.htm?aspxerrorpath=/ews/exchange.asmx"
        ):
            # Redirect to genericerrorpage.htm is ridiculous behaviour for random outages. OK to retry.
            #
            # Redirect to '/internalsite/internalerror.asp' or '/internalsite/initparams.aspx' is caused by e.g. TLS
            # certificate f*ckups on the Exchange server. We should not retry those.
            raise ErrorInternalServerTransientError(f"Caused by HTTP 302 redirect to {response.headers['location']}")
        if response.status_code in (301, 302):
            try:
                redirect_url = get_redirect_url(response=response, allow_relative=False)
            except RelativeRedirect as e:
                log.debug("Redirect not allowed but we were relative redirected (%s -> %s)", response.url, e.value)
                raise RedirectError(url=e.value)
            log.debug("Redirect not allowed but we were redirected ( (%s -> %s)", response.url, redirect_url)
            raise RedirectError(url=redirect_url)
        if b"The referenced account is currently locked out" in response.content:
            raise UnauthorizedError("The referenced account is currently locked out")
        if response.status_code == 401 and self.fail_fast:
            # This is a login failure
            raise UnauthorizedError(f"Invalid credentials for {response.url}")
        if response.status_code == 401:
            # EWS sometimes throws 401's when it wants us to throttle connections. OK to retry.
            raise ErrorServerBusy("Caused by HTTP 401 response")
        if response.status_code == 500 and b"Server Error in '/EWS' Application" in response.content:
            # "Server Error in '/EWS' Application" has been seen in highly concurrent settings. OK to retry.
            raise ErrorInternalServerTransientError("Caused by \"Server Error in 'EWS' Application\"")
        if response.status_code == 503:
            # Internal server error. OK to retry.
            raise ErrorInternalServerTransientError("Caused by HTTP 503 response")
        # This could be anything. Let higher layers handle this
        raise MalformedResponseError(
            f"Unknown failure in response. Code: {response.status_code} headers: {response.headers} "
            f"content: {response.text}"
        )


class FailFast(RetryPolicy):
    """Fail immediately on server errors."""

    @property
    def fail_fast(self):
        return True

    @property
    def back_off_until(self):
        return None

    def back_off(self, seconds):
        raise ValueError("Cannot back off with fail-fast policy")


class FaultTolerance(RetryPolicy):
    """Enables fault-tolerant error handling. Tells internal methods to do an exponential back off when requests start
    failing, and wait up to max_wait seconds before failing.
    """

    # Back off 60 seconds if we didn't get an explicit suggested value
    DEFAULT_BACKOFF = 60

    def __init__(self, max_wait=3600):
        self.max_wait = max_wait
        self._back_off_until = None
        self._back_off_lock = Lock()

    def __getstate__(self):
        # Locks cannot be pickled
        state = self.__dict__.copy()
        del state["_back_off_lock"]
        return state

    def __setstate__(self, state):
        # Restore the lock
        self.__dict__.update(state)
        self._back_off_lock = Lock()

    @property
    def fail_fast(self):
        return False

    @property
    def back_off_until(self):
        """Return the back off value as a datetime. Reset the current back off value if it has expired."""
        if self._back_off_until is None:
            return None
        with self._back_off_lock:
            if self._back_off_until is None:
                return None
            if self._back_off_until < datetime.datetime.now():
                self._back_off_until = None  # The back off value has expired. Reset
                return None
            return self._back_off_until

    @back_off_until.setter
    def back_off_until(self, value):
        with self._back_off_lock:
            self._back_off_until = value

    def back_off(self, seconds):
        if seconds is None:
            seconds = self.DEFAULT_BACKOFF
        if seconds > self.max_wait:
            # We lost patience. Session is cleaned up in outer loop
            raise RateLimitError("Max timeout reached", wait=seconds)
        value = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        with self._back_off_lock:
            self._back_off_until = value

    def raise_response_errors(self, response):
        try:
            return super().raise_response_errors(response)
        except (ErrorInternalServerTransientError, ErrorServerBusy) as e:
            # Pass on the retry header value
            retry_after = _get_retry_after(response)
            if retry_after:
                raise ErrorServerBusy(e.args[0], back_off=retry_after)
            raise
