from ..items import Persona as Persona
from ..properties import PersonaId as PersonaId
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService, to_item_id as to_item_id
from _typeshed import Incomplete
from collections.abc import Generator

class GetPersona(EWSAccountService):
    SERVICE_NAME: str
    def call(self, personas) -> Generator[Incomplete, Incomplete]: ...
    def get_payload(self, persona): ...
