from .base import (
    AFFECTED_TASK_OCCURRENCES_CHOICES,
    ALL_OCCURRENCES,
    ALL_PROPERTIES,
    ALWAYS_OVERWRITE,
    AUTO_RESOLVE,
    CONFLICT_RESOLUTION_CHOICES,
    DEFAULT,
    DELETE_TYPE_CHOICES,
    HARD_DELETE,
    ID_ONLY,
    MESSAGE_DISPOSITION_CHOICES,
    MOVE_TO_DELETED_ITEMS,
    NEVER_OVERWRITE,
    SAVE_ONLY,
    SEND_AND_SAVE_COPY,
    SEND_MEETING_CANCELLATIONS_CHOICES,
    SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES,
    SEND_MEETING_INVITATIONS_CHOICES,
    SEND_ONLY,
    SEND_ONLY_TO_ALL,
    SEND_ONLY_TO_CHANGED,
    SEND_TO_ALL_AND_SAVE_COPY,
    SEND_TO_CHANGED_AND_SAVE_COPY,
    SEND_TO_NONE,
    SHAPE_CHOICES,
    SOFT_DELETE,
    SPECIFIED_OCCURRENCE_ONLY,
    BulkCreateResult,
    RegisterMixIn,
)
from .calendar_item import (
    CONFERENCE_TYPES,
    AcceptItem,
    CalendarItem,
    CancelCalendarItem,
    DeclineItem,
    MeetingCancellation,
    MeetingMessage,
    MeetingRequest,
    MeetingResponse,
    TentativelyAcceptItem,
    _Booking,
)
from .contact import Contact, DistributionList, Persona
from .item import BaseItem, Item
from .message import ForwardItem, Message, ReplyAllToItem, ReplyToItem
from .post import PostItem, PostReplyItem
from .task import Task

# Traversal enums
SHALLOW = "Shallow"
SOFT_DELETED = "SoftDeleted"
ASSOCIATED = "Associated"
ITEM_TRAVERSAL_CHOICES = (SHALLOW, SOFT_DELETED, ASSOCIATED)

# Contacts search (ResolveNames) scope enums
ACTIVE_DIRECTORY = "ActiveDirectory"
ACTIVE_DIRECTORY_CONTACTS = "ActiveDirectoryContacts"
CONTACTS = "Contacts"
CONTACTS_ACTIVE_DIRECTORY = "ContactsActiveDirectory"
SEARCH_SCOPE_CHOICES = (ACTIVE_DIRECTORY, ACTIVE_DIRECTORY_CONTACTS, CONTACTS, CONTACTS_ACTIVE_DIRECTORY)


ITEM_CLASSES = (
    _Booking,
    CalendarItem,
    Contact,
    DistributionList,
    Item,
    Message,
    MeetingMessage,
    MeetingRequest,
    MeetingResponse,
    MeetingCancellation,
    PostItem,
    Task,
)

__all__ = [
    "RegisterMixIn",
    "MESSAGE_DISPOSITION_CHOICES",
    "SAVE_ONLY",
    "SEND_ONLY",
    "SEND_AND_SAVE_COPY",
    "CalendarItem",
    "AcceptItem",
    "TentativelyAcceptItem",
    "DeclineItem",
    "CancelCalendarItem",
    "MeetingRequest",
    "MeetingResponse",
    "MeetingCancellation",
    "CONFERENCE_TYPES",
    "Contact",
    "Persona",
    "DistributionList",
    "SEND_MEETING_INVITATIONS_CHOICES",
    "SEND_TO_NONE",
    "SEND_ONLY_TO_ALL",
    "SEND_TO_ALL_AND_SAVE_COPY",
    "SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES",
    "SEND_ONLY_TO_CHANGED",
    "SEND_TO_CHANGED_AND_SAVE_COPY",
    "SEND_MEETING_CANCELLATIONS_CHOICES",
    "AFFECTED_TASK_OCCURRENCES_CHOICES",
    "ALL_OCCURRENCES",
    "SPECIFIED_OCCURRENCE_ONLY",
    "CONFLICT_RESOLUTION_CHOICES",
    "NEVER_OVERWRITE",
    "AUTO_RESOLVE",
    "ALWAYS_OVERWRITE",
    "DELETE_TYPE_CHOICES",
    "HARD_DELETE",
    "SOFT_DELETE",
    "MOVE_TO_DELETED_ITEMS",
    "BaseItem",
    "Item",
    "BulkCreateResult",
    "Message",
    "ReplyToItem",
    "ReplyAllToItem",
    "ForwardItem",
    "PostItem",
    "PostReplyItem",
    "Task",
    "ITEM_TRAVERSAL_CHOICES",
    "SHALLOW",
    "SOFT_DELETED",
    "ASSOCIATED",
    "SHAPE_CHOICES",
    "ID_ONLY",
    "DEFAULT",
    "ALL_PROPERTIES",
    "SEARCH_SCOPE_CHOICES",
    "ACTIVE_DIRECTORY",
    "ACTIVE_DIRECTORY_CONTACTS",
    "CONTACTS",
    "CONTACTS_ACTIVE_DIRECTORY",
    "ITEM_CLASSES",
]
