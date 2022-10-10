import logging

from cached_property import threaded_cached_property

from .credentials import BaseCredentials, BaseOAuth2Credentials
from .errors import InvalidEnumValue, InvalidTypeError
from .protocol import FailFast, RetryPolicy
from .transport import AUTH_TYPE_MAP, CREDENTIALS_REQUIRED, OAUTH2
from .util import split_url
from .version import Version

log = logging.getLogger(__name__)


class Configuration:
    """Contains information needed to create an authenticated connection to an EWS endpoint.

    The 'credentials' argument contains the credentials needed to authenticate with the server. Multiple credentials
    implementations are available in 'exchangelib.credentials'.

    config = Configuration(credentials=Credentials('john@example.com', 'MY_SECRET'), ...)

    The 'server' and 'service_endpoint' arguments are mutually exclusive. The former must contain only a domain name,
    the latter a full URL:

        config = Configuration(server='example.com', ...)
        config = Configuration(service_endpoint='https://mail.example.com/EWS/Exchange.asmx', ...)

    If you know which authentication type the server uses, you add that as a hint in 'auth_type'. Likewise, you can
    add the server version as a hint. This allows to skip the auth type and version guessing routines:

        config = Configuration(auth_type=NTLM, ...)
        config = Configuration(version=Version(build=Build(15, 1, 2, 3)), ...)

    You can use 'retry_policy' to define a custom retry policy for handling server connection failures:

        config = Configuration(retry_policy=FaultTolerance(max_wait=3600), ...)

    'max_connections' defines the max number of connections allowed for this server. This may be restricted by
    policies on the Exchange server.
    """

    def __init__(
        self,
        credentials=None,
        server=None,
        service_endpoint=None,
        auth_type=None,
        version=None,
        retry_policy=None,
        max_connections=None,
    ):
        if not isinstance(credentials, (BaseCredentials, type(None))):
            raise InvalidTypeError("credentials", credentials, BaseCredentials)
        if auth_type is None and isinstance(credentials, BaseOAuth2Credentials):
            # Set a default auth type for the credentials where this makes sense
            auth_type = OAUTH2
        if auth_type is not None and auth_type not in AUTH_TYPE_MAP:
            raise InvalidEnumValue("auth_type", auth_type, AUTH_TYPE_MAP)
        if credentials is None and auth_type in CREDENTIALS_REQUIRED:
            raise ValueError(f"Auth type {auth_type!r} was detected but no credentials were provided")
        if server and service_endpoint:
            raise AttributeError("Only one of 'server' or 'service_endpoint' must be provided")
        if not retry_policy:
            retry_policy = FailFast()
        if not isinstance(version, (Version, type(None))):
            raise InvalidTypeError("version", version, Version)
        if not isinstance(retry_policy, RetryPolicy):
            raise InvalidTypeError("retry_policy", retry_policy, RetryPolicy)
        if not isinstance(max_connections, (int, type(None))):
            raise InvalidTypeError("max_connections", max_connections, int)
        self._credentials = credentials
        if server:
            self.service_endpoint = f"https://{server}/EWS/Exchange.asmx"
        else:
            self.service_endpoint = service_endpoint
        self.auth_type = auth_type
        self.version = version
        self.retry_policy = retry_policy
        self.max_connections = max_connections

    @property
    def credentials(self):
        # Do not update credentials from this class. Instead, do it from Protocol
        return self._credentials

    @threaded_cached_property
    def server(self):
        if not self.service_endpoint:
            return None
        return split_url(self.service_endpoint)[1]

    def __repr__(self):
        args_str = ", ".join(
            f"{k}={getattr(self, k)!r}"
            for k in ("credentials", "service_endpoint", "auth_type", "version", "retry_policy")
        )
        return f"{self.__class__.__name__}({args_str})"
