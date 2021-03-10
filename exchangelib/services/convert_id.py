from .common import EWSService
from ..properties import AlternateId, AlternatePublicFolderId, AlternatePublicFolderItemId, ID_FORMATS
from ..util import create_element, set_xml_value
from ..version import EXCHANGE_2007_SP1


class ConvertId(EWSService):
    """Takes a list of IDs to convert. Returns a list of converted IDs or exception instances, in the same order as the
    input list.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/convertid-operation

    """
    SERVICE_NAME = 'ConvertId'
    supported_from = EXCHANGE_2007_SP1

    def call(self, items, destination_format):
        if destination_format not in ID_FORMATS:
            raise ValueError("'destination_format' %r must be one of %s" % (destination_format, ID_FORMATS))
        cls_map = {cls.response_tag(): cls for cls in (
            AlternateId, AlternatePublicFolderId, AlternatePublicFolderItemId
        )}
        for elem in self._chunked_get_elements(self.get_payload, items=items, destination_format=destination_format):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield cls_map[elem.tag].from_xml(elem, account=None)

    def get_payload(self, items, destination_format):
        supported_item_classes = AlternateId, AlternatePublicFolderId, AlternatePublicFolderItemId
        convertid = create_element('m:%s' % self.SERVICE_NAME, attrs=dict(DestinationFormat=destination_format))
        item_ids = create_element('m:SourceIds')
        for item in items:
            if not isinstance(item, supported_item_classes):
                raise ValueError("'item' value %r must be an instance of %r" % (item, supported_item_classes))
            set_xml_value(item_ids, item, version=self.protocol.version)
        if not item_ids:
            raise ValueError('"items" must not be empty')
        convertid.append(item_ids)
        return convertid

    @classmethod
    def _get_elements_in_container(cls, container):
        # We may have other elements in here, e.g. 'ResponseCode'. Filter away those.
        return container.findall(AlternateId.response_tag()) \
            + container.findall(AlternatePublicFolderId.response_tag()) \
            + container.findall(AlternatePublicFolderItemId.response_tag())
