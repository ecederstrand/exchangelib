from ..util import create_element, MNS
from .common import EWSAccountService, EWSPooledMixIn, create_item_ids_element, create_shape_element


class GetItem(EWSAccountService, EWSPooledMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getitem"""
    SERVICE_NAME = 'GetItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, items, additional_fields, shape):
        """Returns all items in an account that correspond to a list of ID's, in stable order.

        Args:
          items: a list of (id, changekey) tuples or Item objects
          additional_fields: the extra fields that should be returned with the item, as FieldPath objects
          shape: The shape of returned objects

        Returns:
          XML elements for the items, in stable order

        """
        return self._pool_requests(payload_func=self.get_payload, **dict(
            items=items,
            additional_fields=additional_fields,
            shape=shape,
        ))

    def get_payload(self, items, additional_fields, shape):
        getitem = create_element('m:%s' % self.SERVICE_NAME)
        itemshape = create_shape_element(
            tag='m:ItemShape', shape=shape, additional_fields=additional_fields, version=self.account.version
        )
        getitem.append(itemshape)
        item_ids = create_item_ids_element(items=items, version=self.account.version)
        getitem.append(item_ids)
        return getitem
