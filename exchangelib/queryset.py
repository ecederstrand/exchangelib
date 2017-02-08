# coding=utf-8
from __future__ import unicode_literals

import logging
from copy import deepcopy
from operator import attrgetter

from future.utils import python_2_unicode_compatible
from six import string_types

from .restriction import Q
from .services import IdOnly

log = logging.getLogger(__name__)


class MultipleObjectsReturned(Exception):
    pass


class DoesNotExist(Exception):
    pass


@python_2_unicode_compatible
class QuerySet(object):
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

    def __init__(self, folder):
        self.folder = folder
        self.q = Q()
        self.only_fields = None
        self.order_fields = None
        self.reversed = False
        self.return_format = self.NONE
        self.calendar_view = None
        self.page_size = None

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
        assert isinstance(self.q, (type(None), Q))
        assert isinstance(self.only_fields, (type(None), tuple))
        assert isinstance(self.order_fields, (type(None), tuple))
        assert self.reversed in (True, False)
        assert self.return_format in self.RETURN_TYPES
        # Only mutable objects need to be deepcopied. Folder should be the same object
        new_qs = self.__class__(self.folder)
        new_qs.q = None if self.q is None else deepcopy(self.q)
        new_qs.only_fields = self.only_fields
        new_qs.order_fields = self.order_fields
        new_qs.reversed = self.reversed
        new_qs.return_format = self.return_format
        new_qs.calendar_view = self.calendar_view
        return new_qs

    def _check_fields(self, field_names):
        allowed_field_names = set(self.folder.allowed_field_names()) | {'item_id', 'changekey'}
        for f in field_names:
            if not isinstance(f, string_types):
                raise ValueError("Fieldname '%s' must be a string" % f)
            if f not in allowed_field_names:
                raise ValueError("Unknown fieldname '%s'" % f)

    def _query(self):
        if self.only_fields is None:
            # The list of fields was not restricted. Get all fields we support, as a set
            additional_fields = self.folder.allowed_field_names()
        else:
            assert isinstance(self.only_fields, tuple)
            # Remove ItemId and ChangeKey. We get them unconditionally
            additional_fields = {f for f in self.only_fields if f not in {'item_id', 'changekey'}}
        complex_fields_requested = bool(additional_fields & self.folder.complex_field_names())
        if self.order_fields:
            extra_order_fields = {f.lstrip('-') for f in self.order_fields} - additional_fields
        else:
            extra_order_fields = set()
        if extra_order_fields:
            # Also fetch order_by fields that we only need for sorting
            additional_fields.update(extra_order_fields)
        find_item_kwargs = dict(
            additional_fields=None,
            shape=IdOnly,
            calendar_view=self.calendar_view,
            page_size=self.page_size,
        )
        if not additional_fields and not self.order_fields:
            # TODO: if self.order_fields only contain item_id or changekey, we can still take this shortcut
            # We requested no additional fields and we need to do no sorting, so we can take a shortcut by setting
            # additional_fields=None. This tells find_items() to do less work
            assert not complex_fields_requested
            return self.folder.find_items(self.q, **find_item_kwargs)
        if complex_fields_requested:
            # The FindItems service does not support complex field types. Fallback to getting ids and calling GetItems
            items = self.folder.fetch(
                ids=self.folder.find_items(self.q, **find_item_kwargs),
                only_fields=additional_fields
            )
        else:
            find_item_kwargs['additional_fields'] = additional_fields
            items = self.folder.find_items(self.q, **find_item_kwargs)
        if self.order_fields:
            # Ordering and reversing is greedy
            assert isinstance(self.order_fields, tuple)
            # Sorting in Python is stable, so when we search on multiple fields, we can do a sort on each of the
            # requested fields in reverse order. Reverse each sort operation if the field is prefixed with '-'
            for f in reversed(self.order_fields):
                items = sorted(items, key=attrgetter(f.lstrip('-')), reverse=f.startswith('-'))
            if self.reversed:
                items = reversed(items)
            if extra_order_fields:
                # Nullify the fields we only needed for sorting
                def clean_item(i):
                    for f in extra_order_fields:
                        setattr(i, f, None)
                    return i

                return (clean_item(i) for i in items)
        return items

    def __iter__(self):
        # Fill cache if this is the first iteration. Return an iterator over the results. Make this non-greedy by
        # filling the cache while we are iterating.
        #
        # We don't set self._cache until the iterator is finished. Otherwise an interrupted iterator would leave the
        # cache in an inconsistent state.
        if self._cache is not None:
            for val in self._cache:
                yield val
            return

        log.debug('Initializing cache')
        if self.q is None:
            self._cache = []
            return

        _cache = []
        result_formatter = {
            self.VALUES: self.as_values,
            self.VALUES_LIST: self.as_values_list,
            self.FLAT: self.as_flat_values_list,
            self.NONE: lambda res_iter: res_iter,
        }[self.return_format]
        for val in result_formatter(self._query()):
            _cache.append(val)
            yield val
        self._cache = _cache

    def __len__(self):
        if self._cache is not None:
            return len(self._cache)
        # This queryset has no cache yet. Call the optimized counting implementation
        return self.count()

    def __getitem__(self, key):
        # Support indexing and slicing
        list(self.__iter__())  # Make sure cache is full by iterating the full query result
        return self._cache[key]

    def as_values(self, iterable):
        if len(self.only_fields) == 0:
            raise ValueError('values() requires at least one field name')
        additional_fields = tuple(f for f in self.only_fields if f not in {'item_id', 'changekey'})
        if not additional_fields and not self.order_fields:
            # _query() will return an iterator of (item_id, changekey) tuples
            if 'changekey' not in self.only_fields:
                for item_id, changekey in iterable:
                    yield {'item_id': item_id}
            elif 'item_id' not in self.only_fields:
                for item_id, changekey in iterable:
                    yield {'changekey': changekey}
            else:
                for item_id, changekey in iterable:
                    yield {'item_id': item_id, 'changekey': changekey}
            return
        for i in iterable:
            yield {k: getattr(i, k) for k in self.only_fields}

    def as_values_list(self, iterable):
        if len(self.only_fields) == 0:
            raise ValueError('values_list() requires at least one field name')
        additional_fields = tuple(f for f in self.only_fields if f not in {'item_id', 'changekey'})

        if not additional_fields and not self.order_fields:
            # _query() will return an iterator of (item_id, changekey) tuples
            if 'changekey' not in self.only_fields:
                for item_id, changekey in iterable:
                    yield (item_id,)
            elif 'item_id' not in self.only_fields:
                for item_id, changekey in iterable:
                    yield (changekey,)
            else:
                for item_id, changekey in iterable:
                    yield (item_id, changekey)
            return
        for i in iterable:
            yield tuple(getattr(i, f) for f in self.only_fields)

    def as_flat_values_list(self, iterable):
        if len(self.only_fields) != 1:
            raise ValueError('flat=True requires exactly one field name')
        additional_fields = tuple(f for f in self.only_fields if f not in {'item_id', 'changekey'})

        if not additional_fields and not self.order_fields:
            # _query() will return an iterator of (item_id, changekey) tuples
            if 'item_id' in self.only_fields:
                for item_id, changekey in iterable:
                    yield item_id
            elif 'changekey' in self.only_fields:
                for item_id, changekey in iterable:
                    yield changekey
            else:
                assert False
            return
        for i in iterable:
            yield getattr(i, self.only_fields[0])

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
        """ Return a query that is quaranteed to be empty  """
        new_qs = self.copy()
        new_qs.q = None
        return new_qs

    def filter(self, *args, **kwargs):
        """ Return everything that matches these search criteria """
        new_qs = self.copy()
        q = Q.from_filter_args(self.folder.__class__, *args, **kwargs) or Q()
        new_qs.q = q if new_qs.q is None else new_qs.q & q
        return new_qs

    def exclude(self, *args, **kwargs):
        """ Return everything that does NOT match these search criteria """
        new_qs = self.copy()
        q = ~Q.from_filter_args(self.folder.__class__, *args, **kwargs) or Q()
        new_qs.q = q if new_qs.q is None else new_qs.q & q
        return new_qs

    def only(self, *args):
        """ Fetch only the specified field names. All other item fields will be 'None' """
        try:
            self._check_fields(args)
        except ValueError as e:
            raise ValueError("%s in only()" % e.args[0])
        new_qs = self.copy()
        new_qs.only_fields = args
        return new_qs

    def order_by(self, *args):
        """ Return the query result sorted by the specified field names. Field names prefixed with '-' will be sorted
        in reverse order. This will make the query greedy """
        try:
            self._check_fields(f.lstrip('-') for f in args)
        except ValueError as e:
            raise ValueError("%s in order_by()" % e.args[0])
        new_qs = self.copy()
        new_qs.order_fields = args
        return new_qs

    def reverse(self):
        """ Return the entire query result in reverse order. This will make the query greedy """
        new_qs = self.copy()
        if not self.order_fields:
            raise ValueError('Reversing only makes sense if there are order_by fields')
        new_qs.reversed = not self.reversed
        return new_qs

    def values(self, *args):
        """ Return the values of the specified field names as dicts """
        try:
            self._check_fields(args)
        except ValueError as e:
            raise ValueError("%s in values()" % e.args[0])
        new_qs = self.copy()
        new_qs.only_fields = args
        new_qs.return_format = self.VALUES
        return new_qs

    def values_list(self, *args, **kwargs):
        """ Return the values of the specified field names as lists. If called with flat=True and only one field name,
        return only this value instead of a list.

        Allow an arbitrary list of fields in *args, possibly ending with flat=True|False"""
        flat = kwargs.pop('flat', False)
        if kwargs:
            raise AttributeError('Unknown kwargs: %s' % kwargs)
        try:
            self._check_fields(args)
        except ValueError as e:
            raise ValueError("%s in values_list()" % e.args[0])
        new_qs = self.copy()
        new_qs.only_fields = args
        new_qs.return_format = self.FLAT if flat else self.VALUES_LIST
        return new_qs

    ###########################
    #
    # Methods that end chaining
    #
    ###########################
    def iterator(self, page_size=None):
        """ Return the query result as an iterator, without caching the result. 'page_size' is the number of items to
        fetch from the server per request. """
        if self._cache is not None:
            return self._cache
        # Return an iterator that doesn't bother with caching
        self.page_size = page_size
        return self._query()

    def get(self, *args, **kwargs):
        """ Assume the query will return exactly one item. Return that item """
        if self._cache is not None and not args and not kwargs:
            # We can only safely use the cache if get() is called without args
            items = self._cache
        else:
            new_qs = self.filter(*args, **kwargs)
            items = list(new_qs.__iter__())
        if len(items) == 0:
            raise DoesNotExist()
        if len(items) != 1:
            raise MultipleObjectsReturned()
        return items[0]

    def count(self):
        """ Get the query count, with as little effort as possible """
        if self._cache is not None:
            return len(self._cache)
        new_qs = self.copy()
        new_qs.only_fields = tuple()
        new_qs.order_fields = None
        new_qs.reversed = False
        new_qs.return_format = self.NONE
        return len(list(new_qs.__iter__()))

    def exists(self):
        """ Find out if the query contains any hits, with as little effort as possible """
        return self.count() > 0

    def delete(self):
        """ Delete the items matching the query, with as little effort as possible """
        from .folders import ALL_OCCURRENCIES
        if self._cache is not None:
            return self.folder.account.bulk_delete(ids=self._cache, affected_task_occurrences=ALL_OCCURRENCIES)
        new_qs = self.copy()
        new_qs.only_fields = tuple()
        new_qs.order_fields = None
        new_qs.reversed = False
        new_qs.return_format = self.NONE
        return self.folder.account.bulk_delete(ids=new_qs, affected_task_occurrences=ALL_OCCURRENCIES)
