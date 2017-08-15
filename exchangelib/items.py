from __future__ import unicode_literals

import logging
from decimal import Decimal

from future.utils import python_2_unicode_compatible
from six import string_types

from .ewsdatetime import UTC_NOW
from .extended_properties import ExtendedProperty
from .fields import BooleanField, IntegerField, DecimalField, Base64Field, TextField, TextListField, ChoiceField, \
    URIField, BodyField, DateTimeField, MessageHeaderField, PhoneNumberField, EmailAddressField, PhysicalAddressField, \
    ExtendedPropertyField, AttachmentField, RecurrenceField, MailboxField,  MailboxListField, AttendeesField, Choice, \
    OccurrenceField, OccurrenceListField, MemberListField, EWSElementField, EffectiveRightsField
from .properties import EWSElement, ItemId, ConversationId
from .recurrence import FirstOccurrence, LastOccurrence, Occurrence, DeletedOccurrence
from .util import create_element, is_iterable
from .version import EXCHANGE_2010, EXCHANGE_2013

string_type = string_types[0]
log = logging.getLogger(__name__)


# MessageDisposition values. See https://msdn.microsoft.com/en-us/library/office/aa565209(v=exchg.150).aspx
SAVE_ONLY = 'SaveOnly'
SEND_ONLY = 'SendOnly'
SEND_AND_SAVE_COPY = 'SendAndSaveCopy'
MESSAGE_DISPOSITION_CHOICES = (SAVE_ONLY, SEND_ONLY, SEND_AND_SAVE_COPY)

# SendMeetingInvitations values: see https://msdn.microsoft.com/en-us/library/office/aa565209(v=exchg.150).aspx
# SendMeetingInvitationsOrCancellations: see https://msdn.microsoft.com/en-us/library/office/aa580254(v=exchg.150).aspx
# SendMeetingCancellations values: see https://msdn.microsoft.com/en-us/library/office/aa562961(v=exchg.150).aspx
SEND_TO_NONE = 'SendToNone'
SEND_ONLY_TO_ALL = 'SendOnlyToAll'
SEND_ONLY_TO_CHANGED = 'SendOnlyToChanged'
SEND_TO_ALL_AND_SAVE_COPY = 'SendToAllAndSaveCopy'
SEND_TO_CHANGED_AND_SAVE_COPY = 'SendToChangedAndSaveCopy'
SEND_MEETING_INVITATIONS_CHOICES = (SEND_TO_NONE, SEND_ONLY_TO_ALL, SEND_TO_ALL_AND_SAVE_COPY)
SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES = (SEND_TO_NONE, SEND_ONLY_TO_ALL, SEND_ONLY_TO_CHANGED,
                                                      SEND_TO_ALL_AND_SAVE_COPY, SEND_TO_CHANGED_AND_SAVE_COPY)
SEND_MEETING_CANCELLATIONS_CHOICES = (SEND_TO_NONE, SEND_ONLY_TO_ALL, SEND_TO_ALL_AND_SAVE_COPY)

# AffectedTaskOccurrences values. See https://msdn.microsoft.com/en-us/library/office/aa562961(v=exchg.150).aspx
ALL_OCCURRENCIES = 'AllOccurrences'
SPECIFIED_OCCURRENCE_ONLY = 'SpecifiedOccurrenceOnly'
AFFECTED_TASK_OCCURRENCES_CHOICES = (ALL_OCCURRENCIES, SPECIFIED_OCCURRENCE_ONLY)

# ConflictResolution values. See https://msdn.microsoft.com/en-us/library/office/aa580254(v=exchg.150).aspx
NEVER_OVERWRITE = 'NeverOverwrite'
AUTO_RESOLVE = 'AutoResolve'
ALWAYS_OVERWRITE = 'AlwaysOverwrite'
CONFLICT_RESOLUTION_CHOICES = (NEVER_OVERWRITE, AUTO_RESOLVE, ALWAYS_OVERWRITE)

# DeleteType values. See https://msdn.microsoft.com/en-us/library/office/aa562961(v=exchg.150).aspx
HARD_DELETE = 'HardDelete'
SOFT_DELETE = 'SoftDelete'
MOVE_TO_DELETED_ITEMS = 'MoveToDeletedItems'
DELETE_TYPE_CHOICES = (HARD_DELETE, SOFT_DELETE, MOVE_TO_DELETED_ITEMS)

# Traversal enums
SHALLOW = 'Shallow'
SOFT_DELETED = 'SoftDeleted'
ASSOCIATED = 'Associated'
ITEM_TRAVERSAL_CHOICES = (SHALLOW, SOFT_DELETED, ASSOCIATED)

# Shape enums
IdOnly = 'IdOnly'
# AllProperties doesn't actually get all properties in FindItem, just the "first-class" ones. See
#    http://msdn.microsoft.com/en-us/library/office/dn600367(v=exchg.150).aspx
AllProperties = 'AllProperties'
SHAPE_CHOICES = (IdOnly, AllProperties)


class Item(EWSElement):
    ELEMENT_NAME = 'Item'

    # FIELDS is an ordered list of attributes supported by this item class. Not all possible attributes are
    # supported. See full list at
    # https://msdn.microsoft.com/en-us/library/office/aa580790(v=exchg.150).aspx

    # 'extern_id' is not a native EWS Item field. We use it for identification when item originates in an external
    # system. The field is implemented as an extended property on the Item.
    FIELDS = [
        TextField('item_id', is_read_only=True, is_searchable=False),
        TextField('changekey', is_read_only=True, is_searchable=False),
        # TODO: MimeContent actually supports writing, but is still untested
        Base64Field('mime_content', field_uri='item:MimeContent', is_read_only=True),
        TextField('subject', field_uri='item:Subject', max_length=255),
        ChoiceField('sensitivity', field_uri='item:Sensitivity', choices={
            Choice('Normal'), Choice('Personal'), Choice('Private'), Choice('Confidential')
        }, is_required=True, default='Normal'),
        TextField('text_body', field_uri='item:TextBody', is_read_only=True, supported_from=EXCHANGE_2013),
        BodyField('body', field_uri='item:Body'),  # Accepts and returns Body or HTMLBody instances
        AttachmentField('attachments', field_uri='item:Attachments'),  # ItemAttachment or FileAttachment
        DateTimeField('datetime_received', field_uri='item:DateTimeReceived', is_read_only=True),
        IntegerField('size', field_uri='item:Size', is_read_only=True),  # Item size in bytes
        TextListField('categories', field_uri='item:Categories'),
        ChoiceField('importance', field_uri='item:Importance', choices={
            Choice('Low'), Choice('Normal'), Choice('High')
        }, is_required=True, default='Normal'),
        TextField('in_reply_to', field_uri='item:InReplyTo', is_read_only_after_send=True),
        BooleanField('is_draft', field_uri='item:IsDraft', is_read_only=True),
        MessageHeaderField('headers', field_uri='item:InternetMessageHeaders', is_read_only=True),
        DateTimeField('datetime_sent', field_uri='item:DateTimeSent', is_read_only=True),
        DateTimeField('datetime_created', field_uri='item:DateTimeCreated', is_read_only=True),
        # Reminder related fields
        BooleanField('reminder_is_set', field_uri='item:ReminderIsSet', is_required=True, default=False),
        DateTimeField('reminder_due_by', field_uri='item:ReminderDueBy', is_required=False,
                      is_required_after_save=True, is_searchable=False),
        IntegerField('reminder_minutes_before_start', field_uri='item:ReminderMinutesBeforeStart',
                     is_required_after_save=True, min=0, default=0),
        # ExtendedProperty fields go here
        EffectiveRightsField('effective_rights', field_uri='item:EffectiveRights', is_read_only=True),
        TextField('last_modified_name', field_uri='item:LastModifiedName', is_read_only=True),
        DateTimeField('last_modified_time', field_uri='item:LastModifiedTime', is_read_only=True),
        EWSElementField('conversation_id', field_uri='item:ConversationId', value_cls=ConversationId,
                        is_read_only=True),
    ]

    # We can't use __slots__ because we need to add extended properties dynamically

    def __init__(self, **kwargs):
        # 'account' is optional but allows calling 'send()' and 'delete()'
        # 'folder' is optional but allows calling 'save()'. If 'folder' has an account, and 'account' is not set,
        # we use folder.account.
        from .folders import Folder
        from .account import Account
        self.account = kwargs.pop('account', None)
        if self.account is not None:
            assert isinstance(self.account, Account)
        self.folder = kwargs.pop('folder', None)
        if self.folder is not None:
            assert isinstance(self.folder, Folder)
            if self.folder.account is not None:
                if self.account is not None:
                    # Make sure the account from kwargs matches the folder account
                    assert self.account == self.folder.account
                self.account = self.folder.account
        super(Item, self).__init__(**kwargs)
        # pylint: disable=access-member-before-definition
        if self.attachments:
            for a in self.attachments:
                if a.parent_item:
                    assert a.parent_item is self  # An attachment cannot refer to 'self' in __init__
                else:
                    a.parent_item = self
                self.attach(self.attachments)
        else:
            self.attachments = []

    def save(self, update_fields=None, conflict_resolution=AUTO_RESOLVE, send_meeting_invitations=SEND_TO_NONE):
        if self.item_id:
            item_id, changekey = self._update(
                update_fieldnames=update_fields,
                message_disposition=SAVE_ONLY,
                conflict_resolution=conflict_resolution,
                send_meeting_invitations=send_meeting_invitations
            )
            assert self.item_id == item_id
            assert self.changekey != changekey
            self.changekey = changekey
        else:
            if update_fields:
                raise ValueError("'update_fields' is only valid for updates")
            item = self._create(message_disposition=SAVE_ONLY, send_meeting_invitations=send_meeting_invitations)
            self.item_id, self.changekey = item.item_id, item.changekey
            for old_att, new_att in zip(self.attachments, item.attachments):
                assert old_att.attachment_id is None
                assert new_att.attachment_id is not None
                old_att.attachment_id = new_att.attachment_id
        return self

    def _create(self, message_disposition, send_meeting_invitations):
        if not self.account:
            raise ValueError('Item must have an account')
        # bulk_create() returns an Item because we want to return item_id on both main item *and* attachments
        res = self.account.bulk_create(
            items=[self], folder=self.folder, message_disposition=message_disposition,
            send_meeting_invitations=send_meeting_invitations)
        if message_disposition in (SEND_ONLY, SEND_AND_SAVE_COPY):
            assert len(res) == 0
            return None
        else:
            assert len(res) == 1, res
            if isinstance(res[0], Exception):
                raise res[0]
            return res[0]

    def _update(self, update_fieldnames, message_disposition, conflict_resolution, send_meeting_invitations):
        if not self.account:
            raise ValueError('Item must have an account')
        assert self.changekey
        if not update_fieldnames:
            # The fields to update was not specified explicitly. Update all fields where update is possible
            update_fieldnames = []
            for f in self.supported_fields(version=self.account.version):
                if f.name == 'attachments':
                    # Attachments are handled separately after item creation
                    continue
                if f.is_read_only:
                    # These cannot be changed
                    continue
                if f.is_required or f.is_required_after_save:
                    if getattr(self, f.name) is None or (f.is_list and not getattr(self, f.name)):
                        # These are required and cannot be deleted
                        continue
                if not self.is_draft and f.is_read_only_after_send:
                    # These cannot be changed when the item is no longer a draft
                    continue
                update_fieldnames.append(f.name)
        # bulk_update() returns a tuple
        res = self.account.bulk_update(
            items=[(self, update_fieldnames)], message_disposition=message_disposition,
            conflict_resolution=conflict_resolution,
            send_meeting_invitations_or_cancellations=send_meeting_invitations)
        if message_disposition == SEND_AND_SAVE_COPY:
            assert len(res) == 0
            return None
        else:
            assert len(res) == 1, res
            if isinstance(res[0], Exception):
                raise res[0]
            return res[0]

    def refresh(self):
        # Updates the item based on fresh data from EWS
        if not self.account:
            raise ValueError('Item must have an account')
        if not self.item_id:
            raise ValueError('Item must have an ID')
        res = list(self.account.fetch(ids=[self]))
        assert len(res) == 1, res
        if isinstance(res[0], Exception):
            raise res[0]
        fresh_item = res[0]
        assert self.item_id == fresh_item.item_id
        assert self.changekey == fresh_item.changekey
        for f in self.FIELDS:
            setattr(self, f.name, getattr(fresh_item, f.name))

    def move(self, to_folder):
        if not self.account:
            raise ValueError('Item must have an account')
        if not self.item_id:
            raise ValueError('Item must have an ID')
        res = self.account.bulk_move(ids=[self], to_folder=to_folder)
        assert len(res) == 1, res
        if isinstance(res[0], Exception):
            raise res[0]
        self.item_id, self.changekey = res[0]
        self.folder = to_folder

    def move_to_trash(self, send_meeting_cancellations=SEND_TO_NONE, affected_task_occurrences=ALL_OCCURRENCIES,
                      suppress_read_receipts=True):
        # Delete and move to the trash folder.
        self._delete(delete_type=MOVE_TO_DELETED_ITEMS, send_meeting_cancellations=send_meeting_cancellations,
                     affected_task_occurrences=affected_task_occurrences, suppress_read_receipts=suppress_read_receipts)
        self.item_id, self.changekey = None, None
        self.folder = self.folder.account.trash

    def soft_delete(self, send_meeting_cancellations=SEND_TO_NONE, affected_task_occurrences=ALL_OCCURRENCIES,
                    suppress_read_receipts=True):
        # Delete and move to the dumpster, if it is enabled.
        self._delete(delete_type=SOFT_DELETE, send_meeting_cancellations=send_meeting_cancellations,
                     affected_task_occurrences=affected_task_occurrences, suppress_read_receipts=suppress_read_receipts)
        self.item_id, self.changekey = None, None
        self.folder = self.folder.account.recoverable_deleted_items

    def delete(self, send_meeting_cancellations=SEND_TO_NONE, affected_task_occurrences=ALL_OCCURRENCIES,
               suppress_read_receipts=True):
        # Remove the item permanently. No copies are stored anywhere.
        self._delete(delete_type=HARD_DELETE, send_meeting_cancellations=send_meeting_cancellations,
                     affected_task_occurrences=affected_task_occurrences, suppress_read_receipts=suppress_read_receipts)
        self.item_id, self.changekey, self.folder = None, None, None

    def _delete(self, delete_type, send_meeting_cancellations, affected_task_occurrences, suppress_read_receipts):
        if not self.account:
            raise ValueError('Item must have an account')
        if not self.item_id:
            raise ValueError('Item must have an ID')
        res = self.account.bulk_delete(
            ids=[self], delete_type=delete_type, send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences, suppress_read_receipts=suppress_read_receipts)
        assert len(res) == 1, res
        if isinstance(res[0], Exception):
            raise res[0]

    def attach(self, attachments):
        """Add an attachment, or a list of attachments, to this item. If the item has already been saved, the
        attachments will be created on the server immediately. If the item has not yet been saved, the attachments will
        be created on the server the item is saved.

        Adding attachments to an existing item will update the changekey of the item.
        """
        if not is_iterable(attachments, generators_allowed=True):
            attachments = [attachments]
        for a in attachments:
            if not a.parent_item:
                a.parent_item = self
            if self.item_id and not a.attachment_id:
                # Already saved object. Attach the attachment server-side now
                a.attach()
            if a not in self.attachments:
                self.attachments.append(a)

    def detach(self, attachments):
        """Remove an attachment, or a list of attachments, from this item. If the item has already been saved, the
        attachments will be deleted on the server immediately. If the item has not yet been saved, the attachments will
        simply not be created on the server the item is saved.

        Removing attachments from an existing item will update the changekey of the item.
        """
        if not is_iterable(attachments, generators_allowed=True):
            attachments = [attachments]
        for a in attachments:
            assert a.parent_item is self
            if self.item_id:
                # Item is already created. Detach  the attachment server-side now
                a.detach()
            if a in self.attachments:
                self.attachments.remove(a)

    @classmethod
    def id_from_xml(cls, elem):
        id_elem = elem.find(ItemId.response_tag())
        if id_elem is None:
            return None, None
        return id_elem.get(ItemId.ID_ATTR), id_elem.get(ItemId.CHANGEKEY_ATTR)

    @classmethod
    def from_xml(cls, elem, account):
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        item_id, changekey = cls.id_from_xml(elem=elem)
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.supported_fields()}
        elem.clear()
        return cls(account=account, item_id=item_id, changekey=changekey, **kwargs)

    @classmethod
    def register(cls, attr_name, attr_cls):
        """
        Register a custom extended property in this item class so they can be accessed just like any other attribute
        """
        try:
            cls.get_field_by_fieldname(attr_name)
        except ValueError:
            pass
        else:
            raise ValueError("'%s' is already registered" % attr_name)
        if not issubclass(attr_cls, ExtendedProperty):
            raise ValueError("'%s' must be a subclass of ExtendedProperty" % attr_cls)
        # Find the correct index for the extended property and insert the new field. We insert after 'reminder_is_set'

        # TODO: This is super hacky and will need to change if we add new fields after 'reminder_minutes_before_start'
        # ExtendedProperty actually goes in between <HasAttachments/><ExtendedProperty/><Culture/>
        # See https://msdn.microsoft.com/en-us/library/office/aa580790(v=exchg.150).aspx
        idx = tuple(f.name for f in cls.FIELDS).index('reminder_minutes_before_start') + 1
        field = ExtendedPropertyField(attr_name, value_cls=attr_cls)
        cls.add_field(field, idx=idx)

    @classmethod
    def deregister(cls, attr_name):
        """
        De-register an extended property that has been registered with register()
        """
        try:
            field = cls.get_field_by_fieldname(attr_name)
        except ValueError:
            raise ValueError("'%s' is not registered" % attr_name)
        if not isinstance(field, ExtendedPropertyField):
            raise ValueError("'%s' is not registered as an ExtendedProperty" % attr_name)
        cls.remove_field(field)

    def __eq__(self, other):
        if isinstance(other, tuple):
            item_id, changekey = other
            return self.item_id == item_id and self.changekey == changekey
        return self.item_id == other.item_id and self.changekey == other.changekey

    def __hash__(self):
        # If we have an item_id and changekey, use that as key. Else return a hash of all attributes
        if self.item_id:
            return hash((self.item_id, self.changekey))
        return hash(tuple(
            tuple(tuple(getattr(self, f.name) or ()) if f.is_list else getattr(self, f.name) for f in self.FIELDS)
        ))

    def __str__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%s' % (f.name, repr(getattr(self, f.name))) for f in self.FIELDS if getattr(self, f.name) is not None
        )

    def __repr__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%s' % (f.name, repr(getattr(self, f.name))) for f in self.FIELDS
        )


@python_2_unicode_compatible
class BulkCreateResult(Item):
    FIELDS = [
        TextField('item_id', is_read_only=True, is_required=True),
        TextField('changekey', is_read_only=True, is_required=True),
        AttachmentField('attachments', field_uri='item:Attachments'),  # ItemAttachment or FileAttachment
    ]

    __slots__ = ('item_id', 'changekey', 'attachments')

    @classmethod
    def from_xml(cls, elem, account):
        item_id, changekey = cls.id_from_xml(elem)
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.supported_fields()}
        elem.clear()
        return cls(item_id=item_id, changekey=changekey, **kwargs)


@python_2_unicode_compatible
class CalendarItem(Item):
    """
    Models a calendar item. Not all attributes are supported. See full list at
    https://msdn.microsoft.com/en-us/library/office/aa564765(v=exchg.150).aspx
    """
    ELEMENT_NAME = 'CalendarItem'
    FIELDS = Item.FIELDS + [
        TextField('uid', field_uri='calendar:UID', is_required=False, is_required_after_save=True, is_searchable=False),
        DateTimeField('start', field_uri='calendar:Start', is_required=True),
        DateTimeField('end', field_uri='calendar:End', is_required=True),
        BooleanField('is_all_day', field_uri='calendar:IsAllDayEvent', is_required=True, default=False),
        ChoiceField('legacy_free_busy_status', field_uri='calendar:LegacyFreeBusyStatus', choices={
            Choice('Free'), Choice('Tentative'), Choice('Busy'), Choice('OOF'), Choice('NoData'),
            Choice('WorkingElsewhere', supported_from=EXCHANGE_2013)
        }, is_required=True, default='Busy'),
        TextField('location', field_uri='calendar:Location', max_length=255),
        BooleanField('is_cancelled', field_uri='calendar:IsCancelled', is_read_only=True),
        ChoiceField('type', field_uri='calendar:CalendarItemType', choices={
            Choice('Single'), Choice('Occurrence'), Choice('Exception'), Choice('RecurringMaster'),
        }, is_read_only=True),
        MailboxField('organizer', field_uri='calendar:Organizer', is_read_only=True),
        AttendeesField('required_attendees', field_uri='calendar:RequiredAttendees', is_searchable=False),
        AttendeesField('optional_attendees', field_uri='calendar:OptionalAttendees', is_searchable=False),
        AttendeesField('resources', field_uri='calendar:Resources', is_searchable=False),
        RecurrenceField('recurrence', field_uri='calendar:Recurrence', is_searchable=False),
        OccurrenceField('first_occurrence', field_uri='calendar:FirstOccurrence', value_cls=FirstOccurrence,
                        is_read_only=True),
        OccurrenceField('last_occurrence', field_uri='calendar:LastOccurrence', value_cls=LastOccurrence,
                        is_read_only=True),
        OccurrenceListField('modified_occurrences', field_uri='calendar:ModifiedOccurrences', value_cls=Occurrence,
                            is_read_only=True),
        OccurrenceListField('deleted_occurrences', field_uri='calendar:DeletedOccurrences', value_cls=DeletedOccurrence,
                            is_read_only=True),
    ]

    def clean(self, version=None):
        # pylint: disable=access-member-before-definition
        super(CalendarItem, self).clean(version=version)
        if self.start and self.end and self.end < self.start:
            raise ValueError("'end' must be greater than 'start' (%s -> %s)", self.start, self.end)

    def to_xml(self, version):
        # WARNING: The order of addition of XML elements is VERY important. Exchange expects XML elements in a
        # specific, non-documented order and will fail with meaningless errors if the order is wrong.
        i = super(CalendarItem, self).to_xml(version=version)
        if version.build < EXCHANGE_2010:
            i.append(create_element('t:MeetingTimeZone', TimeZoneName=self.start.tzinfo.ms_id))
        else:
            i.append(create_element('t:StartTimeZone', Id=self.start.tzinfo.ms_id, Name=self.start.tzinfo.ms_name))
            i.append(create_element('t:EndTimeZone', Id=self.end.tzinfo.ms_id, Name=self.end.tzinfo.ms_name))
        return i


class Message(Item):
    ELEMENT_NAME = 'Message'
    # Supported attrs: see https://msdn.microsoft.com/en-us/library/office/aa494306(v=exchg.150).aspx
    # TODO: This list is incomplete
    FIELDS = Item.FIELDS + [
        MailboxListField('to_recipients', field_uri='message:ToRecipients', is_read_only_after_send=True,
                         is_searchable=False),
        MailboxListField('cc_recipients', field_uri='message:CcRecipients', is_read_only_after_send=True,
                         is_searchable=False),
        MailboxListField('bcc_recipients', field_uri='message:BccRecipients', is_read_only_after_send=True,
                         is_searchable=False),
        BooleanField('is_read_receipt_requested', field_uri='message:IsReadReceiptRequested',
                     is_required=True, default=False, is_read_only_after_send=True),
        BooleanField('is_delivery_receipt_requested', field_uri='message:IsDeliveryReceiptRequested',
                     is_required=True, default=False, is_read_only_after_send=True),
        MailboxField('sender', field_uri='message:Sender', is_read_only=True, is_read_only_after_send=True),
        # We can't use fieldname 'from' since it's a Python keyword
        MailboxField('author', field_uri='message:From', is_read_only_after_send=True),
        BooleanField('is_read', field_uri='message:IsRead', is_required=True, default=False),
        BooleanField('is_response_requested', field_uri='message:IsResponseRequested', default=False, is_required=True),
        MailboxField('reply_to', field_uri='message:ReplyTo', is_read_only_after_send=True, is_searchable=False),
        TextField('message_id', field_uri='message:InternetMessageId', is_read_only=True, is_read_only_after_send=True),
        TextField('references', field_uri='message:References', is_read_only_after_send=True),
    ]

    def send(self, save_copy=True, copy_to_folder=None, conflict_resolution=AUTO_RESOLVE,
             send_meeting_invitations=SEND_TO_NONE):
        # Only sends a message. The message can either be an existing draft stored in EWS or a new message that does
        # not yet exist in EWS.
        if not self.account:
            raise ValueError('Item must have an account')
        if self.item_id:
            res = self.account.bulk_send(ids=[self], save_copy=save_copy, copy_to_folder=copy_to_folder)
            assert len(res) == 1, res
            if isinstance(res[0], Exception):
                raise res[0]
            # The item will be deleted from the original folder
            self.item_id, self.changekey = None, None
            self.folder = copy_to_folder
        else:
            # New message
            if copy_to_folder:
                if not save_copy:
                    raise AttributeError("'save_copy' must be True when 'copy_to_folder' is set")
                # This would better be done via send_and_save() but lets just support it here
                self.folder = copy_to_folder
                return self.send_and_save(conflict_resolution=conflict_resolution,
                                          send_meeting_invitations=send_meeting_invitations)
            assert copy_to_folder is None
            res = self._create(message_disposition=SEND_ONLY, send_meeting_invitations=send_meeting_invitations)
            assert res is None

    def send_and_save(self, update_fields=None, conflict_resolution=AUTO_RESOLVE,
                      send_meeting_invitations=SEND_TO_NONE):
        # Sends Message and saves a copy in the parent folder. Does not return an ItemId.
        if self.item_id:
            res = self._update(
                update_fieldnames=update_fields,
                message_disposition=SEND_AND_SAVE_COPY,
                conflict_resolution=conflict_resolution,
                send_meeting_invitations=send_meeting_invitations
            )
        else:
            res = self._create(
                message_disposition=SEND_AND_SAVE_COPY,
                send_meeting_invitations=send_meeting_invitations
            )
        assert res is None


class Task(Item):
    ELEMENT_NAME = 'Task'
    NOT_STARTED = 'NotStarted'
    COMPLETED = 'Completed'
    # Supported attrs: see https://msdn.microsoft.com/en-us/library/office/aa563930(v=exchg.150).aspx
    # TODO: This list is incomplete
    FIELDS = Item.FIELDS + [
        IntegerField('actual_work', field_uri='task:ActualWork', min=0),
        DateTimeField('assigned_time', field_uri='task:AssignedTime', is_read_only=True),
        TextField('billing_information', field_uri='task:BillingInformation'),
        IntegerField('change_count', field_uri='task:ChangeCount', is_read_only=True, min=0),
        TextListField('companies', field_uri='task:Companies'),
        TextListField('contacts', field_uri='task:Contacts'),
        ChoiceField('delegation_state', field_uri='task:DelegationState', choices={
            Choice('NoMatch'), Choice('OwnNew'), Choice('Owned'), Choice('Accepted'), Choice('Declined'), Choice('Max')
        }, is_read_only=True),
        TextField('delegator', field_uri='task:Delegator', is_read_only=True),
        # 'complete_date' can be set, but is ignored by the server, which sets it to now()
        DateTimeField('complete_date', field_uri='task:CompleteDate', is_read_only=True),
        DateTimeField('due_date', field_uri='task:DueDate'),
        BooleanField('is_complete', field_uri='task:IsComplete', is_read_only=True),
        BooleanField('is_recurring', field_uri='task:IsRecurring', is_read_only=True),
        BooleanField('is_team_task', field_uri='task:IsTeamTask', is_read_only=True),
        TextField('mileage', field_uri='task:Mileage'),
        TextField('owner', field_uri='task:Owner', is_read_only=True),
        DecimalField('percent_complete', field_uri='task:PercentComplete', is_required=True, is_searchable=False,
                     default=Decimal(0.0)),
        DateTimeField('start_date', field_uri='task:StartDate'),
        ChoiceField('status', field_uri='task:Status', choices={
            Choice(NOT_STARTED), Choice('InProgress'), Choice(COMPLETED), Choice('WaitingOnOthers'), Choice('Deferred')
        }, is_required=True, is_searchable=False, default=NOT_STARTED),
        TextField('status_description', field_uri='task:StatusDescription', is_read_only=True),
        IntegerField('total_work', field_uri='task:TotalWork', min=0),
    ]

    def clean(self, version=None):
        # pylint: disable=access-member-before-definition
        super(Task, self).clean(version=version)
        if self.due_date and self.start_date and self.due_date < self.start_date:
            log.warning("'due_date' must be greater than 'start_date' (%s vs %s). Resetting 'due_date'",
                        self.due_date, self.start_date)
            self.due_date = self.start_date
        if self.complete_date:
            if self.status != self.COMPLETED:
                log.warning("'status' must be '%s' when 'complete_date' is set (%s). Resetting",
                            self.COMPLETED, self.status)
                self.status = self.COMPLETED
            now = UTC_NOW()
            if (self.complete_date - now).total_seconds() > 120:
                # Reset complete_date values that are in the future
                # 'complete_date' can be set automatically by the server. Allow some grace between local and server time
                log.warning("'complete_date' must be in the past (%s vs %s). Resetting", self.complete_date, now)
                self.complete_date = now
            if self.start_date and self.complete_date < self.start_date:
                log.warning("'complete_date' must be greater than 'start_date' (%s vs %s). Resetting",
                            self.complete_date, self.start_date)
                self.complete_date = self.start_date
        if self.percent_complete is not None:
            assert Decimal(0) <= self.percent_complete <= Decimal(100), self.percent_complete
            if self.status == self.COMPLETED and self.percent_complete != Decimal(100):
                # percent_complete must be 100% if task is complete
                log.warning("'percent_complete' must be 100 when 'status' is '%s' (%s). Resetting",
                            self.COMPLETED, self.percent_complete)
                self.percent_complete = Decimal(100)
            elif self.status == self.NOT_STARTED and self.percent_complete != Decimal(0):
                # percent_complete must be 0% if task is not started
                log.warning("'percent_complete' must be 0 when 'status' is '%s' (%s). Resetting",
                            self.NOT_STARTED, self.percent_complete)
                self.percent_complete = Decimal(0)

    def complete(self):
        # pylint: disable=access-member-before-definition
        # A helper method to mark a task as complete on the server
        self.status = Task.COMPLETED
        self.percent_complete = Decimal(100)
        self.save()


class Contact(Item):
    ELEMENT_NAME = 'Contact'
    # Supported attrs: see https://msdn.microsoft.com/en-us/library/office/aa581315(v=exchg.150).aspx
    # TODO: This list is incomplete
    FIELDS = Item.FIELDS + [
        TextField('file_as', field_uri='contacts:FileAs'),
        ChoiceField('file_as_mapping', field_uri='contacts:FileAsMapping', choices={
            Choice('None'), Choice('LastCommaFirst'), Choice('FirstSpaceLast'), Choice('Company'),
            Choice('LastCommaFirstCompany'), Choice('CompanyLastFirst'), Choice('LastFirst'),
            Choice('LastFirstCompany'), Choice('CompanyLastCommaFirst'), Choice('LastFirstSuffix'),
            Choice('LastSpaceFirstCompany'), Choice('CompanyLastSpaceFirst'), Choice('LastSpaceFirst'),
            Choice('DisplayName'), Choice('FirstName'), Choice('LastFirstMiddleSuffix'), Choice('LastName'),
            Choice('Empty'),
        }),
        TextField('display_name', field_uri='contacts:DisplayName', is_required=True),
        TextField('given_name', field_uri='contacts:GivenName'),
        TextField('initials', field_uri='contacts:Initials'),
        TextField('middle_name', field_uri='contacts:MiddleName'),
        TextField('nickname', field_uri='contacts:Nickname'),
        TextField('company_name', field_uri='contacts:CompanyName'),
        EmailAddressField('email_addresses', field_uri='contacts:EmailAddress'),
        PhysicalAddressField('physical_addresses', field_uri='contacts:PhysicalAddress'),
        PhoneNumberField('phone_numbers', field_uri='contacts:PhoneNumber'),
        TextField('assistant_name', field_uri='contacts:AssistantName'),
        DateTimeField('birthday', field_uri='contacts:Birthday'),
        URIField('business_homepage', field_uri='contacts:BusinessHomePage'),
        TextListField('companies', field_uri='contacts:Companies', is_searchable=False),
        TextField('department', field_uri='contacts:Department'),
        TextField('generation', field_uri='contacts:Generation'),
        # IMAddressField('im_addresses', field_uri='contacts:ImAddresses'),
        TextField('job_title', field_uri='contacts:JobTitle'),
        TextField('manager', field_uri='contacts:Manager'),
        TextField('mileage', field_uri='contacts:Mileage'),
        TextField('office', field_uri='contacts:OfficeLocation'),
        TextField('profession', field_uri='contacts:Profession'),
        TextField('surname', field_uri='contacts:Surname'),
        # EmailField('email_alias', field_uri='contacts:Alias'),
        # TextField('notes', field_uri='contacts:Notes'),  # Only available from Exchange 2010 SP2
    ]


class DistributionList(Item):
    # Supported attrs: https://msdn.microsoft.com/en-us/library/office/aa566353(v=exchg.150).aspx
    ELEMENT_NAME = 'DistributionList'
    FIELDS = Item.FIELDS + [
        TextField('display_name', field_uri='contacts:DisplayName', is_required=True),
        TextField('file_as', field_uri='contacts:FileAs', is_read_only=True),
        MemberListField('members', field_uri='distributionlist:Members'),
    ]


class PostItem(Item):
    # Supported attrs: https://msdn.microsoft.com/en-us/library/office/bb891851(v=exchg.150).aspx
    # TODO: Untested. Added here to at least be able to parse folders containing PostItem
    ELEMENT_NAME = 'PostItem'
    FIELDS = Item.FIELDS + [
        MailboxField('author', field_uri='message:From', is_read_only_after_send=True),
        TextField('message_id', field_uri='message:InternetMessageId', is_read_only=True, is_read_only_after_send=True),
        BooleanField('is_read', field_uri='message:IsRead', is_required=True, default=False),
        DateTimeField('posted_time', field_uri='postitem:PostedTime', is_read_only=True),
        MailboxField('sender', field_uri='message:Sender', is_read_only=True, is_read_only_after_send=True),
    ]


class MeetingRequest(Message):
    # Supported attrs: https://msdn.microsoft.com/en-us/library/office/aa565229(v=exchg.150).aspx
    # TODO: Untested and unfinished. Only the bare minimum supported to allow reading a folder that contains meeting
    # requests.
    # BUGFIX: To ensure query-set compatibility with mailboxes, this now has a
    # class inheritance from Message and expressly adds to its fields.
    # Overlapping fields have also been deleted. Fix is temporary pending the
    # addition of a specific MeetingMessage class
    ELEMENT_NAME = 'MeetingRequest'
    FIELDS = Message.FIELDS + [
        DateTimeField('start', field_uri='calendar:Start', is_read_only=True, supported_from=EXCHANGE_2010),
        DateTimeField('end', field_uri='calendar:End', is_read_only=True, supported_from=EXCHANGE_2010),
    ]


class MeetingResponse(Message):
    # Supported attrs: https://msdn.microsoft.com/en-us/library/office/aa564337(v=exchg.150).aspx
    # TODO: Untested and unfinished. Only the bare minimum supported to allow reading a folder that contains meeting
    # responses.
    # BUGFIX: To ensure query-set compatibility with mailboxes, this now has a
    # class inheritance from Message and expressly adds to its fields.
    # Overlapping fields have also been deleted. Fix is temporary pending the
    # addition of a specific MeetingMessage class
    ELEMENT_NAME = 'MeetingResponse'
    FIELDS = Message.FIELDS + [
        DateTimeField('start', field_uri='calendar:Start', is_read_only=True, supported_from=EXCHANGE_2010),
        DateTimeField('end', field_uri='calendar:End', is_read_only=True, supported_from=EXCHANGE_2010),
    ]


class MeetingCancellation(Message):
    # Supported attrs: https://msdn.microsoft.com/en-us/library/office/aa564685(v=exchg.150).aspx
    # TODO: Untested and unfinished. Only the bare minimum supported to allow reading a folder that contains meeting
    # cancellations.
    # BUGFIX: To ensure query-set compatibility with mailboxes, this now has a
    # class inheritance from Message and expressly adds to its fields.
    # Overlapping fields have also been deleted. Fix is temporary pending the
    # addition of a specific MeetingMessage class
    ELEMENT_NAME = 'MeetingCancellation'
    FIELDS = Message.FIELDS + [
        DateTimeField('start', field_uri='calendar:Start', is_read_only=True, supported_from=EXCHANGE_2010),
        DateTimeField('end', field_uri='calendar:End', is_read_only=True, supported_from=EXCHANGE_2010),
    ]


ITEM_CLASSES = (CalendarItem, Contact, DistributionList, Message, PostItem, Task, MeetingRequest, MeetingResponse,
                MeetingCancellation)
