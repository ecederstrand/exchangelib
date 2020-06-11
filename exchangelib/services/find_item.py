from collections import OrderedDict

from ..util import create_element, set_xml_value, TNS
from .common import EWSFolderService, PagingEWSMixIn, create_shape_element


class FindItem(EWSFolderService, PagingEWSMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/finditem"""
    SERVICE_NAME = 'FindItem'
    element_container_name = '{%s}Items' % TNS

    def call(self, additional_fields, restriction, order_fields, shape, query_string, depth, calendar_view, max_items,
             offset):
        """Find items in an account.

        Args:
          additional_fields: the extra fields that should be returned with the item, as FieldPath objects
          restriction: a Restriction object for
          order_fields: the fields to sort the results by
          shape: The set of attributes to return
          query_string: a QueryString object
          depth: How deep in the folder structure to search for items
          calendar_view: If set, returns recurring calendar items unfolded
          max_items: the max number of items to return
          offset: the offset relative to the first item in the item collection. Usually 0.

        Returns:
          XML elements for the matching items

        """
        return self._paged_call(payload_func=self.get_payload, max_items=max_items, **dict(
            additional_fields=additional_fields,
            restriction=restriction,
            order_fields=order_fields,
            query_string=query_string,
            shape=shape,
            depth=depth,
            calendar_view=calendar_view,
            page_size=self.chunk_size,
            offset=offset,
        ))

    def get_payload(self, additional_fields, restriction, order_fields, query_string, shape, depth, calendar_view,
                    page_size, offset=0):
        finditem = create_element('m:%s' % self.SERVICE_NAME, attrs=dict(Traversal=depth))
        itemshape = create_shape_element(
            tag='m:ItemShape', shape=shape, additional_fields=additional_fields, version=self.account.version
        )
        finditem.append(itemshape)
        if calendar_view is None:
            view_type = create_element(
                'm:IndexedPageItemView',
                attrs=OrderedDict([
                    ('MaxEntriesReturned', str(page_size)),
                    ('Offset', str(offset)),
                    ('BasePoint', 'Beginning'),
                ])
            )
        else:
            view_type = calendar_view.to_xml(version=self.account.version)
        finditem.append(view_type)
        if restriction:
            finditem.append(restriction.to_xml(version=self.account.version))
        if order_fields:
            finditem.append(set_xml_value(
                create_element('m:SortOrder'),
                order_fields,
                version=self.account.version
            ))
        finditem.append(set_xml_value(
            create_element('m:ParentFolderIds'),
            self.folders,
            version=self.account.version
        ))
        if query_string:
            finditem.append(query_string.to_xml(version=self.account.version))
        return finditem
