import logging

from cached_property import threaded_cached_property

from .credentials import BaseCredentials
from .protocol import RetryPolicy, FailFast
from .transport import AUTH_TYPE_MAP
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

    Finally, you can use 'retry_policy' to define a custom retry policy for handling server connection failures:

        config = Configuration(retry_policy=FaultTolerance(max_wait=3600), ...)

    """

    def __init__(self, credentials=None, server=None, service_endpoint=None, auth_type=None, version=None,
                 retry_policy=None):
        if not isinstance(credentials, (BaseCredentials, type(None))):
            raise ValueError("'credentials' %r must be a Credentials instance" % credentials)
        if server and service_endpoint:
            raise AttributeError("Only one of 'server' or 'service_endpoint' must be provided")
        if auth_type is not None and auth_type not in AUTH_TYPE_MAP:
            raise ValueError("'auth_type' %r must be one of %s"
                             % (auth_type, ', '.join("'%s'" % k for k in sorted(AUTH_TYPE_MAP.keys()))))
        if not retry_policy:
            retry_policy = FailFast()
        if not isinstance(version, (Version, type(None))):
            raise ValueError("'version' %r must be a Version instance" % version)
        if not isinstance(retry_policy, RetryPolicy):
            raise ValueError("'retry_policy' %r must be a RetryPolicy instance" % retry_policy)
        self._credentials = credentials
        if server:
            self.service_endpoint = 'https://%s/EWS/Exchange.asmx' % server
        else:
            self.service_endpoint = service_endpoint
        self.auth_type = auth_type
        self.version = version
        self.retry_policy = retry_policy

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
        return self.__class__.__name__ + '(%s)' % ', '.join('%s=%r' % (k, getattr(self, k)) for k in (
            'credentials', 'service_endpoint', 'auth_type', 'version', 'retry_policy'
        ))
