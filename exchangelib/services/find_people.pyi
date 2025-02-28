from ..errors import InvalidEnumValue as InvalidEnumValue
from ..items import ID_ONLY as ID_ONLY, ITEM_TRAVERSAL_CHOICES as ITEM_TRAVERSAL_CHOICES, Persona as Persona, SHAPE_CHOICES as SHAPE_CHOICES
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from ..version import EXCHANGE_2013 as EXCHANGE_2013
from .common import EWSPagingService as EWSPagingService, folder_ids_element as folder_ids_element, shape_element as shape_element
from _typeshed import Incomplete

log: Incomplete

class FindPeople(EWSPagingService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    supported_from = EXCHANGE_2013
    additional_fields: Incomplete
    shape: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    def call(self, folder, additional_fields, restriction, order_fields, shape, query_string, depth, max_items, offset): ...
    def get_payload(self, folders, additional_fields, restriction, order_fields, query_string, shape, depth, page_size, offset: int = 0): ...
