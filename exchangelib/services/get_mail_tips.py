from .common import EWSService
from ..properties import MailTips
from ..util import create_element, set_xml_value, MNS


class GetMailTips(EWSService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getmailtips-operation"""
    SERVICE_NAME = 'GetMailTips'

    def call(self, sending_as, recipients, mail_tips_requested):
        for elem in self._chunked_get_elements(
            self.get_payload,
            items=recipients,
            sending_as=sending_as,
            mail_tips_requested=mail_tips_requested,
        ):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield MailTips.from_xml(elem=elem, account=None)

    def get_payload(self, recipients, sending_as,  mail_tips_requested):
        payload = create_element('m:%s' % self.SERVICE_NAME)
        set_xml_value(payload, sending_as, version=self.protocol.version)

        recipients_elem = create_element('m:Recipients')
        for recipient in recipients:
            set_xml_value(recipients_elem, recipient, version=self.protocol.version)
        if not recipients_elem:
            raise ValueError('"recipients" must not be empty')
        payload.append(recipients_elem)

        if mail_tips_requested:
            set_xml_value(payload, mail_tips_requested, version=self.protocol.version)
        return payload

    def _get_elements_in_response(self, response):
        for msg in response:
            yield self._get_element_container(message=msg, name=MailTips.response_tag())

    @classmethod
    def _response_message_tag(cls):
        return '{%s}MailTipsResponseMessageType' % MNS
