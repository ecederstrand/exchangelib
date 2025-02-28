import abc
from ..properties import FolderId as FolderId
from ..util import MNS as MNS, TNS as TNS, create_element as create_element, xml_text_to_value as xml_text_to_value
from .common import EWSAccountService as EWSAccountService, add_xml_child as add_xml_child, folder_ids_element as folder_ids_element, parse_folder_elem as parse_folder_elem, shape_element as shape_element
from _typeshed import Incomplete

log: Incomplete

class SyncFolder(EWSAccountService, metaclass=abc.ABCMeta):
    element_container_name: Incomplete
    CREATE: str
    UPDATE: str
    DELETE: str
    CHANGE_TYPES: Incomplete
    shape_tag: Incomplete
    last_in_range_name: Incomplete
    change_types_map: Incomplete
    sync_state: Incomplete
    includes_last_item_in_range: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...

class SyncFolderHierarchy(SyncFolder):
    SERVICE_NAME: str
    shape_tag: str
    last_in_range_name: Incomplete
    folder: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    sync_state: Incomplete
    def call(self, folder, shape, additional_fields, sync_state): ...
    def get_payload(self, folder, shape, additional_fields, sync_state): ...
