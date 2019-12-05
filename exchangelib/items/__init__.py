from .base import RegisterMixIn, MESSAGE_DISPOSITION_CHOICES, SAVE_ONLY, SEND_ONLY, SEND_AND_SAVE_COPY
from .calendar_item import CalendarItem, AcceptItem, TentativelyAcceptItem, DeclineItem, CancelCalendarItem, \
    MeetingRequest, MeetingResponse, MeetingCancellation, CONFERENCE_TYPES
from .contact import Contact, Persona, DistributionList
from .item import SEND_MEETING_INVITATIONS_CHOICES, SEND_TO_NONE, SEND_ONLY_TO_ALL, SEND_TO_ALL_AND_SAVE_COPY, \
    SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES, SEND_ONLY_TO_CHANGED, SEND_TO_CHANGED_AND_SAVE_COPY, \
    SEND_MEETING_CANCELLATIONS_CHOICES, AFFECTED_TASK_OCCURRENCES_CHOICES, ALL_OCCURRENCIES, \
    SPECIFIED_OCCURRENCE_ONLY, CONFLICT_RESOLUTION_CHOICES, NEVER_OVERWRITE, AUTO_RESOLVE, ALWAYS_OVERWRITE, \
    DELETE_TYPE_CHOICES, HARD_DELETE, SOFT_DELETE, MOVE_TO_DELETED_ITEMS, BaseItem, Item, BulkCreateResult, \
    ReadFlagChange, CreateChange, UpdateChange, DeleteChange
from .message import Message, ReplyToItem, ReplyAllToItem, ForwardItem
from .post import PostItem, PostReplyItem
from .task import Task

__all__ = [
    'RegisterMixIn', 'MESSAGE_DISPOSITION_CHOICES', 'SAVE_ONLY', 'SEND_ONLY', 'SEND_AND_SAVE_COPY',
    'CalendarItem', 'AcceptItem', 'TentativelyAcceptItem', 'DeclineItem', 'CancelCalendarItem',
    'MeetingRequest', 'MeetingResponse', 'MeetingCancellation', 'CONFERENCE_TYPES',
    'Contact', 'Persona', 'DistributionList',
    'SEND_MEETING_INVITATIONS_CHOICES', 'SEND_TO_NONE', 'SEND_ONLY_TO_ALL', 'SEND_TO_ALL_AND_SAVE_COPY',
    'SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES', 'SEND_ONLY_TO_CHANGED', 'SEND_TO_CHANGED_AND_SAVE_COPY',
    'SEND_MEETING_CANCELLATIONS_CHOICES', 'AFFECTED_TASK_OCCURRENCES_CHOICES', 'ALL_OCCURRENCIES',
    'SPECIFIED_OCCURRENCE_ONLY', 'CONFLICT_RESOLUTION_CHOICES', 'NEVER_OVERWRITE', 'AUTO_RESOLVE', 'ALWAYS_OVERWRITE',
    'DELETE_TYPE_CHOICES', 'HARD_DELETE', 'SOFT_DELETE', 'MOVE_TO_DELETED_ITEMS', 'BaseItem', 'Item',
    'BulkCreateResult',
    'Message', 'ReplyToItem', 'ReplyAllToItem', 'ForwardItem',
    'PostItem', 'PostReplyItem',
    'Task',
]

# Traversal enums
SHALLOW = 'Shallow'
SOFT_DELETED = 'SoftDeleted'
ASSOCIATED = 'Associated'
ITEM_TRAVERSAL_CHOICES = (SHALLOW, SOFT_DELETED, ASSOCIATED)

# Shape enums
ID_ONLY = 'IdOnly'
DEFAULT = 'Default'
# AllProperties doesn't actually get all properties in FindItem, just the "first-class" ones. See
# https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/email-properties-and-elements-in-ews-in-exchange
ALL_PROPERTIES = 'AllProperties'
SHAPE_CHOICES = (ID_ONLY, DEFAULT, ALL_PROPERTIES)

# Contacts search (ResolveNames) scope enums
ACTIVE_DIRECTORY = 'ActiveDirectory'
ACTIVE_DIRECTORY_CONTACTS = 'ActiveDirectoryContacts'
CONTACTS = 'Contacts'
CONTACTS_ACTIVE_DIRECTORY = 'ContactsActiveDirectory'
SEARCH_SCOPE_CHOICES = (ACTIVE_DIRECTORY, ACTIVE_DIRECTORY_CONTACTS, CONTACTS, CONTACTS_ACTIVE_DIRECTORY)


ITEM_CLASSES = (Item, CalendarItem, Contact, DistributionList, Message, PostItem, Task, MeetingRequest, MeetingResponse,
                MeetingCancellation)
ALL_ITEM_CLASSES = (Item, CalendarItem, Contact, DistributionList, Message, PostItem, Task, MeetingRequest,
                    MeetingResponse, MeetingCancellation, ReadFlagChange, CreateChange, UpdateChange, DeleteChange)
