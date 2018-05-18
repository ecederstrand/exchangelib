# coding=utf-8
from __future__ import unicode_literals

from fnmatch import fnmatch
import logging
from operator import attrgetter

from cached_property import threaded_cached_property
from future.utils import python_2_unicode_compatible
from six import text_type, string_types

from .errors import ErrorAccessDenied, ErrorFolderNotFound, ErrorCannotEmptyFolder, ErrorCannotDeleteObject, \
    ErrorNoPublicFolderReplicaAvailable, ErrorInvalidOperation, ErrorDeleteDistinguishedFolder, ErrorItemNotFound
from .fields import IntegerField, TextField, DateTimeField, FieldPath, EffectiveRightsField, MailboxField, IdField, \
    EWSElementField
from .items import Item, CalendarItem, Contact, Message, Task, MeetingRequest, MeetingResponse, MeetingCancellation, \
    DistributionList, RegisterMixIn, ITEM_CLASSES, ITEM_TRAVERSAL_CHOICES, SHAPE_CHOICES, IdOnly, DELETE_TYPE_CHOICES, \
    HARD_DELETE, Persona
from .properties import ItemId, Mailbox, EWSElement, ParentFolderId
from .queryset import QuerySet, SearchableMixIn
from .restriction import Restriction
from .services import FindFolder, GetFolder, FindItem, CreateFolder, UpdateFolder, DeleteFolder, EmptyFolder, FindPeople
from .transport import TNS, MNS
from .version import EXCHANGE_2007_SP1, EXCHANGE_2010_SP1, EXCHANGE_2013, EXCHANGE_2013_SP1
from .utils import redact_email

string_type = string_types[0]
log = logging.getLogger(__name__)

# Traversal enums
SHALLOW = 'Shallow'
SOFT_DELETED = 'SoftDeleted'
DEEP = 'Deep'
FOLDER_TRAVERSAL_CHOICES = (SHALLOW, DEEP, SOFT_DELETED)


class FolderId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa579461(v=exchg.150).aspx
    ELEMENT_NAME = 'FolderId'

    __slots__ = ItemId.__slots__


class DistinguishedFolderId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580808(v=exchg.150).aspx
    ELEMENT_NAME = 'DistinguishedFolderId'

    FIELDS = [
        IdField('id', field_uri=ItemId.ID_ATTR, is_required=True),
        IdField('changekey', field_uri=ItemId.CHANGEKEY_ATTR),
        MailboxField('mailbox'),
    ]

    __slots__ = ItemId.__slots__ + ('mailbox',)

    def clean(self, version=None):
        super(DistinguishedFolderId, self).clean(version=version)
        if self.id == PublicFoldersRoot.DISTINGUISHED_FOLDER_ID:
            # Avoid "ErrorInvalidOperation: It is not valid to specify a mailbox with the public folder root" from EWS
            self.mailbox = None


class CalendarView(EWSElement):
    """
    MSDN: https://msdn.microsoft.com/en-US/library/office/aa564515%28v=exchg.150%29.aspx
    """
    ELEMENT_NAME = 'CalendarView'
    NAMESPACE = MNS

    FIELDS = [
        DateTimeField('start', field_uri='StartDate', is_required=True, is_attribute=True),
        DateTimeField('end', field_uri='EndDate', is_required=True, is_attribute=True),
        IntegerField('max_items', field_uri='MaxEntriesReturned', min=1, is_attribute=True),
    ]

    __slots__ = ('start', 'end', 'max_items')

    def clean(self, version=None):
        super(CalendarView, self).clean(version=version)
        if self.end < self.start:
            raise ValueError("'start' must be before 'end'")


class FolderCollection(SearchableMixIn):
    def __init__(self, account, folders):
        """ Implements a search API on a collection of folders

        :param account: An Account object
        :param folders: An iterable of folders, e.g. Folder.walk(), Folder.glob(), or [a.calendar, a.inbox]
        """
        self.account = account
        self._folders = folders

    @threaded_cached_property
    def folders(self):
        # Resolve the list of folders, in case it's a generator
        return list(self._folders)

    def __len__(self):
        return len(self.folders)

    def __iter__(self):
        for f in self.folders:
            yield f

    def get(self, *args, **kwargs):
        return QuerySet(self).get(*args, **kwargs)

    def all(self):
        return QuerySet(self).all()

    def none(self):
        return QuerySet(self).none()

    def filter(self, *args, **kwargs):
        """
        Finds items in the folder(s).

        Non-keyword args may be a list of Q instances.

        Optional extra keyword arguments follow a Django-like QuerySet filter syntax (see
           https://docs.djangoproject.com/en/1.10/ref/models/querysets/#field-lookups).

        We don't support '__year' and other date-related lookups. We also don't support '__endswith' or '__iendswith'.

        We support the additional '__not' lookup in place of Django's exclude() for simple cases. For more complicated
        cases you need to create a Q object and use ~Q().

        Examples:

            my_account.inbox.filter(datetime_received__gt=EWSDateTime(2016, 1, 1))
            my_account.calendar.filter(start__range=(EWSDateTime(2016, 1, 1), EWSDateTime(2017, 1, 1)))
            my_account.tasks.filter(subject='Hi mom')
            my_account.tasks.filter(subject__not='Hi mom')
            my_account.tasks.filter(subject__contains='Foo')
            my_account.tasks.filter(subject__icontains='foo')

        'endswith' and 'iendswith' could be emulated by searching with 'contains' or 'icontains' and then
        post-processing items. Fetch the field in question with additional_fields and remove items where the search
        string is not a postfix.
        """
        return QuerySet(self).filter(*args, **kwargs)

    def exclude(self, *args, **kwargs):
        return QuerySet(self).exclude(*args, **kwargs)

    def view(self, start, end, max_items=None, *args, **kwargs):
        """ Implements the CalendarView option to FindItem. The difference between filter() and view() is that filter()
        only returns the master CalendarItem for recurring items, while view() unfolds recurring items and returns all
        CalendarItem occurrences as one would normally expect when presenting a calendar.

        Supports the same semantics as filter, except for 'start' and 'end' keyword attributes which are both required
        and behave differently than filter. Here, they denote the start and end of the timespan of the view. All items
        the overlap the timespan are returned (items that end exactly on 'start' are also returned, for some reason).

        EWS does not allow combining CalendarView with search restrictions (filter and exclude).

        'max_items' defines the maximum number of items returned in this view. Optional.
        """
        qs = QuerySet(self).filter(*args, **kwargs)
        qs.calendar_view = CalendarView(start=start, end=end, max_items=max_items)
        return qs

    def allowed_fields(self):
        # Return non-ID fields of all item classes allowed in this folder type
        fields = set()
        for item_model in self.supported_item_models:
            fields.update(set(item_model.supported_fields(version=self.account.version if self.account else None)))
        return fields

    def complex_fields(self):
        return {f for f in self.allowed_fields() if f.is_complex}

    @property
    def supported_item_models(self):
        return tuple(item_model for folder in self.folders for item_model in folder.supported_item_models)

    def find_items(self, q, shape=IdOnly, depth=SHALLOW, additional_fields=None, order_fields=None,
                   calendar_view=None, page_size=None, max_items=None):
        """
        Private method to call the FindItem service

        :param q: a Q instance containing any restrictions
        :param shape: controls whether to return (item_id, chanegkey) tuples or Item objects. If additional_fields is
               non-null, we always return Item objects.
        :param depth: controls the whether to return soft-deleted items or not.
        :param additional_fields: the extra properties we want on the return objects. Default is no properties. Be
               aware that complex fields can only be fetched with fetch() (i.e. the GetItem service).
        :param order_fields: the SortOrder fields, if any
        :param calendar_view: a CalendarView instance, if any
        :param page_size: the requested number of items per page
        :param max_items: the max number of items to return
        :return: a generator for the returned item IDs or items
        """
        if shape not in SHAPE_CHOICES:
            raise ValueError("'shape' %s must be one of %s" % (shape, SHAPE_CHOICES))
        if depth not in ITEM_TRAVERSAL_CHOICES:
            raise ValueError("'depth' %s must be one of %s" % (depth, ITEM_TRAVERSAL_CHOICES))
        if additional_fields:
            allowed_fields = self.allowed_fields()
            complex_fields = self.complex_fields()
            for f in additional_fields:
                if f.field not in allowed_fields:
                    raise ValueError("'%s' is not a valid field on %s" % (f.field.name, self.supported_item_models))
                if f.field in complex_fields:
                    raise ValueError("find_items() does not support field '%s'. Use fetch() instead" % f.field.name)
        if calendar_view is not None and not isinstance(calendar_view, CalendarView):
            raise ValueError("'calendar_view' %s must be a CalendarView instance" % calendar_view)

        # Build up any restrictions
        if q.is_empty():
            restriction = None
            query_string = None
        elif q.query_string:
            restriction = None
            query_string = Restriction(q, folders=self.folders)
        else:
            restriction = Restriction(q, folders=self.folders)
            query_string = None
        log.debug(
            'Finding %s items un folders %s (shape: %s, depth: %s, additional_fields: %s, restriction: %s)',
            self.folders,
            self.account,
            shape,
            depth,
            additional_fields,
            restriction.q if restriction else None,
        )
        items = FindItem(account=self.account, folders=self.folders, chunk_size=page_size).call(
            additional_fields=additional_fields,
            restriction=restriction,
            order_fields=order_fields,
            shape=shape,
            query_string=query_string,
            depth=depth,
            calendar_view=calendar_view,
            max_items=calendar_view.max_items if calendar_view else max_items,
        )
        if shape == IdOnly and additional_fields is None:
            for i in items:
                yield i if isinstance(i, Exception) else Item.id_from_xml(i)
        else:
            for i in items:
                if isinstance(i, Exception):
                    yield i
                else:
                    item = Folder.item_model_from_tag(i.tag).from_xml(elem=i, account=self.account)
                    yield item

    def _get_folder_fields(self):
        additional_fields = set()
        for folder in self.folders:
            if isinstance(folder, Folder):
                additional_fields.update(
                    FieldPath(field=f) for f in folder.supported_fields(version=self.account.version)
                )
            else:
                additional_fields.update(
                    FieldPath(field=f) for f in Folder.supported_fields(version=self.account.version)
                )
        return additional_fields

    def find_folders(self, shape=IdOnly, depth=DEEP, page_size=None):
        # 'depth' controls whether to return direct children or recurse into sub-folders
        if not self.account:
            raise ValueError('Folder must have an account')
        if shape not in SHAPE_CHOICES:
            raise ValueError("'shape' %s must be one of %s" % (shape, SHAPE_CHOICES))
        if depth not in FOLDER_TRAVERSAL_CHOICES:
            raise ValueError("'depth' %s must be one of %s" % (depth, FOLDER_TRAVERSAL_CHOICES))
        additional_fields = self._get_folder_fields()
        # TODO: Support the Restriction class for folders, too
        return FindFolder(account=self.account, folders=self.folders, chunk_size=page_size).call(
                additional_fields=additional_fields,
                shape=shape,
                depth=depth,
                max_items=None,
        )

    def get_folders(self):
        additional_fields = self._get_folder_fields()
        return GetFolder(account=self.account).call(
                folders=self.folders,
                additional_fields=additional_fields,
                shape=IdOnly
        )


@python_2_unicode_compatible
class Folder(RegisterMixIn, SearchableMixIn):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa581334(v=exchg.150).aspx
    """
    ELEMENT_NAME = 'Folder'
    NAMESPACE = TNS
    DISTINGUISHED_FOLDER_ID = None  # See https://msdn.microsoft.com/en-us/library/office/aa580808(v=exchg.150).aspx
    # Default item type for this folder. See http://msdn.microsoft.com/en-us/library/hh354773(v=exchg.80).aspx
    CONTAINER_CLASS = None
    supported_item_models = ITEM_CLASSES  # The Item types that this folder can contain. Default is all
    # Marks the version from which a distinguished folder was introduced. A possibly authoritative source is:
    # https://github.com/OfficeDev/ews-managed-api/blob/master/Enumerations/WellKnownFolderName.cs
    supported_from = None
    LOCALIZED_NAMES = dict()  # A map of (str)locale: (tuple)localized_folder_names
    ITEM_MODEL_MAP = {cls.response_tag(): cls for cls in ITEM_CLASSES}
    FIELDS = [
        IdField('folder_id', field_uri=FolderId.ID_ATTR),
        IdField('changekey', field_uri=FolderId.CHANGEKEY_ATTR),
        EWSElementField('parent_folder_id', field_uri='folder:ParentFolderId', value_cls=ParentFolderId,
                        is_read_only=True),
        TextField('folder_class', field_uri='folder:FolderClass', is_required_after_save=True),
        TextField('name', field_uri='folder:DisplayName'),
        IntegerField('total_count', field_uri='folder:TotalCount', is_read_only=True),
        IntegerField('child_folder_count', field_uri='folder:ChildFolderCount', is_read_only=True),
        IntegerField('unread_count', field_uri='folder:UnreadCount', is_read_only=True),
        EffectiveRightsField('effective_rights', field_uri='folder:EffectiveRights', is_read_only=True),
    ]

    # Used to register extended properties
    INSERT_AFTER_FIELD = 'child_folder_count'

    def __init__(self, **kwargs):
        self.account = kwargs.pop('account', None)
        self.is_distinguished = kwargs.pop('is_distinguished', False)
        parent = kwargs.pop('parent', None)
        if parent:
            if self.account:
                if parent.account != self.account:
                    raise ValueError("'parent.account' must match 'account'")
            else:
                self.account = parent.account
            if 'parent_folder_id' in kwargs:
                if parent.id != kwargs['parent_folder_id']:
                    raise ValueError("'parent_folder_id' must match 'parent' ID")
            kwargs['parent_folder_id'] = ParentFolderId(id=parent.folder_id, changekey=parent.changekey)
        super(Folder, self).__init__(**kwargs)

    @property
    def is_deleteable(self):
        return not self.is_distinguished

    def clean(self, version=None):
        super(Folder, self).clean(version=version)
        if self.account is not None:
            from .account import Account
            if not isinstance(self.account, Account):
                raise ValueError("'account' %r must be an Account instance" % self.account)

    @property
    def parent(self):
        if not self.parent_folder_id:
            return None
        if self.parent_folder_id.id == self.folder_id:
            # Some folders have a parent that references itself. Avoid circular references here
            return None
        return self.account.root.get_folder(self.parent_folder_id.id)

    @parent.setter
    def parent(self, value):
        if value is None:
            self.parent_folder_id = None
        else:
            if not isinstance(value, Folder):
                raise ValueError("'value' %r must be a Folder instance" % value)
            self.parent_folder_id = ParentFolderId(id=value.folder_id, changekey=value.changekey)
            self.account = value.account

    @property
    def children(self):
        # It's dangerous to return a generator here because we may then call methods on a child that result in the
        # cache being updated while it's iterated.
        return FolderCollection(account=self.account, folders=self.account.root.get_children(self))

    @property
    def parts(self):
        parts = [self]
        f = self.parent
        while f:
            parts.insert(0, f)
            f = f.parent
        return parts

    @property
    def root(self):
        return self.parts[0]

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
        if not cls.supported_from or not version:
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
        for folder_cls in (
                Messages, Tasks, Calendar, ConversationSettings, Contacts, GALContacts, Reminders, RecipientCache,
                RSSFeeds):
            if folder_cls.CONTAINER_CLASS == container_class:
                return folder_cls
        raise KeyError()

    @staticmethod
    def folder_cls_from_folder_name(folder_name, locale):
        """Returns the folder class that matches a localized folder name.

        locale is a string, e.g. 'da_DK'
        """
        for folder_cls in WELLKNOWN_FOLDERS + NON_DELETEABLE_FOLDERS:
            if folder_name.lower() in folder_cls.localized_names(locale):
                return folder_cls
        raise KeyError()

    @classmethod
    def item_model_from_tag(cls, tag):
        try:
            return cls.ITEM_MODEL_MAP[tag]
        except KeyError:
            raise ValueError('Item type %s was unexpected in a %s folder' % (cls.__name__, cls.__name__))

    def allowed_fields(self):
        # Return non-ID fields of all item classes allowed in this folder type
        fields = set()
        for item_model in self.supported_item_models:
            fields.update(set(item_model.supported_fields(version=self.account.version if self.account else None)))
        return fields

    def complex_fields(self):
        return {f for f in self.allowed_fields() if f.is_complex}

    def validate_fields(self, fields):
        # Takes a list of fieldnames or FieldPath objects meant for fetching, and checks that they are valid for this
        # folder. Turns them into FieldPath objects and adds internal timezone fields if necessary.
        from .version import EXCHANGE_2010
        allowed_fields = self.allowed_fields()
        fields = list(fields)
        has_start, has_end = False, False
        for i, field_path in enumerate(fields):
            # Allow both FieldPath instances and string field paths as input
            if isinstance(field_path, string_types):
                field_path = FieldPath.from_string(field_path, folder=self)
                fields[i] = field_path
            if not isinstance(field_path, FieldPath):
                raise ValueError("Field %r must be a string or FieldPath object" % field_path)
            if field_path.field not in allowed_fields:
                raise ValueError("%r is not a valid field on %s" % (field_path.field, self.supported_item_models))
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
            except ValueError:
                pass
        raise ValueError("Unknown fieldname '%s' on class '%s'" % (fieldname, cls.__name__))

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

    def find_people(self, q, shape=IdOnly, depth=SHALLOW, additional_fields=None, order_fields=None, page_size=None,
                    max_items=None):
        """
        Private method to call the FindPeople service

        :param q: a Q instance containing any restrictions
        :param shape: controls whether to return (item_id, chanegkey) tuples or Persona objects. If additional_fields is
               non-null, we always return Persona objects.
        :param depth: controls the whether to return soft-deleted items or not.
        :param additional_fields: the extra properties we want on the return objects. Default is no properties.
        :param order_fields: the SortOrder fields, if any
        :param page_size: the requested number of items per page
        :param max_items: the max number of items to return
        :return: a generator for the returned personas
        """
        if shape not in SHAPE_CHOICES:
            raise ValueError("'shape' %s must be one of %s" % (shape, SHAPE_CHOICES))
        if depth not in ITEM_TRAVERSAL_CHOICES:
            raise ValueError("'depth' %s must be one of %s" % (depth, ITEM_TRAVERSAL_CHOICES))
        if additional_fields:
            allowed_fields = Persona.supported_fields(version=self.account.version)
            complex_fields = {f for f in allowed_fields if f.is_complex}
            for f in additional_fields:
                if f.field not in allowed_fields:
                    raise ValueError("'%s' is not a valid field on %s" % (f.field.name, Persona))
                if f.field in complex_fields:
                    raise ValueError("find_people() does not support field '%s'" % f.field.name)

        # Build up any restrictions
        if q.is_empty():
            restriction = None
            query_string = None
        elif q.query_string:
            restriction = None
            query_string = Restriction(q, folders=[self])
        else:
            restriction = Restriction(q, folders=[self])
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
        )
        for p in personas:
            if isinstance(p, Exception):
                raise p
            yield p

    def bulk_create(self, items, *args, **kwargs):
        return self.account.bulk_create(folder=self, items=items, *args, **kwargs)

    def save(self, update_fields=None):
        if self.folder_id is None:
            # New folder
            if update_fields:
                raise ValueError("'update_fields' is only valid for updates")
            res = list(CreateFolder(account=self.account).call(parent_folder=self.parent, folders=[self]))
            if len(res) != 1:
                raise ValueError('Expected result length 1, but got %s' % res)
            if isinstance(res[0], Exception):
                raise res[0]
            self.folder_id, self.changekey = res[0].folder_id, res[0].changekey
            self.account.root.add_folder(self)  # Add this folder to the cache
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
        folder_id, changekey = res[0].folder_id, res[0].changekey
        if self.folder_id != folder_id:
            raise ValueError('folder_id mismatch')
        # Don't check changekey value. It may not change on no-op updates
        self.changekey = changekey
        self.account.root.update_folder(self)  # Update the folder in the cache
        return None

    def delete(self, delete_type=HARD_DELETE):
        if delete_type not in DELETE_TYPE_CHOICES:
            raise ValueError("'delete_type' %s must be one of %s" % (delete_type, DELETE_TYPE_CHOICES))
        res = list(DeleteFolder(account=self.account).call(folders=[self], delete_type=delete_type))
        if len(res) != 1:
            raise ValueError('Expected result length 1, but got %s' % res)
        if isinstance(res[0], Exception):
            raise res[0]
        self.account.root.remove_folder(self)  # Remove the updated folder from the cache
        self.folder_id, self.changekey = None, None

    def empty(self, delete_type=HARD_DELETE, delete_sub_folders=False):
        if delete_type not in DELETE_TYPE_CHOICES:
            raise ValueError("'delete_type' %s must be one of %s" % (delete_type, DELETE_TYPE_CHOICES))
        res = list(EmptyFolder(account=self.account).call(folders=[self], delete_type=delete_type,
                                                          delete_sub_folders=delete_sub_folders))
        if len(res) != 1:
            raise ValueError('Expected result length 1, but got %s' % res)
        if isinstance(res[0], Exception):
            raise res[0]
        if delete_sub_folders:
            # We don't know exactly what was deleted, so invalidate the entire folder cache to be safe
            self.account.root.clear_cache()

    def wipe(self):
        # Recursively deletes all items in this folder, and all subfolders and their content. Attempts to protect
        # distinguished folders from being deleted. Use with caution!
        log.warning('Wiping %s', self)
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
                    self.all().delete()
                except (ErrorAccessDenied, ErrorCannotDeleteObject):
                    log.warning('Not allowed to delete items in %s', self)
        for f in self.children:
            f.wipe()
            # Remove non-distinguished children that are empty and have no subfolders
            if f.is_deleteable and not f.children:
                log.warning('Deleting folder %s', f)
                try:
                    f.delete()
                except ErrorDeleteDistinguishedFolder:
                    log.warning('Tried to delete a distinguished folder (%s)', f)

    def test_access(self):
        """
        Does a simple FindItem to test (read) access to the folder. Maybe the account doesn't exist, maybe the
        service user doesn't have access to the calendar. This will throw the most common errors.
        """
        list(self.filter(subject='DUMMY').values_list('subject'))
        return True

    @classmethod
    def from_xml(cls, elem, account):
        # fld_type = re.sub('{.*}', '', elem.tag)
        fld_id_elem = elem.find(FolderId.response_tag())
        fld_id = fld_id_elem.get(FolderId.ID_ATTR)
        changekey = fld_id_elem.get(FolderId.CHANGEKEY_ATTR)
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.supported_fields()}
        if not kwargs['name']:
            # Some folders are returned with an empty 'DisplayName' element. Assign a default name to them.
            # TODO: Only do this if we actually requested the 'name' field.
            kwargs['name'] = cls.DISTINGUISHED_FOLDER_ID
        elem.clear()
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
            #     https://technet.microsoft.com/da-dk/library/dd351103(v=exchg.160).aspx
            #
            # Instead, search for a folder class using the localized name. If none are found, fall back to getting the
            # folder class by the "FolderClass" value.
            #
            # The returned XML may contain neither folder class nor name. In that case, we default
            if kwargs['name']:
                try:
                    # TODO: fld_class.LOCALIZED_NAMES is most definitely neither complete nor authoritative
                    folder_cls = cls.folder_cls_from_folder_name(folder_name=kwargs['name'], locale=account.locale)
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
                redacted_name = redact_email(kwargs['name'])
                log.debug('Fallback to class Folder (folder_class %s, name %s)', kwargs['folder_class'], redacted_name)
        return folder_cls(account=account, folder_id=fld_id, changekey=changekey, **kwargs)

    def to_xml(self, version):
        if self.is_distinguished or (not self.folder_id and self.has_distinguished_name):
            # Don't add the changekey here. When modifying folder content, we usually don't care if others have changed
            # the folder content since we fetched the changekey.
            if self.account:
                return DistinguishedFolderId(
                    id=self.DISTINGUISHED_FOLDER_ID,
                    mailbox=Mailbox(email_address=self.account.primary_smtp_address)
                ).to_xml(version=version)
            return DistinguishedFolderId(id=self.DISTINGUISHED_FOLDER_ID).to_xml(version=version)
        if self.folder_id:
            return FolderId(id=self.folder_id, changekey=self.changekey).to_xml(version=version)
        return super(Folder, self).to_xml(version=version)

    @classmethod
    def supported_fields(cls, version=None):
        return tuple(f for f in cls.FIELDS if f.name not in ('folder_id', 'changekey') and f.supports_version(version))

    @classmethod
    def get_distinguished(cls, account):
        """Gets the distinguished folder for this folder class"""
        if not cls.DISTINGUISHED_FOLDER_ID:
            raise ValueError('Class %s must have a DISTINGUISHED_FOLDER_ID value' % cls)
        folders = list(FolderCollection(
            account=account, folders=[cls(account=account, name=cls.DISTINGUISHED_FOLDER_ID)]).get_folders()
        )
        if not folders:
            raise ErrorFolderNotFound('Could not find distinguished folder %s' % cls.DISTINGUISHED_FOLDER_ID)
        if len(folders) != 1:
            raise ValueError('Expected result length 1, but got %s' % folders)
        folder = folders[0]
        if isinstance(folder, Exception):
            raise folder
        if not isinstance(folder, cls):
            raise ValueError("'folder' %r must be a %s instance" % (folder, cls))
        return folder

    def refresh(self):
        if not self.account:
            raise ValueError('Folder must have an account')
        if not self.folder_id:
            raise ValueError('Folder must have an ID')
        folders = list(FolderCollection(account=self.account, folders=[self]).get_folders())
        if not folders:
            raise ErrorFolderNotFound('Folder %s disappeared' % self)
        if len(folders) != 1:
            raise ValueError('Expected result length 1, but got %s' % folders)
        fresh_folder = folders[0]
        if isinstance(fresh_folder, Exception):
            raise fresh_folder
        if self.folder_id != fresh_folder.folder_id:
            raise ValueError('folder_id mismatch')
        # Apparently, the changekey may get updated
        for f in self.FIELDS:
            setattr(self, f.name, getattr(fresh_folder, f.name))

    def __truediv__(self, other):
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

    # Python 2 requires __div__
    __div__ = __truediv__

    def __repr__(self):
        return self.__class__.__name__ + \
               repr((self.account, self.name, self.total_count, self.unread_count, self.child_folder_count,
                     self.folder_class, self.folder_id, self.changekey))

    def __str__(self):
        return '%s (%s)' % (self.__class__.__name__, self.name)


class Root(Folder):
    DISTINGUISHED_FOLDER_ID = 'root'

    def __init__(self, **kwargs):
        super(Root, self).__init__(**kwargs)
        self._subfolders = None  # See self._folders_map()

    def refresh(self):
        self._subfolders = None
        super(Root, self).refresh()

    @property
    def tois(self):
        # 'Top of Information Store' is a folder available in some Exchange accounts. It usually contains the
        # distinguished folders belonging to the account (inbox, calendar, trash etc.).
        return self / 'Top of Information Store'

    def get_folder(self, folder_id):
        return self._folders_map.get(folder_id, None)

    def add_folder(self, folder):
        if not folder.folder_id:
            raise ValueError("'folder' must have a folder_id")
        self._folders_map[folder.folder_id] = folder

    def update_folder(self, folder):
        if not folder.folder_id:
            raise ValueError("'folder' must have a folder_id")
        self._folders_map[folder.folder_id] = folder

    def remove_folder(self, folder):
        if not folder.folder_id:
            raise ValueError("'folder' must have a folder_id")
        try:
            del self._folders_map[folder.folder_id]
        except KeyError:
            pass

    def clear_cache(self):
        self._subfolders = None

    def get_children(self, folder):
        for f in self._folders_map.values():
            if not f.parent:
                continue
            if f.parent.folder_id == folder.folder_id:
                yield f

    @property
    def _folders_map(self):
        if self._subfolders is not None:
            return self._subfolders

        # Map root, and all subfolders of root, at arbitrary depth by folder ID. First get distinguished folders, then
        # everything else. AdminAuditLogs folder is not retrievable and makes the entire request fail.
        folders_map = {self.folder_id: self}
        distinguished_folders = [
            cls(account=self.account, name=cls.DISTINGUISHED_FOLDER_ID) for cls in WELLKNOWN_FOLDERS
            if cls != AdminAuditLogs and cls.supports_version(self.account.version)
        ]
        try:
            for f in FolderCollection(account=self.account, folders=distinguished_folders).get_folders():
                if isinstance(f, (ErrorFolderNotFound, ErrorNoPublicFolderReplicaAvailable)):
                    # This is just a distinguished folder the server does not have
                    continue
                if isinstance(f, ErrorInvalidOperation):
                    # This is probably a distinguished folder the server does not have. We previously tested the exact
                    # error message (f.value), but some Exchange servers return localized error messages, so that's not
                    # possible to do reliably.
                    continue
                if isinstance(f, ErrorItemNotFound):
                    # Another way of telling us that this is a distinguished folder the server does not have
                    continue
                if isinstance(f, Exception):
                    raise f
                folders_map[f.folder_id] = f
            for f in FolderCollection(account=self.account, folders=[self]).find_folders(depth=DEEP):
                if isinstance(f, Exception):
                    raise f
                if f.folder_id in folders_map:
                    # Already exists. Probably a distinguished folder
                    continue
                folders_map[f.folder_id] = f
        except ErrorAccessDenied:
            # We may not have GetFolder or FindFolder access
            pass
        self._subfolders = folders_map
        return folders_map

    def get_default_folder(self, folder_cls):
        # Returns the distinguished folder instance of type folder_cls belonging to this account. If no distinguished
        # folder was found, try as best we can to return the default folder of type 'folder_cls'
        if not folder_cls.DISTINGUISHED_FOLDER_ID:
            raise ValueError("'folder_cls' %s must have a DISTINGUISHED_FOLDER_ID value" % folder_cls)
        try:
            # Get the default folder
            log.debug('Testing default %s folder with GetFolder', folder_cls)
            # Use cached instance if available
            for f in self._folders_map.values():
                if isinstance(f, folder_cls) and f.has_distinguished_name:
                    return f
            return folder_cls.get_distinguished(account=self.account)
        except ErrorAccessDenied:
            # Maybe we just don't have GetFolder access? Try FindItems instead
            log.debug('Testing default %s folder with FindItem', folder_cls)
            fld = folder_cls(account=self.account, name=folder_cls.DISTINGUISHED_FOLDER_ID)
            fld.test_access()
            return self._folders_map.get(fld.folder_id, fld)  # Use cached instance if available
        except ErrorFolderNotFound:
            # There's no folder named fld_class.DISTINGUISHED_FOLDER_ID. Try to guess which folder is the default.
            # Exchange makes this unnecessarily difficult.
            log.debug('Searching default %s folder in full folder list', folder_cls)

        candidates = []
        # Try direct children of TOIS first. TOIS might not exist.
        try:
            same_type = [f for f in self.tois.children if f.__class__ == folder_cls]
            are_distinguished = [f for f in same_type if f.is_distinguished]
            if are_distinguished:
                candidates = are_distinguished
            else:
                candidates = [f for f in same_type if f.name.lower() in folder_cls.localized_names(self.account.locale)]
        except ErrorFolderNotFound:
            pass

        if candidates:
            if len(candidates) > 1:
                raise ValueError(
                    'Multiple possible default %s folders in TOIS: %s'
                    % (folder_cls, [text_type(f.name) for f in candidates])
                )
            return candidates[0]

        # No candidates in TOIS. Try direct children of root.
        same_type = [f for f in self.children if f.__class__ == folder_cls]
        are_distinguished = [f for f in same_type if f.is_distinguished]
        if are_distinguished:
            candidates = are_distinguished
        else:
            candidates = [f for f in same_type if f.name.lower() in folder_cls.localized_names(self.account.locale)]

        if candidates:
            if len(candidates) > 1:
                raise ValueError('Multiple possible default %s folders in root: %s'
                                 % (folder_cls, [text_type(f.name) for f in candidates]))
            return candidates[0]

        raise ErrorFolderNotFound('No useable default %s folders' % folder_cls)


class Calendar(Folder):
    """
    An interface for the Exchange calendar
    """
    DISTINGUISHED_FOLDER_ID = 'calendar'
    CONTAINER_CLASS = 'IPF.Appointment'
    supported_item_models = (CalendarItem,)

    LOCALIZED_NAMES = {
        'da_DK': (u'Kalender',),
        'de_DE': (u'Kalender',),
        'en_US': (u'Calendar',),
        'es_ES': (u'Calendario',),
        'fr_CA': (u'Calendrier',),
        'nl_NL': (u'Agenda',),
        'ru_RU': (u'Календарь',),
        'sv_SE': (u'Kalender',),
    }

    def view(self, *args, **kwargs):
        return FolderCollection(account=self.account, folders=[self]).view(*args, **kwargs)


class DeletedItems(Folder):
    DISTINGUISHED_FOLDER_ID = 'deleteditems'
    CONTAINER_CLASS = 'IPF.Note'
    supported_item_models = ITEM_CLASSES

    LOCALIZED_NAMES = {
        'da_DK': (u'Slettet post',),
        'de_DE': (u'Gelöschte Elemente',),
        'en_US': (u'Deleted Items',),
        'es_ES': (u'Elementos eliminados',),
        'fr_CA': (u'Éléments supprimés',),
        'nl_NL': (u'Verwijderde items',),
        'ru_RU': (u'Удаленные',),
        'sv_SE': (u'Borttaget',),
    }


class Messages(Folder):
    CONTAINER_CLASS = 'IPF.Note'
    supported_item_models = (Message, MeetingRequest, MeetingResponse, MeetingCancellation)


class Drafts(Messages):
    DISTINGUISHED_FOLDER_ID = 'drafts'

    LOCALIZED_NAMES = {
        'da_DK': (u'Kladder',),
        'de_DE': (u'Entwürfe',),
        'en_US': (u'Drafts',),
        'es_ES': (u'Borradores',),
        'fr_CA': (u'Brouillons',),
        'nl_NL': (u'Concepten',),
        'ru_RU': (u'Черновики',),
        'sv_SE': (u'Utkast',),
    }


class Inbox(Messages):
    DISTINGUISHED_FOLDER_ID = 'inbox'

    LOCALIZED_NAMES = {
        'da_DK': (u'Indbakke',),
        'de_DE': (u'Posteingang',),
        'en_US': (u'Inbox',),
        'es_ES': (u'Bandeja de entrada',),
        'fr_CA': (u'Boîte de réception',),
        'nl_NL': (u'Postvak IN',),
        'ru_RU': (u'Входящие',),
        'sv_SE': (u'Inkorgen',),
    }


class Outbox(Messages):
    DISTINGUISHED_FOLDER_ID = 'outbox'

    LOCALIZED_NAMES = {
        'da_DK': (u'Udbakke',),
        'de_DE': (u'Postausgang',),
        'en_US': (u'Outbox',),
        'es_ES': (u'Bandeja de salida',),
        'fr_CA': (u"Boîte d'envoi",),
        'nl_NL': (u'Postvak UIT',),
        'ru_RU': (u'Исходящие',),
        'sv_SE': (u'Utkorgen',),
    }


class SentItems(Messages):
    DISTINGUISHED_FOLDER_ID = 'sentitems'

    LOCALIZED_NAMES = {
        'da_DK': (u'Sendt post',),
        'de_DE': (u'Gesendete Elemente',),
        'en_US': (u'Sent Items',),
        'es_ES': (u'Elementos enviados',),
        'fr_CA': (u'Éléments envoyés',),
        'nl_NL': (u'Verzonden items',),
        'ru_RU': (u'Отправленные',),
        'sv_SE': (u'Skickat',),
    }


class JunkEmail(Messages):
    DISTINGUISHED_FOLDER_ID = 'junkemail'

    LOCALIZED_NAMES = {
        'da_DK': (u'Uønsket e-mail',),
        'de_DE': (u'Junk-E-Mail',),
        'en_US': (u'Junk E-mail',),
        'es_ES': (u'Correo no deseado',),
        'fr_CA': (u'Courrier indésirables',),
        'nl_NL': (u'Ongewenste e-mail',),
        'ru_RU': (u'Нежелательная почта',),
        'sv_SE': (u'Skräppost',),
    }


class Tasks(Folder):
    DISTINGUISHED_FOLDER_ID = 'tasks'
    CONTAINER_CLASS = 'IPF.Task'
    supported_item_models = (Task,)

    LOCALIZED_NAMES = {
        'da_DK': (u'Opgaver',),
        'de_DE': (u'Aufgaben',),
        'en_US': (u'Tasks',),
        'es_ES': (u'Tareas',),
        'fr_CA': (u'Tâches',),
        'nl_NL': (u'Taken',),
        'ru_RU': (u'Задачи',),
        'sv_SE': (u'Uppgifter',),
    }


class Contacts(Folder):
    DISTINGUISHED_FOLDER_ID = 'contacts'
    CONTAINER_CLASS = 'IPF.Contact'
    supported_item_models = (Contact, DistributionList)

    LOCALIZED_NAMES = {
        'da_DK': (u'Kontaktpersoner',),
        'de_DE': (u'Kontakte',),
        'en_US': (u'Contacts',),
        'es_ES': (u'Contactos',),
        'fr_CA': (u'Contacts',),
        'nl_NL': (u'Contactpersonen',),
        'ru_RU': (u'Контакты',),
        'sv_SE': (u'Kontakter',),
    }


class WellknownFolder(Folder):
    # Use this class until we have specific folder implementations
    supported_item_models = ITEM_CLASSES


class AdminAuditLogs(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'adminauditlogs'
    supported_from = EXCHANGE_2013


class ArchiveDeletedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archivedeleteditems'
    supported_from = EXCHANGE_2010_SP1


class ArchiveInbox(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiveinbox'
    supported_from = EXCHANGE_2013_SP1


class ArchiveMsgFolderRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archivemsgfolderroot'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsdeletions'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemspurges'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsroot'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsversions'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiveroot'
    supported_from = EXCHANGE_2010_SP1


class Conflicts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'conflicts'
    supported_from = EXCHANGE_2013


class ConversationHistory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'conversationhistory'
    supported_from = EXCHANGE_2013


class Directory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'directory'
    supported_from = EXCHANGE_2013_SP1


class Favorites(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'favorites'
    supported_from = EXCHANGE_2013


class IMContactList(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Contact.MOC.ImContactList'
    DISTINGUISHED_FOLDER_ID = 'imcontactlist'
    supported_from = EXCHANGE_2013


class Journal(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Journal'
    DISTINGUISHED_FOLDER_ID = 'journal'


class LocalFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'localfailures'
    supported_from = EXCHANGE_2013


class MsgFolderRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'msgfolderroot'


class MyContacts(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'mycontacts'
    supported_from = EXCHANGE_2013


class Notes(WellknownFolder):
    CONTAINER_CLASS = 'IPF.StickyNote'
    DISTINGUISHED_FOLDER_ID = 'notes'
    LOCALIZED_NAMES = {
        'da_DK': (u'Noter',),
    }


class PeopleConnect(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'peopleconnect'
    supported_from = EXCHANGE_2013


class PublicFoldersRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'publicfoldersroot'
    supported_from = EXCHANGE_2007_SP1


class QuickContacts(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Contact.MOC.QuickContacts'
    DISTINGUISHED_FOLDER_ID = 'quickcontacts'
    supported_from = EXCHANGE_2013


class RecipientCache(Contacts):
    DISTINGUISHED_FOLDER_ID = 'recipientcache'
    CONTAINER_CLASS = 'IPF.Contact.RecipientCache'
    supported_from = EXCHANGE_2013

    LOCALIZED_NAMES = {}


class RecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsdeletions'
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemspurges'
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsroot'
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsversions'
    supported_from = EXCHANGE_2010_SP1


class SearchFolders(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'searchfolders'


class ServerFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'serverfailures'
    supported_from = EXCHANGE_2013


class SyncIssues(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'syncissues'
    supported_from = EXCHANGE_2013


class ToDoSearch(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Task'
    DISTINGUISHED_FOLDER_ID = 'todosearch'
    supported_from = EXCHANGE_2013

    LOCALIZED_NAMES = {
        None: (u'To-Do Search',),
    }


class VoiceMail(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'voicemail'


# See http://msdn.microsoft.com/en-us/library/microsoft.exchange.webservices.data.wellknownfoldername(v=exchg.80).aspx
# and https://msdn.microsoft.com/en-us/library/office/aa580808(v=exchg.150).aspx
WELLKNOWN_FOLDERS = [
    AdminAuditLogs,
    ArchiveDeletedItems,
    ArchiveInbox,
    ArchiveMsgFolderRoot,
    ArchiveRecoverableItemsDeletions,
    ArchiveRecoverableItemsPurges,
    ArchiveRecoverableItemsRoot,
    ArchiveRecoverableItemsVersions,
    ArchiveRoot,
    Calendar,
    Conflicts,
    Contacts,
    ConversationHistory,
    DeletedItems,
    Directory,
    Drafts,
    Favorites,
    IMContactList,
    Inbox,
    Journal,
    JunkEmail,
    LocalFailures,
    MsgFolderRoot,
    MyContacts,
    Notes,
    Outbox,
    PeopleConnect,
    PublicFoldersRoot,
    QuickContacts,
    RecipientCache,
    RecoverableItemsDeletions,
    RecoverableItemsPurges,
    RecoverableItemsRoot,
    RecoverableItemsVersions,
    Root,
    SearchFolders,
    SentItems,
    ServerFailures,
    SyncIssues,
    Tasks,
    ToDoSearch,
    VoiceMail,
]


class NonDeleteableFolderMixin:
    @property
    def is_deleteable(self):
        return False


class AllContacts(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'

    LOCALIZED_NAMES = {
        None: (u'AllContacts',),
    }


class AllItems(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF'

    LOCALIZED_NAMES = {
        None: (u'AllItems',),
    }


class CalendarLogging(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Calendar Logging',),
    }


class CommonViews(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Common Views',),
    }


class ConversationSettings(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Configuration'
    LOCALIZED_NAMES = {
        'da_DK': (u'Indstillinger for samtalehandlinger',),
    }


class DeferredAction(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Deferred Action',),
    }


class ExchangeSyncData(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'ExchangeSyncData',),
    }


class FreebusyData(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Freebusy Data',),
    }


class Friends(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'

    LOCALIZED_NAMES = {
        'de_DE': (u'Bekannte',),
    }


class GALContacts(NonDeleteableFolderMixin, Contacts):
    DISTINGUISHED_FOLDER_ID = None
    CONTAINER_CLASS = 'IPF.Contact.GalContacts'

    LOCALIZED_NAMES = {
        None: ('GAL Contacts',),
    }


class Location(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Location',),
    }


class MailboxAssociations(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'MailboxAssociations',),
    }


class MyContactsExtended(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'
    LOCALIZED_NAMES = {
        None: (u'MyContactsExtended',),
    }


class ParkedMessages(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = None
    LOCALIZED_NAMES = {
        None: (u'ParkedMessages',),
    }


class Reminders(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'Outlook.Reminder'
    LOCALIZED_NAMES = {
        'da_DK': (u'Påmindelser',),
    }


class RSSFeeds(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Note.OutlookHomepage'
    LOCALIZED_NAMES = {
        None: (u'RSS Feeds',),
    }


class Schedule(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Schedule',),
    }


class Sharing(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Note'
    LOCALIZED_NAMES = {
        None: (u'Sharing',),
    }


class Shortcuts(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Shortcuts',),
    }


class SpoolerQueue(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Spooler Queue',),
    }


class System(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'System',),
    }


class TemporarySaves(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'TemporarySaves',),
    }


class Views(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Views',),
    }


class WorkingSet(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Working Set',),
    }


# Folders that return 'ErrorDeleteDistinguishedFolder' when we try to delete them. I can't find any official docs
# listing these folders.
NON_DELETEABLE_FOLDERS = [
    AllContacts,
    AllItems,
    CalendarLogging,
    CommonViews,
    ConversationSettings,
    DeferredAction,
    ExchangeSyncData,
    FreebusyData,
    Friends,
    GALContacts,
    Location,
    MailboxAssociations,
    MyContactsExtended,
    ParkedMessages,
    Reminders,
    RSSFeeds,
    Schedule,
    Sharing,
    Shortcuts,
    SpoolerQueue,
    System,
    TemporarySaves,
    Views,
    WorkingSet,
]
