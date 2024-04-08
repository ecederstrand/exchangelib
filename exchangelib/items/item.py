import logging

from ..fields import (
    AttachmentField,
    BodyField,
    BooleanField,
    CharField,
    CharListField,
    Choice,
    ChoiceField,
    CultureField,
    DateTimeField,
    EffectiveRightsField,
    EWSElementField,
    FieldPath,
    IntegerField,
    MessageHeaderField,
    MimeContentField,
    TextField,
    URIField,
)
from ..properties import (
    ConversationId,
    Fields,
    OccurrenceItemId,
    ParentFolderId,
    RecurringMasterItemId,
    ReferenceItemId,
    ResponseObjects,
)
from ..util import is_iterable, require_account, require_id
from ..version import EXCHANGE_2010, EXCHANGE_2013
from .base import (
    ALL_OCCURRENCES,
    AUTO_RESOLVE,
    HARD_DELETE,
    ID_ONLY,
    MOVE_TO_DELETED_ITEMS,
    SAVE_ONLY,
    SEND_AND_SAVE_COPY,
    SEND_TO_NONE,
    SOFT_DELETE,
    BaseItem,
)

log = logging.getLogger(__name__)


class Item(BaseItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/item"""

    ELEMENT_NAME = "Item"

    mime_content = MimeContentField(field_uri="item:MimeContent", is_read_only_after_send=True)
    _id = BaseItem.FIELDS["_id"]
    parent_folder_id = EWSElementField(field_uri="item:ParentFolderId", value_cls=ParentFolderId, is_read_only=True)
    item_class = CharField(field_uri="item:ItemClass", is_read_only=True)
    subject = CharField(field_uri="item:Subject")
    sensitivity = ChoiceField(
        field_uri="item:Sensitivity",
        choices={Choice("Normal"), Choice("Personal"), Choice("Private"), Choice("Confidential")},
        is_required=True,
        default="Normal",
    )
    text_body = TextField(field_uri="item:TextBody", is_read_only=True, supported_from=EXCHANGE_2013)
    body = BodyField(field_uri="item:Body")  # Accepts and returns Body or HTMLBody instances
    attachments = AttachmentField(field_uri="item:Attachments")  # ItemAttachment or FileAttachment
    datetime_received = DateTimeField(field_uri="item:DateTimeReceived", is_read_only=True)
    size = IntegerField(field_uri="item:Size", is_read_only=True)  # Item size in bytes
    categories = CharListField(field_uri="item:Categories")
    importance = ChoiceField(
        field_uri="item:Importance",
        choices={Choice("Low"), Choice("Normal"), Choice("High")},
        is_required=True,
        default="Normal",
    )
    in_reply_to = TextField(field_uri="item:InReplyTo")
    is_submitted = BooleanField(field_uri="item:IsSubmitted", is_read_only=True)
    is_draft = BooleanField(field_uri="item:IsDraft", is_read_only=True)
    is_from_me = BooleanField(field_uri="item:IsFromMe", is_read_only=True)
    is_resend = BooleanField(field_uri="item:IsResend", is_read_only=True)
    is_unmodified = BooleanField(field_uri="item:IsUnmodified", is_read_only=True)
    headers = MessageHeaderField(field_uri="item:InternetMessageHeaders", is_read_only=True)
    datetime_sent = DateTimeField(field_uri="item:DateTimeSent", is_read_only=True)
    datetime_created = DateTimeField(field_uri="item:DateTimeCreated", is_read_only=True)
    response_objects = EWSElementField(
        field_uri="item:ResponseObjects",
        value_cls=ResponseObjects,
        is_read_only=True,
    )
    # Placeholder for ResponseObjects
    reminder_due_by = DateTimeField(field_uri="item:ReminderDueBy", is_required_after_save=True, is_searchable=False)
    reminder_is_set = BooleanField(field_uri="item:ReminderIsSet", is_required=True, default=False)
    reminder_minutes_before_start = IntegerField(
        field_uri="item:ReminderMinutesBeforeStart", is_required_after_save=True, min=0, default=0
    )
    display_cc = TextField(field_uri="item:DisplayCc", is_read_only=True)
    display_to = TextField(field_uri="item:DisplayTo", is_read_only=True)
    has_attachments = BooleanField(field_uri="item:HasAttachments", is_read_only=True)
    # ExtendedProperty fields go here
    culture = CultureField(field_uri="item:Culture", is_required_after_save=True, is_searchable=False)
    effective_rights = EffectiveRightsField(field_uri="item:EffectiveRights", is_read_only=True)
    last_modified_name = CharField(field_uri="item:LastModifiedName", is_read_only=True)
    last_modified_time = DateTimeField(field_uri="item:LastModifiedTime", is_read_only=True)
    is_associated = BooleanField(field_uri="item:IsAssociated", is_read_only=True, supported_from=EXCHANGE_2010)
    web_client_read_form_query_string = URIField(
        field_uri="item:WebClientReadFormQueryString", is_read_only=True, supported_from=EXCHANGE_2010
    )
    web_client_edit_form_query_string = URIField(
        field_uri="item:WebClientEditFormQueryString", is_read_only=True, supported_from=EXCHANGE_2010
    )
    conversation_id = EWSElementField(
        field_uri="item:ConversationId", value_cls=ConversationId, is_read_only=True, supported_from=EXCHANGE_2010
    )
    unique_body = BodyField(field_uri="item:UniqueBody", is_read_only=True, supported_from=EXCHANGE_2010)

    FIELDS = Fields()

    # Used to register extended properties
    INSERT_AFTER_FIELD = "has_attachments"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.attachments:
            for a in self.attachments:
                if a.parent_item:
                    if a.parent_item is not self:
                        raise ValueError(f"'parent_item' of attachment {a} must point to this item")
                else:
                    a.parent_item = self
                self.attach(self.attachments)
        else:
            self.attachments = []

    def save(self, update_fields=None, conflict_resolution=AUTO_RESOLVE, send_meeting_invitations=SEND_TO_NONE):
        from .task import Task

        if self.id:
            item_id, changekey = self._update(
                update_fieldnames=update_fields,
                message_disposition=SAVE_ONLY,
                conflict_resolution=conflict_resolution,
                send_meeting_invitations=send_meeting_invitations,
            )
            if (
                self.id != item_id
                and not isinstance(self._id, (OccurrenceItemId, RecurringMasterItemId))
                and not isinstance(self, Task)
            ):
                # When we update an item with an OccurrenceItemId as ID, EWS returns the ID of the occurrence, so
                # the ID of this item changes.
                #
                # When we update certain fields on a task, the ID may change. A full description is available at
                # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/updateitem-operation-task
                raise ValueError("'id' mismatch in returned update response")
            # Don't check that changekeys are different. No-op saves will sometimes leave the changekey intact
            self._id = self.ID_ELEMENT_CLS(item_id, changekey)
        else:
            if update_fields:
                raise ValueError("'update_fields' is only valid for updates")
            tmp_attachments = None
            if self.account and self.account.version.build < EXCHANGE_2013 and self.attachments:
                # At least some versions prior to Exchange 2013 can't save attachments immediately. You need to first
                # save, then attach. Store the attachment of this item temporarily and attach later.
                tmp_attachments, self.attachments = self.attachments, []
            item = self._create(message_disposition=SAVE_ONLY, send_meeting_invitations=send_meeting_invitations)
            self._id = self.ID_ELEMENT_CLS(item.id, item.changekey)
            for old_att, new_att in zip(self.attachments, item.attachments):
                if old_att.attachment_id is not None:
                    raise ValueError("Old 'attachment_id' is not empty")
                if new_att.attachment_id is None:
                    raise ValueError("New 'attachment_id' is empty")
                old_att.attachment_id = new_att.attachment_id
            if tmp_attachments:
                # Exchange 2007 workaround. See above
                self.attach(tmp_attachments)
        return self

    @require_account
    def _create(self, message_disposition, send_meeting_invitations):
        # Return a BulkCreateResult because we want to return the ID of both the main item *and* attachments. In send
        # and send-and-save-copy mode, the server does not return an ID, so we just return True.
        from ..services import CreateItem

        return CreateItem(account=self.account).get(
            items=[self],
            folder=self.folder,
            message_disposition=message_disposition,
            send_meeting_invitations=send_meeting_invitations,
        )

    def _update_fieldnames(self):
        from .contact import Contact, DistributionList

        # Return the list of fields we are allowed to update
        update_fieldnames = []
        for f in self.supported_fields(version=self.account.version):
            if f.name == "attachments":
                # Attachments are handled separately after item creation
                continue
            if f.is_read_only:
                # These cannot be changed
                continue
            if (f.is_required or f.is_required_after_save) and (
                getattr(self, f.name) is None or (f.is_list and not getattr(self, f.name))
            ):
                # These are required and cannot be deleted
                continue
            if not self.is_draft and f.is_read_only_after_send:
                # These cannot be changed when the item is no longer a draft
                continue
            if f.name == "message_id" and f.is_read_only_after_send:
                # 'message_id' doesn't support updating, no matter the draft status
                continue
            if f.name == "mime_content" and isinstance(self, (Contact, DistributionList)):
                # Contact and DistributionList don't support updating mime_content, no matter the draft status
                continue
            update_fieldnames.append(f.name)
        return update_fieldnames

    @require_account
    def _update(self, update_fieldnames, message_disposition, conflict_resolution, send_meeting_invitations):
        from ..services import UpdateItem

        if not self.changekey:
            raise ValueError(f"{self.__class__.__name__} must have changekey")
        if not update_fieldnames:
            # The fields to update was not specified explicitly. Update all fields where update is possible
            update_fieldnames = self._update_fieldnames()
        return UpdateItem(account=self.account).get(
            items=[(self, update_fieldnames)],
            message_disposition=message_disposition,
            conflict_resolution=conflict_resolution,
            send_meeting_invitations_or_cancellations=send_meeting_invitations,
            suppress_read_receipts=True,
            expect_result=message_disposition != SEND_AND_SAVE_COPY,
        )

    @require_id
    def refresh(self):
        # Updates the item based on fresh data from EWS
        from ..services import GetItem

        additional_fields = {FieldPath(field=f) for f in self.supported_fields(version=self.account.version)}
        res = GetItem(account=self.account).get(items=[self], additional_fields=additional_fields, shape=ID_ONLY)
        if self.id != res.id and not isinstance(self._id, (OccurrenceItemId, RecurringMasterItemId)):
            # When we refresh an item with an OccurrenceItemId as ID, EWS returns the ID of the occurrence, so
            # the ID of this item changes.
            raise ValueError("'id' mismatch in returned update response")
        for f in self.FIELDS:
            setattr(self, f.name, getattr(res, f.name))
        # 'parent_item' should point to 'self', not 'fresh_item'. That way, 'fresh_item' can be garbage collected.
        for a in self.attachments:
            a.parent_item = self
        return self

    @require_id
    def copy(self, to_folder):
        from ..services import CopyItem

        # If 'to_folder' is a public folder or a folder in a different mailbox then None is returned
        return CopyItem(account=self.account).get(
            items=[self],
            to_folder=to_folder,
            expect_result=None,
        )

    @require_id
    def move(self, to_folder):
        from ..services import MoveItem

        res = MoveItem(account=self.account).get(
            items=[self],
            to_folder=to_folder,
            expect_result=None,
        )
        if res is None:
            # Assume 'to_folder' is a public folder or a folder in a different mailbox
            self._id = None
            return
        self._id = self.ID_ELEMENT_CLS(*res)
        self.folder = to_folder

    def move_to_trash(
        self,
        send_meeting_cancellations=SEND_TO_NONE,
        affected_task_occurrences=ALL_OCCURRENCES,
        suppress_read_receipts=True,
    ):
        # Delete and move to the trash folder.
        self._delete(
            delete_type=MOVE_TO_DELETED_ITEMS,
            send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences,
            suppress_read_receipts=suppress_read_receipts,
        )
        self._id = None
        self.folder = self.account.trash

    def soft_delete(
        self,
        send_meeting_cancellations=SEND_TO_NONE,
        affected_task_occurrences=ALL_OCCURRENCES,
        suppress_read_receipts=True,
    ):
        # Delete and move to the dumpster, if it is enabled.
        self._delete(
            delete_type=SOFT_DELETE,
            send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences,
            suppress_read_receipts=suppress_read_receipts,
        )
        self._id = None
        self.folder = self.account.recoverable_items_deletions

    def delete(
        self,
        send_meeting_cancellations=SEND_TO_NONE,
        affected_task_occurrences=ALL_OCCURRENCES,
        suppress_read_receipts=True,
    ):
        # Remove the item permanently. No copies are stored anywhere.
        self._delete(
            delete_type=HARD_DELETE,
            send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences,
            suppress_read_receipts=suppress_read_receipts,
        )
        self._id, self.folder = None, None

    @require_id
    def _delete(self, delete_type, send_meeting_cancellations, affected_task_occurrences, suppress_read_receipts):
        from ..services import DeleteItem

        DeleteItem(account=self.account).get(
            items=[self],
            delete_type=delete_type,
            send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences,
            suppress_read_receipts=suppress_read_receipts,
        )

    @require_id
    def archive(self, to_folder):
        from ..services import ArchiveItem

        return ArchiveItem(account=self.account).get(items=[self], to_folder=to_folder, expect_result=True)

    def attach(self, attachments):
        """Add an attachment, or a list of attachments, to this item. If the item has already been saved, the
        attachments will be created on the server immediately. If the item has not yet been saved, the attachments will
        be created on the server when the item is saved.

        Adding attachments to an existing item will update the changekey of the item.

        :param attachments:
        """
        if not is_iterable(attachments, generators_allowed=True):
            attachments = [attachments]
        for a in attachments:
            if not a.parent_item:
                a.parent_item = self
            if self.id and not a.attachment_id:
                # Already saved object. Attach the attachment server-side now
                a.attach()
            if a not in self.attachments:
                self.attachments.append(a)

    def detach(self, attachments):
        """Remove an attachment, or a list of attachments, from this item. If the item has already been saved, the
        attachments will be deleted on the server immediately. If the item has not yet been saved, the attachments will
        simply not be created on the server the item is saved.

        Removing attachments from an existing item will update the changekey of the item.

        :param attachments:
        """
        if not is_iterable(attachments, generators_allowed=True):
            attachments = [attachments]
        if attachments is self.attachments:
            # Don't remove from the same list we are iterating
            attachments = list(attachments)
        for a in attachments:
            if a.parent_item is not self:
                raise ValueError("Attachment does not belong to this item")
            if self.id:
                # Item is already created. Detach  the attachment server-side now
                a.detach()
            if a in self.attachments:
                self.attachments.remove(a)

    @require_id
    def create_forward(self, subject, body, to_recipients, cc_recipients=None, bcc_recipients=None):
        from .message import ForwardItem

        return ForwardItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            subject=subject,
            new_body=body,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
            bcc_recipients=bcc_recipients,
        )

    def forward(self, subject, body, to_recipients, cc_recipients=None, bcc_recipients=None):
        return self.create_forward(
            subject,
            body,
            to_recipients,
            cc_recipients,
            bcc_recipients,
        ).send()
