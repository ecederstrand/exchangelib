from ..errors import InvalidEnumValue as InvalidEnumValue
from ..items import DELETE_TYPE_CHOICES as DELETE_TYPE_CHOICES
from ..util import create_element as create_element
from .common import EWSAccountService as EWSAccountService, folder_ids_element as folder_ids_element

class EmptyFolder(EWSAccountService):
    SERVICE_NAME: str
    returns_elements: bool
    def call(self, folders, delete_type, delete_sub_folders): ...
    def get_payload(self, folders, delete_type, delete_sub_folders): ...
