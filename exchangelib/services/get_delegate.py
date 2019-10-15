from ..errors import MalformedResponseError
from ..util import create_element, set_xml_value, MNS
from ..version import EXCHANGE_2007_SP1
from .common import EWSAccountService


class GetDelegate(EWSAccountService):
    """
    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getdelegate-operation
    """
    SERVICE_NAME = 'GetDelegate'
    element_container_name = '{%s}DelegateUserResponseMessageType' % MNS

    def call(self, user_ids, include_permissions):
        if self.protocol.version.build < EXCHANGE_2007_SP1:
            raise NotImplementedError(
                '%r is only supported for Exchange 2007 SP1 servers and later' % self.SERVICE_NAME)
        from ..properties import DLMailbox, DelegateUser  # The service expects a Mailbox element in the MNS namespace
        elements = self._get_elements(payload=self.get_payload(
            mailbox=DLMailbox(email_address=self.account.primary_smtp_address),
            user_ids=user_ids,
            include_permissions=include_permissions,
        ))
        for elem in elements:
            if isinstance(elem, Exception):
                raise elem
            yield DelegateUser.from_xml(elem=elem, account=self.account)

    def get_payload(self, mailbox, user_ids, include_permissions):
        payload = create_element(
            'm:%s' % self.SERVICE_NAME,
            attrs=dict(IncludePermissions='true' if include_permissions else 'false'),
        )
        set_xml_value(payload, mailbox, version=self.protocol.version)
        if user_ids:
            set_xml_value(payload, user_ids, version=self.protocol.version)
        return payload

    def _get_element_container(self, *args, **kwargs):
        try:
            return super(GetDelegate, self)._get_element_container(*args, **kwargs)
        except MalformedResponseError:
            # When there are no delegates, the response does not contain a DelegateUserResponseMessageType element
            return []

    @classmethod
    def _response_message_tag(cls):
        return '{%s}%sResponseMessage' % (MNS, cls.SERVICE_NAME)
