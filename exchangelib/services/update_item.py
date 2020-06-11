from collections import OrderedDict
import logging

from ..ewsdatetime import EWSDate
from ..util import create_element, set_xml_value, MNS
from ..version import EXCHANGE_2010, EXCHANGE_2013_SP1
from .common import EWSAccountService, EWSPooledMixIn, to_item_id

log = logging.getLogger(__name__)


class UpdateItem(EWSAccountService, EWSPooledMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/updateitem"""
    SERVICE_NAME = 'UpdateItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, items, conflict_resolution, message_disposition, send_meeting_invitations_or_cancellations,
             suppress_read_receipts):
        from ..items import CONFLICT_RESOLUTION_CHOICES, MESSAGE_DISPOSITION_CHOICES, \
            SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES, SEND_ONLY
        if conflict_resolution not in CONFLICT_RESOLUTION_CHOICES:
            raise ValueError("'conflict_resolution' %s must be one of %s" % (
                conflict_resolution, CONFLICT_RESOLUTION_CHOICES
            ))
        if message_disposition not in MESSAGE_DISPOSITION_CHOICES:
            raise ValueError("'message_disposition' %s must be one of %s" % (
                message_disposition, MESSAGE_DISPOSITION_CHOICES
            ))
        if send_meeting_invitations_or_cancellations not in SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES:
            raise ValueError("'send_meeting_invitations_or_cancellations' %s must be one of %s" % (
                send_meeting_invitations_or_cancellations, SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES
            ))
        if suppress_read_receipts not in (True, False):
            raise ValueError("'suppress_read_receipts' %s must be True or False" % suppress_read_receipts)
        if message_disposition == SEND_ONLY:
            raise ValueError('Cannot send-only existing objects. Use SendItem service instead')
        return self._pool_requests(payload_func=self.get_payload, **dict(
            items=items,
            conflict_resolution=conflict_resolution,
            message_disposition=message_disposition,
            send_meeting_invitations_or_cancellations=send_meeting_invitations_or_cancellations,
            suppress_read_receipts=suppress_read_receipts,
        ))

    def _delete_item_elem(self, field_path):
        deleteitemfield = create_element('t:DeleteItemField')
        return set_xml_value(deleteitemfield, field_path, version=self.account.version)

    def _set_item_elem(self, item_model, field_path, value):
        setitemfield = create_element('t:SetItemField')
        set_xml_value(setitemfield, field_path, version=self.account.version)
        folderitem = create_element(item_model.request_tag())
        field_elem = field_path.field.to_xml(value, version=self.account.version)
        set_xml_value(folderitem, field_elem, version=self.account.version)
        setitemfield.append(folderitem)
        return setitemfield

    @staticmethod
    def _sorted_fields(item_model, fieldnames):
        # Take a list of fieldnames and return the (unique) fields in the order they are mentioned in item_class.FIELDS.
        # Checks that all fieldnames are valid.
        unique_fieldnames = list(OrderedDict.fromkeys(fieldnames))  # Make field names unique ,but keep ordering
        # Loop over FIELDS and not supported_fields(). Upstream should make sure not to update a non-supported field.
        for f in item_model.FIELDS:
            if f.name in unique_fieldnames:
                unique_fieldnames.remove(f.name)
                yield f
        if unique_fieldnames:
            raise ValueError("Field name(s) %s are not valid for a '%s' item" % (
                ', '.join("'%s'" % f for f in unique_fieldnames), item_model.__name__))

    def _get_item_update_elems(self, item, fieldnames):
        from ..items import CalendarItem
        fieldnames_copy = list(fieldnames)

        if item.__class__ == CalendarItem:
            # For CalendarItem items where we update 'start' or 'end', we want to update internal timezone fields
            item.clean_timezone_fields(version=self.account.version)  # Possibly also sets timezone values
            meeting_tz_field, start_tz_field, end_tz_field = CalendarItem.timezone_fields()
            if self.account.version.build < EXCHANGE_2010:
                if 'start' in fieldnames_copy or 'end' in fieldnames_copy:
                    fieldnames_copy.append(meeting_tz_field.name)
            else:
                if 'start' in fieldnames_copy:
                    fieldnames_copy.append(start_tz_field.name)
                if 'end' in fieldnames_copy:
                    fieldnames_copy.append(end_tz_field.name)
        else:
            meeting_tz_field, start_tz_field, end_tz_field = None, None, None

        for field in self._sorted_fields(item_model=item.__class__, fieldnames=fieldnames_copy):
            if field.is_read_only:
                raise ValueError('%s is a read-only field' % field.name)
            value = self._get_item_value(item, field, meeting_tz_field, start_tz_field, end_tz_field)
            if value is None or (field.is_list and not value):
                # A value of None or [] means we want to remove this field from the item
                for elem in self._get_delete_item_elems(field=field):
                    yield elem
            else:
                for elem in self._get_set_item_elems(item_model=item.__class__, field=field, value=value):
                    yield elem

    def _get_item_value(self, item, field, meeting_tz_field, start_tz_field, end_tz_field):
        from ..items import CalendarItem
        value = field.clean(getattr(item, field.name), version=self.account.version)  # Make sure the value is OK
        if item.__class__ == CalendarItem:
            # For CalendarItem items where we update 'start' or 'end', we want to send values in the local timezone
            if field.name in ('start', 'end') and type(value) == EWSDate:
                # EWS always expects a datetime
                return item.date_to_datetime(field_name=field.name)
            if self.account.version.build < EXCHANGE_2010:
                if field.name in ('start', 'end'):
                    value = value.astimezone(getattr(item, meeting_tz_field.name))
            else:
                if field.name == 'start':
                    value = value.astimezone(getattr(item, start_tz_field.name))
                elif field.name == 'end':
                    value = value.astimezone(getattr(item, end_tz_field.name))
        return value

    def _get_delete_item_elems(self, field):
        from ..fields import FieldPath
        if field.is_required or field.is_required_after_save:
            raise ValueError('%s is a required field and may not be deleted' % field.name)
        for field_path in FieldPath(field=field).expand(version=self.account.version):
            yield self._delete_item_elem(field_path=field_path)

    def _get_set_item_elems(self, item_model, field, value):
        from ..fields import FieldPath, IndexedField
        from ..indexed_properties import MultiFieldIndexedElement
        if isinstance(field, IndexedField):
            # TODO: Maybe the set/delete logic should extend into subfields, not just overwrite the whole item.
            for v in value:
                # TODO: We should also delete the labels that no longer exist in the list
                if issubclass(field.value_cls, MultiFieldIndexedElement):
                    # We have subfields. Generate SetItem XML for each subfield. SetItem only accepts items that
                    # have the one value set that we want to change. Create a new IndexedField object that has
                    # only that value set.
                    for subfield in field.value_cls.supported_fields(version=self.account.version):
                        yield self._set_item_elem(
                            item_model=item_model,
                            field_path=FieldPath(field=field, label=v.label, subfield=subfield),
                            value=field.value_cls(**{'label': v.label, subfield.name: getattr(v, subfield.name)}),
                        )
                else:
                    # The simpler IndexedFields with only one subfield
                    subfield = field.value_cls.value_field(version=self.account.version)
                    yield self._set_item_elem(
                        item_model=item_model,
                        field_path=FieldPath(field=field, label=v.label, subfield=subfield),
                        value=v,
                    )
        else:
            yield self._set_item_elem(item_model=item_model, field_path=FieldPath(field=field), value=value)

    def get_payload(self, items, conflict_resolution, message_disposition, send_meeting_invitations_or_cancellations,
                    suppress_read_receipts):
        # Takes a list of (Item, fieldnames) tuples where 'Item' is a instance of a subclass of Item and 'fieldnames'
        # are the attribute names that were updated. Returns the XML for an UpdateItem call.
        # an UpdateItem request.
        from ..properties import ItemId
        if self.account.version.build >= EXCHANGE_2013_SP1:
            updateitem = create_element(
                'm:%s' % self.SERVICE_NAME,
                attrs=OrderedDict([
                    ('ConflictResolution', conflict_resolution),
                    ('MessageDisposition', message_disposition),
                    ('SendMeetingInvitationsOrCancellations', send_meeting_invitations_or_cancellations),
                    ('SuppressReadReceipts', 'true' if suppress_read_receipts else 'false'),
                ])
            )
        else:
            updateitem = create_element(
                'm:%s' % self.SERVICE_NAME,
                attrs=OrderedDict([
                    ('ConflictResolution', conflict_resolution),
                    ('MessageDisposition', message_disposition),
                    ('SendMeetingInvitationsOrCancellations', send_meeting_invitations_or_cancellations),
                ])
            )
        itemchanges = create_element('m:ItemChanges')
        version = self.account.version
        for item, fieldnames in items:
            if not fieldnames:
                raise ValueError('"fieldnames" must not be empty')
            itemchange = create_element('t:ItemChange')
            log.debug('Updating item %s fields %s', item, fieldnames)
            set_xml_value(itemchange, to_item_id(item, ItemId, version=version), version=version)
            updates = create_element('t:Updates')
            for elem in self._get_item_update_elems(item=item, fieldnames=fieldnames):
                updates.append(elem)
            itemchange.append(updates)
            itemchanges.append(itemchange)
        if not len(itemchanges):
            raise ValueError('"items" must not be empty')
        updateitem.append(itemchanges)
        return updateitem
