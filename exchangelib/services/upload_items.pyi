from ..properties import ItemId as ItemId, ParentFolderId as ParentFolderId
from ..util import MNS as MNS, add_xml_child as add_xml_child, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService, to_item_id as to_item_id
from _typeshed import Incomplete

class UploadItems(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    def call(self, items): ...
    def get_payload(self, items): ...
