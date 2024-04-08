import abc

from ..fields import FieldPath, IndexedField
from ..properties import FolderId
from ..util import MNS, create_element, set_xml_value
from .common import EWSAccountService, parse_folder_elem, to_item_id


class BaseUpdateService(EWSAccountService, metaclass=abc.ABCMeta):
    """Base class for UpdateFolder and UpdateItem"""

    SET_FIELD_ELEMENT_NAME = None
    DELETE_FIELD_ELEMENT_NAME = None
    CHANGE_ELEMENT_NAME = None
    CHANGES_ELEMENT_NAME = None

    @staticmethod
    def _sorted_fields(target_model, fieldnames):
        # Take a list of fieldnames and return the fields in the order they are mentioned in target_model.FIELDS.
        # Checks that all fieldnames are valid.
        fieldnames_copy = list(fieldnames)
        # Loop over FIELDS and not supported_fields(). Upstream should make sure not to update a non-supported field.
        for f in target_model.FIELDS:
            if f.name in fieldnames_copy:
                fieldnames_copy.remove(f.name)
                yield f
        if fieldnames_copy:
            raise ValueError(f"Field name(s) {fieldnames_copy} are not valid {target_model.__name__!r} fields")

    def _get_value(self, target, field):
        return field.clean(getattr(target, field.name), version=self.account.version)  # Make sure the value is OK

    def _set_field_elems(self, target_model, field, value):
        if isinstance(field, IndexedField):
            # Generate either set or delete elements for all combinations of labels and subfields
            supported_labels = field.value_cls.get_field_by_fieldname("label").supported_choices(
                version=self.account.version
            )
            seen_labels = set()
            subfields = field.value_cls.supported_fields(version=self.account.version)
            for v in value:
                seen_labels.add(v.label)
                for subfield in subfields:
                    field_path = FieldPath(field=field, label=v.label, subfield=subfield)
                    subfield_value = getattr(v, subfield.name)
                    if not subfield_value:
                        # Generate delete elements for blank subfield values
                        yield self._delete_field_elem(field_path=field_path)
                    else:
                        # Generate set elements for non-null subfield values
                        yield self._set_field_elem(
                            target_model=target_model,
                            field_path=field_path,
                            value=field.value_cls(**{"label": v.label, subfield.name: subfield_value}),
                        )
                # Generate delete elements for all subfields of all labels not mentioned in the list of values
                for label in (label for label in supported_labels if label not in seen_labels):
                    for subfield in subfields:
                        yield self._delete_field_elem(field_path=FieldPath(field=field, label=label, subfield=subfield))
        else:
            yield self._set_field_elem(target_model=target_model, field_path=FieldPath(field=field), value=value)

    def _set_field_elem(self, target_model, field_path, value):
        set_field = create_element(self.SET_FIELD_ELEMENT_NAME)
        set_xml_value(set_field, field_path, version=self.account.version)
        folder = create_element(target_model.request_tag())
        field_elem = field_path.field.to_xml(value, version=self.account.version)
        set_xml_value(folder, field_elem, version=self.account.version)
        set_field.append(folder)
        return set_field

    def _delete_field_elems(self, field):
        for field_path in FieldPath(field=field).expand(version=self.account.version):
            yield self._delete_field_elem(field_path=field_path)

    def _delete_field_elem(self, field_path):
        delete_folder_field = create_element(self.DELETE_FIELD_ELEMENT_NAME)
        return set_xml_value(delete_folder_field, field_path, version=self.account.version)

    def _update_elems(self, target, fieldnames):
        target_model = target.__class__

        for field in self._sorted_fields(target_model=target_model, fieldnames=fieldnames):
            if field.is_read_only:
                raise ValueError(f"{field.name!r} is a read-only field")
            value = self._get_value(target, field)

            if value is None or (field.is_list and not value):
                # A value of None or [] means we want to remove this field from the item
                if field.is_required or field.is_required_after_save:
                    raise ValueError(f"{field.name!r} is a required field and may not be deleted")
                yield from self._delete_field_elems(field)
                continue

            yield from self._set_field_elems(target_model=target_model, field=field, value=value)

    def _change_elem(self, target, fieldnames):
        if not fieldnames:
            raise ValueError("'fieldnames' must not be empty")
        change = create_element(self.CHANGE_ELEMENT_NAME)
        set_xml_value(change, self._target_elem(target), version=self.account.version)
        updates = create_element("t:Updates")
        for elem in self._update_elems(target=target, fieldnames=fieldnames):
            updates.append(elem)
        change.append(updates)
        return change

    @staticmethod
    @abc.abstractmethod
    def _target_elem(target):
        """Convert the object to update to an XML element"""

    def _changes_elem(self, target_changes):
        changes = create_element(self.CHANGES_ELEMENT_NAME)
        for target, fieldnames in target_changes:
            if not target.account:
                target.account = self.account
            changes.append(self._change_elem(target=target, fieldnames=fieldnames))
        return changes


class UpdateFolder(BaseUpdateService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/updatefolder-operation"""

    SERVICE_NAME = "UpdateFolder"
    SET_FIELD_ELEMENT_NAME = "t:SetFolderField"
    DELETE_FIELD_ELEMENT_NAME = "t:DeleteFolderField"
    CHANGE_ELEMENT_NAME = "t:FolderChange"
    CHANGES_ELEMENT_NAME = "m:FolderChanges"
    element_container_name = f"{{{MNS}}}Folders"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.folders = []  # A hack to communicate parsing args to _elems_to_objs()

    def call(self, folders):
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        self.folders = list(folders)  # Convert to a list, in case 'folders' is a generator. We're iterating twice.
        return self._elems_to_objs(self._chunked_get_elements(self.get_payload, items=self.folders))

    def _elems_to_objs(self, elems):
        for (folder, _), elem in zip(self.folders, elems):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield parse_folder_elem(elem=elem, folder=folder, account=self.account)

    @staticmethod
    def _target_elem(target):
        return to_item_id(target, FolderId)

    def get_payload(self, folders):
        # Takes a list of (Folder, fieldnames) tuples where 'Folder' is an instance of a subclass of Folder and
        # 'fieldnames' are the attribute names that were updated.
        payload = create_element(f"m:{self.SERVICE_NAME}")
        payload.append(self._changes_elem(target_changes=folders))
        return payload
