from ..configuration import Configuration as Configuration
from ..errors import AutoDiscoverCircularRedirect as AutoDiscoverCircularRedirect, AutoDiscoverFailed as AutoDiscoverFailed, RedirectError as RedirectError, TransportError as TransportError
from ..protocol import FailFast as FailFast, Protocol as Protocol
from ..transport import get_unauthenticated_autodiscover_response as get_unauthenticated_autodiscover_response
from ..util import CONNECTION_ERRORS as CONNECTION_ERRORS, get_domain as get_domain, get_redirect_url as get_redirect_url
from .cache import autodiscover_cache as autodiscover_cache
from .protocol import AutodiscoverProtocol as AutodiscoverProtocol
from _typeshed import Incomplete

log: Incomplete
DNS_LOOKUP_ERRORS: Incomplete

class SrvRecord:
    priority: Incomplete
    weight: Incomplete
    port: Incomplete
    srv: Incomplete
    def __init__(self, priority, weight, port, srv) -> None: ...
    def __hash__(self): ...
    def __eq__(self, other): ...

def discover(email, credentials: Incomplete | None = None, auth_type: Incomplete | None = None, retry_policy: Incomplete | None = None): ...

class Autodiscovery:
    INITIAL_RETRY_POLICY: Incomplete
    MAX_REDIRECTS: int
    DNS_RESOLVER_KWARGS: Incomplete
    DNS_RESOLVER_ATTRS: Incomplete
    DNS_RESOLVER_LIFETIME: Incomplete
    URL_PATH: str
    email: Incomplete
    credentials: Incomplete
    def __init__(self, email, credentials: Incomplete | None = None) -> None: ...
    def discover(self): ...
    def clear(self) -> None: ...
    def resolver(self): ...
