from ..errors import InvalidTypeError as InvalidTypeError
from ..folders import BaseFolder as BaseFolder
from ..properties import FolderId as FolderId
from ..util import create_element as create_element
from .common import EWSAccountService as EWSAccountService, folder_ids_element as folder_ids_element, item_ids_element as item_ids_element

class SendItem(EWSAccountService):
    SERVICE_NAME: str
    returns_elements: bool
    def call(self, items, saved_item_folder): ...
    def get_payload(self, items, saved_item_folder): ...
