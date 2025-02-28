from ..properties import MovedItemId as MovedItemId
from ..util import create_element as create_element
from .common import EWSAccountService as EWSAccountService, item_ids_element as item_ids_element

class MarkAsJunk(EWSAccountService):
    SERVICE_NAME: str
    def call(self, items, is_junk, move_item): ...
    def get_payload(self, items, is_junk, move_item): ...
