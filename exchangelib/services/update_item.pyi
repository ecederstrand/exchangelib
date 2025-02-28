from ..errors import InvalidEnumValue as InvalidEnumValue
from ..ewsdatetime import EWSDate as EWSDate
from ..items import CONFLICT_RESOLUTION_CHOICES as CONFLICT_RESOLUTION_CHOICES, CalendarItem as CalendarItem, Item as Item, MESSAGE_DISPOSITION_CHOICES as MESSAGE_DISPOSITION_CHOICES, SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES as SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES, SEND_ONLY as SEND_ONLY
from ..properties import ItemId as ItemId
from ..util import MNS as MNS, create_element as create_element
from ..version import EXCHANGE_2013_SP1 as EXCHANGE_2013_SP1
from .common import to_item_id as to_item_id
from .update_folder import BaseUpdateService as BaseUpdateService
from _typeshed import Incomplete

class UpdateItem(BaseUpdateService):
    SERVICE_NAME: str
    SET_FIELD_ELEMENT_NAME: str
    DELETE_FIELD_ELEMENT_NAME: str
    CHANGE_ELEMENT_NAME: str
    CHANGES_ELEMENT_NAME: str
    element_container_name: Incomplete
    def call(self, items, conflict_resolution, message_disposition, send_meeting_invitations_or_cancellations, suppress_read_receipts): ...
    def get_payload(self, items, conflict_resolution, message_disposition, send_meeting_invitations_or_cancellations, suppress_read_receipts): ...
