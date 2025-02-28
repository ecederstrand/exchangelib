from ..errors import MalformedResponseError as MalformedResponseError
from ..properties import FailedMailbox as FailedMailbox, SearchableMailbox as SearchableMailbox
from ..util import MNS as MNS, add_xml_child as add_xml_child, create_element as create_element
from ..version import EXCHANGE_2013 as EXCHANGE_2013
from .common import EWSService as EWSService
from _typeshed import Incomplete

class GetSearchableMailboxes(EWSService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    failed_mailboxes_container_name: Incomplete
    supported_from = EXCHANGE_2013
    cls_map: Incomplete
    def call(self, search_filter, expand_group_membership): ...
    def get_payload(self, search_filter, expand_group_membership): ...
