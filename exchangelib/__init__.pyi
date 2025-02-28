from .account import Account as Account, Identity as Identity
from .attachments import FileAttachment as FileAttachment, ItemAttachment as ItemAttachment
from .autodiscover import discover as discover
from .configuration import Configuration as Configuration, O365InteractiveConfiguration as O365InteractiveConfiguration
from .credentials import Credentials as Credentials, DELEGATE as DELEGATE, IMPERSONATION as IMPERSONATION, OAuth2AuthorizationCodeCredentials as OAuth2AuthorizationCodeCredentials, OAuth2Credentials as OAuth2Credentials, OAuth2LegacyCredentials as OAuth2LegacyCredentials
from .ewsdatetime import EWSDate as EWSDate, EWSDateTime as EWSDateTime, EWSTimeZone as EWSTimeZone, UTC as UTC, UTC_NOW as UTC_NOW
from .extended_properties import ExtendedProperty as ExtendedProperty
from .folders import DEEP as DEEP, Folder as Folder, FolderCollection as FolderCollection, RootOfHierarchy as RootOfHierarchy, SHALLOW as SHALLOW
from .items import AcceptItem as AcceptItem, CalendarItem as CalendarItem, CancelCalendarItem as CancelCalendarItem, Contact as Contact, DeclineItem as DeclineItem, DistributionList as DistributionList, ForwardItem as ForwardItem, Message as Message, PostItem as PostItem, PostReplyItem as PostReplyItem, ReplyAllToItem as ReplyAllToItem, ReplyToItem as ReplyToItem, Task as Task, TentativelyAcceptItem as TentativelyAcceptItem
from .properties import Attendee as Attendee, Body as Body, DLMailbox as DLMailbox, HTMLBody as HTMLBody, ItemId as ItemId, Mailbox as Mailbox, Room as Room, RoomList as RoomList, UID as UID
from .protocol import BaseProtocol as BaseProtocol, FailFast as FailFast, FaultTolerance as FaultTolerance, NoVerifyHTTPAdapter as NoVerifyHTTPAdapter, TLSClientAuth as TLSClientAuth
from .restriction import Q as Q
from .settings import OofSettings as OofSettings
from .transport import BASIC as BASIC, CBA as CBA, DIGEST as DIGEST, GSSAPI as GSSAPI, NTLM as NTLM, OAUTH2 as OAUTH2, SSPI as SSPI
from .version import Build as Build, Version as Version

__all__ = ['AcceptItem', 'Account', 'Attendee', 'BASIC', 'BaseProtocol', 'Body', 'Build', 'CBA', 'CalendarItem', 'CancelCalendarItem', 'Configuration', 'Contact', 'Credentials', 'DEEP', 'DELEGATE', 'DIGEST', 'DLMailbox', 'DeclineItem', 'DistributionList', 'EWSDate', 'EWSDateTime', 'EWSTimeZone', 'ExtendedProperty', 'FailFast', 'FaultTolerance', 'FileAttachment', 'Folder', 'FolderCollection', 'ForwardItem', 'GSSAPI', 'HTMLBody', 'IMPERSONATION', 'Identity', 'ItemAttachment', 'ItemId', 'Mailbox', 'Message', 'NTLM', 'NoVerifyHTTPAdapter', 'O365InteractiveConfiguration', 'OAUTH2', 'OAuth2AuthorizationCodeCredentials', 'OAuth2Credentials', 'OAuth2LegacyCredentials', 'OofSettings', 'PostItem', 'PostReplyItem', 'Q', 'ReplyAllToItem', 'ReplyToItem', 'Room', 'RoomList', 'RootOfHierarchy', 'SHALLOW', 'SSPI', 'TLSClientAuth', 'Task', 'TentativelyAcceptItem', 'UID', 'UTC', 'UTC_NOW', 'Version', '__version__', 'close_connections', 'discover']

__version__: str

def close_connections() -> None: ...
