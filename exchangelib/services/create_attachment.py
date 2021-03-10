from .common import EWSAccountService, to_item_id
from ..properties import ParentItemId
from ..util import create_element, set_xml_value, MNS


class CreateAttachment(EWSAccountService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/createattachment-operation
    """
    SERVICE_NAME = 'CreateAttachment'
    element_container_name = '{%s}Attachments' % MNS

    def call(self, parent_item, items):
        from ..attachments import FileAttachment, ItemAttachment
        cls_map = {cls.response_tag(): cls for cls in (FileAttachment, ItemAttachment)}
        for elem in self._chunked_get_elements(self.get_payload, items=items, parent_item=parent_item):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield cls_map[elem.tag].from_xml(elem=elem, account=self.account)

    def get_payload(self, items, parent_item):
        from ..items import BaseItem
        payload = create_element('m:%s' % self.SERVICE_NAME)
        version = self.account.version
        if isinstance(parent_item, BaseItem):
            # to_item_id() would convert this to a normal ItemId, but the service wants a ParentItemId
            parent_item = ParentItemId(parent_item.id, parent_item.changekey)
        set_xml_value(payload, to_item_id(parent_item, ParentItemId, version=version), version=version)
        attachments = create_element('m:Attachments')
        for item in items:
            set_xml_value(attachments, item, version=self.account.version)
        if not attachments:
            raise ValueError('"items" must not be empty')
        payload.append(attachments)
        return payload
