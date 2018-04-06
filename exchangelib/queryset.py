# coding=utf-8
from __future__ import unicode_literals

from copy import deepcopy
from itertools import islice
import logging

from future.utils import python_2_unicode_compatible

from .items import CalendarItem, IdOnly
from .fields import FieldPath, FieldOrder
from .restriction import Q
from .version import EXCHANGE_2010

log = logging.getLogger(__name__)


class MultipleObjectsReturned(Exception):
    pass


class DoesNotExist(Exception):
    pass


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

        self._cache = None

    def copy(self):
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
        return new_qs

    @property
    def is_cached(self):
        return self._cache is not None

    def _get_field_path(self, s):
        from .items import Persona
        if self.request_type == self.PERSONA:
            return FieldPath(field=Persona.get_field_by_fieldname(s))
        for folder in self.folder_collection:
            try:
                return FieldPath.from_string(s, folder=folder)
            except ValueError:
                pass
        raise ValueError("Unknown fieldname '%s' on folders '%s'" % (s, self.folder_collection.folders))

    def _get_field_order(self, s):
        from .items import Persona
        if self.request_type == self.PERSONA:
            field_path = FieldPath(field=Persona.get_field_by_fieldname(s.lstrip('-')))
            reverse = s.startswith('-')
            return FieldOrder(field_path=field_path, reverse=reverse)
        for folder in self.folder_collection:
            try:
                return FieldOrder.from_string(s, folder=folder)
            except ValueError:
                pass
        raise ValueError("Unknown fieldname '%s' on folders '%s'" % (s, self.folder_collection.folders))

    @property
    def _item_id_field(self):
        return self._get_field_path('item_id')

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
                additional_fields = {FieldPath(field=f) for f in self.folder_collection.allowed_fields()}
                complex_fields_requested = True
        else:
            additional_fields = self._additional_fields()
            complex_fields_requested = \
                bool(set(f.field for f in additional_fields) & self.folder_collection.complex_fields())

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
            folder = list(self.folder_collection)[0]
            items = folder.find_people(
                self.q,
                shape=IdOnly,
                depth=SHALLOW,
                additional_fields=additional_fields,
                order_fields=order_fields,
                page_size=self.page_size,
                max_items=self.max_items,
            )
        else:
            find_item_kwargs = dict(
                shape=IdOnly,  # Always use IdOnly here, because AllProperties doesn't actually get *all* properties
                additional_fields=additional_fields,
                order_fields=order_fields,
                calendar_view=self.calendar_view,
                page_size=self.page_size,
                max_items=self.max_items,
            )

            if complex_fields_requested:
                # The FindItem service does not support complex field types. Tell find_items() to return
                # (item_id, changekey) tuples, and pass that to fetch().
                find_item_kwargs['additional_fields'] = None
                items = self.folder_collection.account.fetch(
                    ids=self.folder_collection.find_items(self.q, **find_item_kwargs),
                    only_fields=additional_fields,
                    chunk_size=self.page_size,
                )
            else:
                if not additional_fields:
                    # If additional_fields is the empty set, we only requested item_id and changekey fields. We can then
                    # take a shortcut by using (shape=IdOnly, additional_fields=None) to tell find_items() to return
                    # (item_id, changekey) tuples. We'll post-process those later.
                    find_item_kwargs['additional_fields'] = None
                items = self.folder_collection.find_items(self.q, **find_item_kwargs)

        if not must_sort_clientside:
            return items

        # Resort to client-side sorting of the order_by fields. This is greedy. Sorting in Python is stable, so when
        # sorting on multiple fields, we can just do a sort on each of the requested fields in reverse order. Reverse
        # each sort operation if the field was marked as such.
        def get_value_or_default(item, field_order):
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

        for f in reversed(self.order_fields):
            try:
                items = sorted(items, key=lambda i: get_value_or_default(i, f), reverse=f.reverse)
            except TypeError as e:
                if 'unorderable types' not in e.args[0]:
                    raise
                raise ValueError((
                    "Cannot sort on field '%s'. The field has no default value defined, and there are either items "
                    "with None values for this field, or the query contains exception instances (original error: %s).")
                                 % (f.field_path, e))
        if not extra_order_fields:
            return items

        # Nullify the fields we only needed for sorting. Make sure to handle exceptions.
        def clean_item(i):
            if isinstance(i, Exception):
                return i
            for f in extra_order_fields:
                setattr(i, f.field.name, None)
            return i
        return (clean_item(i) for i in items)

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
        result_formatter = {
            self.VALUES: self._as_values,
            self.VALUES_LIST: self._as_values_list,
            self.FLAT: self._as_flat_values_list,
            self.NONE: self._as_items,
        }[self.return_format]
        for val in result_formatter(self._query()):
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
        # TODO: We could optimize this for large indexes or slices (e.g. [999] or [999:1002]) by letting the FindItem
        # service expose the 'offset' value, so we don't need to get the first 999 items.
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
        else:
            if not self.is_cached and idx < 100:
                # If idx is small, optimize a bit by setting self.page_size to only get as many items as strictly needed
                self.page_size = idx + 1
                self.max_items = idx + 1
            # Support non-negative indexes by consuming the iterator up to the index
            for i, val in enumerate(self.__iter__()):
                if i == idx:
                    return val
            raise IndexError()

    def _getitem_slice(self, s):
        if ((s.start or 0) < 0) or ((s.stop or 0) < 0) or ((s.step or 0) < 0):
            # islice() does not support negative start, stop and step. Make sure cache is full by iterating the full
            # query result, and then slice on the cache.
            list(self.__iter__())
            return self._cache[s]
        if not self.is_cached and s.stop is not None and s.stop < 100:
            # If the range is small, optimize a bit by setting self.page_size to only get as many items as strictly
            # needed.
            self.page_size = s.stop
            self.max_items = s.stop
        return islice(self.__iter__(), s.start, s.stop, s.step)

    def _as_items(self, iterable):
        from .items import Item
        if self.only_fields:
            has_non_attribute_fields = bool({f for f in self.only_fields if not f.field.is_attribute})
            if not has_non_attribute_fields:
                # _query() will return an iterator of (item_id, changekey) tuples
                if self._changekey_field not in self.only_fields:
                    for i in iterable:
                        if isinstance(i, Exception):
                            yield i
                            continue
                        item_id, changekey = i
                        yield Item(item_id=item_id)
                elif self._item_id_field not in self.only_fields:
                    for i in iterable:
                        if isinstance(i, Exception):
                            yield i
                            continue
                        item_id, changekey = i
                        yield Item(changekey=changekey)
                else:
                    for i in iterable:
                        if isinstance(i, Exception):
                            yield i
                            continue
                        item_id, changekey = i
                        yield Item(item_id=item_id, changekey=changekey)
                return
        for i in iterable:
            yield i

    def _as_values(self, iterable):
        if not self.only_fields:
            raise ValueError('values() requires at least one field name')
        has_non_attribute_fields = bool({f for f in self.only_fields if not f.field.is_attribute})
        if not has_non_attribute_fields:
            # _query() will return an iterator of (item_id, changekey) tuples
            if self._changekey_field not in self.only_fields:
                for i in iterable:
                    if isinstance(i, Exception):
                        yield i
                        continue
                    item_id, changekey = i
                    yield {'item_id': item_id}
            elif self._item_id_field not in self.only_fields:
                for i in iterable:
                    if isinstance(i, Exception):
                        yield i
                        continue
                    item_id, changekey = i
                    yield {'changekey': changekey}
            else:
                for i in iterable:
                    if isinstance(i, Exception):
                        yield i
                        continue
                    item_id, changekey = i
                    yield {'item_id': item_id, 'changekey': changekey}
            return
        for i in iterable:
            if isinstance(i, Exception):
                yield i
                continue
            yield {f.path: f.get_value(i) for f in self.only_fields}

    def _as_values_list(self, iterable):
        if not self.only_fields:
            raise ValueError('values_list() requires at least one field name')
        has_non_attribute_fields = bool({f for f in self.only_fields if not f.field.is_attribute})
        if not has_non_attribute_fields:
            # _query() will return an iterator of (item_id, changekey) tuples
            if self._changekey_field not in self.only_fields:
                for i in iterable:
                    if isinstance(i, Exception):
                        yield i
                        continue
                    item_id, changekey = i
                    yield (item_id,)
            elif self._item_id_field not in self.only_fields:
                for i in iterable:
                    if isinstance(i, Exception):
                        yield i
                        continue
                    item_id, changekey = i
                    yield (changekey,)
            else:
                for i in iterable:
                    if isinstance(i, Exception):
                        yield i
                        continue
                    item_id, changekey = i
                    yield (item_id, changekey)
            return
        for i in iterable:
            if isinstance(i, Exception):
                yield i
                continue
            yield tuple(f.get_value(i) for f in self.only_fields)

    def _as_flat_values_list(self, iterable):
        if not self.only_fields or len(self.only_fields) != 1:
            raise ValueError('flat=True requires exactly one field name')
        flat_field_path = self.only_fields[0]
        if flat_field_path == self._item_id_field:
            # _query() will return an iterator of (item_id, changekey) tuples
            for i in iterable:
                if isinstance(i, Exception):
                    yield i
                    continue
                item_id, changekey = i
                yield item_id
            return
        if flat_field_path == self._changekey_field:
            # _query() will return an iterator of (item_id, changekey) tuples
            for i in iterable:
                if isinstance(i, Exception):
                    yield i
                    continue
                item_id, changekey = i
                yield changekey
            return
        for i in iterable:
            if isinstance(i, Exception):
                yield i
                continue
            yield flat_field_path.get_value(i)

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
        new_qs = self.copy()
        return new_qs

    def none(self):
        """ Return a query that is guaranteed to be empty  """
        new_qs = self.copy()
        new_qs.q = None
        return new_qs

    def filter(self, *args, **kwargs):
        """ Return everything that matches these search criteria """
        new_qs = self.copy()
        q = Q(*args, **kwargs)
        new_qs.q = q if new_qs.q is None else new_qs.q & q
        return new_qs

    def exclude(self, *args, **kwargs):
        """ Return everything that does NOT match these search criteria """
        new_qs = self.copy()
        q = ~Q(*args, **kwargs)
        new_qs.q = q if new_qs.q is None else new_qs.q & q
        return new_qs

    def people(self):
        """ Changes the queryset to search the folder for Personas instead of Items """
        new_qs = self.copy()
        new_qs.request_type = self.PERSONA
        return new_qs

    def only(self, *args):
        """ Fetch only the specified field names. All other item fields will be 'None' """
        try:
            only_fields = tuple(self._get_field_path(arg) for arg in args)
        except ValueError as e:
            raise ValueError("%s in only()" % e.args[0])
        new_qs = self.copy()
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
        new_qs = self.copy()
        new_qs.order_fields = order_fields
        return new_qs

    def reverse(self):
        """ Return the entire query result in reverse order """
        if not self.order_fields:
            raise ValueError('Reversing only makes sense if there are order_by fields')
        new_qs = self.copy()
        for f in new_qs.order_fields:
            f.reverse = not f.reverse
        return new_qs

    def values(self, *args):
        """ Return the values of the specified field names as dicts """
        try:
            only_fields = tuple(self._get_field_path(arg) for arg in args)
        except ValueError as e:
            raise ValueError("%s in values()" % e.args[0])
        new_qs = self.copy()
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
        new_qs = self.copy()
        new_qs.only_fields = only_fields
        new_qs.return_format = self.FLAT if flat else self.VALUES_LIST
        return new_qs

    ###########################
    #
    # Methods that end chaining
    #
    ###########################
    def iterator(self):
        """ Return the query result as an iterator, without caching the result. 'page_size' is the number of items to
        fetch from the server per request. """
        if self.q is None:
            return []
        if self.is_cached:
            return self._cache
        # Return an iterator that doesn't bother with caching
        return self._query()

    def get(self, *args, **kwargs):
        """ Assume the query will return exactly one item. Return that item """
        if self.is_cached and not args and not kwargs:
            # We can only safely use the cache if get() is called without args
            items = self._cache
        elif not args and set(kwargs.keys()) in ({'item_id'}, {'item_id', 'changekey'}):
            # We allow calling get(item_id=..., changekey=...) to get a single item, but only if exactly these two
            # kwargs are present.
            account = self.folder_collection.account
            item_id = self._item_id_field.field.clean(kwargs['item_id'], version=account.version)
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
        new_qs = self.copy()
        new_qs.only_fields = tuple()
        new_qs.order_fields = None
        new_qs.return_format = self.NONE
        new_qs.page_size = page_size
        return len(list(new_qs.__iter__()))

    def exists(self):
        """ Find out if the query contains any hits, with as little effort as possible """
        if self.is_cached:
            return len(self._cache) > 0
        new_qs = self.copy()
        new_qs.max_items = 1
        return new_qs.count(page_size=1) > 0

    def delete(self, page_size=1000):
        """ Delete the items matching the query, with as little effort as possible. 'page_size' is the number of items
        to fetch and delete from the server per request. We're only fetching the IDs, so keep it high"""
        from .items import ALL_OCCURRENCIES
        if self.is_cached:
            res = self.folder_collection.account.bulk_delete(
                ids=self._cache,
                affected_task_occurrences=ALL_OCCURRENCIES,
                chunk_size=page_size,
            )
            self._cache = None  # Invalidate the cache after delete, regardless of the results
            return res
        new_qs = self.copy()
        new_qs.only_fields = tuple()
        new_qs.order_fields = None
        new_qs.return_format = self.NONE
        new_qs.page_size = page_size
        return self.folder_collection.account.bulk_delete(
            ids=new_qs,
            affected_task_occurrences=ALL_OCCURRENCIES,
            chunk_size=page_size,
        )

    def __str__(self):
        fmt_args = [('q', str(self.q)), ('folders', '[%s]' % ', '.join(str(f) for f in self.folder_collection.folders))]
        if self.is_cached:
            fmt_args.append(('len', str(len(self))))
        return self.__class__.__name__ + '(%s)' % ', '.join('%s=%s' % (k, v) for k, v in fmt_args)
