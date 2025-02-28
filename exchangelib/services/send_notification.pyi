from ..errors import InvalidEnumValue as InvalidEnumValue
from ..properties import Notification as Notification
from ..util import MNS as MNS, create_element as create_element
from .common import EWSService as EWSService, add_xml_child as add_xml_child
from _typeshed import Incomplete

class SendNotification(EWSService):
    SERVICE_NAME: str
    OK: str
    UNSUBSCRIBE: str
    STATUS_CHOICES: Incomplete
    def ok_payload(self): ...
    def unsubscribe_payload(self): ...
    def get_payload(self, status): ...
