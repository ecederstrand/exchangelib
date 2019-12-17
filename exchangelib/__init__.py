from __future__ import unicode_literals

from .account import Account
from .attachments import FileAttachment, ItemAttachment
from .autodiscover import discover
from .configuration import Configuration
from .credentials import DELEGATE, IMPERSONATION, Credentials, OAuth2Credentials, \
    OAuth2AuthorizationCodeCredentials
from .ewsdatetime import EWSDate, EWSDateTime, EWSTimeZone, UTC, UTC_NOW
from .extended_properties import ExtendedProperty
from .folders import Folder, FolderCollection, SHALLOW, DEEP
from .items import AcceptItem, TentativelyAcceptItem, DeclineItem, CalendarItem, CancelCalendarItem, Contact, \
    DistributionList, Message, PostItem, Task
from .properties import Body, HTMLBody, ItemId, Mailbox, Attendee, Room, RoomList, UID, DLMailbox
from .protocol import FaultTolerance, FailFast
from .settings import OofSettings
from .restriction import Q
from .transport import BASIC, DIGEST, NTLM, GSSAPI, SSPI, OAUTH2
from .version import Build, Version

__version__ = '2.1.1'

__all__ = [
    '__version__',
    'Account',
    'FileAttachment', 'ItemAttachment',
    'discover',
    'Configuration',
    'DELEGATE', 'IMPERSONATION', 'Credentials', 'OAuth2AuthorizationCodeCredentials', 'OAuth2Credentials',
    'EWSDate', 'EWSDateTime', 'EWSTimeZone', 'UTC', 'UTC_NOW',
    'ExtendedProperty',
    'Folder', 'FolderCollection', 'SHALLOW', 'DEEP',
    'AcceptItem', 'TentativelyAcceptItem', 'DeclineItem', 'CalendarItem', 'CancelCalendarItem', 'Contact',
    'DistributionList', 'Message', 'PostItem', 'Task',
    'ItemId', 'Mailbox', 'DLMailbox', 'Attendee', 'Room', 'RoomList', 'Body', 'HTMLBody', 'UID',
    'FailFast', 'FaultTolerance',
    'OofSettings',
    'Q',
    'BASIC', 'DIGEST', 'NTLM', 'GSSAPI', 'SSPI', 'OAUTH2',
    'Build', 'Version',
]


def close_connections():
    from .autodiscover import close_connections as close_autodiscover_connections
    from .protocol import close_connections as close_protocol_connections
    close_autodiscover_connections()
    close_protocol_connections()
