from ..errors import InvalidTypeError as InvalidTypeError
from ..folders import BaseFolder as BaseFolder
from ..properties import FolderId as FolderId
from ..util import MNS as MNS, create_element as create_element
from .common import EWSAccountService as EWSAccountService, folder_ids_element as folder_ids_element
from _typeshed import Incomplete

class MoveFolder(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    def call(self, folders, to_folder): ...
    def get_payload(self, folders, to_folder): ...
