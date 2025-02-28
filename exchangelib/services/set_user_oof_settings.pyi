from ..errors import InvalidTypeError as InvalidTypeError
from ..properties import AvailabilityMailbox as AvailabilityMailbox, Mailbox as Mailbox
from ..settings import OofSettings as OofSettings
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService

class SetUserOofSettings(EWSAccountService):
    SERVICE_NAME: str
    returns_elements: bool
    def call(self, oof_settings, mailbox): ...
    def get_payload(self, oof_settings, mailbox): ...
