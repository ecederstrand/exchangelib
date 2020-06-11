from ..util import create_element, set_xml_value, MNS
from ..version import EXCHANGE_2007_SP1
from .common import EWSAccountService, EWSPooledMixIn


class GetDelegate(EWSAccountService, EWSPooledMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getdelegate-operation"""
    SERVICE_NAME = 'GetDelegate'

    def call(self, user_ids, include_permissions):
        if self.protocol.version.build < EXCHANGE_2007_SP1:
            raise NotImplementedError(
                '%r is only supported for Exchange 2007 SP1 servers and later' % self.SERVICE_NAME)
        from ..properties import DLMailbox, DelegateUser  # The service expects a Mailbox element in the MNS namespace

        if user_ids:
            # Pool requests to avoid arbitrarily large requests when user_ids is huge
            res = self._pool_requests(
                items=user_ids,
                payload_func=self.get_payload,
                **dict(
                    mailbox=DLMailbox(email_address=self.account.primary_smtp_address),
                    include_permissions=include_permissions,
                )
            )
        else:
            # Pooling expects an iterable of items but we have None. Just call _get_elements directly.
            res = self._get_elements(payload=self.get_payload(
                mailbox=DLMailbox(email_address=self.account.primary_smtp_address),
                user_ids=user_ids,
                include_permissions=include_permissions,
            ))

        for elem in res:
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

    def _get_elements_in_container(self, container):
        # We may have other elements in here, e.g. 'ResponseCode'. Filter away those.
        from ..properties import DelegateUser
        return container.findall(DelegateUser.response_tag())

    def _get_element_container(self, message, response_message=None, name=None):
        # Do nothing. See self._response_message_tag.
        return message

    @classmethod
    def _response_message_tag(cls):
        # We're using this in place of self.element_container_name because self._get_soap_messages expects to find
        # elements at this level. We'll let self._get_element_container do nothing instead.
        return '{%s}DelegateUserResponseMessageType' % MNS
