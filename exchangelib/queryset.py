import abc
import logging
from contextlib import suppress
from copy import deepcopy
from itertools import islice

from .errors import DoesNotExist, ErrorItemNotFound, InvalidEnumValue, InvalidTypeError, MultipleObjectsReturned
from .fields import FieldOrder, FieldPath
from .items import ID_ONLY, CalendarItem
from .properties import InvalidField
from .restriction import Q
from .version import EXCHANGE_2010

log = logging.getLogger(__name__)

MISSING_ITEM_ERRORS = (ErrorItemNotFound,)


class SearchableMixIn:
    """Implement a search API for inheritance."""

    @abc.abstractmethod
    def get(self, *args, **kwargs):
        """Return a single object"""

    @abc.abstractmethod
    def all(self):
        """Return all objects, unfiltered"""

    @abc.abstractmethod
    def none(self):
        """Return an empty result"""

    @abc.abstractmethod
    def filter(self, *args, **kwargs):
        """Apply filters to a query"""

    @abc.abstractmethod
    def exclude(self, *args, **kwargs):
        """Apply filters to a query"""

    @abc.abstractmethod
    def people(self):
        """Search for personas"""


class QuerySet(SearchableMixIn):
    """A Django QuerySet-like class for querying items. Defers query until the QuerySet is consumed. Supports
    chaining to build up complex queries.

    Django QuerySet documentation: https://docs.djangoproject.com/en/dev/ref/models/querysets/
    """

    VALUES = "values"
    VALUES_LIST = "values_list"
    FLAT = "flat"
    NONE = "none"
    RETURN_TYPES = (VALUES, VALUES_LIST, FLAT, NONE)

    ITEM = "item"
    PERSONA = "persona"
    REQUEST_TYPES = (ITEM, PERSONA)

    def __init__(self, folder_collection, request_type=ITEM):
        from .folders import FolderCollection

        if not isinstance(folder_collection, FolderCollection):
            raise InvalidTypeError("folder_collection", folder_collection, FolderCollection)
        self.folder_collection = folder_collection  # A FolderCollection instance
        if request_type not in self.REQUEST_TYPES:
            raise InvalidEnumValue("request_type", request_type, self.REQUEST_TYPES)
        self.request_type = request_type
        self.q = Q()  # Default to no restrictions
        self.only_fields = None
        self.order_fields = None
        self.return_format = self.NONE
        self.calendar_view = None
        self.page_size = None
        self.chunk_size = None
        self.max_items = None
        self.offset = 0
        self._depth = None

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
        # Only mutable objects need to be deepcopied. Folder should be the same object
        new_qs = self.__class__(self.folder_collection, request_type=self.request_type)
        new_qs.q = deepcopy(self.q)
        new_qs.only_fields = self.only_fields
        new_qs.order_fields = None if self.order_fields is None else deepcopy(self.order_fields)
        new_qs.return_format = self.return_format
        new_qs.calendar_view = self.calendar_view
        new_qs.page_size = self.page_size
        new_qs.chunk_size = self.chunk_size
        new_qs.max_items = self.max_items
        new_qs.offset = self.offset
        new_qs._depth = self._depth
        return new_qs

    def _get_field_path(self, field_path):
        from .items import Persona

        if self.request_type == self.PERSONA:
            return FieldPath(field=Persona.get_field_by_fieldname(field_path))
        for folder in self.folder_collection:
            with suppress(InvalidField):
                return FieldPath.from_string(field_path=field_path, folder=folder)
        raise InvalidField(f"Unknown field path {field_path!r} on folders {self.folder_collection.folders}")

    def _get_field_order(self, field_path):
        from .items import Persona

        if self.request_type == self.PERSONA:
            return FieldOrder(
                field_path=FieldPath(field=Persona.get_field_by_fieldname(field_path.lstrip("-"))),
                reverse=field_path.startswith("-"),
            )
        for folder in self.folder_collection:
            with suppress(InvalidField):
                return FieldOrder.from_string(field_path=field_path, folder=folder)
        raise InvalidField(f"Unknown field path {field_path!r} on folders {self.folder_collection.folders}")

    @property
    def _id_field(self):
        return self._get_field_path("id")

    @property
    def _changekey_field(self):
        return self._get_field_path("changekey")

    def _additional_fields(self):
        if not isinstance(self.only_fields, tuple):
            raise InvalidTypeError("only_fields", self.only_fields, tuple)
        # Remove ItemId and ChangeKey. We get them unconditionally
        additional_fields = {f for f in self.only_fields if not f.field.is_attribute}
        if self.request_type != self.ITEM:
            return additional_fields

        # For CalendarItem items, we want to inject internal timezone fields into the requested fields.
        has_start = "start" in {f.field.name for f in additional_fields}
        has_end = "end" in {f.field.name for f in additional_fields}
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
        if self.only_fields is None:
            # We didn't restrict list of field paths. Get all fields from the server, including extended properties.
            if self.request_type == self.PERSONA:
                additional_fields = {}  # GetPersona doesn't take explicit fields. Don't bother calculating the list
                complex_fields_requested = True
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

        find_kwargs = dict(
            shape=ID_ONLY,  # Always use IdOnly here, because AllProperties doesn't actually get *all* properties
            depth=self._depth,
            additional_fields=additional_fields,
            order_fields=order_fields,
            page_size=self.page_size,
            max_items=self.max_items,
            offset=self.offset,
        )
        if self.request_type == self.PERSONA:
            if complex_fields_requested:
                find_kwargs["additional_fields"] = None
                items = self.folder_collection.account.fetch_personas(
                    ids=self.folder_collection.find_people(self.q, **find_kwargs)
                )
            else:
                if not additional_fields:
                    find_kwargs["additional_fields"] = None
                items = self.folder_collection.find_people(self.q, **find_kwargs)
        else:
            find_kwargs["calendar_view"] = self.calendar_view
            if complex_fields_requested:
                # The FindItem service does not support complex field types. Tell find_items() to return
                # (id, changekey) tuples, and pass that to fetch().
                find_kwargs["additional_fields"] = None
                unfiltered_items = self.folder_collection.account.fetch(
                    ids=self.folder_collection.find_items(self.q, **find_kwargs),
                    only_fields=additional_fields,
                    chunk_size=self.chunk_size,
                )
                # We may be unlucky that the item disappeared between the FindItem and the GetItem calls
                items = filter(lambda i: not isinstance(i, MISSING_ITEM_ERRORS), unfiltered_items)
            else:
                if not additional_fields:
                    # If additional_fields is the empty set, we only requested ID and changekey fields. We can then
                    # take a shortcut by using (shape=ID_ONLY, additional_fields=None) to tell find_items() to return
                    # (id, changekey) tuples. We'll post-process those later.
                    find_kwargs["additional_fields"] = None
                items = self.folder_collection.find_items(self.q, **find_kwargs)

        if not must_sort_clientside:
            return items

        # Resort to client-side sorting of the order_by fields. This is greedy. Sorting in Python is stable, so when
        # sorting on multiple fields, we can just do a sort on each of the requested fields in reverse order. Reverse
        # each sort operation if the field was marked as such.
        for f in reversed(self.order_fields):
            try:
                items = sorted(items, key=lambda i: _get_sort_value_or_default(i, f), reverse=f.reverse)
            except TypeError as e:
                if "unorderable types" not in e.args[0]:
                    raise
                raise ValueError(
                    f"Cannot sort on field {f.field_path!r}. The field has no default value defined, and there are "
                    f"either items with None values for this field, or the query contains exception instances "
                    f"(original error: {e})."
                )
        if not extra_order_fields:
            return items

        # Nullify the fields we only needed for sorting before returning
        return (_rinse_item(i, extra_order_fields) for i in items)

    def __iter__(self):
        # Fill cache if this is the first iteration. Return an iterator over the results. Make this non-greedy by
        # filling the cache while we are iterating.
        #
        if self.q.is_never():
            return

        log.debug("Initializing cache")
        yield from self._format_items(items=self._query(), return_format=self.return_format)

    # Do not implement __len__. The implementation of list() tries to preallocate memory by calling __len__ on the
    # given sequence, before calling __iter__. If we implemented __len__, we would end up calling FindItems twice, once
    # to get the result of self.count(), and once to return the actual result.
    #
    # Also, according to https://stackoverflow.com/questions/37189968/how-to-have-list-consume-iter-without-calling-len,
    # a __len__ implementation should be cheap. That does not hold for self.count().
    #
    # def __len__(self):
    #     return self.count()

    def __getitem__(self, idx_or_slice):
        # Support indexing and slicing. This is non-greedy when possible (slicing start, stop and step are not negative,
        # and we're ordering on at most one field), and will only fill the cache if the entire query is iterated.
        if isinstance(idx_or_slice, int):
            return self._getitem_idx(idx_or_slice)
        return self._getitem_slice(idx_or_slice)

    def _getitem_idx(self, idx):
        if idx < 0:
            # Support negative indexes by reversing the queryset and negating the index value
            reverse_idx = -(idx + 1)
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
        from .services import FindItem

        if ((s.start or 0) < 0) or ((s.stop or 0) < 0) or ((s.step or 0) < 0):
            # islice() does not support negative start, stop and step. Make sure cache is full by iterating the full
            # query result, and then slice on the cache.
            return list(self.__iter__())[s]
        # Optimize by setting an exact offset and max_items value
        new_qs = self._copy_self()
        if s.start is not None and s.stop is not None:
            new_qs.offset = s.start
            new_qs.max_items = s.stop - s.start
        elif s.start is not None:
            new_qs.offset = s.start
        elif s.stop is not None:
            new_qs.max_items = s.stop
        if new_qs.page_size is None and new_qs.max_items is not None and new_qs.max_items < FindItem.PAGE_SIZE:
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
            elif self._id_field not in self.only_fields:
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
            raise ValueError("values() requires at least one field name")
        return self._item_yielder(
            iterable=iterable,
            item_func=lambda i: {f.path: _get_value_or_default(f, i) for f in self.only_fields},
            id_only_func=lambda item_id, changekey: {"id": item_id},
            changekey_only_func=lambda item_id, changekey: {"changekey": changekey},
            id_and_changekey_func=lambda item_id, changekey: {"id": item_id, "changekey": changekey},
        )

    def _as_values_list(self, iterable):
        if not self.only_fields:
            raise ValueError("values_list() requires at least one field name")
        return self._item_yielder(
            iterable=iterable,
            item_func=lambda i: tuple(_get_value_or_default(f, i) for f in self.only_fields),
            id_only_func=lambda item_id, changekey: (item_id,),
            changekey_only_func=lambda item_id, changekey: (changekey,),
            id_and_changekey_func=lambda item_id, changekey: (item_id, changekey),
        )

    def _as_flat_values_list(self, iterable):
        if not self.only_fields or len(self.only_fields) != 1:
            raise ValueError("flat=True requires exactly one field name")
        return self._item_yielder(
            iterable=iterable,
            item_func=lambda i: _get_value_or_default(self.only_fields[0], i),
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
        """ """
        new_qs = self._copy_self()
        return new_qs

    def none(self):
        """ """
        new_qs = self._copy_self()
        new_qs.q = Q(conn_type=Q.NEVER)
        return new_qs

    def filter(self, *args, **kwargs):
        new_qs = self._copy_self()
        q = Q(*args, **kwargs)
        new_qs.q = new_qs.q & q
        return new_qs

    def exclude(self, *args, **kwargs):
        new_qs = self._copy_self()
        q = ~Q(*args, **kwargs)
        new_qs.q = new_qs.q & q
        return new_qs

    def people(self):
        """Change the queryset to search the folder for Personas instead of Items."""
        new_qs = self._copy_self()
        new_qs.request_type = self.PERSONA
        return new_qs

    def only(self, *args):
        """Fetch only the specified field names. All other item fields will be 'None'."""
        try:
            only_fields = tuple(self._get_field_path(arg) for arg in args)
        except ValueError as e:
            raise ValueError(f"{e.args[0]} in only()")
        new_qs = self._copy_self()
        new_qs.only_fields = only_fields
        return new_qs

    def order_by(self, *args):
        """

        :return: The QuerySet in reverse order. EWS only supports server-side sorting on a single field. Sorting on
          multiple fields is implemented client-side and will therefore make the query greedy.
        """
        try:
            order_fields = tuple(self._get_field_order(arg) for arg in args)
        except ValueError as e:
            raise ValueError(f"{e.args[0]} in order_by()")
        new_qs = self._copy_self()
        new_qs.order_fields = order_fields
        return new_qs

    def reverse(self):
        """Reverses the ordering of the queryset."""
        if not self.order_fields:
            raise ValueError("Reversing only makes sense if there are order_by fields")
        new_qs = self._copy_self()
        for f in new_qs.order_fields:
            f.reverse = not f.reverse
        return new_qs

    def values(self, *args):
        try:
            only_fields = tuple(self._get_field_path(arg) for arg in args)
        except ValueError as e:
            raise ValueError(f"{e.args[0]} in values()")
        new_qs = self._copy_self()
        new_qs.only_fields = only_fields
        new_qs.return_format = self.VALUES
        return new_qs

    def values_list(self, *args, **kwargs):
        """Return the values of the specified field names as a list of lists. If called with flat=True and only one
        field name, returns a list of values.
        """
        flat = kwargs.pop("flat", False)
        if kwargs:
            raise AttributeError(f"Unknown kwargs: {kwargs}")
        if flat and len(args) != 1:
            raise ValueError("flat=True requires exactly one field name")
        try:
            only_fields = tuple(self._get_field_path(arg) for arg in args)
        except ValueError as e:
            raise ValueError(f"{e.args[0]} in values_list()")
        new_qs = self._copy_self()
        new_qs.only_fields = only_fields
        new_qs.return_format = self.FLAT if flat else self.VALUES_LIST
        return new_qs

    def depth(self, depth):
        """Specify the search depth. Possible values are: SHALLOW, ASSOCIATED or DEEP.

        :param depth:
        """
        new_qs = self._copy_self()
        new_qs._depth = depth
        return new_qs

    ###########################
    #
    # Methods that end chaining
    #
    ###########################

    def get(self, *args, **kwargs):
        """Assume the query will return exactly one item. Return that item."""
        if not args and set(kwargs) in ({"id"}, {"id", "changekey"}):
            # We allow calling get(id=..., changekey=...) to get a single item, but only if exactly these two
            # kwargs are present.
            account = self.folder_collection.account
            item_id = self._id_field.field.clean(kwargs["id"], version=account.version)
            changekey = self._changekey_field.field.clean(kwargs.get("changekey"), version=account.version)
            # The folders we're querying may not support all fields
            if self.only_fields is None:
                only_fields = {FieldPath(field=f) for f in self.folder_collection.allowed_item_fields()}
            else:
                only_fields = self.only_fields
            items = list(account.fetch(ids=[(item_id, changekey)], only_fields=only_fields))
        else:
            new_qs = self.filter(*args, **kwargs)
            items = list(new_qs.__iter__())
        if not items:
            raise DoesNotExist()
        if len(items) != 1:
            raise MultipleObjectsReturned()
        item = items[0]
        if isinstance(item, Exception):
            raise item
        return item

    def count(self, page_size=1000):
        """Get the query count, with as little effort as possible

        :param page_size: The number of items to fetch per request. We're only fetching the IDs, so keep it high.
        (Default value = 1000)
        """
        new_qs = self._copy_self()
        new_qs.only_fields = ()
        new_qs.order_fields = None
        new_qs.return_format = self.NONE
        new_qs.page_size = page_size
        # 'chunk_size' not needed since we never need to call GetItem
        return len(list(new_qs.__iter__()))

    def exists(self):
        """Find out if the query contains any hits, with as little effort as possible."""
        new_qs = self._copy_self()
        new_qs.max_items = 1
        return new_qs.count(page_size=1) > 0

    def _id_only_copy_self(self):
        new_qs = self._copy_self()
        new_qs.only_fields = ()
        new_qs.order_fields = None
        new_qs.return_format = self.NONE
        return new_qs

    def delete(self, page_size=1000, chunk_size=100, **delete_kwargs):
        """Delete the items matching the query, with as little effort as possible

        :param page_size: The number of items to fetch per request. We're only fetching the IDs, so keep it high.
        (Default value = 1000)
        :param chunk_size: The number of items to delete per request. (Default value = 100)
        :param delete_kwargs:
        """
        ids = self._id_only_copy_self()
        ids.page_size = page_size
        return self.folder_collection.account.bulk_delete(ids=ids, chunk_size=chunk_size, **delete_kwargs)

    def send(self, page_size=1000, chunk_size=100, **send_kwargs):
        """Send the items matching the query, with as little effort as possible

        :param page_size: The number of items to fetch per request. We're only fetching the IDs, so keep it high.
        (Default value = 1000)
        :param chunk_size: The number of items to send per request. (Default value = 100)
        :param send_kwargs:
        """
        ids = self._id_only_copy_self()
        ids.page_size = page_size
        return self.folder_collection.account.bulk_send(ids=ids, chunk_size=chunk_size, **send_kwargs)

    def copy(self, to_folder, page_size=1000, chunk_size=100, **copy_kwargs):
        """Copy the items matching the query, with as little effort as possible

        :param to_folder:
        :param page_size: The number of items to fetch per request. We're only fetching the IDs, so keep it high.
        (Default value = 1000)
        :param chunk_size: The number of items to copy per request. (Default value = 100)
        :param copy_kwargs:
        """
        ids = self._id_only_copy_self()
        ids.page_size = page_size
        return self.folder_collection.account.bulk_copy(
            ids=ids, to_folder=to_folder, chunk_size=chunk_size, **copy_kwargs
        )

    def move(self, to_folder, page_size=1000, chunk_size=100):
        """Move the items matching the query, with as little effort as possible. 'page_size' is the number of items
        to fetch and move per request. We're only fetching the IDs, so keep it high.

        :param to_folder:
        :param page_size: The number of items to fetch per request. We're only fetching the IDs, so keep it high.
        (Default value = 1000)
        :param chunk_size: The number of items to move per request. (Default value = 100)
        """
        ids = self._id_only_copy_self()
        ids.page_size = page_size
        return self.folder_collection.account.bulk_move(
            ids=ids,
            to_folder=to_folder,
            chunk_size=chunk_size,
        )

    def archive(self, to_folder, page_size=1000, chunk_size=100):
        """Archive the items matching the query, with as little effort as possible. 'page_size' is the number of items
        to fetch and move per request. We're only fetching the IDs, so keep it high.

        :param to_folder:
        :param page_size: The number of items to fetch per request. We're only fetching the IDs, so keep it high.
        (Default value = 1000)
        :param chunk_size: The number of items to archive per request. (Default value = 100)
        """
        ids = self._id_only_copy_self()
        ids.page_size = page_size
        return self.folder_collection.account.bulk_archive(
            ids=ids,
            to_folder=to_folder,
            chunk_size=chunk_size,
        )

    def mark_as_junk(self, page_size=1000, chunk_size=1000, **mark_as_junk_kwargs):
        """Mark the items matching the query as junk, with as little effort as possible. 'page_size' is the number of
        items to fetch and mark per request. We're only fetching the IDs, so keep it high.

        :param page_size: The number of items to fetch per request. We're only fetching the IDs, so keep it high.
        (Default value = 1000)
        :param chunk_size: The number of items to mark as junk per request. (Default value = 100)
        :param mark_as_junk_kwargs:
        """
        ids = self._id_only_copy_self()
        ids.page_size = page_size
        return self.folder_collection.account.bulk_mark_as_junk(ids=ids, chunk_size=chunk_size, **mark_as_junk_kwargs)

    def __str__(self):
        fmt_args = [("q", str(self.q)), ("folders", f"[{', '.join(str(f) for f in self.folder_collection.folders)}]")]
        args_str = ", ".join(f"{k}={v}" for k, v in fmt_args)
        return f"{self.__class__.__name__}({args_str})"


def _get_value_or_default(field, item):
    # When we request specific fields using .values() or .values_list(), the incoming item type may not have the field
    # we are requesting. Return None when this happens instead of raising an AttributeError.
    try:
        return field.get_value(item)
    except AttributeError:
        return None


def _get_sort_value_or_default(item, field_order):
    # Python can only sort values when <, > and = are implemented for the two types. Try as best we can to sort
    # items, even when the item may have a None value for the field in question, or when the item is an
    # Exception. In that case, we calculate a default value and sort all None values and exceptions as the default
    # value.
    if isinstance(item, Exception):
        return _default_field_value(field_order.field_path.field)
    val = field_order.field_path.get_sort_value(item)
    if val is None:
        return _default_field_value(field_order.field_path.field)
    return val


def _default_field_value(field):
    """Return the default value of a field. If the field does not have a default value, try creating an empty instance
    of the field value class. If that doesn't work, there's really nothing we can do about it; we'll raise an error.
    """
    return field.default or ([field.value_cls()] if field.is_list else field.value_cls())


def _rinse_item(i, fields_to_nullify):
    """Set fields in fields_to_nullify to None. Make sure to accept exceptions."""
    if isinstance(i, Exception):
        return i
    for f in fields_to_nullify:
        setattr(i, f.field.name, None)
    return i
