from ..errors import ErrorNameResolutionMultipleResults as ErrorNameResolutionMultipleResults
from ..properties import Mailbox as Mailbox
from ..util import MNS as MNS, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSService as EWSService
from _typeshed import Incomplete

class ExpandDL(EWSService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    WARNINGS_TO_IGNORE_IN_RESPONSE = ErrorNameResolutionMultipleResults
    def call(self, distribution_list): ...
    def get_payload(self, distribution_list): ...
