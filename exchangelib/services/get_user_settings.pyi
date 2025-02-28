from ..errors import MalformedResponseError as MalformedResponseError
from ..properties import UserResponse as UserResponse
from ..transport import DEFAULT_ENCODING as DEFAULT_ENCODING
from ..util import ANS as ANS, add_xml_child as add_xml_child, create_element as create_element, ns_translation as ns_translation, set_xml_value as set_xml_value, xml_to_str as xml_to_str
from ..version import EXCHANGE_2010 as EXCHANGE_2010
from .common import EWSService as EWSService
from _typeshed import Incomplete

log: Incomplete

class GetUserSettings(EWSService):
    SERVICE_NAME: str
    NS_MAP: Incomplete
    element_container_name: Incomplete
    supported_from = EXCHANGE_2010
    def call(self, users, settings): ...
    def wrap(self, content, api_version: Incomplete | None = None): ...
    def get_payload(self, users, settings): ...
