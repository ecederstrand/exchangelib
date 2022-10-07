import abc
import datetime
import time
import unittest
import unittest.util
from decimal import Decimal
from keyword import kwlist

from dateutil.relativedelta import relativedelta

from exchangelib.errors import (
    ErrorInvalidPropertySet,
    ErrorInvalidValueForProperty,
    ErrorItemNotFound,
    ErrorPropertyUpdate,
    ErrorUnsupportedPathForQuery,
)
from exchangelib.extended_properties import ExternId
from exchangelib.fields import (
    AttachmentField,
    BodyField,
    BooleanField,
    ChoiceField,
    CultureField,
    FieldPath,
    IdField,
    IndexedField,
    TextField,
)
from exchangelib.indexed_properties import MultiFieldIndexedElement, SingleFieldIndexedElement
from exchangelib.items import BaseItem, CalendarItem, Contact, DistributionList, Item, Task
from exchangelib.properties import Attendee, Mailbox
from exchangelib.queryset import Q
from exchangelib.util import value_to_xml_text

from ..common import (
    EWSTest,
    get_random_choice,
    get_random_date,
    get_random_datetime,
    get_random_datetime_range,
    get_random_decimal,
    get_random_string,
    get_random_substring,
)


class BaseItemTest(EWSTest, metaclass=abc.ABCMeta):
    TEST_FOLDER = None
    FOLDER_CLASS = None
    ITEM_CLASS = None

    @classmethod
    def setUpClass(cls):
        if cls is BaseItemTest:
            raise unittest.SkipTest("Skip BaseItemTest, it's only for inheritance")
        super().setUpClass()

    def setUp(self):
        super().setUp()
        if self.TEST_FOLDER:
            self.test_folder = getattr(self.account, self.TEST_FOLDER)
        else:
            self.test_folder = self.get_test_folder(self.account.inbox).save()

    def tearDown(self):
        # Delete all test items and delivery receipts
        try:
            self.test_folder.filter(
                Q(categories__contains=self.categories) | Q(subject__startswith="Delivered: Subject: ")
            ).delete()
            if not self.TEST_FOLDER:
                self.test_folder.delete()
        except Exception as e:
            print(f"Exception in tearDown of {self}: {e}")
            pass
        super().tearDown()

    def get_random_insert_kwargs(self):
        insert_kwargs = {}
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_read_only:
                # These cannot be created
                continue
            if f.name == "mime_content":
                # This needs special formatting. See separate test_mime_content() test
                continue
            if f.name == "attachments":
                # Testing attachments is heavy. Leave this to specific tests
                insert_kwargs[f.name] = []
                continue
            if f.name == "resources":
                # The test server doesn't have any resources
                insert_kwargs[f.name] = []
                continue
            if f.name == "optional_attendees":
                # 'optional_attendees' and 'required_attendees' are mutually exclusive
                insert_kwargs[f.name] = None
                continue
            if f.name == "start":
                start = get_random_date()
                insert_kwargs[f.name], insert_kwargs["end"] = get_random_datetime_range(
                    start_date=start, end_date=start, tz=self.account.default_timezone
                )
                insert_kwargs["recurrence"] = self.random_val(self.ITEM_CLASS.get_field_by_fieldname("recurrence"))
                insert_kwargs["recurrence"].boundary.start = insert_kwargs[f.name].date()
                continue
            if f.name == "start_date":
                insert_kwargs[f.name] = get_random_datetime().date()
                insert_kwargs["due_date"] = insert_kwargs[f.name]
                # Don't set 'recurrence' here. It's difficult to test updates so we'll test task recurrence separately
                insert_kwargs["recurrence"] = None
                continue
            if f.name == "end":
                continue
            if f.name == "is_all_day":
                # For CalendarItem instances, the 'is_all_day' attribute affects the 'start' and 'end' values. Changing
                # from 'false' to 'true' removes the time part of these datetimes.
                insert_kwargs["is_all_day"] = False
                continue
            if f.name == "recurrence":
                continue
            if f.name == "due_date":
                continue
            if f.name == "start_date":
                continue
            if f.name == "status":
                # Start with an incomplete task
                status = get_random_choice(set(f.supported_choices(version=self.account.version)) - {Task.COMPLETED})
                insert_kwargs[f.name] = status
                if status == Task.NOT_STARTED:
                    insert_kwargs["percent_complete"] = Decimal(0)
                else:
                    insert_kwargs["percent_complete"] = get_random_decimal(1, 99)
                continue
            if f.name == "percent_complete":
                continue
            insert_kwargs[f.name] = self.random_val(f)
        return insert_kwargs

    def get_item_fields(self):
        return (
            self.ITEM_CLASS.get_field_by_fieldname("id"),
            self.ITEM_CLASS.get_field_by_fieldname("changekey"),
        ) + tuple(f for f in self.ITEM_CLASS.FIELDS if f.name != "_id")

    def get_random_update_kwargs(self, item, insert_kwargs):
        update_kwargs = {}
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_read_only:
                # These cannot be changed
                continue
            if not item.is_draft and f.is_read_only_after_send:
                # These cannot be changed when the item is no longer a draft
                continue
            if f.name == "message_id" and f.is_read_only_after_send:
                # Cannot be updated, regardless of draft status
                continue
            if f.name == "attachments":
                # Testing attachments is heavy. Leave this to specific tests
                update_kwargs[f.name] = []
                continue
            if f.name == "resources":
                # The test server doesn't have any resources
                update_kwargs[f.name] = []
                continue
            if isinstance(f, AttachmentField):
                # Attachments are handled separately
                continue
            if f.name == "start":
                start = get_random_date(start_date=insert_kwargs["end"].date())
                update_kwargs[f.name], update_kwargs["end"] = get_random_datetime_range(
                    start_date=start, end_date=start, tz=self.account.default_timezone
                )
                update_kwargs["recurrence"] = self.random_val(self.ITEM_CLASS.get_field_by_fieldname("recurrence"))
                update_kwargs["recurrence"].boundary.start = update_kwargs[f.name].date()
                continue
            if f.name == "start_date":
                update_kwargs[f.name] = get_random_datetime().date()
                update_kwargs["due_date"] = update_kwargs[f.name]
                # Don't set 'recurrence' here. It's difficult to test updates so we'll test task recurrence separately
                update_kwargs["recurrence"] = None
                continue
            if f.name == "end":
                continue
            if f.name == "recurrence":
                continue
            if f.name == "due_date":
                continue
            if f.name == "start_date":
                continue
            if f.name == "status":
                # Update task to a completed state
                update_kwargs[f.name] = Task.COMPLETED
                update_kwargs["percent_complete"] = Decimal(100)
                continue
            if f.name == "percent_complete":
                continue
            if f.name == "reminder_is_set":
                if self.ITEM_CLASS == Task:
                    # Task type doesn't allow updating 'reminder_is_set' to True
                    update_kwargs[f.name] = False
                else:
                    update_kwargs[f.name] = not insert_kwargs[f.name]
                continue
            if isinstance(f, BooleanField):
                update_kwargs[f.name] = not insert_kwargs[f.name]
                continue
            if f.value_cls in (Mailbox, Attendee):
                if insert_kwargs[f.name] is None:
                    update_kwargs[f.name] = self.random_val(f)
                else:
                    update_kwargs[f.name] = None
                continue
            update_kwargs[f.name] = self.random_val(f)
        if self.ITEM_CLASS == CalendarItem:
            # EWS always sets due date to 'start'
            update_kwargs["reminder_due_by"] = update_kwargs["start"]
        if update_kwargs.get("is_all_day", False):
            # For is_all_day items, EWS will remove the time part of start and end values
            update_kwargs["start"] = update_kwargs["start"].date()
            update_kwargs["end"] = (update_kwargs["end"] + datetime.timedelta(days=1)).date()
        return update_kwargs

    def get_test_item(self, folder=None, categories=None):
        item_kwargs = self.get_random_insert_kwargs()
        item_kwargs["categories"] = categories or self.categories
        return self.ITEM_CLASS(folder=folder or self.test_folder, **item_kwargs)

    def get_test_folder(self, folder=None):
        return self.FOLDER_CLASS(parent=folder or self.test_folder, name=get_random_string(8))

    def get_item_by_id(self, item):
        _id, changekey = item if isinstance(item, tuple) else (item.id, item.changekey)
        return self.account.root.get(id=_id, changekey=changekey)


class CommonItemTest(BaseItemTest):
    @classmethod
    def setUpClass(cls):
        if cls is CommonItemTest:
            raise unittest.SkipTest("Skip CommonItemTest, it's only for inheritance")
        super().setUpClass()

    def test_field_names(self):
        # Test that fieldnames don't clash with Python keywords
        for f in self.ITEM_CLASS.FIELDS:
            self.assertNotIn(f.name, kwlist)

    def test_magic(self):
        item = self.get_test_item()
        self.assertIn("subject=", str(item))
        self.assertIn(item.__class__.__name__, repr(item))

    def test_queryset_nonsearchable_fields(self):
        for f in self.get_item_fields():
            with self.subTest(f=f):
                if f.is_searchable or isinstance(f, IdField) or not f.supports_version(self.account.version):
                    continue
                if f.name in ("percent_complete", "allow_new_time_proposal"):
                    # These fields don't raise an error when used in a filter, but also don't match anything in a filter
                    continue
                try:
                    filter_val = f.clean(self.random_val(f))
                    filter_kwargs = {f"{f.name}__in": filter_val} if f.is_list else {f.name: filter_val}

                    # We raise ValueError when searching on an is_searchable=False field
                    with self.assertRaises(ValueError):
                        list(self.test_folder.filter(**filter_kwargs))

                    # Make sure the is_searchable=False setting is correct by searching anyway and testing that this
                    # fails server-side. This only works for values that we are actually able to convert to a search
                    # string.
                    try:
                        value_to_xml_text(filter_val)
                    except TypeError:
                        continue

                    f.is_searchable = True
                    if f.name in ("reminder_due_by", "conversation_index"):
                        # Filtering is accepted but doesn't work
                        self.assertEqual(self.test_folder.filter(**filter_kwargs).count(), 0)
                    else:
                        with self.assertRaises((ErrorUnsupportedPathForQuery, ErrorInvalidValueForProperty)):
                            list(self.test_folder.filter(**filter_kwargs))
                finally:
                    f.is_searchable = False

    def _reduce_fields_for_filter(self, item, fields):
        for f in fields:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if not f.is_searchable:
                # Cannot be used in a QuerySet
                continue
            if getattr(item, f.name) is None:
                # We cannot filter on None values
                continue
            if self.ITEM_CLASS == Contact and f.name in ("body", "display_name"):
                # filtering 'body' or 'display_name' on Contact items doesn't work at all. Error in EWS?
                continue
            yield f

    def _run_filter_tests(self, qs, f, filter_kwargs, val):
        for kw in filter_kwargs:
            with self.subTest(f=f, kw=kw):
                retries = 0
                matches = qs.filter(**kw).count()
                # __in with an empty list returns an empty result
                expected = 0 if f.is_list and not val and list(kw)[0].endswith("__in") else 1
                if f.is_complex and matches != expected:
                    # Complex fields sometimes fail a search using generated data. In practice, they almost always
                    # work anyway. Try a couple of times; it seems EWS has a search index that needs to catch up.
                    if isinstance(f, (BodyField, IndexedField)):
                        # These fields are particularly flaky when filtering. Give up early without failing.
                        continue
                    for _ in range(5):
                        retries += 1
                        time.sleep(retries * retries)  # Exponential sleep
                        matches = qs.filter(**kw).count()
                        if matches == expected:
                            break
                    self.skipTest(f"Filter expression {kw} on complex field still failing after multiple retries")
                self.assertEqual(matches, expected, (f.name, val, kw, retries))

    def test_filter_on_simple_fields(self):
        # Test that we can filter on all simple fields
        item = self.get_test_item()
        fields = []
        for f in self._reduce_fields_for_filter(item, self.get_item_fields()):
            if f.is_list:
                continue
            fields.append(f)
        if not fields:
            self.skipTest("No matching simple fields on this model")
        item.save()
        common_qs = self.test_folder.filter(categories__contains=self.categories)
        for f in fields:
            val = getattr(item, f.name)
            # Filter with =, __in and __contains. We could have more filters here, but these should always match.
            filter_kwargs = [{f.name: val}, {f"{f.name}__in": [val]}]
            if isinstance(f, TextField) and not isinstance(f, ChoiceField):
                # Choice fields cannot be filtered using __contains. Sort of makes sense.
                filter_kwargs.append({f"{f.name}__contains": get_random_substring(val)})
            self._run_filter_tests(common_qs, f, filter_kwargs, val)

    def test_filter_on_list_fields(self):
        # Test that we can filter on all list fields
        item = self.get_test_item()
        fields = []
        for f in self._reduce_fields_for_filter(item, self.get_item_fields()):
            if not f.is_list:
                continue
            if issubclass(f.value_cls, MultiFieldIndexedElement):
                continue
            if issubclass(f.value_cls, SingleFieldIndexedElement):
                continue
            # This test is exceptionally slow. Only test list fields that are not also found on the base Item class
            if self.ITEM_CLASS != Item:
                if f.name in Item.FIELDS:
                    continue
            fields.append(f)
        if not fields:
            self.skipTest("No matching list fields on this model")
        item.save()
        common_qs = self.test_folder.filter(categories__contains=self.categories)
        for f in fields:
            val = getattr(item, f.name)
            # Filter multi-value fields with =, __in and __contains
            # Does not work in O365
            # filter_kwargs = [{f"{f.name}__in": val}, {f"{f.name}__contains": val}]
            filter_kwargs = [{f"{f.name}__in": val}]
            self._run_filter_tests(common_qs, f, filter_kwargs, val)

    def test_filter_on_single_field_index_fields(self):
        # Test that we can filter on all index fields
        item = self.get_test_item()
        fields = []
        for f in self._reduce_fields_for_filter(item, self.get_item_fields()):
            if not issubclass(f.value_cls, SingleFieldIndexedElement):
                continue
            fields.append(f)
        if not fields:
            self.skipTest("No matching single index fields on this model")
        item.save()
        common_qs = self.test_folder.filter(categories__contains=self.categories)
        for f in fields:
            val = getattr(item, f.name)
            # For these, we may filter by item or subfield value
            filter_kwargs = []
            for v in val:
                for subfield in f.value_cls.supported_fields(version=self.account.version):
                    field_path = FieldPath(field=f, label=v.label, subfield=subfield)
                    path, subval = field_path.path, field_path.get_value(item)
                    if subval is None:
                        continue
                    filter_kwargs.extend(
                        [
                            {f.name: v},
                            {path: subval},
                            {f"{path}__in": [subval]},
                            {f"{path}__contains": get_random_substring(subval)},
                        ]
                    )
            self._run_filter_tests(common_qs, f, filter_kwargs, val)

    def test_filter_on_multi_field_index_fields(self):
        # Test that we can filter on all index fields
        item = self.get_test_item()
        fields = []
        for f in self._reduce_fields_for_filter(item, self.get_item_fields()):
            if not issubclass(f.value_cls, MultiFieldIndexedElement):
                continue
            fields.append(f)
        if not fields:
            self.skipTest("No matching multi index fields on this model")
        item.save()
        common_qs = self.test_folder.filter(categories__contains=self.categories)
        for f in fields:
            val = getattr(item, f.name)
            # Filter multi-value fields with =, __in and __contains
            # For these, we need to filter on the subfield
            filter_kwargs = []
            for v in val:
                for subfield in f.value_cls.supported_fields(version=self.account.version):
                    field_path = FieldPath(field=f, label=v.label, subfield=subfield)
                    path, subval = field_path.path, field_path.get_value(item)
                    if subval is None:
                        continue
                    filter_kwargs.extend(
                        [{path: subval}, {f"{path}__in": [subval]}, {f"{path}__contains": get_random_substring(subval)}]
                    )
            self._run_filter_tests(common_qs, f, filter_kwargs, val)

    def test_text_field_settings(self):
        # Test that the max_length and is_complex field settings are correctly set for text fields
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if not isinstance(f, TextField):
                    continue
                if isinstance(f, ChoiceField):
                    # This one can't contain random values
                    continue
                if isinstance(f, CultureField):
                    # This one can't contain random values
                    continue
                if f.is_read_only:
                    continue
                if f.name == "categories":
                    # We're filtering on this one, so leave it alone
                    continue
                item = self.get_test_item().save()
                old_max_length = getattr(f, "max_length", None)
                old_is_complex = f.is_complex
                try:
                    # Set a string long enough to not be handled by FindItems
                    f.max_length = 4000
                    if f.is_list:
                        setattr(
                            item, f.name, [get_random_string(f.max_length) for _ in range(len(getattr(item, f.name)))]
                        )
                    else:
                        setattr(item, f.name, get_random_string(f.max_length))
                    try:
                        item.save(update_fields=[f.name])
                    except ErrorPropertyUpdate:
                        # Some fields throw this error when updated to a huge value
                        self.assertIn(f.name, ["given_name", "middle_name", "surname"])
                        continue
                    except ErrorInvalidPropertySet:
                        # Some fields can not be updated after save
                        self.assertTrue(f.is_read_only_after_send)
                        continue
                    # is_complex=True forces the query to use GetItems which will always get the full value
                    f.is_complex = True
                    new_full_item = self.test_folder.all().only(f.name).get(id=item.id)
                    new_full = getattr(new_full_item, f.name)
                    if old_max_length:
                        if f.is_list:
                            for s in new_full:
                                self.assertEqual(len(s), old_max_length, (f.name, len(s), old_max_length))
                        else:
                            self.assertEqual(len(new_full), old_max_length, (f.name, len(new_full), old_max_length))

                    # is_complex=False forces the query to use FindItems which will only get the short value
                    f.is_complex = False
                    new_short_item = {
                        i.id: i
                        for i in self.test_folder.all().only(f.name).filter(categories__contains=self.categories)
                    }[item.id]
                    new_short = getattr(new_short_item, f.name)

                    if not old_is_complex:
                        self.assertEqual(new_short, new_full, (f.name, new_short, new_full))
                finally:
                    if old_max_length:
                        f.max_length = old_max_length
                    else:
                        delattr(f, "max_length")
                    f.is_complex = old_is_complex

    def test_save_and_delete(self):
        # Test that we can create, update and delete single items using methods directly on the item.
        insert_kwargs = self.get_random_insert_kwargs()
        insert_kwargs["categories"] = self.categories
        item = self.ITEM_CLASS(folder=self.test_folder, **insert_kwargs)
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)

        # Create
        item.save()
        self.assertIsNotNone(item.id)
        self.assertIsNotNone(item.changekey)
        for k, v in insert_kwargs.items():
            self.assertEqual(getattr(item, k), v, (k, getattr(item, k), v))
        # Test that whatever we have locally also matches whatever is in the DB
        fresh_item = self.get_item_by_id(item)
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                old, new = getattr(item, f.name), getattr(fresh_item, f.name)
                if f.is_read_only and old is None:
                    # Some fields are automatically set server-side
                    continue
                if f.name == "reminder_due_by":
                    # EWS sets a default value if it is not set on insert. Ignore
                    continue
                if f.name == "mime_content":
                    # This will change depending on other contents fields
                    continue
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))

        # Update
        update_kwargs = self.get_random_update_kwargs(item=item, insert_kwargs=insert_kwargs)
        for k, v in update_kwargs.items():
            setattr(item, k, v)
        item.save()
        for k, v in update_kwargs.items():
            self.assertEqual(getattr(item, k), v, (k, getattr(item, k), v))
        # Test that whatever we have locally also matches whatever is in the DB
        fresh_item = self.get_item_by_id(item)
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                old, new = getattr(item, f.name), getattr(fresh_item, f.name)
                if f.is_read_only and old is None:
                    # Some fields are automatically updated server-side
                    continue
                if f.name == "mime_content":
                    # This will change depending on other contents fields
                    continue
                if f.name == "reminder_due_by":
                    if new is None:
                        # EWS does not always return a value if reminder_is_set is False.
                        continue
                    if old is not None:
                        # EWS sometimes randomly sets the new reminder due date to one month before or after we
                        # wanted it, and sometimes 30 days before or after. But only sometimes...
                        old_date = old.astimezone(self.account.default_timezone).date()
                        new_date = new.astimezone(self.account.default_timezone).date()
                        if getattr(item, "is_all_day", False) and old_date == new_date:
                            # There is some weirdness with the time part of the reminder_due_by value for all-day events
                            item.reminder_due_by = new
                            continue
                        if relativedelta(month=1) + new_date == old_date:
                            item.reminder_due_by = new
                            continue
                        if relativedelta(month=1) + old_date == new_date:
                            item.reminder_due_by = new
                            continue
                        if abs(old_date - new_date) == datetime.timedelta(days=30):
                            item.reminder_due_by = new
                            continue
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))

        # Hard delete
        item_id = (item.id, item.changekey)
        item.delete()
        for e in self.account.fetch(ids=[item_id]):
            # It's gone from the account
            self.assertIsInstance(e, ErrorItemNotFound)
        # Really gone, not just changed ItemId
        items = self.test_folder.filter(categories__contains=item.categories)
        self.assertEqual(items.count(), 0)

    def test_item_insert(self):
        # Test insert
        insert_kwargs = self.get_random_insert_kwargs()
        insert_kwargs["categories"] = self.categories
        item = self.ITEM_CLASS(folder=self.test_folder, **insert_kwargs)
        # Test with generator as argument
        insert_ids = self.test_folder.bulk_create(items=(i for i in [item]))
        self.assertEqual(len(insert_ids), 1)
        self.assertIsInstance(insert_ids[0], BaseItem)
        find_ids = list(self.test_folder.filter(categories__contains=item.categories).values_list("id", "changekey"))
        self.assertEqual(len(find_ids), 1)
        self.assertEqual(len(find_ids[0]), 2, find_ids[0])
        self.assertEqual(insert_ids, find_ids)
        # Test with generator as argument
        item = list(self.account.fetch(ids=(i for i in find_ids)))[0]
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                    # Timezone fields will (and must) be populated automatically from the timestamp
                    continue
                if f.is_read_only:
                    continue
                if f.name == "reminder_due_by":
                    # EWS sets a default value if it is not set on insert. Ignore
                    continue
                if f.name == "mime_content":
                    # This will change depending on other contents fields
                    continue
                old, new = insert_kwargs[f.name], getattr(item, f.name)
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))

    def test_item_update(self):
        # Test update
        insert_kwargs = self.get_random_insert_kwargs()
        insert_kwargs["categories"] = self.categories
        item = self.ITEM_CLASS(folder=self.test_folder, **insert_kwargs).save()
        update_kwargs = self.get_random_update_kwargs(item=item, insert_kwargs=insert_kwargs)
        if self.ITEM_CLASS in (Contact, DistributionList):
            # Contact and DistributionList don't support mime_type updates at all
            update_kwargs.pop("mime_content", None)
        update_fieldnames = [f for f in update_kwargs if f != "attachments"]
        for k, v in update_kwargs.items():
            setattr(item, k, v)
        # Test with generator as argument
        update_ids = self.account.bulk_update(items=(i for i in [(item, update_fieldnames)]))
        self.assertEqual(len(update_ids), 1)
        self.assertEqual(len(update_ids[0]), 2, update_ids)
        self.assertEqual(item.id, update_ids[0][0])  # ID should be the same
        self.assertNotEqual(item.changekey, update_ids[0][1])  # Changekey should change when item is updated
        item = self.get_item_by_id(update_ids[0])
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                    # Timezone fields will (and must) be populated automatically from the timestamp
                    continue
                if f.is_read_only or f.is_read_only_after_send:
                    # These cannot be changed
                    continue
                if f.name == "mime_content":
                    # This will change depending on other contents fields
                    continue
                old, new = getattr(item, f.name), update_kwargs[f.name]
                if f.name == "reminder_due_by":
                    if old is None:
                        # EWS does not always return a value if reminder_is_set is False. Set one now
                        item.reminder_due_by = new
                        continue
                    if new is not None:
                        # EWS sometimes randomly sets the new reminder due date to one month before or after we
                        # wanted it, and sometimes 30 days before or after. But only sometimes...
                        old_date = old.astimezone(self.account.default_timezone).date()
                        new_date = new.astimezone(self.account.default_timezone).date()
                        if getattr(item, "is_all_day", False) and old_date == new_date:
                            # There is some weirdness with the time part of the reminder_due_by value for all-day events
                            item.reminder_due_by = new
                            continue
                        if relativedelta(month=1) + new_date == old_date:
                            item.reminder_due_by = new
                            continue
                        if relativedelta(month=1) + old_date == new_date:
                            item.reminder_due_by = new
                            continue
                        if abs(old_date - new_date) == datetime.timedelta(days=30):
                            item.reminder_due_by = new
                            continue
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))

    def test_item_update_wipe(self):
        # Test wiping or removing fields
        insert_kwargs = self.get_random_insert_kwargs()
        insert_kwargs["categories"] = self.categories
        item = self.ITEM_CLASS(folder=self.test_folder, **insert_kwargs).save()
        update_kwargs = self.get_random_update_kwargs(item=item, insert_kwargs=insert_kwargs)
        if self.ITEM_CLASS in (Contact, DistributionList):
            # Contact and DistributionList don't support mime_type updates at all
            update_kwargs.pop("mime_content", None)
        update_fieldnames = [f for f in update_kwargs if f != "attachments"]
        wipe_kwargs = {}
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_required or f.is_required_after_save:
                # These cannot be deleted
                continue
            if f.is_read_only or f.is_read_only_after_send:
                # These cannot be changed
                continue
            wipe_kwargs[f.name] = None
        for k, v in wipe_kwargs.items():
            setattr(item, k, v)
        wipe_ids = self.account.bulk_update([(item, update_fieldnames)])
        self.assertEqual(len(wipe_ids), 1)
        self.assertEqual(len(wipe_ids[0]), 2, wipe_ids)
        self.assertEqual(item.id, wipe_ids[0][0])  # ID should be the same
        self.assertNotEqual(item.changekey, wipe_ids[0][1])  # Changekey should not be the same when item is updated
        item = self.get_item_by_id(wipe_ids[0])
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                    # Timezone fields will (and must) be populated automatically from the timestamp
                    continue
                if f.is_required or f.is_required_after_save:
                    continue
                if f.is_read_only or f.is_read_only_after_send:
                    continue
                old, new = getattr(item, f.name), wipe_kwargs[f.name]
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))

    def test_item_update_extended_properties(self):
        item = self.get_test_item().save()
        item = self.get_item_by_id(item)  # An Item saved in Inbox becomes a Message
        item.__class__.register("extern_id", ExternId)

        try:
            # Test extern_id = None, which deletes the extended property entirely
            extern_id = None
            item.extern_id = extern_id
            wipe2_ids = self.account.bulk_update([(item, ["extern_id"])])
            self.assertEqual(len(wipe2_ids), 1)
            self.assertEqual(len(wipe2_ids[0]), 2, wipe2_ids)
            self.assertEqual(item.id, wipe2_ids[0][0])  # ID must be the same
            self.assertNotEqual(item.changekey, wipe2_ids[0][1])  # Changekey must change when item is updated
            updated_item = self.get_item_by_id(wipe2_ids[0])
            self.assertEqual(updated_item.extern_id, extern_id)
        finally:
            item.__class__.deregister("extern_id")
