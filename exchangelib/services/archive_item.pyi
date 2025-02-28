from ..items import Item as Item
from ..util import MNS as MNS, create_element as create_element
from ..version import EXCHANGE_2013 as EXCHANGE_2013
from .common import EWSAccountService as EWSAccountService, folder_ids_element as folder_ids_element, item_ids_element as item_ids_element
from _typeshed import Incomplete

class ArchiveItem(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    supported_from = EXCHANGE_2013
    def call(self, items, to_folder): ...
    def get_payload(self, items, to_folder): ...
