from ..errors import ErrorAccessDenied as ErrorAccessDenied, ErrorFolderNotFound as ErrorFolderNotFound, ErrorInvalidOperation as ErrorInvalidOperation, ErrorItemNotFound as ErrorItemNotFound, ErrorNoPublicFolderReplicaAvailable as ErrorNoPublicFolderReplicaAvailable
from ..util import MNS as MNS, create_element as create_element
from .common import EWSAccountService as EWSAccountService, folder_ids_element as folder_ids_element, parse_folder_elem as parse_folder_elem, shape_element as shape_element
from _typeshed import Incomplete

class GetFolder(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    ERRORS_TO_CATCH_IN_RESPONSE: Incomplete
    folders: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    def call(self, folders, additional_fields, shape): ...
    def get_payload(self, folders, additional_fields, shape): ...
