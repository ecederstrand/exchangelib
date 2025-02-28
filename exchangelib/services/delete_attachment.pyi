from ..properties import RootItemId as RootItemId
from ..util import create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService, attachment_ids_element as attachment_ids_element

class DeleteAttachment(EWSAccountService):
    SERVICE_NAME: str
    def call(self, items): ...
    def get_payload(self, items): ...
