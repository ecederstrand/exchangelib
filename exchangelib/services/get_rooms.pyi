from ..properties import Room as Room
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from ..version import EXCHANGE_2010 as EXCHANGE_2010
from .common import EWSService as EWSService
from _typeshed import Incomplete

class GetRooms(EWSService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    supported_from = EXCHANGE_2010
    def call(self, room_list): ...
    def get_payload(self, room_list): ...
