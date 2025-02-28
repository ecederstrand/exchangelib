from ..errors import InvalidEnumValue as InvalidEnumValue
from ..items import AFFECTED_TASK_OCCURRENCES_CHOICES as AFFECTED_TASK_OCCURRENCES_CHOICES, DELETE_TYPE_CHOICES as DELETE_TYPE_CHOICES, SEND_MEETING_CANCELLATIONS_CHOICES as SEND_MEETING_CANCELLATIONS_CHOICES
from ..util import create_element as create_element
from ..version import EXCHANGE_2013_SP1 as EXCHANGE_2013_SP1
from .common import EWSAccountService as EWSAccountService, item_ids_element as item_ids_element

class DeleteItem(EWSAccountService):
    SERVICE_NAME: str
    returns_elements: bool
    def call(self, items, delete_type, send_meeting_cancellations, affected_task_occurrences, suppress_read_receipts): ...
    def get_payload(self, items, delete_type, send_meeting_cancellations, affected_task_occurrences, suppress_read_receipts): ...
