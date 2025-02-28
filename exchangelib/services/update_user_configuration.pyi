from ..util import create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService

class UpdateUserConfiguration(EWSAccountService):
    SERVICE_NAME: str
    returns_elements: bool
    def call(self, user_configuration): ...
    def get_payload(self, user_configuration): ...
