from ..errors import EWSError as EWSError, InvalidTypeError as InvalidTypeError
from ..properties import Notification as Notification
from ..util import DocumentYielder as DocumentYielder, DummyResponse as DummyResponse, MNS as MNS, create_element as create_element, get_xml_attr as get_xml_attr, get_xml_attrs as get_xml_attrs
from .common import EWSAccountService as EWSAccountService, add_xml_child as add_xml_child
from _typeshed import Incomplete

log: Incomplete
xml_log: Incomplete

class GetStreamingEvents(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    prefer_affinity: bool
    OK: str
    CLOSED: str
    connection_status: Incomplete
    streaming: bool
    def __init__(self, *args, **kwargs) -> None: ...
    timeout: Incomplete
    def call(self, subscription_ids, connection_timeout): ...
    def get_payload(self, subscription_ids, connection_timeout): ...
