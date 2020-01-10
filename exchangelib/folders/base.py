# coding=utf-8
from __future__ import unicode_literals
from contextlib import contextmanager

from contextlib import contextmanager
from fnmatch import fnmatch
import logging
from operator import attrgetter

from ..errors import ErrorAccessDenied, ErrorFolderNotFound, ErrorCannotEmptyFolder, ErrorCannotDeleteObject, \
    ErrorDeleteDistinguishedFolder
from ..fields import IntegerField, CharField, FieldPath, EffectiveRightsField, PermissionSetField, EWSElementField, \
    Field, Base64Field
from ..items import CalendarItem, RegisterMixIn, Persona, ITEM_CLASSES, ITEM_TRAVERSAL_CHOICES, SHAPE_CHOICES, \
    ID_ONLY, DELETE_TYPE_CHOICES, HARD_DELETE, ALL_ITEM_CLASSES, SHALLOW as SHALLOW_ITEMS
from ..properties import Mailbox, FolderId, ParentFolderId, InvalidField, DistinguishedFolderId
from ..queryset import QuerySet, SearchableMixIn, DoesNotExist
from ..restriction import Restriction
from ..services import CreateFolder, UpdateFolder, DeleteFolder, EmptyFolder, FindPeople, EVENT_TYPES, \
    SyncFolderItems, SubscribePushFolder, SubscribeStreamingFolder, UnsubscribeStreamingFolder, GetStreamingEvents
from ..util import TNS
from ..version import Version, EXCHANGE_2007_SP1, EXCHANGE_2010
from .collections import FolderCollection
from .queryset import SingleFolderQuerySet, SHALLOW as SHALLOW_FOLDERS, DEEP as DEEP_FOLDERS

log = logging.getLogger(__name__)


class BaseFolder(RegisterMixIn, SearchableMixIn):
    """Base class for all classes that implement a folder"""
    ELEMENT_NAME = 'Folder'
    NAMESPACE = TNS
    # See https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/distinguishedfolderid
    DISTINGUISHED_FOLDER_ID = None
    # Default item type for this folder. See
    # https://docs.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-oxosfld/68a85898-84fe-43c4-b166-4711c13cdd61
    CONTAINER_CLASS = None
    supported_item_models = ITEM_CLASSES  # The Item types that this folder can contain. Default is all
    # Marks the version from which a distinguished folder was introduced. A possibly authoritative source is:
    # https://github.com/OfficeDev/ews-managed-api/blob/master/Enumerations/WellKnownFolderName.cs
    supported_from = None
    # Whether this folder type is allowed with the GetFolder service
    get_folder_allowed = True
    DEFAULT_FOLDER_TRAVERSAL_DEPTH = DEEP_FOLDERS
    DEFAULT_ITEM_TRAVERSAL_DEPTH = SHALLOW_ITEMS
    LOCALIZED_NAMES = dict()  # A map of (str)locale: (tuple)localized_folder_names
    ITEM_MODEL_MAP = {cls.response_tag(): cls for cls in ALL_ITEM_CLASSES}
    ID_ELEMENT_CLS = FolderId
    LOCAL_FIELDS = [
        EWSElementField('parent_folder_id', field_uri='folder:ParentFolderId', value_cls=ParentFolderId,
                        is_read_only=True),
        CharField('folder_class', field_uri='folder:FolderClass', is_required_after_save=True),
        CharField('name', field_uri='folder:DisplayName'),
        IntegerField('total_count', field_uri='folder:TotalCount', is_read_only=True),
        IntegerField('child_folder_count', field_uri='folder:ChildFolderCount', is_read_only=True),
        IntegerField('unread_count', field_uri='folder:UnreadCount', is_read_only=True),
        # Base64Field('sync_state', field_uri='folder:SyncState', is_read_only=True),
    ]
    FIELDS = RegisterMixIn.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS) + ('is_distinguished',)

    # Used to register extended properties
    INSERT_AFTER_FIELD = 'child_folder_count'

    def __init__(self, **kwargs):
        self.is_distinguished = kwargs.pop('is_distinguished', False)
        super().__init__(**kwargs)
        self.sync_state = None

    @property
    def account(self):
        raise NotImplementedError()

    @property
    def root(self):
        raise NotImplementedError()

    @property
    def parent(self):
        raise NotImplementedError()

    @property
    def is_deleteable(self):
        return not self.is_distinguished

    def clean(self, version=None):
        # pylint: disable=access-member-before-definition
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
        return ''.join('/%s' % p.name for p in self.parts)

    def _walk(self):
        for c in self.children:
            yield c
            for f in c.walk():
                yield f

    def walk(self):
        return FolderCollection(account=self.account, folders=self._walk())

    def _glob(self, pattern):
        split_pattern = pattern.rsplit('/', 1)
        head, tail = (split_pattern[0], None) if len(split_pattern) == 1 else split_pattern
        if head == '':
            # We got an absolute path. Restart globbing at root
            for f in self.root.glob(tail or '*'):
                yield f
        elif head == '..':
            # Relative path with reference to parent. Restart globbing at parent
            if not self.parent:
                raise ValueError('Already at top')
            for f in self.parent.glob(tail or '*'):
                yield f
        elif head == '**':
            # Match anything here or in any subfolder at arbitrary depth
            for c in self.walk():
                if fnmatch(c.name, tail or '*'):
                    yield c
        else:
            # Regular pattern
            for c in self.children:
                if not fnmatch(c.name, head):
                    continue
                if tail is None:
                    yield c
                    continue
                for f in c.glob(tail):
                    yield f

    def glob(self, pattern):
        return FolderCollection(account=self.account, folders=self._glob(pattern))

    def tree(self):
        """
        Returns a string representation of the folder structure of this folder. Example:

        root
        ├── inbox
        │   └── todos
        └── archive
            ├── Last Job
            ├── exchangelib issues
            └── Mom
        """
        tree = '%s\n' % self.name
        children = list(self.children)
        for i, c in enumerate(sorted(children, key=attrgetter('name')), start=1):
            nodes = c.tree().split('\n')
            for j, node in enumerate(nodes, start=1):
                if i != len(children) and j == 1:
                    # Not the last child, but the first node, which is the name of the child
                    tree += '├── %s\n' % node
                elif i != len(children) and j > 1:
                    # Not the last child, and not name of child
                    tree += '│   %s\n' % node
                elif i == len(children) and j == 1:
                    # Not the last child, but the first node, which is the name of the child
                    tree += '└── %s\n' % node
                else:  # Last child, and not name of child
                    tree += '    %s\n' % node
        return tree.strip()

    @classmethod
    def supports_version(cls, version):
        # 'version' is a Version instance, for convenience by callers
        if not isinstance(version, Version):
            raise ValueError("'version' %r must be a Version instance" % version)
        if not cls.supported_from:
            return True
        return version.build >= cls.supported_from

    @property
    def has_distinguished_name(self):
        return self.name and self.DISTINGUISHED_FOLDER_ID and self.name.lower() == self.DISTINGUISHED_FOLDER_ID.lower()

    @classmethod
    def localized_names(cls, locale):
        # Return localized names for a specific locale. If no locale-specific names exist, return the default names,
        # if any.
        return tuple(s.lower() for s in cls.LOCALIZED_NAMES.get(locale, cls.LOCALIZED_NAMES.get(None, [])))

    @staticmethod
    def folder_cls_from_container_class(container_class):
        """Returns a reasonable folder class given a container class, e.g. 'IPF.Note'. Don't iterate WELLKNOWN_FOLDERS
        because many folder classes have the same CONTAINER_CLASS.
        """
        from .known_folders import Messages, Tasks, Calendar, ConversationSettings, Contacts, GALContacts, Reminders, \
            RecipientCache, RSSFeeds
        for folder_cls in (
                Messages, Tasks, Calendar, ConversationSettings, Contacts, GALContacts, Reminders, RecipientCache,
                RSSFeeds):
            if folder_cls.CONTAINER_CLASS == container_class:
                return folder_cls
        raise KeyError()

    @classmethod
    def item_model_from_tag(cls, tag):
        try:
            return cls.ITEM_MODEL_MAP[tag]
        except KeyError:
            raise ValueError('Item type %s was unexpected in a %s folder' % (tag, cls.__name__))

    @classmethod
    def allowed_item_fields(cls, version):
        # Return non-ID fields of all item classes allowed in this folder type
        fields = set()
        for item_model in cls.supported_item_models:
            fields.update(
                set(item_model.supported_fields(version=version))
            )
        return fields

    def validate_item_field(self, field, version):
        # Takes a fieldname, Field or FieldPath object pointing to an item field, and checks that it is valid
        # for the item types supported by this folder.

        # For each field, check if the field is valid for any of the item models supported by this folder
        for item_model in self.supported_item_models:
            try:
                item_model.validate_field(field=field, version=version)
                break
            except InvalidField:
                continue
        else:
            raise InvalidField("%r is not a valid field on %s" % (field, self.supported_item_models))

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
            if not isinstance(field_path, FieldPath):
                raise ValueError("Field %r must be a string or FieldPath instance" % field_path)
            if field_path.field.name == 'start':
                has_start = True
            elif field_path.field.name == 'end':
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
            try:
                return item_model.get_field_by_fieldname(fieldname)
            except InvalidField:
                pass
        raise InvalidField("%r is not a valid field name on %s" % (fieldname, cls.supported_item_models))

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
        return QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self]),
            request_type=QuerySet.PERSONA,
        )

    def find_people(self, q, shape=ID_ONLY, depth=None, additional_fields=None, order_fields=None,
                    page_size=None, max_items=None, offset=0):
        """
        Private method to call the FindPeople service

        :param q: a Q instance containing any restrictions
        :param shape: controls whether to return (id, chanegkey) tuples or Persona objects. If additional_fields is
               non-null, we always return Persona objects.
        :param depth: controls the whether to return soft-deleted items or not.
        :param additional_fields: the extra properties we want on the return objects. Default is no properties.
        :param order_fields: the SortOrder fields, if any
        :param page_size: the requested number of items per page
        :param max_items: the max number of items to return
        :param offset: the offset relative to the first item in the item collection
        :return: a generator for the returned personas
        """
        if shape not in SHAPE_CHOICES:
            raise ValueError("'shape' %s must be one of %s" % (shape, SHAPE_CHOICES))
        if depth is None:
            depth = self.DEFAULT_ITEM_TRAVERSAL_DEPTH
        if depth not in ITEM_TRAVERSAL_CHOICES:
            raise ValueError("'depth' %s must be one of %s" % (depth, ITEM_TRAVERSAL_CHOICES))
        if additional_fields:
            for f in additional_fields:
                Persona.validate_field(field=f, version=self.account.version)
                if f.field.is_complex:
                    raise ValueError("find_people() does not support field '%s'" % f.field.name)

        # Build up any restrictions
        if q.is_empty():
            restriction = None
            query_string = None
        elif q.query_string:
            restriction = None
            query_string = Restriction(q, folders=[self], applies_to=Restriction.ITEMS)
        else:
            restriction = Restriction(q, folders=[self], applies_to=Restriction.ITEMS)
            query_string = None
        personas = FindPeople(account=self.account, chunk_size=page_size).call(
                folder=self,
                additional_fields=additional_fields,
                restriction=restriction,
                order_fields=order_fields,
                shape=shape,
                query_string=query_string,
                depth=depth,
                max_items=max_items,
                offset=offset,
        )
        for p in personas:
            if isinstance(p, Exception):
                raise p
            yield p

    def bulk_create(self, items, *args, **kwargs):
        return self.account.bulk_create(folder=self, items=items, *args, **kwargs)

    def save(self, update_fields=None):
        if self.id is None:
            # New folder
            if update_fields:
                raise ValueError("'update_fields' is only valid for updates")
            res = list(CreateFolder(account=self.account).call(parent_folder=self.parent, folders=[self]))
            if len(res) != 1:
                raise ValueError('Expected result length 1, but got %s' % res)
            if isinstance(res[0], Exception):
                raise res[0]
            self.id, self.changekey = res[0].id, res[0].changekey
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
                if f.is_required or f.is_required_after_save:
                    if getattr(self, f.name) is None or (f.is_list and not getattr(self, f.name)):
                        # These are required and cannot be deleted
                        continue
                update_fields.append(f.name)
        res = list(UpdateFolder(account=self.account).call(folders=[(self, update_fields)]))
        if len(res) != 1:
            raise ValueError('Expected result length 1, but got %s' % res)
        if isinstance(res[0], Exception):
            raise res[0]
        folder_id, changekey = res[0].id, res[0].changekey
        if self.id != folder_id:
            raise ValueError('ID mismatch')
        # Don't check changekey value. It may not change on no-op updates
        self.changekey = changekey
        self.root.update_folder(self)  # Update the folder in the cache
        return None

    def delete(self, delete_type=HARD_DELETE):
        if delete_type not in DELETE_TYPE_CHOICES:
            raise ValueError("'delete_type' %s must be one of %s" % (delete_type, DELETE_TYPE_CHOICES))
        res = list(DeleteFolder(account=self.account).call(folders=[self], delete_type=delete_type))
        if len(res) != 1:
            raise ValueError('Expected result length 1, but got %s' % res)
        if isinstance(res[0], Exception):
            raise res[0]
        self.root.remove_folder(self)  # Remove the updated folder from the cache
        self.id, self.changekey = None, None

    def empty(self, delete_type=HARD_DELETE, delete_sub_folders=False):
        if delete_type not in DELETE_TYPE_CHOICES:
            raise ValueError("'delete_type' %s must be one of %s" % (delete_type, DELETE_TYPE_CHOICES))
        res = list(EmptyFolder(account=self.account).call(
            folders=[self], delete_type=delete_type, delete_sub_folders=delete_sub_folders)
        )
        if len(res) != 1:
            raise ValueError('Expected result length 1, but got %s' % res)
        if isinstance(res[0], Exception):
            raise res[0]
        if delete_sub_folders:
            # We don't know exactly what was deleted, so invalidate the entire folder cache to be safe
            self.root.clear_cache()

    def wipe(self, page_size=None):
        # Recursively deletes all items in this folder, and all subfolders and their content. Attempts to protect
        # distinguished folders from being deleted. Use with caution!
        log.warning('Wiping %s', self)
        delete_kwargs = {}
        if page_size:
            delete_kwargs['page_size'] = page_size
        has_distinguished_subfolders = any(f.is_distinguished for f in self.children)
        try:
            if has_distinguished_subfolders:
                self.empty(delete_sub_folders=False)
            else:
                self.empty(delete_sub_folders=True)
        except (ErrorAccessDenied, ErrorCannotEmptyFolder):
            try:
                if has_distinguished_subfolders:
                    raise  # We already tried this
                self.empty(delete_sub_folders=False)
            except (ErrorAccessDenied, ErrorCannotEmptyFolder):
                log.warning('Not allowed to empty %s. Trying to delete items instead', self)
                try:
                    self.all().delete(**delete_kwargs)
                except (ErrorAccessDenied, ErrorCannotDeleteObject):
                    log.warning('Not allowed to delete items in %s', self)
        for f in self.children:
            f.wipe(page_size=page_size)
            # Remove non-distinguished children that are empty and have no subfolders
            if f.is_deleteable and not f.children:
                log.warning('Deleting folder %s', f)
                try:
                    f.delete()
                except ErrorDeleteDistinguishedFolder:
                    log.warning('Tried to delete a distinguished folder (%s)', f)

    def sync(self, max_changes):
        # Only use sync if sync_state is fully updated. First sync's with EWS will return (id, changekey) tuples
        # for ALL items until the cursor hits the end of the state. Subsequent calls will return only specific changes.
        # If you want to use sync, please ensure you re-use the sync_state properly (and persist it)
        for change in SyncFolderItems(account=self.account, folders=[self]).call(self.sync_state, None, max_changes):
            if isinstance(change, Exception):
                yield change
            else:
                item = self.item_model_from_tag(change.tag).from_xml(elem=change, account=self.account)
                yield item

    def changes(self, max_changes=512):
        # More user friendly method. No need to worry about sync_states. Will return changes as they happen.

        if not self.sync_state:
            return []

        changes = []
        while True:
            res = list(self.sync(max_changes))
            if len(res) < max_changes:
                break
            changes.extend(res)
        return changes

    def subscribe(self):
        # Subscribe for streaming notifications
        # Usage:
        # 1. Get subscription id for folder by calling subscribe
        # 2. Call events which will block until changes on the folder happen or timeout is hit
        # 3. Process changes and call unsubcribe with subscriptionId to end the subscription
        for subscription_id in SubscribeStreamingFolder(account=self.account, folders=[self]).call(events=EVENT_TYPES):
            yield subscription_id

    def unsubscribe(self, subscription_id):
        # Unsubscribe from streaming notifications
        if not subscription_id:
            raise ValueError('Cannot unsubscribe without a subscription id')
        ret = UnsubscribeStreamingFolder(account=self.account).call(subscription_id)
        if isinstance(ret, Exception):
            raise ret

    @contextmanager
    def stream_events(self):
        # Get streaming events - this will block until it hits timeout or enough data is accumulated
        # TODO: Add stream=True for GetStreamingEvents and figure out how to accumulate data on the socket
        subscription_ids = self.subscribe()
        for event in GetStreamingEvents(account=self.account).call(subscription_ids):
            yield event
        for subscription_id in subscription_ids:
            self.unsubscribe(subscription_id)

    def events(self, subscription_ids):
        # Get streaming events - this will block until it hits timeout or enough data is accumulated
        # TODO: Add stream=True for GetStreamingEvents and figure out how to accumulate data on the socket
        subscription_ids = self.subscribe()
        for event in GetStreamingEvents(account=self.account).call(subscription_ids):
            if isinstance(event, Exception):
                yield event
            else:
                yield event
        for subscription_id in subscription_ids:
            self.unsubscribe(subscription_id)

    def push(self, callback_url):
        # Subscribe for push notifications from EWS to your server. Server must handle unsubcribe / re-use / validation
        for subscription_id in SubscribePushFolder(account=self.account, folders=[self]).call(
                events=EVENT_TYPES, callback_url=callback_url):
            yield subscription_id

    def test_access(self):
        """
        Does a simple FindItem to test (read) access to the folder. Maybe the account doesn't exist, maybe the
        service user doesn't have access to the calendar. This will throw the most common errors.
        """
        self.all().exists()
        return True

    @classmethod
    def _kwargs_from_elem(cls, elem, account):
        folder_id, changekey = cls.id_from_xml(elem)
        kwargs = dict(id=folder_id, changekey=changekey)
        # Check for 'DisplayName' element before collecting kwargs because because that clears the elements
        has_name_elem = elem.find(cls.get_field_by_fieldname('name').response_tag()) is not None
        kwargs.update({
            f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS if f.name not in ('id', 'changekey')
        })
        if has_name_elem and not kwargs['name']:
            # When we request the 'DisplayName' property, some folders may still be returned with an empty value.
            # Assign a default name to these folders.
            kwargs['name'] = cls.DISTINGUISHED_FOLDER_ID
        return kwargs

    def to_xml(self, version):
        if self.is_distinguished:
            # Don't add the changekey here. When modifying folder content, we usually don't care if others have changed
            # the folder content since we fetched the changekey.
            if self.account:
                return DistinguishedFolderId(
                    id=self.DISTINGUISHED_FOLDER_ID,
                    mailbox=Mailbox(email_address=self.account.primary_smtp_address)
                ).to_xml(version=version)
            return DistinguishedFolderId(id=self.DISTINGUISHED_FOLDER_ID).to_xml(version=version)
        if self.id:
            return FolderId(id=self.id, changekey=self.changekey).to_xml(version=version)
        return super().to_xml(version=version)

    @classmethod
    def resolve(cls, account, folder):
        # Resolve a single folder
        folders = list(FolderCollection(account=account, folders=[folder]).resolve())
        if not folders:
            raise ErrorFolderNotFound('Could not find folder %r' % folder)
        if len(folders) != 1:
            raise ValueError('Expected result length 1, but got %s' % folders)
        f = folders[0]
        if isinstance(f, Exception):
            raise f
        if f.__class__ != cls:
            raise ValueError("Expected folder %r to be a %s instance" % (f, cls))
        return f

    def refresh(self):
        if not self.account:
            raise ValueError('%s must have an account' % self.__class__.__name__)
        if not self.id:
            raise ValueError('%s must have an ID' % self.__class__.__name__)
        fresh_folder = self.resolve(account=self.account, folder=self)
        if self.id != fresh_folder.id:
            raise ValueError('ID mismatch')
        # Apparently, the changekey may get updated
        for f in self.FIELDS:
            setattr(self, f.name, getattr(fresh_folder, f.name))

    def __floordiv__(self, other):
        """Same as __truediv__ but does not touch the folder cache.

        This is useful if the folder hierarchy contains a huge number of folders and you don't want to fetch them all"""
        if other == '..':
            raise ValueError('Cannot get parent without a folder cache')

        if other == '.':
            return self

        # Assume an exact match on the folder name in a shallow search will only return at most one folder
        try:
            return SingleFolderQuerySet(account=self.account, folder=self).depth(SHALLOW_FOLDERS).get(name=other)
        except DoesNotExist:
            raise ErrorFolderNotFound("No subfolder with name '%s'" % other)

    def __truediv__(self, other):
        # Support the some_folder / 'child_folder' / 'child_of_child_folder' navigation syntax
        if other == '..':
            if not self.parent:
                raise ValueError('Already at top')
            return self.parent
        if other == '.':
            return self
        for c in self.children:
            if c.name == other:
                return c
        raise ErrorFolderNotFound("No subfolder with name '%s'" % other)

    def __repr__(self):
        return self.__class__.__name__ + \
               repr((self.root, self.name, self.total_count, self.unread_count, self.child_folder_count,
                     self.folder_class, self.id, self.changekey))

    def __str__(self):
        return '%s (%s)' % (self.__class__.__name__, self.name)


class Folder(BaseFolder):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/folder"""
    LOCAL_FIELDS = [
        PermissionSetField('permission_set', field_uri='folder:PermissionSet', supported_from=EXCHANGE_2007_SP1),
        EffectiveRightsField('effective_rights', field_uri='folder:EffectiveRights', is_read_only=True,
                             supported_from=EXCHANGE_2007_SP1),
    ]
    FIELDS = BaseFolder.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS) + ('_root',)

    def __init__(self, **kwargs):
        self._root = kwargs.pop('root', None)  # This is a pointer to the root of the folder hierarchy
        parent = kwargs.pop('parent', None)
        if parent:
            if self.root:
                if parent.root != self.root:
                    raise ValueError("'parent.root' must match 'root'")
            else:
                self.root = parent.root
            if 'parent_folder_id' in kwargs:
                if parent.id != kwargs['parent_folder_id']:
                    raise ValueError("'parent_folder_id' must match 'parent' ID")
            kwargs['parent_folder_id'] = ParentFolderId(id=parent.id, changekey=parent.changekey)
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
            raise TypeError('For folders, custom fields must be registered on the Folder class')
        return super().register(*args, **kwargs)

    @classmethod
    def deregister(cls, *args, **kwargs):
        if cls is not Folder:
            raise TypeError('For folders, custom fields must be registered on the Folder class')
        return super().deregister(*args, **kwargs)

    @classmethod
    def get_distinguished(cls, root):
        """Gets the distinguished folder for this folder class"""
        try:
            return cls.resolve(
                account=root.account,
                folder=cls(root=root, name=cls.DISTINGUISHED_FOLDER_ID, is_distinguished=True)
            )
        except ErrorFolderNotFound:
            raise ErrorFolderNotFound('Could not find distinguished folder %r' % cls.DISTINGUISHED_FOLDER_ID)

    @property
    def parent(self):
        if not self.parent_folder_id:
            return None
        if self.parent_folder_id.id == self.id:
            # Some folders have a parent that references itself. Avoid circular references here
            return None
        return self.root.get_folder(self.parent_folder_id.id)

    @parent.setter
    def parent(self, value):
        if value is None:
            self.parent_folder_id = None
        else:
            if not isinstance(value, BaseFolder):
                raise ValueError("'value' %r must be a Folder instance" % value)
            self.root = value.root
            self.parent_folder_id = ParentFolderId(id=value.id, changekey=value.changekey)

    def clean(self, version=None):
        # pylint: disable=access-member-before-definition
        from .roots import RootOfHierarchy
        super().clean(version=version)
        if self.root and not isinstance(self.root, RootOfHierarchy):
            raise ValueError("'root' %r must be a RootOfHierarchy instance" % self.root)

    @classmethod
    def from_xml(cls, elem, account):
        raise NotImplementedError('Use from_xml_with_root() instead')

    @classmethod
    def from_xml_with_root(cls, elem, root):
        kwargs = cls._kwargs_from_elem(elem=elem, account=root.account)
        cls._clear(elem)
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
            if kwargs['name']:
                try:
                    # TODO: fld_class.LOCALIZED_NAMES is most definitely neither complete nor authoritative
                    folder_cls = root.folder_cls_from_folder_name(folder_name=kwargs['name'],
                                                                  locale=root.account.locale)
                    log.debug('Folder class %s matches localized folder name %s', folder_cls, kwargs['name'])
                except KeyError:
                    pass
            if kwargs['folder_class'] and folder_cls == Folder:
                try:
                    folder_cls = cls.folder_cls_from_container_class(container_class=kwargs['folder_class'])
                    log.debug('Folder class %s matches container class %s (%s)', folder_cls, kwargs['folder_class'],
                              kwargs['name'])
                except KeyError:
                    pass
            if folder_cls == Folder:
                log.debug('Fallback to class Folder (folder_class %s, name %s)', kwargs['folder_class'], kwargs['name'])
        return folder_cls(root=root, **kwargs)
