from .account import Account, Identity
from .attachments import FileAttachment, ItemAttachment
from .autodiscover import discover
from .configuration import Configuration
from .credentials import DELEGATE, IMPERSONATION, Credentials, OAuth2AuthorizationCodeCredentials, OAuth2Credentials
from .ewsdatetime import UTC, UTC_NOW, EWSDate, EWSDateTime, EWSTimeZone
from .extended_properties import ExtendedProperty
from .folders import DEEP, SHALLOW, Folder, FolderCollection, RootOfHierarchy
from .items import (
    AcceptItem,
    CalendarItem,
    CancelCalendarItem,
    Contact,
    DeclineItem,
    DistributionList,
    ForwardItem,
    Message,
    PostItem,
    PostReplyItem,
    ReplyAllToItem,
    ReplyToItem,
    Task,
    TentativelyAcceptItem,
)
from .properties import UID, Attendee, Body, DLMailbox, HTMLBody, ItemId, Mailbox, Room, RoomList
from .protocol import BaseProtocol, FailFast, FaultTolerance, NoVerifyHTTPAdapter, TLSClientAuth
from .restriction import Q
from .settings import OofSettings
from .transport import BASIC, CBA, DIGEST, GSSAPI, NTLM, OAUTH2, SSPI
from .version import Build, Version

__version__ = "4.7.5"

__all__ = [
    "__version__",
    "AcceptItem",
    "Account",
    "Attendee",
    "BASIC",
    "BaseProtocol",
    "Body",
    "Build",
    "CBA",
    "CalendarItem",
    "CancelCalendarItem",
    "Configuration",
    "Contact",
    "Credentials",
    "DEEP",
    "DELEGATE",
    "DIGEST",
    "DLMailbox",
    "DeclineItem",
    "DistributionList",
    "EWSDate",
    "EWSDateTime",
    "EWSTimeZone",
    "ExtendedProperty",
    "FailFast",
    "FaultTolerance",
    "FileAttachment",
    "Folder",
    "FolderCollection",
    "ForwardItem",
    "GSSAPI",
    "HTMLBody",
    "IMPERSONATION",
    "Identity",
    "ItemAttachment",
    "ItemId",
    "Mailbox",
    "Message",
    "NTLM",
    "NoVerifyHTTPAdapter",
    "OAUTH2",
    "OAuth2AuthorizationCodeCredentials",
    "OAuth2Credentials",
    "OofSettings",
    "PostItem",
    "PostReplyItem",
    "Q",
    "ReplyAllToItem",
    "ReplyToItem",
    "Room",
    "RoomList",
    "RootOfHierarchy",
    "SHALLOW",
    "SSPI",
    "TLSClientAuth",
    "Task",
    "TentativelyAcceptItem",
    "UID",
    "UTC",
    "UTC_NOW",
    "Version",
    "close_connections",
    "discover",
]

# Set a default user agent, e.g. "exchangelib/3.1.1 (python-requests/2.22.0)"
import requests.utils

BaseProtocol.USERAGENT = f"{__name__}/{__version__} ({requests.utils.default_user_agent()})"


def close_connections():
    from .autodiscover import close_connections as close_autodiscover_connections
    from .protocol import close_connections as close_protocol_connections

    close_autodiscover_connections()
    close_protocol_connections()
