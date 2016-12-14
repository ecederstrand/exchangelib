from __future__ import unicode_literals

import logging

from .protocol import Protocol
from .transport import AUTH_TYPE_MAP

log = logging.getLogger(__name__)


class Configuration(object):
    """
    Assembles a connection protocol when autodiscover is not used.

    If the server is not configured with autodiscover, the following should be sufficient:

        config = Configuration(server='example.com', credentials=Credentials('MYWINDOMAIN\myusername', 'topsecret'))
        account = Account(primary_smtp_address='john@example.com', config=config)

    You can also set the EWS service endpoint directly:

        config = Configuration(service_endpoint='https://mail.example.com/EWS/Exchange.asmx', credentials=...)

    If you know which authentication type the server uses, you add that as a hint:

        config = Configuration(service_endpoint='https://example.com/EWS/Exchange.asmx', auth_type=NTLM, credentials=..)

    If you want to use autodiscover, don't use a Configuration object. Instead, set up an account like this:

        credentials = Credentials(username='MYWINDOMAIN\myusername', password='topsecret')
        account = Account(primary_smtp_address='john@example.com', credentials=credentials, autodiscover=True)

    """

    def __init__(self, credentials, server=None, has_ssl=True, service_endpoint=None, auth_type=None,
                 verify_ssl=True, **kwargs):
        if kwargs:
            username = kwargs.pop('username')
            password = kwargs.pop('password')
            if username or password:
                raise DeprecationWarning("'username' and 'password' args are deprecated. Use 'credentials' instead")
            assert not kwargs
        if auth_type is not None and auth_type not in AUTH_TYPE_MAP:
            raise AttributeError('Unsupported auth type %s' % auth_type)
        if not (server or service_endpoint):
            raise AttributeError('Either server or service_endpoint must be provided')
        # Set up a default protocol that non-autodiscover accounts can use
        if not service_endpoint:
            service_endpoint = '%s://%s/EWS/Exchange.asmx' % ('https' if has_ssl else 'http', server)
        self.protocol = Protocol(
            service_endpoint=service_endpoint,
            auth_type=auth_type,
            credentials=credentials,
            verify_ssl=verify_ssl,
        )

    @property
    def credentials(self):
        return self.protocol.credentials

    def __repr__(self):
        return self.__class__.__name__ + repr((self.protocol,))
