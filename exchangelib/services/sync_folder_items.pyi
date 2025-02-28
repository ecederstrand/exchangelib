from ..errors import InvalidEnumValue as InvalidEnumValue, InvalidTypeError as InvalidTypeError
from ..folders import BaseFolder as BaseFolder
from ..properties import ItemId as ItemId
from ..util import MNS as MNS, TNS as TNS, peek as peek, xml_text_to_value as xml_text_to_value
from .common import add_xml_child as add_xml_child, item_ids_element as item_ids_element
from .sync_folder_hierarchy import SyncFolder as SyncFolder
from _typeshed import Incomplete

class SyncFolderItems(SyncFolder):
    SERVICE_NAME: str
    SYNC_SCOPES: Incomplete
    READ_FLAG_CHANGE: str
    CHANGE_TYPES: Incomplete
    shape_tag: str
    last_in_range_name: Incomplete
    change_types_map: Incomplete
    sync_state: Incomplete
    def call(self, folder, shape, additional_fields, sync_state, ignore, max_changes_returned, sync_scope): ...
    def get_payload(self, folder, shape, additional_fields, sync_state, ignore, max_changes_returned, sync_scope): ...
