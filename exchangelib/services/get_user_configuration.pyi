from ..errors import InvalidEnumValue as InvalidEnumValue
from ..properties import UserConfiguration as UserConfiguration
from ..util import create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService
from _typeshed import Incomplete

ID: str
DICTIONARY: str
XML_DATA: str
BINARY_DATA: str
ALL: str
PROPERTIES_CHOICES: Incomplete

class GetUserConfiguration(EWSAccountService):
    SERVICE_NAME: str
    def call(self, user_configuration_name, properties): ...
    def get_payload(self, user_configuration_name, properties): ...
