from .credentials import BaseCredentials as BaseCredentials, BaseOAuth2Credentials as BaseOAuth2Credentials, O365InteractiveCredentials as O365InteractiveCredentials
from .errors import InvalidEnumValue as InvalidEnumValue, InvalidTypeError as InvalidTypeError
from .protocol import FailFast as FailFast, RetryPolicy as RetryPolicy
from .transport import AUTH_TYPE_MAP as AUTH_TYPE_MAP, CREDENTIALS_REQUIRED as CREDENTIALS_REQUIRED, OAUTH2 as OAUTH2
from .util import split_url as split_url
from .version import Version as Version
from _typeshed import Incomplete

log: Incomplete

class Configuration:
    service_endpoint: Incomplete
    auth_type: Incomplete
    version: Incomplete
    retry_policy: Incomplete
    max_connections: Incomplete
    def __init__(self, credentials: Incomplete | None = None, server: Incomplete | None = None, service_endpoint: Incomplete | None = None, auth_type: Incomplete | None = None, version: Incomplete | None = None, retry_policy: Incomplete | None = None, max_connections: Incomplete | None = None) -> None: ...
    @property
    def credentials(self): ...
    def server(self): ...

class O365InteractiveConfiguration(Configuration):
    SERVER: str
    def __init__(self, client_id, username) -> None: ...
