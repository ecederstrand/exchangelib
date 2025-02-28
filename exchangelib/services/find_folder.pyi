from ..errors import InvalidEnumValue as InvalidEnumValue
from ..folders import Folder as Folder
from ..folders.queryset import FOLDER_TRAVERSAL_CHOICES as FOLDER_TRAVERSAL_CHOICES
from ..items import SHAPE_CHOICES as SHAPE_CHOICES
from ..util import MNS as MNS, TNS as TNS, create_element as create_element
from ..version import EXCHANGE_2010 as EXCHANGE_2010
from .common import EWSPagingService as EWSPagingService, folder_ids_element as folder_ids_element, shape_element as shape_element
from _typeshed import Incomplete

class FindFolder(EWSPagingService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    paging_container_name: Incomplete
    root: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    def call(self, folders, additional_fields, restriction, shape, depth, max_items, offset): ...
    def get_payload(self, folders, additional_fields, restriction, shape, depth, page_size, offset: int = 0): ...
