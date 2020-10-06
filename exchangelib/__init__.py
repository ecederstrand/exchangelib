from .account import Account, Identity
from .attachments import FileAttachment, ItemAttachment
from .autodiscover import discover
from .configuration import Configuration
from .credentials import DELEGATE, IMPERSONATION, Credentials, OAuth2Credentials, \
    OAuth2AuthorizationCodeCredentials
from .ewsdatetime import EWSDate, EWSDateTime, EWSTimeZone, UTC, UTC_NOW
from .extended_properties import ExtendedProperty
from .folders import Folder, RootOfHierarchy, FolderCollection, SHALLOW, DEEP
from .items import AcceptItem, TentativelyAcceptItem, DeclineItem, CalendarItem, CancelCalendarItem, Contact, \
    DistributionList, Message, PostItem, Task, ForwardItem, ReplyToItem, ReplyAllToItem
from .properties import Body, HTMLBody, ItemId, Mailbox, Attendee, Room, RoomList, UID, DLMailbox
from .protocol import FaultTolerance, FailFast, BaseProtocol, NoVerifyHTTPAdapter, TLSClientAuth
from .settings import OofSettings
from .restriction import Q
from .transport import BASIC, DIGEST, NTLM, GSSAPI, SSPI, OAUTH2, CBA
from .version import Build, Version

__version__ = '3.2.1'

__all__ = [
    '__version__',
    'Account', 'Identity',
    'FileAttachment', 'ItemAttachment',
    'discover',
    'Configuration',
    'DELEGATE', 'IMPERSONATION', 'Credentials', 'OAuth2AuthorizationCodeCredentials', 'OAuth2Credentials',
    'EWSDate', 'EWSDateTime', 'EWSTimeZone', 'UTC', 'UTC_NOW',
    'ExtendedProperty',
    'Folder', 'RootOfHierarchy', 'FolderCollection', 'SHALLOW', 'DEEP',
    'AcceptItem', 'TentativelyAcceptItem', 'DeclineItem', 'CalendarItem', 'CancelCalendarItem', 'Contact',
    'DistributionList', 'Message', 'PostItem', 'Task', 'ForwardItem', 'ReplyToItem', 'ReplyAllToItem',
    'ItemId', 'Mailbox', 'DLMailbox', 'Attendee', 'Room', 'RoomList', 'Body', 'HTMLBody', 'UID',
    'FailFast', 'FaultTolerance', 'BaseProtocol', 'NoVerifyHTTPAdapter', 'TLSClientAuth',
    'OofSettings',
    'Q',
    'BASIC', 'DIGEST', 'NTLM', 'GSSAPI', 'SSPI', 'OAUTH2', 'CBA',
    'Build', 'Version',
]

# Set a default user agent, e.g. "exchangelib/3.1.1 (python-requests/2.22.0)"
import requests.utils
BaseProtocol.USERAGENT = "%s/%s (%s)" % (__name__, __version__, requests.utils.default_user_agent())


def close_connections():
    from .autodiscover import close_connections as close_autodiscover_connections
    from .protocol import close_connections as close_protocol_connections
    close_autodiscover_connections()
    close_protocol_connections()
