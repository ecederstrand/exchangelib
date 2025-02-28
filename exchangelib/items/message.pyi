from ..fields import Base64Field as Base64Field, BooleanField as BooleanField, CharField as CharField, EWSElementField as EWSElementField, MailboxField as MailboxField, MailboxListField as MailboxListField, TextField as TextField
from ..properties import ReferenceItemId as ReferenceItemId, ReminderMessageData as ReminderMessageData
from ..util import require_account as require_account, require_id as require_id
from ..version import EXCHANGE_2013 as EXCHANGE_2013, EXCHANGE_2013_SP1 as EXCHANGE_2013_SP1
from .base import AUTO_RESOLVE as AUTO_RESOLVE, BaseReplyItem as BaseReplyItem, SEND_AND_SAVE_COPY as SEND_AND_SAVE_COPY, SEND_ONLY as SEND_ONLY, SEND_TO_NONE as SEND_TO_NONE
from .item import Item as Item
from _typeshed import Incomplete

log: Incomplete

class Message(Item):
    ELEMENT_NAME: str
    sender: Incomplete
    to_recipients: Incomplete
    cc_recipients: Incomplete
    bcc_recipients: Incomplete
    is_read_receipt_requested: Incomplete
    is_delivery_receipt_requested: Incomplete
    conversation_index: Incomplete
    conversation_topic: Incomplete
    author: Incomplete
    message_id: Incomplete
    is_read: Incomplete
    is_response_requested: Incomplete
    references: Incomplete
    reply_to: Incomplete
    received_by: Incomplete
    received_representing: Incomplete
    reminder_message_data: Incomplete
    folder: Incomplete
    def send(self, save_copy: bool = True, copy_to_folder: Incomplete | None = None, conflict_resolution=..., send_meeting_invitations=...): ...
    def send_and_save(self, update_fields: Incomplete | None = None, conflict_resolution=..., send_meeting_invitations=...): ...
    def create_reply(self, subject, body, to_recipients: Incomplete | None = None, cc_recipients: Incomplete | None = None, bcc_recipients: Incomplete | None = None, author: Incomplete | None = None): ...
    def reply(self, subject, body, to_recipients: Incomplete | None = None, cc_recipients: Incomplete | None = None, bcc_recipients: Incomplete | None = None, author: Incomplete | None = None): ...
    def create_reply_all(self, subject, body, author: Incomplete | None = None): ...
    def reply_all(self, subject, body, author: Incomplete | None = None): ...
    def mark_as_junk(self, is_junk: bool = True, move_item: bool = True) -> None: ...

class ReplyToItem(BaseReplyItem):
    ELEMENT_NAME: str

class ReplyAllToItem(BaseReplyItem):
    ELEMENT_NAME: str

class ForwardItem(BaseReplyItem):
    ELEMENT_NAME: str
