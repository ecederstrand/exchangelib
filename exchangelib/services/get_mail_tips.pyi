from ..properties import MailTips as MailTips
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSService as EWSService

class GetMailTips(EWSService):
    SERVICE_NAME: str
    def call(self, sending_as, recipients, mail_tips_requested): ...
    def get_payload(self, recipients, sending_as, mail_tips_requested): ...
