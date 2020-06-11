from ..util import create_element, MNS
from ..version import EXCHANGE_2010
from .common import EWSService


class GetRoomLists(EWSService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getroomlists"""
    SERVICE_NAME = 'GetRoomLists'
    element_container_name = '{%s}RoomLists' % MNS

    def call(self):
        from ..properties import RoomList

        if self.protocol.version.build < EXCHANGE_2010:
            raise NotImplementedError('%s is only supported for Exchange 2010 servers and later' % self.SERVICE_NAME)
        for elem in self._get_elements(payload=self.get_payload()):
            yield RoomList.from_xml(elem=elem, account=None)

    def get_payload(self):
        return create_element('m:%s' % self.SERVICE_NAME)
