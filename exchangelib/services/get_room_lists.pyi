from ..properties import RoomList as RoomList
from ..util import MNS as MNS, create_element as create_element
from ..version import EXCHANGE_2010 as EXCHANGE_2010
from .common import EWSService as EWSService
from _typeshed import Incomplete

class GetRoomLists(EWSService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    supported_from = EXCHANGE_2010
    def call(self): ...
    def get_payload(self): ...
