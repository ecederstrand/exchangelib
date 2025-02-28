from ..errors import ResponseMessageError as ResponseMessageError
from ..util import MNS as MNS, create_element as create_element
from .common import EWSAccountService as EWSAccountService, item_ids_element as item_ids_element
from _typeshed import Incomplete

class ExportItems(EWSAccountService):
    ERRORS_TO_CATCH_IN_RESPONSE = ResponseMessageError
    SERVICE_NAME: str
    element_container_name: Incomplete
    def call(self, items): ...
    def get_payload(self, items): ...
