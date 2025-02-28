from ..attachments import FileAttachment as FileAttachment, ItemAttachment as ItemAttachment
from ..items import BaseItem as BaseItem
from ..properties import ParentItemId as ParentItemId
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService, to_item_id as to_item_id
from _typeshed import Incomplete

class CreateAttachment(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    cls_map: Incomplete
    def call(self, parent_item, items): ...
    def get_payload(self, items, parent_item): ...
