from ..util import create_element, set_xml_value, MNS
from ..version import EXCHANGE_2010
from .common import EWSService


class GetRooms(EWSService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getrooms"""
    SERVICE_NAME = 'GetRooms'
    element_container_name = '{%s}Rooms' % MNS

    def call(self, roomlist):
        from ..properties import Room
        if self.protocol.version.build < EXCHANGE_2010:
            raise NotImplementedError('%s is only supported for Exchange 2010 servers and later' % self.SERVICE_NAME)

        for elem in self._get_elements(payload=self.get_payload(roomlist=roomlist)):
            yield Room.from_xml(elem=elem, account=None)

    def get_payload(self, roomlist):
        getrooms = create_element('m:%s' % self.SERVICE_NAME)
        set_xml_value(getrooms, roomlist, version=self.protocol.version)
        return getrooms
