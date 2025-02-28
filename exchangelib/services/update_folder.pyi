import abc
from ..fields import FieldPath as FieldPath, IndexedField as IndexedField
from ..properties import FolderId as FolderId
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService, parse_folder_elem as parse_folder_elem, to_item_id as to_item_id
from _typeshed import Incomplete

class BaseUpdateService(EWSAccountService, metaclass=abc.ABCMeta):
    SET_FIELD_ELEMENT_NAME: Incomplete
    DELETE_FIELD_ELEMENT_NAME: Incomplete
    CHANGE_ELEMENT_NAME: Incomplete
    CHANGES_ELEMENT_NAME: Incomplete

class UpdateFolder(BaseUpdateService):
    SERVICE_NAME: str
    SET_FIELD_ELEMENT_NAME: str
    DELETE_FIELD_ELEMENT_NAME: str
    CHANGE_ELEMENT_NAME: str
    CHANGES_ELEMENT_NAME: str
    element_container_name: Incomplete
    folders: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    def call(self, folders): ...
    def get_payload(self, folders): ...
