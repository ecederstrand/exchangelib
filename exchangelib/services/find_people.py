from collections import OrderedDict
import logging

from ..errors import MalformedResponseError, ErrorServerBusy
from ..util import create_element, set_xml_value, xml_to_str, MNS
from .common import EWSAccountService, PagingEWSMixIn, create_shape_element

log = logging.getLogger(__name__)


class FindPeople(EWSAccountService, PagingEWSMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/findpeople-operation"""
    SERVICE_NAME = 'FindPeople'
    element_container_name = '{%s}People' % MNS

    def call(self, folder, additional_fields, restriction, order_fields, shape, query_string, depth, max_items, offset):
        """Find items in an account.

        Args:
          folder: the Folder object to query
          additional_fields: the extra fields that should be returned with the item, as FieldPath objects
          restriction: a Restriction object for
          order_fields: the fields to sort the results by
          shape: The set of attributes to return
          query_string: a QueryString object
          depth: How deep in the folder structure to search for items
          max_items: the max number of items to return
          offset: the offset relative to the first item in the item collection. Usually 0.

        Returns:
          XML elements for the matching items

        """
        from ..items import Persona, ID_ONLY
        personas = self._paged_call(payload_func=self.get_payload, max_items=max_items, **dict(
            folder=folder,
            additional_fields=additional_fields,
            restriction=restriction,
            order_fields=order_fields,
            query_string=query_string,
            shape=shape,
            depth=depth,
            page_size=self.chunk_size,
            offset=offset,
        ))
        if shape == ID_ONLY and additional_fields is None:
            for p in personas:
                yield p if isinstance(p, Exception) else Persona.id_from_xml(p)
        else:
            for p in personas:
                yield p if isinstance(p, Exception) else Persona.from_xml(p, account=self.account)

    def get_payload(self, folder, additional_fields, restriction, order_fields, query_string, shape, depth, page_size,
                    offset=0):
        findpeople = create_element('m:%s' % self.SERVICE_NAME, attrs=dict(Traversal=depth))
        personashape = create_shape_element(
            tag='m:PersonaShape', shape=shape, additional_fields=additional_fields, version=self.account.version
        )
        findpeople.append(personashape)
        view_type = create_element(
            'm:IndexedPageItemView',
            attrs=OrderedDict([
                ('MaxEntriesReturned', str(page_size)),
                ('Offset', str(offset)),
                ('BasePoint', 'Beginning'),
            ])
        )
        findpeople.append(view_type)
        if restriction:
            findpeople.append(restriction.to_xml(version=self.account.version))
        if order_fields:
            findpeople.append(set_xml_value(
                create_element('m:SortOrder'),
                order_fields,
                version=self.account.version
            ))
        findpeople.append(set_xml_value(
            create_element('m:ParentFolderId'),
            folder,
            version=self.account.version
        ))
        if query_string:
            findpeople.append(query_string.to_xml(version=self.account.version))
        return findpeople

    def _paged_call(self, payload_func, max_items, **kwargs):
        item_count = kwargs['offset']
        while True:
            log.debug('EWS %s, account %s, service %s: Getting items at offset %s',
                      self.protocol.service_endpoint, self.account, self.SERVICE_NAME, item_count)
            kwargs['offset'] = item_count
            try:
                response = self._get_response_xml(payload=payload_func(**kwargs))
            except ErrorServerBusy as e:
                self._handle_backoff(e)
                continue
            # Collect a tuple of (rootfolder, total_items) tuples
            parsed_pages = [self._get_page(message) for message in response]
            if len(parsed_pages) != 1:
                # We can only query one folder, so there should only be one element in response
                raise MalformedResponseError("Expected single item in 'response', got %s" % len(parsed_pages))
            rootfolder, total_items = parsed_pages[0]
            if rootfolder is not None:
                container = rootfolder.find(self.element_container_name)
                if container is None:
                    raise MalformedResponseError('No %s elements in ResponseMessage (%s)' % (
                        self.element_container_name, xml_to_str(rootfolder)))
                for elem in self._get_elements_in_container(container=container):
                    item_count += 1
                    yield elem
                if max_items and item_count >= max_items:
                    log.debug("'max_items' count reached")
                    break
            if total_items <= 0 or item_count >= total_items:
                log.debug('Got all items in view')
                break

    def _get_page(self, message):
        self._get_element_container(message=message)  # Just raise exceptions
        total_items = int(message.find('{%s}TotalNumberOfPeopleInView' % MNS).text)
        first_matching = int(message.find('{%s}FirstMatchingRowIndex' % MNS).text)
        first_loaded = int(message.find('{%s}FirstLoadedRowIndex' % MNS).text)
        log.debug('%s: Got page with total items %s, first matching %s, first loaded %s ', self.SERVICE_NAME,
                  total_items, first_matching, first_loaded)
        return message, total_items
