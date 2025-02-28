from ..properties import DLMailbox as DLMailbox, DelegateUser as DelegateUser, UserId as UserId
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from ..version import EXCHANGE_2007_SP1 as EXCHANGE_2007_SP1
from .common import EWSAccountService as EWSAccountService
from _typeshed import Incomplete

class GetDelegate(EWSAccountService):
    SERVICE_NAME: str
    ERRORS_TO_CATCH_IN_RESPONSE: Incomplete
    supported_from = EXCHANGE_2007_SP1
    def call(self, user_ids, include_permissions): ...
    def get_payload(self, user_ids, mailbox, include_permissions): ...
