# coding=utf-8
"""
Implements an Exchange user object and access types. Exchange provides two different ways of granting access for a
login to a specific account. Impersonation is used mainly for service accounts that connect via EWS. Delegate is used
for ad-hoc access e.g. granted manually by the user.
See http://blogs.msdn.com/b/exchangedev/archive/2009/06/15/exchange-impersonation-vs-delegate-access.aspx
"""
from __future__ import unicode_literals

import abc
import logging
from threading import RLock

from future.utils import python_2_unicode_compatible

from .util import PickleMixIn

log = logging.getLogger(__name__)

IMPERSONATION = 'impersonation'
DELEGATE = 'delegate'
ACCESS_TYPES = (IMPERSONATION, DELEGATE)


class BaseCredentials(object):
    """
    Base for credential storage.

    Establishes a method for refreshing credentials (mostly useful with
    OAuth, which expires tokens relatively frequently) and provides a
    lock for synchronizing access to the object around refreshes.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self):
        super(BaseCredentials, self).__init__()
        self._lock = RLock()

    @property
    def lock(self):
        return self._lock

    @abc.abstractmethod
    def refresh(self, session):
        """
        Obtain a new set of valid credentials. This is mostly intended
        to support OAuth token refreshing, which can happen in long-
        running applications or those that cache access tokens and so
        might start with a token close to expiration.

        :param session: requests session asking for refreshed credentials
        """
        raise NotImplementedError(
            'Credentials object does not support refreshing. '
            + 'See class documentation on automatic refreshing, or subclass and implement refresh().'
        )


@python_2_unicode_compatible
class Credentials(BaseCredentials, PickleMixIn):
    """
    Keeps login info the way Exchange likes it.

    :param username: Usernames for authentication are of one of these forms:
    * PrimarySMTPAddress
    * WINDOMAIN\\username
    * User Principal Name (UPN)

    :param password: Clear-text password
    """
    EMAIL = 'email'
    DOMAIN = 'domain'
    UPN = 'upn'

    __slots__ = ('username', 'password', 'type')

    def __init__(self, username, password):
        super(Credentials, self).__init__()
        if username.count('@') == 1:
            self.type = self.EMAIL
        elif username.count('\\') == 1:
            self.type = self.DOMAIN
        else:
            self.type = self.UPN
        self.username = username
        self.password = password

    def __eq__(self, other):
        for k in self.__slots__:
            if getattr(self, k) != getattr(other, k):
                return False
        return True

    def __hash__(self):
        return hash((self.username, self.password))

    def __repr__(self):
        return self.__class__.__name__ + repr((self.username, '********'))

    def __str__(self):
        return self.username


@python_2_unicode_compatible
class OAuth2Credentials(BaseCredentials, PickleMixIn):
    """
    Login info for OAuth 2.0 client credentials authentication, as well
    as a base for other OAuth 2.0 grant types.

    This is primarily useful for in-house applications accessing data
    from a single Microsoft account. For applications that will access
    multiple tenants' data, the client credentials flow does not give
    the application enough information to restrict end users' access to
    the appropriate account. Use OAuth2AuthorizationCodeCredentials and
    the associated auth code grant type for multi-tenant applications.

    :param client_id: ID of an authorized OAuth application
    :param client_secret: Secret associated with the OAuth application
    :param tenant_id: Microsoft tenant ID of the account to access
    """
    __slots__ = ('client_id', 'client_secret', 'tenant_id')

    def __init__(self, client_id, client_secret, tenant_id):
        super(OAuth2Credentials, self).__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id

    def refresh(self, session):
        # Creating a new session gets a new access token, so there's no
        # work here to refresh the credentials. This implementation just
        # makes sure we don't raise a NotImplementedError.
        pass

    def on_token_auto_refreshed(self, access_token):
        """
        Called after the access token is refreshed (requests-oauthlib
        can automatically refresh tokens if given an OAuth client ID and
        secret, so this is how our copy of the token stays up-to-date).
        Applications that cache access tokens can override this to store
        the new token - just remember to call the super() method!

        :param access_token: New token obtained by refreshing
        """
        # Ensure we don't update the object in the middle of a new session
        # being created, which could cause a race
        with self.lock:
            self.access_token = access_token

    def __eq__(self, other):
        for k in self.__slots__:
            if getattr(self, k) != getattr(other, k):
                return False
        return True

    def __hash__(self):
        return hash((self.client_id, self.client_secret, self.tenant_id))

    def __repr__(self):
        return self.__class__.__name__ + repr((self.client_id, '********'))

    def __str__(self):
        return self.client_id


@python_2_unicode_compatible
class OAuth2AuthorizationCodeCredentials(OAuth2Credentials, PickleMixIn):
    """
    Login info for OAuth 2.0 authentication using the authorization code
    grant type. This can be used in one of several ways:
    * Given an authorization code, client ID, and client secret, fetch a
      token ourselves and refresh it as needed if supplied with a refresh
      token.
    * Given an existing access token, refresh token, client ID, and
      client secret, use the access token until it expires and then
      refresh it as needed.
    * Given only an existing access token, use it until it expires. This
      can be used to let the calling application refresh tokens itself
      by subclassing and implementing refresh().

    Unlike the base (client credentials) grant, authorization code
    credentials don't require a Microsoft tenant ID because each access
    token (and the authorization code used to get the access token) is
    restricted to a single tenant.

    :params client_id: ID of an authorized OAuth application, required
        for automatic token fetching and refreshing
    :params client_secret: Secret associated with the OAuth application
    :params authorization_code: Code obtained when authorizing the
        application to access an account. In combination with client_id
        and client_secret, will be used to obtain an access token.
    :params access_token: Previously-obtained access token. If a token
        exists and the application will handle refreshing by itself (or
        opts not to handle it), this parameter alone is sufficient.
    """
    __slots__ = ('access_token', 'authorization_code')

    def __init__(self, client_id=None, client_secret=None, authorization_code=None, access_token=None):
        super(OAuth2AuthorizationCodeCredentials, self).__init__(client_id, client_secret, tenant_id=None)
        self.access_token = access_token
        self.authorization_code = authorization_code

    def __eq__(self, other):
        for k in self.__slots__:
            if getattr(self, k) != getattr(other, k):
                return False
        return True

    def __hash__(self):
        return hash((self.access_token['access_token'], self.authorization_code))

    def __repr__(self):
        return self.__class__.__name__ + ' ' + str(self)

    def __str__(self):
        client_id = self.client_id
        credential = '[access_token]' if self.access_token is not None else \
            ('[authorization code]' if self.authorization_code is not None else None)
        description = ' '.join(filter(None, [client_id, credential]))
        return description or '[underspecified credentials]'
