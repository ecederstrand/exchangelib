from ..util import create_element, set_xml_value, MNS
from .common import EWSService, to_item_id


class GetPersona(EWSService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getpersona-operation"""
    SERVICE_NAME = 'GetPersona'

    def call(self, persona):
        from ..items import Persona
        elements = list(self._get_elements(payload=self.get_payload(persona=persona)))
        if len(elements) != 1:
            raise ValueError('Expected exactly one element in response')
        elem = elements[0]
        if isinstance(elem, Exception):
            raise elem
        return Persona.from_xml(elem=elem.find(Persona.response_tag()), account=None)

    def get_payload(self, persona):
        from ..properties import PersonaId
        version = self.protocol.version
        payload = create_element('m:%s' % self.SERVICE_NAME)
        set_xml_value(payload, to_item_id(persona, PersonaId, version=version), version=version)
        return payload

    @classmethod
    def _response_tag(cls):
        return '{%s}%sResponseMessage' % (MNS, cls.SERVICE_NAME)
