"""
Implements an Exchange user object and access types. Exchange provides two different ways of granting access for a
login to a specific account. Impersonation is used mainly for service accounts that connect via EWS. Delegate is used
for ad-hoc access e.g. granted manually by the user.
See https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/impersonation-and-ews-in-exchange
"""

import abc
import logging
from threading import RLock

import oauthlib.oauth2
from cached_property import threaded_cached_property

from .errors import InvalidTypeError

log = logging.getLogger(__name__)

IMPERSONATION = "impersonation"
DELEGATE = "delegate"
ACCESS_TYPES = (IMPERSONATION, DELEGATE)


class BaseCredentials(metaclass=abc.ABCMeta):
    """Base class for credential storage."""

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.__dict__)

    def __hash__(self):
        return hash(tuple((getattr(self, k) for k in self.__dict__)))


class Credentials(BaseCredentials):
    r"""Keeps login info the way Exchange likes it.

    Usernames for authentication are of one of these forms:
    * PrimarySMTPAddress
    * WINDOMAIN\username
    * User Principal Name (UPN)
      password: Clear-text password
    """

    EMAIL = "email"
    DOMAIN = "domain"
    UPN = "upn"

    def __init__(self, username, password):
        super().__init__()
        if username.count("@") == 1:
            self.type = self.EMAIL
        elif username.count("\\") == 1:
            self.type = self.DOMAIN
        else:
            self.type = self.UPN
        self.username = username
        self.password = password

    def __repr__(self):
        return self.__class__.__name__ + repr((self.username, "********"))

    def __str__(self):
        return self.username


class BaseOAuth2Credentials(BaseCredentials):
    """Base class for all classes that implement OAuth 2.0 authentication"""

    def __init__(self, client_id, client_secret, tenant_id=None, identity=None, access_token=None):
        """

        :param client_id: ID of an authorized OAuth application, required for automatic token fetching and refreshing
        :param client_secret: Secret associated with the OAuth application
        :param tenant_id: Microsoft tenant ID of the account to access
        :param identity: An Identity object representing the account that these credentials are connected to.
        :param access_token: Previously-obtained access token, as a dict or an oauthlib.oauth2.OAuth2Token
        """
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.identity = identity
        self.access_token = access_token

        self._lock = RLock()

    @property
    def lock(self):
        return self._lock

    @property
    def access_token(self):
        return self._access_token

    @access_token.setter
    def access_token(self, access_token):
        if access_token is not None and not isinstance(access_token, dict):
            raise InvalidTypeError("access_token", access_token, oauthlib.oauth2.OAuth2Token)
        self._access_token = access_token

    def refresh(self, session):
        """Obtain a new set of valid credentials. This is intended to support OAuth token refreshing, which can
        happen in long-running applications or those that cache access tokens and so might start with a token close to
        expiration.

        :param session: requests session asking for refreshed credentials
        :return:
        """
        # Creating a new session gets a new access token, so there's no work here to refresh the credentials.

    def on_token_auto_refreshed(self, access_token):
        """Set the access_token. Called after the access token is refreshed (requests-oauthlib can automatically
        refresh tokens if given an OAuth client ID and secret, so this is how our copy of the token stays up-to-date).
        Applications that cache access tokens can override this to store the new token - just remember to call the
        super() method.

        :param access_token: New token obtained by refreshing
        """
        # Ensure we don't update the object in the middle of a new session being created, which could cause a race.
        with self.lock:
            log.debug("%s auth token for %s", "Refreshing" if self.access_token else "Setting", self.client_id)
            self.access_token = access_token

    def sig(self):
        # Like hash(self), but pulls in the access token. Protocol.refresh_credentials() uses this to find out
        # if the access_token needs to be refreshed.
        res = []
        for k in self.__dict__:
            if k in ("_lock", "identity"):
                continue
            if k == "_access_token":
                res.append(self.access_token["access_token"] if self.access_token else None)
                continue
            res.append(getattr(self, k))
        return hash(tuple(res))

    @property
    def token_url(self):
        """The URL to request tokens from"""
        # We may not know (or need) the Microsoft tenant ID. If not, use common/ to let Microsoft select the appropriate
        # tenant for the provided authorization code or refresh token.
        return f"https://login.microsoftonline.com/{self.tenant_id or 'common'}/oauth2/v2.0/token"  # nosec

    @property
    def scope(self):
        """The scope we ask for the token to have"""
        return ["https://outlook.office365.com/.default"]

    def session_params(self):
        """Extra parameters to use when creating the session"""
        res = {"token": self.access_token}  # Token may be None
        if self.client_id and self.client_secret:
            # If we're given a client ID and secret, we have enough to refresh access tokens ourselves. In other
            # cases the session will raise TokenExpiredError, and we'll need to ask the calling application to
            # refresh the token (that covers cases where the caller doesn't have access to the client secret but
            # is working with a service that can provide it refreshed tokens on a limited basis).
            res.update(
                {
                    "auto_refresh_kwargs": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    "auto_refresh_url": self.token_url,
                    "token_updater": self.on_token_auto_refreshed,
                }
            )
        return res

    def token_params(self):
        """Extra parameters when requesting the token"""
        return {"include_client_id": True}

    @threaded_cached_property
    @abc.abstractmethod
    def client(self):
        """The client implementation to use for this credential class"""

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.__dict__ if k != "_lock")

    def __hash__(self):
        # 'access_token' may be refreshed once in a while. This should not affect the hash signature.
        # 'identity' is just informational and should also not affect the hash signature.
        return hash(tuple(getattr(self, k) for k in self.__dict__ if k not in ("_lock", "identity", "_access_token")))

    def __str__(self):
        return self.client_id

    def __repr__(self):
        return self.__class__.__name__ + repr((self.client_id, "********"))

    def __getstate__(self):
        # The lock cannot be pickled
        state = self.__dict__.copy()
        del state["_lock"]
        return state

    def __setstate__(self, state):
        # Restore the lock
        self.__dict__.update(state)
        self._lock = RLock()


class OAuth2Credentials(BaseOAuth2Credentials):
    """Login info for OAuth 2.0 client credentials authentication, as well as a base for other OAuth 2.0 grant types.

    This is primarily useful for in-house applications accessing data from a single Microsoft account. For applications
    that will access multiple tenants' data, the client credentials flow does not give the application enough
    information to restrict end users' access to the appropriate account. Use OAuth2AuthorizationCodeCredentials and
    the associated auth code grant type for multi-tenant applications.
    """

    @threaded_cached_property
    def client(self):
        return oauthlib.oauth2.BackendApplicationClient(client_id=self.client_id)


class OAuth2LegacyCredentials(OAuth2Credentials):
    """Login info for OAuth 2.0 authentication using delegated permissions and application permissions.

    This requires the app to acquire username and password from the user and pass that when requesting authentication
    tokens for the given user. This allows the app to act as the signed-in user.
    """

    def __init__(self, username, password, **kwargs):
        """
        :param username: The username of the user to act as
        :param password: The password of the user to act as
        """
        super().__init__(**kwargs)
        self.username = username
        self.password = password

    def token_params(self):
        res = super().token_params()
        res.update(
            {
                "username": self.username,
                "password": self.password,
            }
        )
        return res

    @threaded_cached_property
    def client(self):
        return oauthlib.oauth2.LegacyApplicationClient(client_id=self.client_id)

    @property
    def scope(self):
        return ["https://outlook.office365.com/EWS.AccessAsUser.All"]


class OAuth2AuthorizationCodeCredentials(BaseOAuth2Credentials):
    """Login info for OAuth 2.0 authentication using the authorization code grant type. This can be used in one of
    several ways:
    * Given an authorization code, client ID, and client secret, fetch a token ourselves and refresh it as needed if
      supplied with a refresh token.
    * Given an existing access token, client ID, and client secret, use the access token until it expires and then
      refresh it as needed.
    * Given only an existing access token, use it until it expires. This can be used to let the calling application
      refresh tokens itself by subclassing and implementing refresh().

    Unlike the base (client credentials) grant, authorization code credentials don't require a Microsoft tenant ID
    because each access token (and the authorization code used to get the access token) is restricted to a single
    tenant.
    """

    def __init__(self, authorization_code=None, **kwargs):
        """

        :param authorization_code: Code obtained when authorizing the application to access an account. In combination
          with client_id and client_secret, will be used to obtain an access token.
        """
        for attr in ("client_id", "client_secret"):
            # Allow omitting these kwargs
            kwargs[attr] = kwargs.pop(attr, None)
        super().__init__(**kwargs)
        self.authorization_code = authorization_code

    @property
    def scope(self):
        res = super().scope
        res.append("offline_access")
        return res

    def token_params(self):
        res = super().token_params()
        res["code"] = self.authorization_code  # Auth code may be None
        self.authorization_code = None  # We can only use the code once
        return res

    @threaded_cached_property
    def client(self):
        return oauthlib.oauth2.WebApplicationClient(client_id=self.client_id)

    def __repr__(self):
        return self.__class__.__name__ + repr(
            (self.client_id, "[client_secret]", "[authorization_code]", "[access_token]")
        )

    def __str__(self):
        client_id = self.client_id
        credential = (
            "[access_token]"
            if self.access_token is not None
            else ("[authorization_code]" if self.authorization_code is not None else None)
        )
        description = " ".join(filter(None, [client_id, credential]))
        return description or "[underspecified credentials]"
