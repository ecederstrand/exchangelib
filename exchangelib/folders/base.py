import abc
import logging
from contextlib import suppress
from fnmatch import fnmatch
from operator import attrgetter

from ..errors import (
    ErrorAccessDenied,
    ErrorCannotDeleteObject,
    ErrorCannotEmptyFolder,
    ErrorDeleteDistinguishedFolder,
    ErrorFolderNotFound,
    ErrorItemNotFound,
    ErrorRecoverableItemsAccessDenied,
    InvalidTypeError,
)
from ..fields import (
    CharField,
    EffectiveRightsField,
    EWSElementField,
    Field,
    FieldPath,
    IdElementField,
    IntegerField,
    InvalidField,
    PermissionSetField,
)
from ..items import HARD_DELETE, ITEM_CLASSES
from ..items import SHALLOW as SHALLOW_ITEMS
from ..items import CalendarItem, RegisterMixIn
from ..properties import (
    DistinguishedFolderId,
    EWSMeta,
    FolderId,
    Mailbox,
    ParentFolderId,
    UserConfiguration,
    UserConfigurationName,
    UserConfigurationNameMNS,
)
from ..queryset import DoesNotExist, SearchableMixIn
from ..util import TNS, is_iterable, require_id
from ..version import EXCHANGE_2007_SP1, EXCHANGE_2010, SupportedVersionClassMixIn
from .collections import FolderCollection, PullSubscription, PushSubscription, StreamingSubscription, SyncCompleted
from .queryset import DEEP as DEEP_FOLDERS
from .queryset import MISSING_FOLDER_ERRORS
from .queryset import SHALLOW as SHALLOW_FOLDERS
from .queryset import SingleFolderQuerySet

log = logging.getLogger(__name__)

DELETE_FOLDER_ERRORS = (
    ErrorAccessDenied,
    ErrorCannotDeleteObject,
    ErrorCannotEmptyFolder,
    ErrorItemNotFound,
)


class BaseFolder(RegisterMixIn, SearchableMixIn, SupportedVersionClassMixIn, metaclass=EWSMeta):
    """Base class for all classes that implement a folder."""

    ELEMENT_NAME = "Folder"
    NAMESPACE = TNS
    # See https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/distinguishedfolderid
    DISTINGUISHED_FOLDER_ID = None
    # Default item type for this folder. See
    # https://docs.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-oxosfld/68a85898-84fe-43c4-b166-4711c13cdd61
    CONTAINER_CLASS = None
    supported_item_models = ITEM_CLASSES  # The Item types that this folder can contain. Default is all
    # Whether this folder type is allowed with the GetFolder service
    get_folder_allowed = True
    DEFAULT_FOLDER_TRAVERSAL_DEPTH = DEEP_FOLDERS
    DEFAULT_ITEM_TRAVERSAL_DEPTH = SHALLOW_ITEMS
    LOCALIZED_NAMES = {}  # A map of (str)locale: (tuple)localized_folder_names
    ITEM_MODEL_MAP = {cls.response_tag(): cls for cls in ITEM_CLASSES}
    ID_ELEMENT_CLS = FolderId

    _id = IdElementField(field_uri="folder:FolderId", value_cls=ID_ELEMENT_CLS)
    _distinguished_id = IdElementField(field_uri="folder:DistinguishedFolderId", value_cls=DistinguishedFolderId)
    parent_folder_id = EWSElementField(field_uri="folder:ParentFolderId", value_cls=ParentFolderId, is_read_only=True)
    folder_class = CharField(field_uri="folder:FolderClass", is_required_after_save=True)
    name = CharField(field_uri="folder:DisplayName")
    total_count = IntegerField(field_uri="folder:TotalCount", is_read_only=True)
    child_folder_count = IntegerField(field_uri="folder:ChildFolderCount", is_read_only=True)
    unread_count = IntegerField(field_uri="folder:UnreadCount", is_read_only=True)

    __slots__ = "item_sync_state", "folder_sync_state"

    # Used to register extended properties
    INSERT_AFTER_FIELD = "child_folder_count"

    def __init__(self, **kwargs):
        self.item_sync_state = kwargs.pop("item_sync_state", None)
        self.folder_sync_state = kwargs.pop("folder_sync_state", None)
        super().__init__(**kwargs)

    @property
    @abc.abstractmethod
    def account(self):
        """Return the account this folder belongs to"""

    @property
    @abc.abstractmethod
    def root(self):
        """Return the root folder this folder belongs to"""

    @property
    @abc.abstractmethod
    def parent(self):
        """Return the parent folder of this folder"""

    @property
    def is_distinguished(self):
        return self._distinguished_id or (self.DISTINGUISHED_FOLDER_ID and not self._id)

    @property
    def is_deletable(self):
        return not self.is_distinguished

    def clean(self, version=None):
        super().clean(version=version)
        # Set a default folder class for new folders. A folder class cannot be changed after saving.
        if self.id is None and self.folder_class is None:
            self.folder_class = self.CONTAINER_CLASS

    @property
    def children(self):
        # It's dangerous to return a generator here because we may then call methods on a child that result in the
        # cache being updated while it's iterated.
        return FolderCollection(account=self.account, folders=self.root.get_children(self))

    @property
    def parts(self):
        parts = [self]
        f = self.parent
        while f:
            parts.insert(0, f)
            f = f.parent
        return parts

    @property
    def absolute(self):
        return "".join(f"/{p.name}" for p in self.parts)

    def _walk(self):
        for c in self.children:
            yield c
            yield from c.walk()

    def walk(self):
        return FolderCollection(account=self.account, folders=self._walk())

    def _glob(self, pattern):
        split_pattern = pattern.split("/", maxsplit=1)
        head, tail = (split_pattern[0], None) if len(split_pattern) == 1 else split_pattern
        if head == "":
            # We got an absolute path. Restart globbing at root
            yield from self.root.glob(tail or "*")
        elif head == "..":
            # Relative path with reference to parent. Restart globbing at parent
            if not self.parent:
                raise ValueError("Already at top")
            yield from self.parent.glob(tail or "*")
        elif head == "**":
            # Match anything here or in any sub-folder at arbitrary depth
            for c in self.walk():
                # fnmatch() may be case-sensitive depending on operating system:
                # force a case-insensitive match since case appears not to
                # matter for folders in Exchange
                if fnmatch(c.name.lower(), (tail or "*").lower()):
                    yield c
        else:
            # Regular pattern
            for c in self.children:
                # See note above on fnmatch() case-sensitivity
                if not fnmatch(c.name.lower(), head.lower()):
                    continue
                if tail is None:
                    yield c
                    continue
                yield from c.glob(tail)

    def glob(self, pattern):
        return FolderCollection(account=self.account, folders=self._glob(pattern))

    def tree(self):
        """Return a string representation of the folder structure of this folder. Example:

        root
        ├── inbox
        │   └── todos
        └── archive
            ├── Last Job
            ├── exchangelib issues
            └── Mom
        """
        tree = f"{self.name}\n"
        children = list(self.children)
        for i, c in enumerate(sorted(children, key=attrgetter("name")), start=1):
            nodes = c.tree().split("\n")
            for j, node in enumerate(nodes, start=1):
                if i != len(children) and j == 1:
                    # Not the last child, but the first node, which is the name of the child
                    tree += f"├── {node}\n"
                elif i != len(children) and j > 1:
                    # Not the last child, and not name of child
                    tree += f"│   {node}\n"
                elif i == len(children) and j == 1:
                    # Not the last child, but the first node, which is the name of the child
                    tree += f"└── {node}\n"
                else:  # Last child and not name of child
                    tree += f"    {node}\n"
        return tree.strip()

    @property
    def has_distinguished_name(self):
        return self.name and self.DISTINGUISHED_FOLDER_ID and self.name.lower() == self.DISTINGUISHED_FOLDER_ID.lower()

    @classmethod
    def localized_names(cls, locale):
        # Return localized names for a specific locale. If no locale-specific names exist, return the default names,
        # if any.
        return tuple(s.lower() for s in cls.LOCALIZED_NAMES.get(locale, cls.LOCALIZED_NAMES.get(None, [cls.__name__])))

    @staticmethod
    def folder_cls_from_container_class(container_class):
        """Return a reasonable folder class given a container class, e.g. 'IPF.Note'. Don't iterate WELLKNOWN_FOLDERS
        because many folder classes have the same CONTAINER_CLASS.

        :param container_class:
        :return:
        """
        from .known_folders import (
            ApplicationData,
            Calendar,
            Companies,
            Contacts,
            ConversationSettings,
            CrawlerData,
            DlpPolicyEvaluation,
            EventCheckPoints,
            FreeBusyCache,
            GALContacts,
            Messages,
            OrganizationalContacts,
            PeopleCentricConversationBuddies,
            RecipientCache,
            RecoveryPoints,
            Reminders,
            RSSFeeds,
            Signal,
            SwssItems,
            Tasks,
        )

        for folder_cls in (
            ApplicationData,
            Calendar,
            Companies,
            Contacts,
            ConversationSettings,
            CrawlerData,
            DlpPolicyEvaluation,
            EventCheckPoints,
            FreeBusyCache,
            GALContacts,
            Messages,
            OrganizationalContacts,
            PeopleCentricConversationBuddies,
            RSSFeeds,
            RecipientCache,
            RecoveryPoints,
            Reminders,
            Signal,
            SwssItems,
            Tasks,
        ):
            if folder_cls.CONTAINER_CLASS == container_class:
                return folder_cls
        raise KeyError()

    @classmethod
    def item_model_from_tag(cls, tag):
        try:
            return cls.ITEM_MODEL_MAP[tag]
        except KeyError:
            raise ValueError(f"Item type {tag} was unexpected in a {cls.__name__} folder")

    @classmethod
    def allowed_item_fields(cls, version):
        # Return non-ID fields of all item classes allowed in this folder type
        fields = set()
        for item_model in cls.supported_item_models:
            fields.update(set(item_model.supported_fields(version=version)))
        return fields

    def validate_item_field(self, field, version):
        FolderCollection(account=self.account, folders=[self]).validate_item_field(field=field, version=version)

    def normalize_fields(self, fields):
        # Takes a list of fieldnames, Field or FieldPath objects pointing to item fields. Turns them into FieldPath
        # objects and adds internal timezone fields if necessary. Assume fields are already validated.
        fields = list(fields)
        has_start, has_end = False, False
        for i, field_path in enumerate(fields):
            # Allow both Field and FieldPath instances and string field paths as input
            if isinstance(field_path, str):
                field_path = FieldPath.from_string(field_path=field_path, folder=self)
                fields[i] = field_path
            elif isinstance(field_path, Field):
                field_path = FieldPath(field=field_path)
                fields[i] = field_path
            if field_path.field.name == "start":
                has_start = True
            elif field_path.field.name == "end":
                has_end = True

        # For CalendarItem items, we want to inject internal timezone fields. See also CalendarItem.clean()
        if CalendarItem in self.supported_item_models:
            meeting_tz_field, start_tz_field, end_tz_field = CalendarItem.timezone_fields()
            if self.account.version.build < EXCHANGE_2010:
                if has_start or has_end:
                    fields.append(FieldPath(field=meeting_tz_field))
            else:
                if has_start:
                    fields.append(FieldPath(field=start_tz_field))
                if has_end:
                    fields.append(FieldPath(field=end_tz_field))
        return fields

    @classmethod
    def get_item_field_by_fieldname(cls, fieldname):
        for item_model in cls.supported_item_models:
            with suppress(InvalidField):
                return item_model.get_field_by_fieldname(fieldname)
        raise InvalidField(f"{fieldname!r} is not a valid field name on {cls.supported_item_models}")

    def get(self, *args, **kwargs):
        return FolderCollection(account=self.account, folders=[self]).get(*args, **kwargs)

    def all(self):
        return FolderCollection(account=self.account, folders=[self]).all()

    def none(self):
        return FolderCollection(account=self.account, folders=[self]).none()

    def filter(self, *args, **kwargs):
        return FolderCollection(account=self.account, folders=[self]).filter(*args, **kwargs)

    def exclude(self, *args, **kwargs):
        return FolderCollection(account=self.account, folders=[self]).exclude(*args, **kwargs)

    def people(self):
        # No point in using a FolderCollection because FindPeople only supports one folder
        return FolderCollection(account=self.account, folders=[self]).people()

    def bulk_create(self, items, *args, **kwargs):
        return self.account.bulk_create(folder=self, items=items, *args, **kwargs)

    def save(self, update_fields=None):
        from ..services import CreateFolder, UpdateFolder

        if self.id is None:
            # New folder
            if update_fields:
                raise ValueError("'update_fields' is only valid for updates")
            res = CreateFolder(account=self.account).get(parent_folder=self.parent, folders=[self])
            self._id = self.ID_ELEMENT_CLS(res.id, res.changekey)
            self.root.add_folder(self)  # Add this folder to the cache
            return self

        # Update folder
        if not update_fields:
            # The fields to update was not specified explicitly. Update all fields where update is possible
            update_fields = []
            for f in self.supported_fields(version=self.account.version):
                if f.is_read_only:
                    # These cannot be changed
                    continue
                if (f.is_required or f.is_required_after_save) and (
                    getattr(self, f.name) is None or (f.is_list and not getattr(self, f.name))
                ):
                    # These are required and cannot be deleted
                    continue
                update_fields.append(f.name)
        res = UpdateFolder(account=self.account).get(folders=[(self, update_fields)])
        folder_id, changekey = res.id, res.changekey
        if self.id != folder_id:
            raise ValueError("ID mismatch")
        # Don't check changekey value. It may not change on no-op updates
        self.changekey = changekey
        self.root.update_folder(self)  # Update the folder in the cache
        return self

    def move(self, to_folder):
        from ..services import MoveFolder

        res = MoveFolder(account=self.account).get(folders=[self], to_folder=to_folder)
        folder_id, changekey = res.id, res.changekey
        if self.id != folder_id:
            raise ValueError("ID mismatch")
        # Don't check changekey value. It may not change on no-op moves
        self.changekey = changekey
        self.parent_folder_id = ParentFolderId(id=to_folder.id, changekey=to_folder.changekey)
        self.root.update_folder(self)  # Update the folder in the cache

    def delete(self, delete_type=HARD_DELETE):
        from ..services import DeleteFolder

        DeleteFolder(account=self.account).get(folders=[self], delete_type=delete_type)
        self.root.remove_folder(self)  # Remove the updated folder from the cache
        self._id = None

    def empty(self, delete_type=HARD_DELETE, delete_sub_folders=False):
        from ..services import EmptyFolder

        EmptyFolder(account=self.account).get(
            folders=[self], delete_type=delete_type, delete_sub_folders=delete_sub_folders
        )
        if delete_sub_folders:
            # We don't know exactly what was deleted, so invalidate the entire folder cache to be safe
            self.root.clear_cache()

    def wipe(self, page_size=None, chunk_size=None, _seen=None, _level=0):
        # Recursively deletes all items in this folder, and all sub-folders and their content. Attempts to protect
        # distinguished folders from being deleted. Use with caution!
        from .known_folders import Audits

        _seen = _seen or set()
        if self.id in _seen:
            raise RecursionError(f"We already tried to wipe {self}")
        if _level > 16:
            raise RecursionError(f"Max recursion level reached: {_level}")
        _seen.add(self.id)
        if isinstance(self, Audits):
            # Shortcircuit because this folder can have many items that are all non-deletable
            log.warning("Cannot wipe audits folder %s", self)
            return
        if self.is_distinguished and "recoverableitems" in self.DISTINGUISHED_FOLDER_ID:
            log.warning("Cannot wipe recoverable items folder %s", self)
            return
        log.warning("Wiping %s", self)
        has_non_deletable_subfolders = any(not f.is_deletable for f in self.children)
        try:
            if has_non_deletable_subfolders:
                self.empty()
            else:
                self.empty(delete_sub_folders=True)
        except ErrorRecoverableItemsAccessDenied:
            log.warning("Access denied to %s. Skipping", self)
            return
        except DELETE_FOLDER_ERRORS:
            try:
                if has_non_deletable_subfolders:
                    raise  # We already tried this
                self.empty()
            except DELETE_FOLDER_ERRORS:
                log.warning("Not allowed to empty %s. Trying to delete items instead", self)
                kwargs = {}
                if page_size is not None:
                    kwargs["page_size"] = page_size
                if chunk_size is not None:
                    kwargs["chunk_size"] = chunk_size
                try:
                    self.all().delete(**kwargs)
                except DELETE_FOLDER_ERRORS:
                    log.warning("Not allowed to delete items in %s", self)
        _level += 1
        for f in self.children:
            f.wipe(page_size=page_size, chunk_size=chunk_size, _seen=_seen, _level=_level)
            # Remove non-distinguished children that are empty and have no sub-folders
            if f.is_deletable and not f.children:
                log.warning("Deleting folder %s", f)
                try:
                    f.delete()
                except ErrorDeleteDistinguishedFolder:
                    log.warning("Tried to delete a distinguished folder (%s)", f)

    def test_access(self):
        """Does a simple FindItem to test (read) access to the folder. Maybe the account doesn't exist, maybe the
        service user doesn't have access to the calendar. This will throw the most common errors.
        """
        self.all().exists()
        return True

    @classmethod
    def _kwargs_from_elem(cls, elem, account):
        # Check for 'DisplayName' element before collecting kwargs because that clears the elements
        has_name_elem = elem.find(cls.get_field_by_fieldname("name").response_tag()) is not None
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS}
        if has_name_elem and not kwargs["name"]:
            # When we request the 'DisplayName' property, some folders may still be returned with an empty value.
            # Assign a default name to these folders.
            kwargs["name"] = cls.DISTINGUISHED_FOLDER_ID
        return kwargs

    def to_id(self):
        # Use self._distinguished_id as-is if we have it. This could be a DistinguishedFolderId with a mailbox pointing
        # to a shared mailbox.
        if self._distinguished_id:
            return self._distinguished_id
        if self._id:
            return self._id
        if not self.DISTINGUISHED_FOLDER_ID:
            raise ValueError(f"{self} must be a distinguished folder or have an ID")
        self._distinguished_id = DistinguishedFolderId(
            id=self.DISTINGUISHED_FOLDER_ID,
            mailbox=Mailbox(email_address=self.account.primary_smtp_address),
        )
        return self._distinguished_id

    @classmethod
    def resolve(cls, account, folder):
        # Resolve a single folder
        folders = list(FolderCollection(account=account, folders=[folder]).resolve())
        if not folders:
            raise ErrorFolderNotFound(f"Could not find folder {folder!r}")
        if len(folders) != 1:
            raise ValueError(f"Expected result length 1, but got {folders}")
        f = folders[0]
        if isinstance(f, Exception):
            raise f
        if f.__class__ != cls:
            raise ValueError(f"Expected folder {f!r} to be a {cls} instance")
        return f

    @require_id
    def refresh(self):
        fresh_folder = self.resolve(account=self.account, folder=self)
        if self.id != fresh_folder.id:
            raise ValueError("ID mismatch")
        # Apparently, the changekey may get updated
        for f in self.FIELDS:
            setattr(self, f.name, getattr(fresh_folder, f.name))
        return self

    @require_id
    def get_user_configuration(self, name, properties=None):
        from ..services import GetUserConfiguration
        from ..services.get_user_configuration import ALL

        if properties is None:
            properties = ALL
        return GetUserConfiguration(account=self.account).get(
            user_configuration_name=UserConfigurationNameMNS(name=name, folder=self),
            properties=properties,
        )

    @require_id
    def create_user_configuration(self, name, dictionary=None, xml_data=None, binary_data=None):
        from ..services import CreateUserConfiguration

        user_configuration = UserConfiguration(
            user_configuration_name=UserConfigurationName(name=name, folder=self),
            dictionary=dictionary,
            xml_data=xml_data,
            binary_data=binary_data,
        )
        return CreateUserConfiguration(account=self.account).get(user_configuration=user_configuration)

    @require_id
    def update_user_configuration(self, name, dictionary=None, xml_data=None, binary_data=None):
        from ..services import UpdateUserConfiguration

        user_configuration = UserConfiguration(
            user_configuration_name=UserConfigurationName(name=name, folder=self),
            dictionary=dictionary,
            xml_data=xml_data,
            binary_data=binary_data,
        )
        return UpdateUserConfiguration(account=self.account).get(user_configuration=user_configuration)

    @require_id
    def delete_user_configuration(self, name):
        from ..services import DeleteUserConfiguration

        return DeleteUserConfiguration(account=self.account).get(
            user_configuration_name=UserConfigurationNameMNS(name=name, folder=self)
        )

    @require_id
    def subscribe_to_pull(self, event_types=None, watermark=None, timeout=60):
        """Create a pull subscription.

        :param event_types: List of event types to subscribe to. Possible values defined in SubscribeToPull.EVENT_TYPES
        :param watermark: An event bookmark as returned by some sync services
        :param timeout: Timeout of the subscription, in minutes. Timeout is reset when the server receives a
        GetEvents request for this subscription.
        :return: The subscription ID and a watermark
        """
        from ..services import SubscribeToPull

        if event_types is None:
            event_types = SubscribeToPull.EVENT_TYPES
        return FolderCollection(account=self.account, folders=[self]).subscribe_to_pull(
            event_types=event_types,
            watermark=watermark,
            timeout=timeout,
        )

    @require_id
    def subscribe_to_push(self, callback_url, event_types=None, watermark=None, status_frequency=1):
        """Create a push subscription.

        :param callback_url: A client-defined URL that the server will call
        :param event_types: List of event types to subscribe to. Possible values defined in SubscribeToPush.EVENT_TYPES
        :param watermark: An event bookmark as returned by some sync services
        :param status_frequency: The frequency, in minutes, that the callback URL will be called with.
        :return: The subscription ID and a watermark
        """
        from ..services import SubscribeToPush

        if event_types is None:
            event_types = SubscribeToPush.EVENT_TYPES
        return FolderCollection(account=self.account, folders=[self]).subscribe_to_push(
            event_types=event_types,
            watermark=watermark,
            status_frequency=status_frequency,
            callback_url=callback_url,
        )

    @require_id
    def subscribe_to_streaming(self, event_types=None):
        """Create a streaming subscription.

        :param event_types: List of event types to subscribe to. Possible values defined in SubscribeToPush.EVENT_TYPES
        :return: The subscription ID
        """
        from ..services import SubscribeToStreaming

        if event_types is None:
            event_types = SubscribeToStreaming.EVENT_TYPES
        return FolderCollection(account=self.account, folders=[self]).subscribe_to_streaming(event_types=event_types)

    @require_id
    def pull_subscription(self, **kwargs):
        return PullSubscription(target=self, **kwargs)

    @require_id
    def push_subscription(self, **kwargs):
        return PushSubscription(target=self, **kwargs)

    @require_id
    def streaming_subscription(self, **kwargs):
        return StreamingSubscription(target=self, **kwargs)

    def unsubscribe(self, subscription_id):
        """Unsubscribe. Only applies to pull and streaming notifications.

        :param subscription_id: A subscription ID as acquired by .subscribe_to_[pull|streaming]()
        :return: True

        This method doesn't need the current folder instance, but it makes sense to keep the method along the other
        sync methods.
        """
        from ..services import Unsubscribe

        return Unsubscribe(account=self.account).get(subscription_id=subscription_id)

    def sync_items(self, sync_state=None, only_fields=None, ignore=None, max_changes_returned=None, sync_scope=None):
        """Return all item changes to a folder, as a generator. If sync_state is specified, get all item changes after
        this sync state. After fully consuming the generator, self.item_sync_state will hold the new sync state.

        :param sync_state: The state of the sync. Returned by a successful call to the SyncFolderItems service.
        :param only_fields: A list of string or FieldPath items specifying the fields to fetch. Default to all fields
        :param ignore: A list of Item IDs to ignore in the sync
        :param max_changes_returned: The max number of change
        :param sync_scope: Specify whether to return just items, or items and folder associated information. Possible
           values are specified in SyncFolderItems.SYNC_SCOPES
        :return: A generator of (change_type, item) tuples
        """
        if not sync_state:
            sync_state = self.item_sync_state
        try:
            yield from FolderCollection(account=self.account, folders=[self]).sync_items(
                sync_state=sync_state,
                only_fields=only_fields,
                ignore=ignore,
                max_changes_returned=max_changes_returned,
                sync_scope=sync_scope,
            )
        except SyncCompleted as e:
            # Set the new sync state on the folder instance
            self.item_sync_state = e.sync_state

    def sync_hierarchy(self, sync_state=None, only_fields=None):
        """Return all folder changes to a folder hierarchy, as a generator. If sync_state is specified, get all folder
        changes after this sync state. After fully consuming the generator, self.folder_sync_state will hold the new
        sync state.

        :param sync_state: The state of the sync. Returned by a successful call to the SyncFolderItems service.
        :param only_fields: A list of string or FieldPath items specifying the fields to fetch. Default to all fields
        :return:
        """
        if not sync_state:
            sync_state = self.folder_sync_state
        try:
            yield from FolderCollection(account=self.account, folders=[self]).sync_hierarchy(
                sync_state=sync_state,
                only_fields=only_fields,
            )
        except SyncCompleted as e:
            # Set the new sync state on the folder instance
            self.folder_sync_state = e.sync_state

    def get_events(self, subscription_id, watermark):
        """Get events since the given watermark. Non-blocking.

        :param subscription_id: A subscription ID as acquired by .subscribe_to_[pull|push]()
        :param watermark: Either the watermark from the subscription, or as returned by the last .get_events() call.
        :return: A Notification object containing a list of events

        This method doesn't need the current folder instance, but it makes sense to keep the method along the other
        sync methods.
        """
        from ..services import GetEvents

        svc = GetEvents(account=self.account)
        while True:
            notification = svc.get(subscription_id=subscription_id, watermark=watermark)
            yield notification
            if not notification.more_events:
                break

    def get_streaming_events(self, subscription_id_or_ids, connection_timeout=1, max_notifications_returned=None):
        """Get events since the subscription was created, in streaming mode. This method will block as many minutes
        as specified by 'connection_timeout'.

        :param subscription_id_or_ids: A subscription ID, or list of IDs, as acquired by .subscribe_to_streaming()
        :param connection_timeout: Timeout of the connection, in minutes. The connection is closed after this timeout
        is reached.
        :param max_notifications_returned: If specified, will exit after receiving this number of notifications
        :return: A generator of Notification objects, each containing a list of events

        This method doesn't need the current folder instance, but it makes sense to keep the method along the other
        sync methods.
        """
        from ..services import GetStreamingEvents

        svc = GetStreamingEvents(account=self.account)
        subscription_ids = (
            subscription_id_or_ids
            if is_iterable(subscription_id_or_ids, generators_allowed=True)
            else [subscription_id_or_ids]
        )
        for i, notification in enumerate(
            svc.call(subscription_ids=subscription_ids, connection_timeout=connection_timeout), start=1
        ):
            yield notification
            if max_notifications_returned and i >= max_notifications_returned:
                svc.stop_streaming()
                break

    def __floordiv__(self, other):
        """Support the some_folder // 'child_folder' // 'child_of_child_folder' navigation syntax.

        Works like as __truediv__ but does not touch the folder cache.

        This is useful if the folder hierarchy contains a huge number of folders, and you don't want to fetch them all

        :param other:
        :return:
        """
        if other == "..":
            raise ValueError("Cannot get parent without a folder cache")

        if other == ".":
            return self

        # Assume an exact match on the folder name in a shallow search will only return at most one folder
        try:
            return SingleFolderQuerySet(account=self.account, folder=self).depth(SHALLOW_FOLDERS).get(name=other)
        except DoesNotExist:
            raise ErrorFolderNotFound(f"No subfolder with name {other!r}")

    def __truediv__(self, other):
        """Support the some_folder / 'child_folder' / 'child_of_child_folder' navigation syntax."""
        if other == "..":
            if not self.parent:
                raise ValueError("Already at top")
            return self.parent
        if other == ".":
            return self
        for c in self.children:
            # Folders are case-insensitive server-side. Let's do that here as well.
            if c.name.lower() == other.lower():
                return c
        raise ErrorFolderNotFound(f"No subfolder with name {other!r}")

    def __repr__(self):
        return self.__class__.__name__ + repr(
            (
                self.root,
                self.name,
                self.total_count,
                self.unread_count,
                self.child_folder_count,
                self.folder_class,
                self.id,
                self.changekey,
            )
        )

    def __str__(self):
        return f"{self.__class__.__name__} ({self.name})"


class Folder(BaseFolder):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/folder"""

    permission_set = PermissionSetField(field_uri="folder:PermissionSet", supported_from=EXCHANGE_2007_SP1)
    effective_rights = EffectiveRightsField(
        field_uri="folder:EffectiveRights", is_read_only=True, supported_from=EXCHANGE_2007_SP1
    )

    __slots__ = ("_root",)

    def __init__(self, **kwargs):
        self._root = kwargs.pop("root", None)  # This is a pointer to the root of the folder hierarchy
        parent = kwargs.pop("parent", None)
        if parent:
            if self.root:
                if parent.root != self.root:
                    raise ValueError("'parent.root' must match 'root'")
            else:
                self.root = parent.root
            if "parent_folder_id" in kwargs and parent.id != kwargs["parent_folder_id"]:
                raise ValueError("'parent_folder_id' must match 'parent' ID")
            kwargs["parent_folder_id"] = ParentFolderId(id=parent.id, changekey=parent.changekey)
        super().__init__(**kwargs)

    @property
    def account(self):
        if self.root is None:
            return None
        return self.root.account

    @property
    def root(self):
        return self._root

    @root.setter
    def root(self, value):
        self._root = value

    @classmethod
    def register(cls, *args, **kwargs):
        if cls is not Folder:
            raise TypeError("For folders, custom fields must be registered on the Folder class")
        return super().register(*args, **kwargs)

    @classmethod
    def deregister(cls, *args, **kwargs):
        if cls is not Folder:
            raise TypeError("For folders, custom fields must be registered on the Folder class")
        return super().deregister(*args, **kwargs)

    @classmethod
    def get_distinguished(cls, account):
        """Get the distinguished folder for this folder class.

        :param account:
        :return:
        """
        try:
            return cls.resolve(
                account=account,
                folder=DistinguishedFolderId(
                    id=cls.DISTINGUISHED_FOLDER_ID,
                    mailbox=Mailbox(email_address=account.primary_smtp_address),
                ),
            )
        except MISSING_FOLDER_ERRORS:
            raise ErrorFolderNotFound(f"Could not find distinguished folder {cls.DISTINGUISHED_FOLDER_ID!r}")

    @property
    def parent(self):
        if not self.parent_folder_id:
            return None
        if self.parent_folder_id.id == self.id:
            # Some folders have a parent that references itself. Avoid circular references here
            return None
        return self.root.get_folder(self.parent_folder_id)

    @parent.setter
    def parent(self, value):
        if value is None:
            self.parent_folder_id = None
        else:
            if not isinstance(value, BaseFolder):
                raise InvalidTypeError("value", value, BaseFolder)
            self.root = value.root
            self.parent_folder_id = ParentFolderId(id=value.id, changekey=value.changekey)

    def clean(self, version=None):
        from .roots import RootOfHierarchy

        super().clean(version=version)
        if self.root and not isinstance(self.root, RootOfHierarchy):
            raise InvalidTypeError("root", self.root, RootOfHierarchy)

    @classmethod
    def from_xml_with_root(cls, elem, root):
        folder = cls.from_xml(elem=elem, account=root.account)
        folder_cls = cls
        if cls == Folder:
            # We were called on the generic Folder class. Try to find a more specific class to return objects as.
            #
            # The "FolderClass" element value is the only indication we have in the FindFolder response of which
            # folder class we should create the folder with. And many folders share the same 'FolderClass' value, e.g.
            # Inbox and DeletedItems. We want to distinguish between these because otherwise we can't locate the right
            # folders types for e.g. Account.inbox and Account.trash.
            #
            # We should be able to just use the name, but apparently default folder names can be renamed to a set of
            # localized names using a PowerShell command:
            # https://docs.microsoft.com/en-us/powershell/module/exchange/client-access/Set-MailboxRegionalConfiguration
            #
            # Instead, search for a folder class using the localized name. If none are found, fall back to getting the
            # folder class by the "FolderClass" value.
            #
            # The returned XML may contain neither folder class nor name. In that case, we default to the generic
            # Folder class.
            if folder.name:
                with suppress(KeyError):
                    # TODO: fld_class.LOCALIZED_NAMES is most definitely neither complete nor authoritative
                    folder_cls = root.folder_cls_from_folder_name(
                        folder_name=folder.name,
                        folder_class=folder.folder_class,
                        locale=root.account.locale,
                    )
                    log.debug("Folder class %s matches localized folder name %s", folder_cls, folder.name)
            if folder.folder_class and folder_cls == Folder:
                with suppress(KeyError):
                    folder_cls = cls.folder_cls_from_container_class(container_class=folder.folder_class)
                    log.debug(
                        "Folder class %s matches container class %s (%s)", folder_cls, folder.folder_class, folder.name
                    )
            if folder_cls == Folder:
                log.debug("Fallback to class Folder (folder_class %s, name %s)", folder.folder_class, folder.name)
        return folder_cls(root=root, **{f.name: getattr(folder, f.name) for f in folder.FIELDS})
