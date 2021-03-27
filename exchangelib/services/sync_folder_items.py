from .common import add_xml_child, create_item_ids_element
from .sync_folder_hierarchy import SyncFolder
from ..properties import ItemId
from ..util import xml_text_to_value, peek, TNS, MNS


class SyncFolderItems(SyncFolder):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/syncfolderitems-operation
    """

    SERVICE_NAME = 'SyncFolderItems'
    SYNC_SCOPES = {
        'NormalItems',
        'NormalAndAssociatedItems',
    }
    # Extra change type
    READ_FLAG_CHANGE = 'read_flag_change'
    CHANGE_TYPES = SyncFolder.CHANGE_TYPES + (READ_FLAG_CHANGE,)
    shape_tag = 'm:ItemShape'
    last_in_range_name = '{%s}IncludesLastItemInRange' % MNS

    def _change_types_map(self):
        res = super()._change_types_map()
        res['{%s}ReadFlagChange' % TNS] = self.READ_FLAG_CHANGE
        return res

    def call(self, folder, shape, additional_fields, sync_state, ignore, max_changes_returned, sync_scope):
        from ..folders.base import BaseFolder
        self.sync_state = sync_state
        if max_changes_returned is None:
            max_changes_returned = self.chunk_size
        if max_changes_returned <= 0:
            raise ValueError("'max_changes_returned' %s must be a positive integer" % max_changes_returned)
        if sync_scope is not None and sync_scope not in self.SYNC_SCOPES:
            raise ValueError("'sync_scope' %s must be one of %r" % (sync_scope, self.SYNC_SCOPES))
        change_types = self._change_types_map()
        for elem in self._get_elements(payload=self.get_payload(
                folder=folder,
                shape=shape,
                additional_fields=additional_fields,
                sync_state=sync_state,
                ignore=ignore,
                max_changes_returned=max_changes_returned,
                sync_scope=sync_scope,
        )):
            if isinstance(elem, Exception):
                yield elem
                continue
            change_type = change_types[elem.tag]
            if change_type == self.READ_FLAG_CHANGE:
                item = (
                    ItemId.from_xml(elem=elem.find(ItemId.response_tag()), account=self.account),
                    xml_text_to_value(elem.find('{%s}IsRead' % TNS).text, bool)
                )
            elif change_type == self.DELETE:
                item = ItemId.from_xml(elem=elem.find(ItemId.response_tag()), account=self.account)
            else:
                # We can't find() the element because we don't know which tag to look for. The change element can
                # contain multiple item types, each with their own tag.
                item_elem = elem[0]
                item = BaseFolder.item_model_from_tag(item_elem.tag).from_xml(elem=item_elem, account=self.account)
            yield change_type, item

    def get_payload(self, folder, shape, additional_fields, sync_state, ignore, max_changes_returned, sync_scope):
        syncfolderitems = self._partial_get_payload(
            folder=folder, shape=shape, additional_fields=additional_fields, sync_state=sync_state
        )
        is_empty, ignore = (True, None) if ignore is None else peek(ignore)
        if not is_empty:
            item_ids = create_item_ids_element(items=ignore, version=self.account.version, tag='m:Ignore')
            syncfolderitems.append(item_ids)
        add_xml_child(syncfolderitems, 'm:MaxChangesReturned', max_changes_returned)
        if sync_scope:
            add_xml_child(syncfolderitems, 'm:SyncScope', sync_scope)
        return syncfolderitems
