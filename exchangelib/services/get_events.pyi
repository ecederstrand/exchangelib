from ..properties import Notification as Notification
from ..util import create_element as create_element
from .common import EWSAccountService as EWSAccountService, add_xml_child as add_xml_child
from _typeshed import Incomplete

log: Incomplete

class GetEvents(EWSAccountService):
    SERVICE_NAME: str
    prefer_affinity: bool
    def call(self, subscription_id, watermark): ...
    def get_payload(self, subscription_id, watermark): ...
