from ..properties import FreeBusyView as FreeBusyView
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSService as EWSService
from _typeshed import Incomplete

class GetUserAvailability(EWSService):
    SERVICE_NAME: str
    tzinfo: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    def call(self, tzinfo, mailbox_data, timezone, free_busy_view_options): ...
    def get_payload(self, mailbox_data, timezone, free_busy_view_options): ...
