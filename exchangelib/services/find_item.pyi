from ..errors import InvalidEnumValue as InvalidEnumValue
from ..folders.base import BaseFolder as BaseFolder
from ..items import ID_ONLY as ID_ONLY, ITEM_TRAVERSAL_CHOICES as ITEM_TRAVERSAL_CHOICES, Item as Item, SHAPE_CHOICES as SHAPE_CHOICES
from ..util import MNS as MNS, TNS as TNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSPagingService as EWSPagingService, folder_ids_element as folder_ids_element, shape_element as shape_element
from _typeshed import Incomplete

class FindItem(EWSPagingService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    paging_container_name: Incomplete
    additional_fields: Incomplete
    shape: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    def call(self, folders, additional_fields, restriction, order_fields, shape, query_string, depth, calendar_view, max_items, offset): ...
    def get_payload(self, folders, additional_fields, restriction, order_fields, query_string, shape, depth, calendar_view, page_size, offset: int = 0): ...
