from ..errors import ResponseMessageError
from ..util import create_element, MNS
from .common import EWSAccountService, EWSPooledMixIn, create_item_ids_element


class ExportItems(EWSAccountService, EWSPooledMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/exportitems-operation"""
    ERRORS_TO_CATCH_IN_RESPONSE = ResponseMessageError
    SERVICE_NAME = 'ExportItems'
    element_container_name = '{%s}Data' % MNS

    def call(self, items):
        return self._pool_requests(payload_func=self.get_payload, **dict(items=items))

    def get_payload(self, items):
        exportitems = create_element('m:%s' % self.SERVICE_NAME)
        item_ids = create_item_ids_element(items=items, version=self.account.version)
        exportitems.append(item_ids)
        return exportitems

    # We need to override this since ExportItemsResponseMessage is formatted a
    #  little bit differently. Namely, all we want is the 64bit string in the
    #  Data tag.
    def _get_elements_in_container(self, container):
        return [container.text]
