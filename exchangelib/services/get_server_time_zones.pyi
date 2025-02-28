from ..properties import TimeZoneDefinition as TimeZoneDefinition
from ..util import MNS as MNS, create_element as create_element, peek as peek, set_xml_value as set_xml_value
from ..version import EXCHANGE_2010 as EXCHANGE_2010
from .common import EWSService as EWSService
from _typeshed import Incomplete

class GetServerTimeZones(EWSService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    supported_from = EXCHANGE_2010
    def call(self, timezones: Incomplete | None = None, return_full_timezone_data: bool = False): ...
    def get_payload(self, timezones, return_full_timezone_data): ...
