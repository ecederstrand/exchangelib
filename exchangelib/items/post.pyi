from ..fields import BodyField as BodyField, DateTimeField as DateTimeField, MailboxField as MailboxField, TextField as TextField
from .item import Item as Item
from .message import Message as Message
from _typeshed import Incomplete

log: Incomplete

class PostItem(Item):
    ELEMENT_NAME: str
    conversation_index: Incomplete
    conversation_topic: Incomplete
    author: Incomplete
    message_id: Incomplete
    is_read: Incomplete
    posted_time: Incomplete
    references: Incomplete
    sender: Incomplete

class PostReplyItem(Item):
    ELEMENT_NAME: str
    new_body: Incomplete
    culture_idx: Incomplete
    sender_idx: Incomplete
    FIELDS: Incomplete
