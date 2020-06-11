import logging

from ..util import create_element, set_xml_value
from ..version import EXCHANGE_2007_SP1
from .common import EWSPooledMixIn

log = logging.getLogger(__name__)


class ConvertId(EWSPooledMixIn):
    """Takes a list of IDs to convert. Returns a list of converted IDs or exception instances, in the same order as the
    input list.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/convertid-operation

    """
    SERVICE_NAME = 'ConvertId'

    def call(self, items, destination_format):
        if self.protocol.version.build < EXCHANGE_2007_SP1:
            raise NotImplementedError(
                '%r is only supported for Exchange 2007 SP1 servers and later' % self.SERVICE_NAME)
        from ..properties import ID_FORMATS
        if destination_format not in ID_FORMATS:
            raise ValueError("'destination_format' %r must be one of %s" % (destination_format, ID_FORMATS))
        return self._pool_requests(payload_func=self.get_payload, **dict(
            items=items,
            destination_format=destination_format,
        ))

    def get_payload(self, items, destination_format):
        from ..properties import AlternateId, AlternatePublicFolderId, AlternatePublicFolderItemId
        supported_item_classes = AlternateId, AlternatePublicFolderId, AlternatePublicFolderItemId
        convertid = create_element('m:%s' % self.SERVICE_NAME, attrs=dict(DestinationFormat=destination_format))
        item_ids = create_element('m:SourceIds')
        for item in items:
            log.debug('Collecting item %s', item)
            if not isinstance(item, supported_item_classes):
                raise ValueError("'item' value %r must be an instance of %r" % (item, supported_item_classes))
            set_xml_value(item_ids, item, version=self.protocol.version)
        if not len(item_ids):
            raise ValueError('"items" must not be empty')
        convertid.append(item_ids)
        return convertid

    def _get_elements_in_container(self, container):
        # We may have other elements in here, e.g. 'ResponseCode'. Filter away those.
        from ..properties import AlternateId, AlternatePublicFolderId, AlternatePublicFolderItemId
        return container.findall(AlternateId.response_tag()) \
            + container.findall(AlternatePublicFolderId.response_tag()) \
            + container.findall(AlternatePublicFolderItemId.response_tag())

    def _get_element_container(self, message, response_message=None, name=None):
        # There is no element container
        return message
