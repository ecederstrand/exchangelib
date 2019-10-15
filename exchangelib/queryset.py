# coding=utf-8
from __future__ import unicode_literals

from copy import deepcopy
from itertools import islice
import logging

from future.utils import python_2_unicode_compatible

from .errors import MultipleObjectsReturned, DoesNotExist
from .items import CalendarItem, ID_ONLY
from .fields import FieldPath, FieldOrder
from .properties import InvalidField
from .restriction import Q
from .services import CHUNK_SIZE
from .version import EXCHANGE_2010

log = logging.getLogger(__name__)


class SearchableMixIn(object):
    # Implements a search API for inheritance
    def get(self, *args, **kwargs):
        raise NotImplementedError()

    def all(self):
        raise NotImplementedError()

    def none(self):
        raise NotImplementedError()

    def filter(self, *args, **kwargs):
        raise NotImplementedError()

    def exclude(self, *args, **kwargs):
        raise NotImplementedError()

    def people(self):
        raise NotImplementedError()


@python_2_unicode_compatible
class QuerySet(SearchableMixIn):
    """
    A Django QuerySet-like class for querying items. Defers queries until the QuerySet is consumed. Supports chaining to
    build up complex queries.

    Django QuerySet documentation: https://docs.djangoproject.com/en/dev/ref/models/querysets/
    """
    VALUES = 'values'
    VALUES_LIST = 'values_list'
    FLAT = 'flat'
    NONE = 'none'
    RETURN_TYPES = (VALUES, VALUES_LIST, FLAT, NONE)

    ITEM = 'item'
    PERSONA = 'persona'
    REQUEST_TYPES = (ITEM, PERSONA)

    def __init__(self, folder_collection, request_type=ITEM):
        from .folders import FolderCollection
        if not isinstance(folder_collection, FolderCollection):
            raise ValueError("folder_collection value '%s' must be a FolderCollection instance" % folder_collection)
        self.folder_collection = folder_collection  # A FolderCollection instance
        if request_type not in self.REQUEST_TYPES:
            raise ValueError("'request_type' %r must be one of %s" % (request_type, self.REQUEST_TYPES))
        self.request_type = request_type
        self.q = Q()  # Default to no restrictions. 'None' means 'return nothing'
        self.only_fields = None
        self.order_fields = None
        self.return_format = self.NONE
        self.calendar_view = None
        self.page_size = None
        self.max_items = None
        self.offset = 0

        self._cache = None

    def _copy_self(self):
        # When we copy a queryset where the cache has already been filled, we don't copy the cache. Thus, a copied
        # queryset will fetch results from the server again.
        #
        # All other behaviour would be awkward:
        #
        # qs = QuerySet(f).filter(foo='bar')
        # items = list(qs)
        # new_qs = qs.exclude(bar='baz')  # This should work, and should fetch from the server
        #
        if not isinstance(self.q, (type(None), Q)):
            raise ValueError("self.q value '%s' must be None or a Q instance" % self.q)
        if not isinstance(self.only_fields, (type(None), tuple)):
            raise ValueError("self.only_fields value '%s' must be None or a tuple" % self.only_fields)
        if not isinstance(self.order_fields, (type(None), tuple)):
            raise ValueError("self.order_fields value '%s' must be None or a tuple" % self.order_fields)
        if self.return_format not in self.RETURN_TYPES:
            raise ValueError("self.return_value '%s' must be one of %s" % (self.return_format, self.RETURN_TYPES))
        # Only mutable objects need to be deepcopied. Folder should be the same object
        new_qs = self.__class__(self.folder_collection, request_type=self.request_type)
        new_qs.q = None if self.q is None else deepcopy(self.q)
        new_qs.only_fields = self.only_fields
        new_qs.order_fields = None if self.order_fields is None else deepcopy(self.order_fields)
        new_qs.return_format = self.return_format
        new_qs.calendar_view = self.calendar_view
        new_qs.page_size = self.page_size
        new_qs.max_items = self.max_items
        new_qs.offset = self.offset
        return new_qs

    @property
    def is_cached(self):
        return self._cache is not None

    def _get_field_path(self, field_path):
        from .items import Persona
        if self.request_type == self.PERSONA:
            return FieldPath(field=Persona.get_field_by_fieldname(field_path))
        for folder in self.folder_collection:
            try:
                return FieldPath.from_string(field_path=field_path, folder=folder)
            except InvalidField:
                pass
        raise InvalidField("Unknown field path %r on folders %s" % (field_path, self.folder_collection.folders))

    def _get_field_order(self, field_path):
        from .items import Persona
        if self.request_type == self.PERSONA:
            return FieldOrder(
                field_path=FieldPath(field=Persona.get_field_by_fieldname(field_path.lstrip('-'))),
                reverse=field_path.startswith('-'),
            )
        for folder in self.folder_collection:
            try:
                return FieldOrder.from_string(field_path=field_path, folder=folder)
            except InvalidField:
                pass
        raise InvalidField("Unknown field path %r on folders %s" % (field_path, self.folder_collection.folders))

    @property
    def _item_id_field(self):
        return self._get_field_path('id')

    @property
    def _changekey_field(self):
        return self._get_field_path('changekey')

    def _additional_fields(self):
        if not isinstance(self.only_fields, tuple):
            raise ValueError("'only_fields' value %r must be a tuple" % self.only_fields)
        # Remove ItemId and ChangeKey. We get them unconditionally
        additional_fields = {f for f in self.only_fields if not f.field.is_attribute}
        if self.request_type != self.ITEM:
            return additional_fields

        # For CalendarItem items, we want to inject internal timezone fields into the requested fields.
        has_start = 'start' in {f.field.name for f in additional_fields}
        has_end = 'end' in {f.field.name for f in additional_fields}
        meeting_tz_field, start_tz_field, end_tz_field = CalendarItem.timezone_fields()
        if self.folder_collection.account.version.build < EXCHANGE_2010:
            if has_start or has_end:
                additional_fields.add(FieldPath(field=meeting_tz_field))
        else:
            if has_start:
                additional_fields.add(FieldPath(field=start_tz_field))
            if has_end:
                additional_fields.add(FieldPath(field=end_tz_field))
        return additional_fields

    def _format_items(self, items, return_format):
        return {
            self.VALUES: self._as_values,
            self.VALUES_LIST: self._as_values_list,
            self.FLAT: self._as_flat_values_list,
            self.NONE: self._as_items,
        }[return_format](items)

    def _query(self):
        from .folders import SHALLOW
        from .items import Persona
        if self.only_fields is None:
            # We didn't restrict list of field paths. Get all fields from the server, including extended properties.
            if self.request_type == self.PERSONA:
                additional_fields = {FieldPath(field=f) for f in Persona.supported_fields(
                    version=self.folder_collection.account.version
                ) if not f.is_complex}
                complex_fields_requested = False
            else:
                additional_fields = {FieldPath(field=f) for f in self.folder_collection.allowed_item_fields()}
                complex_fields_requested = True
        else:
            additional_fields = self._additional_fields()
            complex_fields_requested = any(f.field.is_complex for f in additional_fields)

        # EWS can do server-side sorting on multiple fields. A caveat is that server-side sorting is not supported
        # for calendar views. In this case, we do all the sorting client-side.
        if self.calendar_view:
            must_sort_clientside = bool(self.order_fields)
            order_fields = None
        else:
            must_sort_clientside = False
            order_fields = self.order_fields

        if must_sort_clientside:
            # Also fetch order_by fields that we only need for client-side sorting.
            extra_order_fields = {f.field_path for f in self.order_fields} - additional_fields
            if extra_order_fields:
                additional_fields.update(extra_order_fields)
        else:
            extra_order_fields = set()

        if self.request_type == self.PERSONA:
            if len(self.folder_collection) != 1:
                raise ValueError('Personas can only be queried on a single folder')
            items = list(self.folder_collection)[0].find_people(
                self.q,
                shape=ID_ONLY,
                depth=SHALLOW,
                additional_fields=additional_fields,
                order_fields=order_fields,
                page_size=self.page_size,
                max_items=self.max_items,
                offset=self.offset,
            )
        else:
            find_item_kwargs = dict(
                shape=ID_ONLY,  # Always use IdOnly here, because AllProperties doesn't actually get *all* properties
                additional_fields=additional_fields,
                order_fields=order_fields,
                calendar_view=self.calendar_view,
                page_size=self.page_size,
                max_items=self.max_items,
                offset=self.offset,
            )

            if complex_fields_requested:
                # The FindItem service does not support complex field types. Tell find_items() to return
                # (id, changekey) tuples, and pass that to fetch().
                find_item_kwargs['additional_fields'] = None
                items = self.folder_collection.account.fetch(
                    ids=self.folder_collection.find_items(self.q, **find_item_kwargs),
                    only_fields=additional_fields,
                    chunk_size=self.page_size,
                )
            else:
                if not additional_fields:
                    # If additional_fields is the empty set, we only requested ID and changekey fields. We can then
                    # take a shortcut by using (shape=ID_ONLY, additional_fields=None) to tell find_items() to return
                    # (id, changekey) tuples. We'll post-process those later.
                    find_item_kwargs['additional_fields'] = None
                items = self.folder_collection.find_items(self.q, **find_item_kwargs)

        if not must_sort_clientside:
            return items

        # Resort to client-side sorting of the order_by fields. This is greedy. Sorting in Python is stable, so when
        # sorting on multiple fields, we can just do a sort on each of the requested fields in reverse order. Reverse
        # each sort operation if the field was marked as such.
        for f in reversed(self.order_fields):
            try:
                items = sorted(items, key=lambda i: _get_value_or_default(i, f), reverse=f.reverse)
            except TypeError as e:
                if 'unorderable types' not in e.args[0]:
                    raise
                raise ValueError((
                    "Cannot sort on field '%s'. The field has no default value defined, and there are either items "
                    "with None values for this field, or the query contains exception instances (original error: %s).")
                                 % (f.field_path, e))
        if not extra_order_fields:
            return items

        # Nullify the fields we only needed for sorting before returning
        return (_rinse_item(i, extra_order_fields) for i in items)

    def __iter__(self):
        # Fill cache if this is the first iteration. Return an iterator over the results. Make this non-greedy by
        # filling the cache while we are iterating.
        #
        # We don't set self._cache until the iterator is finished. Otherwise an interrupted iterator would leave the
        # cache in an inconsistent state.
        if self.is_cached:
            for val in self._cache:
                yield val
            return

        if self.q is None:
            self._cache = []
            return

        log.debug('Initializing cache')
        _cache = []
        for val in self._format_items(items=self._query(), return_format=self.return_format):
            _cache.append(val)
            yield val
        self._cache = _cache

    def __len__(self):
        if self.is_cached:
            return len(self._cache)
        # This queryset has no cache yet. Call the optimized counting implementation
        return self.count()

    def __getitem__(self, idx_or_slice):
        # Support indexing and slicing. This is non-greedy when possible (slicing start, stop and step are not negative,
        # and we're ordering on at most one field), and will only fill the cache if the entire query is iterated.
        if isinstance(idx_or_slice, int):
            return self._getitem_idx(idx_or_slice)
        return self._getitem_slice(idx_or_slice)

    def _getitem_idx(self, idx):
        if self.is_cached:
            return self._cache[idx]
        if idx < 0:
            # Support negative indexes by reversing the queryset and negating the index value
            reverse_idx = -(idx+1)
            return self.reverse()[reverse_idx]
        # Optimize by setting an exact offset and fetching only 1 item
        new_qs = self._copy_self()
        new_qs.max_items = 1
        new_qs.page_size = 1
        new_qs.offset = idx
        # The iterator will return at most 1 item
        for item in new_qs.__iter__():
            return item
        raise IndexError()

    def _getitem_slice(self, s):
        if ((s.start or 0) < 0) or ((s.stop or 0) < 0) or ((s.step or 0) < 0):
            # islice() does not support negative start, stop and step. Make sure cache is full by iterating the full
            # query result, and then slice on the cache.
            list(self.__iter__())
            return self._cache[s]
        if self.is_cached:
            return islice(self.__iter__(), s.start, s.stop, s.step)
        # Optimize by setting an exact offset and max_items value
        new_qs = self._copy_self()
        if s.start is not None and s.stop is not None:
            new_qs.offset = s.start
            new_qs.max_items = s.stop - s.start
        elif s.start is not None:
            new_qs.offset = s.start
        elif s.stop is not None:
            new_qs.max_items = s.stop
        if new_qs.page_size is None and new_qs.max_items is not None and new_qs.max_items < CHUNK_SIZE:
            new_qs.page_size = new_qs.max_items
        return islice(new_qs.__iter__(), None, None, s.step)

    def _item_yielder(self, iterable, item_func, id_only_func, changekey_only_func, id_and_changekey_func):
        # Transforms results from the server according to the given transform functions. Makes sure to pass on
        # Exception instances unaltered.
        if self.only_fields:
            has_non_attribute_fields = bool({f for f in self.only_fields if not f.field.is_attribute})
        else:
            has_non_attribute_fields = True
        if not has_non_attribute_fields:
            # _query() will return an iterator of (id, changekey) tuples
            if self._changekey_field not in self.only_fields:
                transform_func = id_only_func
            elif self._item_id_field not in self.only_fields:
                transform_func = changekey_only_func
            else:
                transform_func = id_and_changekey_func
            for i in iterable:
                if isinstance(i, Exception):
                    yield i
                    continue
                yield transform_func(*i)
            return
        for i in iterable:
            if isinstance(i, Exception):
                yield i
                continue
            yield item_func(i)

    def _as_items(self, iterable):
        from .items import Item
        return self._item_yielder(
            iterable=iterable,
            item_func=lambda i: i,
            id_only_func=lambda item_id, changekey: Item(id=item_id),
            changekey_only_func=lambda item_id, changekey: Item(changekey=changekey),
            id_and_changekey_func=lambda item_id, changekey: Item(id=item_id, changekey=changekey),
        )

    def _as_values(self, iterable):
        if not self.only_fields:
            raise ValueError('values() requires at least one field name')
        return self._item_yielder(
            iterable=iterable,
            item_func=lambda i: {f.path: f.get_value(i) for f in self.only_fields},
            id_only_func=lambda item_id, changekey: {'id': item_id},
            changekey_only_func=lambda item_id, changekey: {'changekey': changekey},
            id_and_changekey_func=lambda item_id, changekey: {'id': item_id, 'changekey': changekey},
        )

    def _as_values_list(self, iterable):
        if not self.only_fields:
            raise ValueError('values_list() requires at least one field name')
        return self._item_yielder(
            iterable=iterable,
            item_func=lambda i: tuple(f.get_value(i) for f in self.only_fields),
            id_only_func=lambda item_id, changekey: (item_id,),
            changekey_only_func=lambda item_id, changekey: (changekey,),
            id_and_changekey_func=lambda item_id, changekey: (item_id, changekey),
        )

    def _as_flat_values_list(self, iterable):
        if not self.only_fields or len(self.only_fields) != 1:
            raise ValueError('flat=True requires exactly one field name')
        flat_field_path = self.only_fields[0]
        return self._item_yielder(
            iterable=iterable,
            item_func=flat_field_path.get_value,
            id_only_func=lambda item_id, changekey: item_id,
            changekey_only_func=lambda item_id, changekey: changekey,
            id_and_changekey_func=None,  # Can never be called
        )

    ###############################
    #
    # Methods that support chaining
    #
    ###############################
    # Return copies of self, so this works as expected:
    #
    # foo_qs = my_folder.filter(...)
    # foo_qs.filter(foo='bar')
    # foo_qs.filter(foo='baz')  # Should not be affected by the previous statement
    #
    def all(self):
        """ Return everything, without restrictions """
        new_qs = self._copy_self()
        return new_qs

    def none(self):
        """ Return a query that is guaranteed to be empty  """
        new_qs = self._copy_self()
        new_qs.q = None
        return new_qs

    def filter(self, *args, **kwargs):
        """ Return everything that matches these search criteria """
        new_qs = self._copy_self()
        q = Q(*args, **kwargs)
        new_qs.q = q if new_qs.q is None else new_qs.q & q
        return new_qs

    def exclude(self, *args, **kwargs):
        """ Return everything that does NOT match these search criteria """
        new_qs = self._copy_self()
        q = ~Q(*args, **kwargs)
        new_qs.q = q if new_qs.q is None else new_qs.q & q
        return new_qs

    def people(self):
        """ Changes the queryset to search the folder for Personas instead of Items """
        new_qs = self._copy_self()
        new_qs.request_type = self.PERSONA
        return new_qs

    def only(self, *args):
        """ Fetch only the specified field names. All other item fields will be 'None' """
        try:
            only_fields = tuple(self._get_field_path(arg) for arg in args)
        except ValueError as e:
            raise ValueError("%s in only()" % e.args[0])
        new_qs = self._copy_self()
        new_qs.only_fields = only_fields
        return new_qs

    def order_by(self, *args):
        """ Return the query result sorted by the specified field names. Field names prefixed with '-' will be sorted
        in reverse order. EWS only supports server-side sorting on a single field. Sorting on multiple fields is
        implemented client-side and will therefore make the query greedy """
        try:
            order_fields = tuple(self._get_field_order(arg) for arg in args)
        except ValueError as e:
            raise ValueError("%s in order_by()" % e.args[0])
        new_qs = self._copy_self()
        new_qs.order_fields = order_fields
        return new_qs

    def reverse(self):
        """ Return the entire query result in reverse order """
        if not self.order_fields:
            raise ValueError('Reversing only makes sense if there are order_by fields')
        new_qs = self._copy_self()
        for f in new_qs.order_fields:
            f.reverse = not f.reverse
        return new_qs

    def values(self, *args):
        """ Return the values of the specified field names as dicts """
        try:
            only_fields = tuple(self._get_field_path(arg) for arg in args)
        except ValueError as e:
            raise ValueError("%s in values()" % e.args[0])
        new_qs = self._copy_self()
        new_qs.only_fields = only_fields
        new_qs.return_format = self.VALUES
        return new_qs

    def values_list(self, *args, **kwargs):
        """ Return the values of the specified field names as lists. If called with flat=True and only one field name,
        return only this value instead of a list.

        Allow an arbitrary list of fields in *args, possibly ending with flat=True|False"""
        flat = kwargs.pop('flat', False)
        if kwargs:
            raise AttributeError('Unknown kwargs: %s' % kwargs)
        if flat and len(args) != 1:
            raise ValueError('flat=True requires exactly one field name')
        try:
            only_fields = tuple(self._get_field_path(arg) for arg in args)
        except ValueError as e:
            raise ValueError("%s in values_list()" % e.args[0])
        new_qs = self._copy_self()
        new_qs.only_fields = only_fields
        new_qs.return_format = self.FLAT if flat else self.VALUES_LIST
        return new_qs

    ###########################
    #
    # Methods that end chaining
    #
    ###########################
    def iterator(self):
        """ Return the query result as an iterator, without caching the result """
        if self.q is None:
            return []
        if self.is_cached:
            return self._cache
        # Return an iterator that doesn't bother with caching
        return self._format_items(items=self._query(), return_format=self.return_format)

    def get(self, *args, **kwargs):
        """ Assume the query will return exactly one item. Return that item """
        if self.is_cached and not args and not kwargs:
            # We can only safely use the cache if get() is called without args
            items = self._cache
        elif not args and set(kwargs.keys()) in ({'id'}, {'id', 'changekey'}):
            # We allow calling get(id=..., changekey=...) to get a single item, but only if exactly these two
            # kwargs are present.
            account = self.folder_collection.account
            item_id = self._item_id_field.field.clean(kwargs['id'], version=account.version)
            changekey = self._changekey_field.field.clean(kwargs.get('changekey'), version=account.version)
            items = list(account.fetch(ids=[(item_id, changekey)], only_fields=self.only_fields))
        else:
            new_qs = self.filter(*args, **kwargs)
            items = list(new_qs.__iter__())
        if not items:
            raise DoesNotExist()
        if len(items) != 1:
            raise MultipleObjectsReturned()
        return items[0]

    def count(self, page_size=1000):
        """ Get the query count, with as little effort as possible 'page_size' is the number of items to
        fetch from the server per request. We're only fetching the IDs, so keep it high"""
        if self.is_cached:
            return len(self._cache)
        new_qs = self._copy_self()
        new_qs.only_fields = tuple()
        new_qs.order_fields = None
        new_qs.return_format = self.NONE
        new_qs.page_size = page_size
        return len(list(new_qs.__iter__()))

    def exists(self):
        """ Find out if the query contains any hits, with as little effort as possible """
        if self.is_cached:
            return len(self._cache) > 0
        new_qs = self._copy_self()
        new_qs.max_items = 1
        return new_qs.count(page_size=1) > 0

    def _id_only_copy_self(self):
        new_qs = self._copy_self()
        new_qs.only_fields = tuple()
        new_qs.order_fields = None
        new_qs.return_format = self.NONE
        return new_qs

    def delete(self, page_size=1000, **delete_kwargs):
        """ Delete the items matching the query, with as little effort as possible. 'page_size' is the number of items
        to fetch and delete per request. We're only fetching the IDs, so keep it high"""
        if self.is_cached:
            ids = self._cache
        else:
            ids = self._id_only_copy_self()
            ids.page_size = page_size
        res = self.folder_collection.account.bulk_delete(
            ids=ids,
            chunk_size=page_size,
            **delete_kwargs
        )
        self._cache = None  # Invalidate the cache, regardless of the results
        return res

    def send(self, page_size=1000, **send_kwargs):
        """ Send the items matching the query, with as little effort as possible. 'page_size' is the number of items
        to fetch and send per request. We're only fetching the IDs, so keep it high"""
        if self.is_cached:
            ids = self._cache
        else:
            ids = self._id_only_copy_self()
            ids.page_size = page_size
        res = self.folder_collection.account.bulk_send(
            ids=ids,
            chunk_size=page_size,
            **send_kwargs
        )
        self._cache = None  # Invalidate the cache, regardless of the results
        return res

    def copy(self, to_folder, page_size=1000, **copy_kwargs):
        """ Copy the items matching the query, with as little effort as possible. 'page_size' is the number of items
        to fetch and copy per request. We're only fetching the IDs, so keep it high"""
        if self.is_cached:
            ids = self._cache
        else:
            ids = self._id_only_copy_self()
            ids.page_size = page_size
        res = self.folder_collection.account.bulk_copy(
            ids=ids,
            to_folder=to_folder,
            chunk_size=page_size,
            **copy_kwargs
        )
        self._cache = None  # Invalidate the cache, regardless of the results
        return res

    def move(self, to_folder, page_size=1000):
        """ Move the items matching the query, with as little effort as possible. 'page_size' is the number of items
        to fetch and move per request. We're only fetching the IDs, so keep it high"""
        if self.is_cached:
            ids = self._cache
        else:
            ids = self._id_only_copy_self()
            ids.page_size = page_size
        res = self.folder_collection.account.bulk_move(
            ids=ids,
            to_folder=to_folder,
            chunk_size=page_size,
        )
        self._cache = None  # Invalidate the cache after delete, regardless of the results
        return res

    def archive(self, to_folder, page_size=1000):
        """ Archive the items matching the query, with as little effort as possible. 'page_size' is the number of items
        to fetch and move per request. We're only fetching the IDs, so keep it high"""
        if self.is_cached:
            ids = self._cache
        else:
            ids = self._id_only_copy_self()
            ids.page_size = page_size
        res = self.folder_collection.account.bulk_archive(
            ids=ids,
            to_folder=to_folder,
            chunk_size=page_size,
        )
        self._cache = None  # Invalidate the cache after delete, regardless of the results
        return res

    def __str__(self):
        fmt_args = [('q', str(self.q)), ('folders', '[%s]' % ', '.join(str(f) for f in self.folder_collection.folders))]
        if self.is_cached:
            fmt_args.append(('len', str(len(self))))
        return self.__class__.__name__ + '(%s)' % ', '.join('%s=%s' % (k, v) for k, v in fmt_args)


def _get_value_or_default(item, field_order):
    # Python can only sort values when <, > and = are implemented for the two types. Try as best we can to sort
    # items, even when the item may have a None value for the field in question, or when the item is an
    # Exception. If the field to be sorted by does not have a default value, there's really nothing we can do
    # about it; we'll eventually raise a TypeError. If it does, we sort all None values and exceptions as the
    # default value.
    if isinstance(item, Exception):
        return field_order.field_path.field.default
    val = field_order.field_path.get_value(item)
    if val is None:
        return field_order.field_path.field.default
    return val


def _rinse_item(i, fields_to_nullify):
    # Set fields in fields_to_nullify to None. Make sure to accept exceptions.
    if isinstance(i, Exception):
        return i
    for f in fields_to_nullify:
        setattr(i, f.field.name, None)
    return i
