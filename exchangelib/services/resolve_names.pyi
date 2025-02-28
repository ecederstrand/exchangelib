from ..errors import ErrorNameResolutionMultipleResults as ErrorNameResolutionMultipleResults, ErrorNameResolutionNoResults as ErrorNameResolutionNoResults, InvalidEnumValue as InvalidEnumValue
from ..items import Contact as Contact, SEARCH_SCOPE_CHOICES as SEARCH_SCOPE_CHOICES, SHAPE_CHOICES as SHAPE_CHOICES
from ..properties import Mailbox as Mailbox
from ..util import MNS as MNS, add_xml_child as add_xml_child, create_element as create_element
from ..version import EXCHANGE_2010_SP2 as EXCHANGE_2010_SP2
from .common import EWSService as EWSService, folder_ids_element as folder_ids_element
from _typeshed import Incomplete

log: Incomplete

class ResolveNames(EWSService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    ERRORS_TO_CATCH_IN_RESPONSE = ErrorNameResolutionNoResults
    WARNINGS_TO_IGNORE_IN_RESPONSE = ErrorNameResolutionMultipleResults
    candidates_limit: int
    return_full_contact_data: bool
    def __init__(self, *args, **kwargs) -> None: ...
    def call(self, unresolved_entries, parent_folders: Incomplete | None = None, return_full_contact_data: bool = False, search_scope: Incomplete | None = None, contact_data_shape: Incomplete | None = None): ...
    def get_payload(self, unresolved_entries, parent_folders, return_full_contact_data, search_scope, contact_data_shape): ...
