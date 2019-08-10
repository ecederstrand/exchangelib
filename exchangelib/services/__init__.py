# coding=utf-8
"""
Implement a selection of EWS services.

Exchange is very picky about things like the order of XML elements in SOAP requests, so we need to generate XML
automatically instead of taking advantage of Python SOAP libraries and the WSDL file.

Exchange EWS references:
    - 2007: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.80).aspx
    - 2010: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.140).aspx
    - 2013: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.150).aspx
"""

from .common import CHUNK_SIZE
from .copy_item import CopyItem
from .create_attachment import CreateAttachment
from .create_folder import CreateFolder
from .create_item import CreateItem
from .delete_attachment import DeleteAttachment
from .delete_folder import DeleteFolder
from .delete_item import DeleteItem
from .empty_folder import EmptyFolder
from .expand_dl import ExpandDL
from .export_items import ExportItems
from .find_folder import FindFolder
from .find_item import FindItem
from .find_people import FindPeople
from .get_attachment import GetAttachment
from .get_folder import GetFolder
from .get_item import GetItem
from .get_mail_tips import GetMailTips
from .get_persona import GetPersona
from .get_room_lists import GetRoomLists
from .get_rooms import GetRooms
from .get_searchable_mailboxes import GetSearchableMailboxes
from .get_server_time_zones import GetServerTimeZones
from .get_user_availability import GetUserAvailability
from .get_user_oof_settings import GetUserOofSettings
from .move_item import MoveItem
from .resolve_names import ResolveNames
from .send_item import SendItem
from .set_user_oof_settings import SetUserOofSettings
from .subscribe import GetStreamingEvents, SubscribePushFolder, SubscribeStreamingFolder, EVENT_TYPES
from .sync_folder import SyncFolderItems
from .unsubscribe import UnsubscribeStreamingFolder
from .update_folder import UpdateFolder
from .update_item import UpdateItem
from .upload_items import UploadItems

__all__ = [
    'CHUNK_SIZE',
    'CopyItem',
    'CreateAttachment',
    'CreateFolder',
    'CreateItem',
    'DeleteAttachment',
    'DeleteFolder',
    'DeleteItem',
    'EmptyFolder',
    'ExpandDL',
    'ExportItems',
    'FindFolder',
    'FindItem',
    'FindPeople',
    'GetAttachment',
    'GetFolder',
    'GetItem',
    'GetMailTips',
    'GetPersona',
    'GetRoomLists',
    'GetRooms',
    'GetSearchableMailboxes',
    'GetServerTimeZones',
    'GetStreamingEvents',
    'GetUserAvailability',
    'GetUserOofSettings',
    'MoveItem',
    'ResolveNames',
    'SendItem',
    'SetUserOofSettings',
    'EVENT_TYPES',
    'SubscribePushFolder',
    'SubscribeStreamingFolder',
    'SyncFolderItems',
    'UnsubscribeStreamingFolder',
    'UpdateFolder',
    'UpdateItem',
    'UploadItems',
]
