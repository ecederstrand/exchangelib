from .errors import RateLimitError as RateLimitError, TransportError as TransportError, UnauthorizedError as UnauthorizedError
from .util import CONNECTION_ERRORS as CONNECTION_ERRORS, TLS_ERRORS as TLS_ERRORS
from _typeshed import Incomplete

log: Incomplete
NOAUTH: str
NTLM: str
BASIC: str
DIGEST: str
GSSAPI: str
SSPI: str
OAUTH2: str
CBA: str
CREDENTIALS_REQUIRED: Incomplete
AUTH_TYPE_MAP: Incomplete
DEFAULT_ENCODING: str
DEFAULT_HEADERS: Incomplete

def get_auth_instance(auth_type, **kwargs): ...
def get_service_authtype(protocol): ...
def get_autodiscover_authtype(protocol): ...
def get_unauthenticated_autodiscover_response(protocol, method, headers: Incomplete | None = None, data: Incomplete | None = None): ...
def get_auth_method_from_response(response): ...
