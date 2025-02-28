from ..errors import ErrorFolderExists as ErrorFolderExists
from ..util import MNS as MNS, create_element as create_element
from .common import EWSAccountService as EWSAccountService, folder_ids_element as folder_ids_element, parse_folder_elem as parse_folder_elem, set_xml_value as set_xml_value
from _typeshed import Incomplete

class CreateFolder(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    ERRORS_TO_CATCH_IN_RESPONSE: Incomplete
    folders: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    def call(self, parent_folder, folders): ...
    def get_payload(self, folders, parent_folder): ...
