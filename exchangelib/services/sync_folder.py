from ..util import add_xml_child, create_element, set_xml_value, get_xml_attr, MNS
from .common import EWSFolderService


class SyncFolderItems(EWSFolderService):
    """
    https://msdn.microsoft.com/en-us/library/office/aa563967(v=exchg.150).aspx
    """
    SERVICE_NAME = 'SyncFolderItems'
    element_container_name = '{%s}Changes' % MNS

    def call(self, sync_state, ignore, max_changes):
        return self._get_elements(payload=self.get_payload(sync_state, ignore, max_changes))

    def get_payload(self, sync_state, ignore, max_changes):
        payload = create_element(self.SERVICE_NAME, attrs=dict(xmlns=MNS))
        itemshape = create_element('m:ItemShape')
        add_xml_child(itemshape, 't:BaseShape', 'IdOnly')
        payload.append(itemshape)

        folder_ids = create_element('SyncFolderId')
        set_xml_value(folder_ids, self.folders, self.account.version)
        payload.append(folder_ids)

        if sync_state:
            add_xml_child(payload, 'SyncState', sync_state)

        if ignore:
            from ..items import ItemId
            item_ids = create_element('m:ItemIds')
            for item in ignore:
                item_id = ItemId(*(item if isinstance(item, tuple) else (item.item_id, item.changekey)))
                set_xml_value(item_ids, item_id, version=self.account.version)
            payload.append(item_ids)

        add_xml_child(payload, 'MaxChangesReturned', max_changes)
        add_xml_child(payload, 'SyncScope', 'NormalItems')
        return payload

    def _get_elements_in_response(self, response):
        for msg in response:
            sync_state = get_xml_attr(msg, '{%s}SyncState' % MNS)
            for folder in self.folders:
                folder.sync_state = sync_state
        return super(SyncFolderItems, self)._get_elements_in_response(response)

