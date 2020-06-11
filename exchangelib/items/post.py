import logging

from ..fields import TextField, BodyField, DateTimeField, MailboxField
from ..properties import Fields
from .item import Item
from .message import Message

log = logging.getLogger(__name__)


class PostItem(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/postitem"""
    ELEMENT_NAME = 'PostItem'
    LOCAL_FIELDS = Message.LOCAL_FIELDS[6:11] + Fields(
        DateTimeField('posted_time', field_uri='postitem:PostedTime', is_read_only=True),
        TextField('references', field_uri='message:References'),
        MailboxField('sender', field_uri='message:Sender', is_read_only=True, is_read_only_after_send=True),
    )
    FIELDS = Item.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)


class PostReplyItem(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/postreplyitem"""
    # TODO: Untested and unfinished.
    ELEMENT_NAME = 'PostReplyItem'

    LOCAL_FIELDS = Message.LOCAL_FIELDS + Fields(
        BodyField('new_body', field_uri='NewBodyContent'),  # Accepts and returns Body or HTMLBody instances
    )
    # FIELDS on this element only has Item fields up to 'culture'
    culture_idx = None
    for i, field in enumerate(Item.FIELDS):
        if field.name == 'culture':
            culture_idx = i
            break
    FIELDS = Item.FIELDS[:culture_idx + 1] + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)
