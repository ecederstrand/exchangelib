"""Implement a selection of EWS services (operations).

Exchange is very picky about things like the order of XML elements in SOAP requests, so we need to generate XML
automatically instead of taking advantage of Python SOAP libraries and the WSDL file.

Exchange EWS operations overview:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/ews-operations-in-exchange
"""

from .archive_item import ArchiveItem
from .common import EWSService
from .convert_id import ConvertId
from .copy_item import CopyItem
from .create_attachment import CreateAttachment
from .create_folder import CreateFolder
from .create_item import CreateItem
from .create_user_configuration import CreateUserConfiguration
from .delete_attachment import DeleteAttachment
from .delete_folder import DeleteFolder
from .delete_item import DeleteItem
from .delete_user_configuration import DeleteUserConfiguration
from .empty_folder import EmptyFolder
from .expand_dl import ExpandDL
from .export_items import ExportItems
from .find_folder import FindFolder
from .find_item import FindItem
from .find_people import FindPeople
from .get_attachment import GetAttachment
from .get_delegate import GetDelegate
from .get_events import GetEvents
from .get_folder import GetFolder
from .get_item import GetItem
from .get_mail_tips import GetMailTips
from .get_persona import GetPersona
from .get_room_lists import GetRoomLists
from .get_rooms import GetRooms
from .get_searchable_mailboxes import GetSearchableMailboxes
from .get_server_time_zones import GetServerTimeZones
from .get_streaming_events import GetStreamingEvents
from .get_user_availability import GetUserAvailability
from .get_user_configuration import GetUserConfiguration
from .get_user_oof_settings import GetUserOofSettings
from .get_user_settings import GetUserSettings
from .inbox_rules import CreateInboxRule, DeleteInboxRule, GetInboxRules, SetInboxRule
from .mark_as_junk import MarkAsJunk
from .move_folder import MoveFolder
from .move_item import MoveItem
from .resolve_names import ResolveNames
from .send_item import SendItem
from .send_notification import SendNotification
from .set_user_oof_settings import SetUserOofSettings
from .subscribe import SubscribeToPull, SubscribeToPush, SubscribeToStreaming
from .sync_folder_hierarchy import SyncFolderHierarchy
from .sync_folder_items import SyncFolderItems
from .unsubscribe import Unsubscribe
from .update_folder import UpdateFolder
from .update_item import UpdateItem
from .update_user_configuration import UpdateUserConfiguration
from .upload_items import UploadItems

__all__ = [
    "ArchiveItem",
    "ConvertId",
    "CopyItem",
    "CreateAttachment",
    "CreateFolder",
    "CreateItem",
    "CreateUserConfiguration",
    "DeleteAttachment",
    "DeleteFolder",
    "DeleteUserConfiguration",
    "DeleteItem",
    "EmptyFolder",
    "EWSService",
    "ExpandDL",
    "ExportItems",
    "FindFolder",
    "FindItem",
    "FindPeople",
    "GetAttachment",
    "GetDelegate",
    "GetEvents",
    "GetFolder",
    "GetItem",
    "GetMailTips",
    "GetPersona",
    "GetRoomLists",
    "GetRooms",
    "GetSearchableMailboxes",
    "GetServerTimeZones",
    "GetStreamingEvents",
    "GetUserAvailability",
    "GetUserConfiguration",
    "GetUserOofSettings",
    "GetUserSettings",
    "MarkAsJunk",
    "MoveFolder",
    "MoveItem",
    "ResolveNames",
    "SendItem",
    "SendNotification",
    "SetUserOofSettings",
    "SubscribeToPull",
    "SubscribeToPush",
    "SubscribeToStreaming",
    "SyncFolderHierarchy",
    "SyncFolderItems",
    "Unsubscribe",
    "UpdateFolder",
    "UpdateItem",
    "UpdateUserConfiguration",
    "UploadItems",
    "GetInboxRules",
    "CreateInboxRule",
    "SetInboxRule",
    "DeleteInboxRule",
]
