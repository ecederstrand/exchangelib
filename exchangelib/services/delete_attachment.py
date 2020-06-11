from ..util import create_element
from .common import EWSAccountService, create_attachment_ids_element


class DeleteAttachment(EWSAccountService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/deleteattachment-operation"""
    SERVICE_NAME = 'DeleteAttachment'

    def call(self, items):
        return self._get_elements(payload=self.get_payload(
            items=items,
        ))

    def _get_element_container(self, message, response_message=None, name=None):
        # DeleteAttachment returns RootItemIds directly beneath DeleteAttachmentResponseMessage. Collect the elements
        # and make our own fake container.
        from ..properties import RootItemId
        res = super()._get_element_container(
            message=message, response_message=response_message, name=name
        )
        if not res:
            return res
        fake_elem = create_element('FakeContainer')
        for elem in message.findall(RootItemId.response_tag()):
            fake_elem.append(elem)
        return fake_elem

    def get_payload(self, items):
        payload = create_element('m:%s' % self.SERVICE_NAME)
        attachment_ids = create_attachment_ids_element(items=items, version=self.account.version)
        payload.append(attachment_ids)
        return payload
