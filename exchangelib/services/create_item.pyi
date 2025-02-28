from ..errors import InvalidEnumValue as InvalidEnumValue, InvalidTypeError as InvalidTypeError
from ..folders import BaseFolder as BaseFolder
from ..items import BulkCreateResult as BulkCreateResult, MESSAGE_DISPOSITION_CHOICES as MESSAGE_DISPOSITION_CHOICES, SAVE_ONLY as SAVE_ONLY, SEND_AND_SAVE_COPY as SEND_AND_SAVE_COPY, SEND_MEETING_INVITATIONS_CHOICES as SEND_MEETING_INVITATIONS_CHOICES, SEND_ONLY as SEND_ONLY
from ..properties import FolderId as FolderId
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService, folder_ids_element as folder_ids_element
from _typeshed import Incomplete

class CreateItem(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    def call(self, items, folder, message_disposition, send_meeting_invitations): ...
    def get_payload(self, items, folder, message_disposition, send_meeting_invitations): ...
