from ..errors import InvalidEnumValue as InvalidEnumValue, InvalidTypeError as InvalidTypeError
from ..properties import AlternateId as AlternateId, AlternatePublicFolderId as AlternatePublicFolderId, AlternatePublicFolderItemId as AlternatePublicFolderItemId, ID_FORMATS as ID_FORMATS
from ..util import create_element as create_element, set_xml_value as set_xml_value
from .common import EWSService as EWSService
from _typeshed import Incomplete

class ConvertId(EWSService):
    SERVICE_NAME: str
    cls_map: Incomplete
    def call(self, items, destination_format): ...
    def get_payload(self, items, destination_format): ...
