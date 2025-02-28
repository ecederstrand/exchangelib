from ..properties import AvailabilityMailbox as AvailabilityMailbox
from ..settings import OofSettings as OofSettings
from ..util import MNS as MNS, TNS as TNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService
from _typeshed import Incomplete

class GetUserOofSettings(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    def call(self, mailbox): ...
    def get_payload(self, mailbox): ...
