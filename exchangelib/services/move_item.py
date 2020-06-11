from ..util import create_element, set_xml_value, MNS
from .common import EWSAccountService, create_item_ids_element


class MoveItem(EWSAccountService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/moveitem-operation"""
    SERVICE_NAME = 'MoveItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, items, to_folder):
        from ..folders import BaseFolder, FolderId, DistinguishedFolderId
        if not isinstance(to_folder, (BaseFolder, FolderId, DistinguishedFolderId)):
            raise ValueError("'to_folder' %r must be a Folder or FolderId instance" % to_folder)
        return self._get_elements(payload=self.get_payload(
            items=items,
            to_folder=to_folder,
        ))

    def get_payload(self, items, to_folder):
        # Takes a list of items and returns their new item IDs
        moveitem = create_element('m:%s' % self.SERVICE_NAME)
        tofolderid = create_element('m:ToFolderId')
        set_xml_value(tofolderid, to_folder, version=self.account.version)
        moveitem.append(tofolderid)
        item_ids = create_item_ids_element(items=items, version=self.account.version)
        moveitem.append(item_ids)
        return moveitem
