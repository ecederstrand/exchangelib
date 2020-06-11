import logging

from ..util import create_element, set_xml_value, MNS
from .common import EWSAccountService, parse_folder_elem, to_item_id

log = logging.getLogger(__name__)


class UpdateFolder(EWSAccountService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/updatefolder-operation"""
    SERVICE_NAME = 'UpdateFolder'
    element_container_name = '{%s}Folders' % MNS

    def call(self, folders):
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        folders_list = list(f[0] for f in folders)  # Convert to a list, in case 'folders' is a generator
        for folder, elem in zip(folders_list, self._get_elements(payload=self.get_payload(folders=folders))):
            yield parse_folder_elem(elem=elem, folder=folder, account=self.account)

    @staticmethod
    def _sort_fieldnames(folder_model, fieldnames):
        # Take a list of fieldnames and return the fields in the order they are mentioned in folder_model.FIELDS.
        # Loop over FIELDS and not supported_fields(). Upstream should make sure not to update a non-supported field.
        for f in folder_model.FIELDS:
            if f.name in fieldnames:
                yield f.name

    def _set_folder_elem(self, folder_model, field_path, value):
        setfolderfield = create_element('t:SetFolderField')
        set_xml_value(setfolderfield, field_path, version=self.account.version)
        folder = create_element(folder_model.request_tag())
        field_elem = field_path.field.to_xml(value, version=self.account.version)
        set_xml_value(folder, field_elem, version=self.account.version)
        setfolderfield.append(folder)
        return setfolderfield

    def _delete_folder_elem(self, field_path):
        deletefolderfield = create_element('t:DeleteFolderField')
        return set_xml_value(deletefolderfield, field_path, version=self.account.version)

    def _get_folder_update_elems(self, folder, fieldnames):
        from ..fields import FieldPath
        folder_model = folder.__class__
        fieldnames_set = set(fieldnames)

        for fieldname in self._sort_fieldnames(folder_model=folder_model, fieldnames=fieldnames_set):
            field = folder_model.get_field_by_fieldname(fieldname)
            if field.is_read_only:
                raise ValueError('%s is a read-only field' % field.name)
            value = field.clean(getattr(folder, field.name), version=self.account.version)  # Make sure the value is OK

            if value is None or (field.is_list and not value):
                # A value of None or [] means we want to remove this field from the item
                if field.is_required or field.is_required_after_save:
                    raise ValueError('%s is a required field and may not be deleted' % field.name)
                for field_path in FieldPath(field=field).expand(version=self.account.version):
                    yield self._delete_folder_elem(field_path=field_path)
                continue

            yield self._set_folder_elem(folder_model=folder_model, field_path=FieldPath(field=field), value=value)

    def get_payload(self, folders):
        from ..folders import BaseFolder, FolderId, DistinguishedFolderId
        updatefolder = create_element('m:%s' % self.SERVICE_NAME)
        folderchanges = create_element('m:FolderChanges')
        version = self.account.version
        for folder, fieldnames in folders:
            log.debug('Updating folder %s fields %s', folder, fieldnames)
            folderchange = create_element('t:FolderChange')
            if not isinstance(folder, (BaseFolder, FolderId, DistinguishedFolderId)):
                folder = to_item_id(folder, FolderId, version=version)
            set_xml_value(folderchange, folder, version=version)
            updates = create_element('t:Updates')
            for elem in self._get_folder_update_elems(folder=folder, fieldnames=fieldnames):
                updates.append(elem)
            folderchange.append(updates)
            folderchanges.append(folderchange)
        if not len(folderchanges):
            raise ValueError('"folders" must not be empty')
        updatefolder.append(folderchanges)
        return updatefolder
