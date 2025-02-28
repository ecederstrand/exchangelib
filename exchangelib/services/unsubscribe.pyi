from ..util import create_element as create_element
from .common import EWSAccountService as EWSAccountService, add_xml_child as add_xml_child

class Unsubscribe(EWSAccountService):
    SERVICE_NAME: str
    returns_elements: bool
    prefer_affinity: bool
    def call(self, subscription_id): ...
    def get_payload(self, subscription_id): ...
