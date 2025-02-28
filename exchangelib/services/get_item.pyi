from ..folders.base import BaseFolder as BaseFolder
from ..util import MNS as MNS, create_element as create_element
from .common import EWSAccountService as EWSAccountService, item_ids_element as item_ids_element, shape_element as shape_element
from _typeshed import Incomplete

class GetItem(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    def call(self, items, additional_fields, shape): ...
    def get_payload(self, items, additional_fields, shape): ...
