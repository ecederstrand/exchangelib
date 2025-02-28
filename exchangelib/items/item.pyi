from ..fields import AttachmentField as AttachmentField, BodyField as BodyField, BooleanField as BooleanField, CharField as CharField, CharListField as CharListField, Choice as Choice, ChoiceField as ChoiceField, CultureField as CultureField, DateTimeField as DateTimeField, EWSElementField as EWSElementField, EffectiveRightsField as EffectiveRightsField, FieldPath as FieldPath, IntegerField as IntegerField, MessageHeaderField as MessageHeaderField, MimeContentField as MimeContentField, TextField as TextField, URIField as URIField
from ..properties import ConversationId as ConversationId, Fields as Fields, OccurrenceItemId as OccurrenceItemId, ParentFolderId as ParentFolderId, RecurringMasterItemId as RecurringMasterItemId, ReferenceItemId as ReferenceItemId, ResponseObjects as ResponseObjects
from ..util import is_iterable as is_iterable, require_account as require_account, require_id as require_id
from ..version import EXCHANGE_2010 as EXCHANGE_2010, EXCHANGE_2013 as EXCHANGE_2013
from .base import ALL_OCCURRENCES as ALL_OCCURRENCES, AUTO_RESOLVE as AUTO_RESOLVE, BaseItem as BaseItem, HARD_DELETE as HARD_DELETE, ID_ONLY as ID_ONLY, MOVE_TO_DELETED_ITEMS as MOVE_TO_DELETED_ITEMS, SAVE_ONLY as SAVE_ONLY, SEND_AND_SAVE_COPY as SEND_AND_SAVE_COPY, SEND_TO_NONE as SEND_TO_NONE, SOFT_DELETE as SOFT_DELETE
from _typeshed import Incomplete

log: Incomplete

class Item(BaseItem):
    ELEMENT_NAME: str
    mime_content: Incomplete
    parent_folder_id: Incomplete
    item_class: Incomplete
    subject: Incomplete
    sensitivity: Incomplete
    text_body: Incomplete
    body: Incomplete
    attachments: Incomplete
    datetime_received: Incomplete
    size: Incomplete
    categories: Incomplete
    importance: Incomplete
    in_reply_to: Incomplete
    is_submitted: Incomplete
    is_draft: Incomplete
    is_from_me: Incomplete
    is_resend: Incomplete
    is_unmodified: Incomplete
    headers: Incomplete
    datetime_sent: Incomplete
    datetime_created: Incomplete
    response_objects: Incomplete
    reminder_due_by: Incomplete
    reminder_is_set: Incomplete
    reminder_minutes_before_start: Incomplete
    display_cc: Incomplete
    display_to: Incomplete
    has_attachments: Incomplete
    culture: Incomplete
    effective_rights: Incomplete
    last_modified_name: Incomplete
    last_modified_time: Incomplete
    is_associated: Incomplete
    web_client_read_form_query_string: Incomplete
    web_client_edit_form_query_string: Incomplete
    conversation_id: Incomplete
    unique_body: Incomplete
    FIELDS: Incomplete
    INSERT_AFTER_FIELD: str
    def __init__(self, **kwargs) -> None: ...
    def save(self, update_fields: Incomplete | None = None, conflict_resolution=..., send_meeting_invitations=...): ...
    def refresh(self): ...
    def copy(self, to_folder): ...
    folder: Incomplete
    def move(self, to_folder) -> None: ...
    def move_to_trash(self, send_meeting_cancellations=..., affected_task_occurrences=..., suppress_read_receipts: bool = True) -> None: ...
    def soft_delete(self, send_meeting_cancellations=..., affected_task_occurrences=..., suppress_read_receipts: bool = True) -> None: ...
    def delete(self, send_meeting_cancellations=..., affected_task_occurrences=..., suppress_read_receipts: bool = True) -> None: ...
    def archive(self, to_folder): ...
    def attach(self, attachments) -> None: ...
    def detach(self, attachments) -> None: ...
    def create_forward(self, subject, body, to_recipients, cc_recipients: Incomplete | None = None, bcc_recipients: Incomplete | None = None): ...
    def forward(self, subject, body, to_recipients, cc_recipients: Incomplete | None = None, bcc_recipients: Incomplete | None = None): ...
