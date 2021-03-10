import datetime
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from exchangelib.attachments import ItemAttachment
from exchangelib.errors import ErrorItemNotFound, ErrorInternalServerError
from exchangelib.extended_properties import ExtendedProperty, ExternId
from exchangelib.fields import ExtendedPropertyField, CharField
from exchangelib.folders import Inbox, FolderCollection
from exchangelib.items import CalendarItem, Message
from exchangelib.queryset import QuerySet
from exchangelib.restriction import Restriction, Q
from exchangelib.version import Build, EXCHANGE_2007, EXCHANGE_2013

from ..common import get_random_string, mock_version
from .test_basics import CommonItemTest


class GenericItemTest(CommonItemTest):
    # Tests that don't need to be run for every single folder type
    TEST_FOLDER = 'inbox'
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message

    def test_validation(self):
        item = self.get_test_item()
        item.clean()
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                # Test field max_length
                if isinstance(f, CharField) and f.max_length:
                    with self.assertRaises(ValueError):
                        setattr(item, f.name, 'a' * (f.max_length + 1))
                        item.clean()
                        setattr(item, f.name, 'a')

    def test_invalid_direct_args(self):
        item = self.get_test_item()
        item.account = None
        with self.assertRaises(ValueError):
            item.save()  # Must have account on save
        item = self.get_test_item()
        item.id = 'XXX'  # Fake a saved item
        item.account = None
        with self.assertRaises(ValueError):
            item.save()  # Must have account on update
        item = self.get_test_item()
        with self.assertRaises(ValueError):
            item.save(update_fields=['foo', 'bar'])  # update_fields is only valid on update

        item = self.get_test_item()
        item.account = None
        with self.assertRaises(ValueError):
            item.refresh()  # Must have account on refresh
        item = self.get_test_item()
        with self.assertRaises(ValueError):
            item.refresh()  # Refresh an item that has not been saved
        item = self.get_test_item()
        item.save()
        item_id, changekey = item.id, item.changekey
        item.delete()
        item.id, item.changekey = item_id, changekey
        with self.assertRaises(ErrorItemNotFound):
            item.refresh()  # Refresh an item that doesn't exist

        item = self.get_test_item()
        item.account = None
        with self.assertRaises(ValueError):
            item.copy(to_folder=self.test_folder)  # Must have an account on copy
        item = self.get_test_item()
        with self.assertRaises(ValueError):
            item.copy(to_folder=self.test_folder)  # Must be an existing item
        item = self.get_test_item()
        item.save()
        item_id, changekey = item.id, item.changekey
        item.delete()
        item.id, item.changekey = item_id, changekey
        with self.assertRaises(ErrorItemNotFound):
            item.copy(to_folder=self.test_folder)  # Item disappeared

        item = self.get_test_item()
        item.account = None
        with self.assertRaises(ValueError):
            item.move(to_folder=self.test_folder)  # Must have an account on move
        item = self.get_test_item()
        with self.assertRaises(ValueError):
            item.move(to_folder=self.test_folder)  # Must be an existing item
        item = self.get_test_item()
        item.save()
        item_id, changekey = item.id, item.changekey
        item.delete()
        item.id, item.changekey = item_id, changekey
        with self.assertRaises(ErrorItemNotFound):
            item.move(to_folder=self.test_folder)  # Item disappeared

        item = self.get_test_item()
        item.account = None
        with self.assertRaises(ValueError):
            item.delete()  # Must have an account
        item = self.get_test_item()
        with self.assertRaises(ValueError):
            item.delete()  # Must be an existing item
        item = self.get_test_item()
        item.save()
        item_id, changekey = item.id, item.changekey
        item.delete()
        item.id, item.changekey = item_id, changekey
        with self.assertRaises(ErrorItemNotFound):
            item.delete()  # Item disappeared
        item = self.get_test_item()
        with self.assertRaises(ValueError):
            item._delete(delete_type='FOO', send_meeting_cancellations=None, affected_task_occurrences=None,
                         suppress_read_receipts=None)
        with self.assertRaises(ValueError):
            item.delete(send_meeting_cancellations='XXX')
        with self.assertRaises(ValueError):
            item.delete(affected_task_occurrences='XXX')
        with self.assertRaises(ValueError):
            item.delete(suppress_read_receipts='XXX')

    def test_invalid_kwargs_on_send(self):
        # Only Message class has the send() method
        item = self.get_test_item()
        item.account = None
        with self.assertRaises(ValueError):
            item.send()  # Must have account on send
        item = self.get_test_item()
        item.save()
        item_id, changekey = item.id, item.changekey
        item.delete()
        item.id, item.changekey = item_id, changekey
        with self.assertRaises(ErrorItemNotFound):
            item.send()  # Item disappeared
        item = self.get_test_item()
        with self.assertRaises(AttributeError):
            item.send(copy_to_folder=self.account.trash, save_copy=False)  # Inconsistent args

    def test_unsupported_fields(self):
        # Create a field that is not supported by any current versions. Test that we fail when using this field
        class UnsupportedProp(ExtendedProperty):
            property_set_id = 'deadcafe-beef-beef-beef-deadcafebeef'
            property_name = 'Unsupported Property'
            property_type = 'String'

        attr_name = 'unsupported_property'
        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=UnsupportedProp)
        try:
            for f in self.ITEM_CLASS.FIELDS:
                if f.name == attr_name:
                    f.supported_from = Build(99, 99, 99, 99)

            with self.assertRaises(ValueError):
                self.test_folder.get(**{attr_name: 'XXX'})
            with self.assertRaises(ValueError):
                list(self.test_folder.filter(**{attr_name: 'XXX'}))
            with self.assertRaises(ValueError):
                list(self.test_folder.all().only(attr_name))
            with self.assertRaises(ValueError):
                list(self.test_folder.all().values(attr_name))
            with self.assertRaises(ValueError):
                list(self.test_folder.all().values_list(attr_name))
        finally:
            self.ITEM_CLASS.deregister(attr_name=attr_name)

    def test_order_by(self):
        # Test order_by() on normal field
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Subj %s' % i
            test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        self.assertEqual(
            list(qs.order_by('subject').values_list('subject', flat=True)),
            ['Subj 0', 'Subj 1', 'Subj 2', 'Subj 3']
        )
        self.assertEqual(
            list(qs.order_by('-subject').values_list('subject', flat=True)),
            ['Subj 3', 'Subj 2', 'Subj 1', 'Subj 0']
        )
        self.bulk_delete(qs)

        try:
            self.ITEM_CLASS.register('extern_id', ExternId)
            # Test order_by() on ExtendedProperty
            test_items = []
            for i in range(4):
                item = self.get_test_item()
                item.extern_id = 'ID %s' % i
                test_items.append(item)
            self.test_folder.bulk_create(items=test_items)
            qs = QuerySet(
                folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
            ).filter(categories__contains=self.categories)
            self.assertEqual(
                list(qs.order_by('extern_id').values_list('extern_id', flat=True)),
                ['ID 0', 'ID 1', 'ID 2', 'ID 3']
            )
            self.assertEqual(
                list(qs.order_by('-extern_id').values_list('extern_id', flat=True)),
                ['ID 3', 'ID 2', 'ID 1', 'ID 0']
            )
        finally:
            self.ITEM_CLASS.deregister('extern_id')
        self.bulk_delete(qs)

        # Test sorting on multiple fields
        try:
            self.ITEM_CLASS.register('extern_id', ExternId)
            test_items = []
            for i in range(2):
                for j in range(2):
                    item = self.get_test_item()
                    item.subject = 'Subj %s' % i
                    item.extern_id = 'ID %s' % j
                    test_items.append(item)
            self.test_folder.bulk_create(items=test_items)
            qs = QuerySet(
                folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
            ).filter(categories__contains=self.categories)
            self.assertEqual(
                list(qs.order_by('subject', 'extern_id').values('subject', 'extern_id')),
                [{'subject': 'Subj 0', 'extern_id': 'ID 0'},
                 {'subject': 'Subj 0', 'extern_id': 'ID 1'},
                 {'subject': 'Subj 1', 'extern_id': 'ID 0'},
                 {'subject': 'Subj 1', 'extern_id': 'ID 1'}]
            )
            self.assertEqual(
                list(qs.order_by('-subject', 'extern_id').values('subject', 'extern_id')),
                [{'subject': 'Subj 1', 'extern_id': 'ID 0'},
                 {'subject': 'Subj 1', 'extern_id': 'ID 1'},
                 {'subject': 'Subj 0', 'extern_id': 'ID 0'},
                 {'subject': 'Subj 0', 'extern_id': 'ID 1'}]
            )
            self.assertEqual(
                list(qs.order_by('subject', '-extern_id').values('subject', 'extern_id')),
                [{'subject': 'Subj 0', 'extern_id': 'ID 1'},
                 {'subject': 'Subj 0', 'extern_id': 'ID 0'},
                 {'subject': 'Subj 1', 'extern_id': 'ID 1'},
                 {'subject': 'Subj 1', 'extern_id': 'ID 0'}]
            )
            self.assertEqual(
                list(qs.order_by('-subject', '-extern_id').values('subject', 'extern_id')),
                [{'subject': 'Subj 1', 'extern_id': 'ID 1'},
                 {'subject': 'Subj 1', 'extern_id': 'ID 0'},
                 {'subject': 'Subj 0', 'extern_id': 'ID 1'},
                 {'subject': 'Subj 0', 'extern_id': 'ID 0'}]
            )
        finally:
            self.ITEM_CLASS.deregister('extern_id')

    def test_order_by_with_empty_values(self):
        # Test order_by() when some values are empty
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            if i % 2 == 0:
                item.subject = 'Subj %s' % i
            else:
                item.subject = None
            test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        self.assertEqual(
            list(qs.order_by('subject').values_list('subject', flat=True)),
            [None, None, 'Subj 0', 'Subj 2']
        )
        self.assertEqual(
            list(qs.order_by('-subject').values_list('subject', flat=True)),
            ['Subj 2', 'Subj 0', None, None]
        )

    def test_order_by_on_list_field(self):
        # Test order_by() on list fields where some values are empty
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = self.categories[0]  # Make sure we have something unique to filter on
            if i % 2 == 0:
                item.categories = ['Cat %s' % i]
            else:
                item.categories = []
            test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(subject=self.categories[0])
        self.assertEqual(
            list(qs.order_by('categories').values_list('categories', flat=True)),
            [None, None, ['Cat 0'], ['Cat 2']]
        )
        self.assertEqual(
            list(qs.order_by('-categories').values_list('categories', flat=True)),
            [['Cat 2'], ['Cat 0'], None, None]
        )

    def test_finditems(self):
        now = datetime.datetime.now(tz=zoneinfo.ZoneInfo('UTC'))

        # Test argument types
        item = self.get_test_item()
        ids = self.test_folder.bulk_create(items=[item])
        # No arguments. There may be leftover items in the folder, so just make sure there's at least one.
        self.assertGreaterEqual(
            self.test_folder.filter().count(),
            1
        )
        # Q object
        self.assertEqual(
            self.test_folder.filter(Q(subject=item.subject)).count(),
            1
        )
        # Multiple Q objects
        self.assertEqual(
            self.test_folder.filter(Q(subject=item.subject), ~Q(subject=item.subject[:-3] + 'XXX')).count(),
            1
        )
        # Multiple Q object and kwargs
        self.assertEqual(
            self.test_folder.filter(Q(subject=item.subject), categories__contains=item.categories).count(),
            1
        )
        self.bulk_delete(ids)

        # Test categories which are handled specially - only '__contains' and '__in' lookups are supported
        item = self.get_test_item(categories=['TestA', 'TestB'])
        ids = self.test_folder.bulk_create(items=[item])
        common_qs = self.test_folder.filter(subject=item.subject)  # Guard against other simultaneous runs
        self.assertEqual(
            common_qs.filter(categories__contains='ci6xahH1').count(),  # Plain string
            0
        )
        self.assertEqual(
            common_qs.filter(categories__contains=['ci6xahH1']).count(),  # Same, but as list
            0
        )
        self.assertEqual(
            common_qs.filter(categories__contains=['TestA', 'TestC']).count(),  # One wrong category
            0
        )
        self.assertEqual(
            common_qs.filter(categories__contains=['TESTA']).count(),  # Test case insensitivity
            1
        )
        self.assertEqual(
            common_qs.filter(categories__contains=['testa']).count(),  # Test case insensitivity
            1
        )
        self.assertEqual(
            common_qs.filter(categories__contains=['TestA']).count(),  # Partial
            1
        )
        self.assertEqual(
            common_qs.filter(categories__contains=item.categories).count(),  # Exact match
            1
        )
        with self.assertRaises(ValueError):
            common_qs.filter(categories__in='ci6xahH1').count()  # Plain string is not supported
        self.assertEqual(
            common_qs.filter(categories__in=['ci6xahH1']).count(),  # Same, but as list
            0
        )
        self.assertEqual(
            common_qs.filter(categories__in=['TestA', 'TestC']).count(),  # One wrong category
            1
        )
        self.assertEqual(
            common_qs.filter(categories__in=['TestA']).count(),  # Partial
            1
        )
        self.assertEqual(
            common_qs.filter(categories__in=item.categories).count(),  # Exact match
            1
        )
        self.bulk_delete(ids)

        common_qs = self.test_folder.filter(categories__contains=self.categories)
        one_hour = datetime.timedelta(hours=1)
        two_hours = datetime.timedelta(hours=2)
        # Test 'exists'
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            common_qs.filter(datetime_created__exists=True).count(),
            1
        )
        self.assertEqual(
            common_qs.filter(datetime_created__exists=False).count(),
            0
        )
        self.bulk_delete(ids)

        # Test 'range'
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            common_qs.filter(datetime_created__range=(now + one_hour, now + two_hours)).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(datetime_created__range=(now - one_hour, now + one_hour)).count(),
            1
        )
        self.bulk_delete(ids)

        # Test '>'
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            common_qs.filter(datetime_created__gt=now + one_hour).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(datetime_created__gt=now - one_hour).count(),
            1
        )
        self.bulk_delete(ids)

        # Test '>='
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            common_qs.filter(datetime_created__gte=now + one_hour).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(datetime_created__gte=now - one_hour).count(),
            1
        )
        self.bulk_delete(ids)

        # Test '<'
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            common_qs.filter(datetime_created__lt=now - one_hour).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(datetime_created__lt=now + one_hour).count(),
            1
        )
        self.bulk_delete(ids)

        # Test '<='
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            common_qs.filter(datetime_created__lte=now - one_hour).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(datetime_created__lte=now + one_hour).count(),
            1
        )
        self.bulk_delete(ids)

        # Test '='
        item = self.get_test_item()
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            common_qs.filter(subject=item.subject[:-3] + 'XXX').count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject=item.subject).count(),
            1
        )
        self.bulk_delete(ids)

        # Test '!='
        item = self.get_test_item()
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            common_qs.filter(subject__not=item.subject).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__not=item.subject[:-3] + 'XXX').count(),
            1
        )
        self.bulk_delete(ids)

        # Test 'exact'
        item = self.get_test_item()
        item.subject = 'aA' + item.subject[2:]
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            common_qs.filter(subject__exact=item.subject[:-3] + 'XXX').count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__exact=item.subject.lower()).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__exact=item.subject.upper()).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__exact=item.subject).count(),
            1
        )
        self.bulk_delete(ids)

        # Test 'iexact'
        item = self.get_test_item()
        item.subject = 'aA' + item.subject[2:]
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            common_qs.filter(subject__iexact=item.subject[:-3] + 'XXX').count(),
            0
        )
        self.assertIn(
            common_qs.filter(subject__iexact=item.subject.lower()).count(),
            (0, 1)  # iexact search is broken on some EWS versions
        )
        self.assertIn(
            common_qs.filter(subject__iexact=item.subject.upper()).count(),
            (0, 1)  # iexact search is broken on some EWS versions
        )
        self.assertEqual(
            common_qs.filter(subject__iexact=item.subject).count(),
            1
        )
        self.bulk_delete(ids)

        # Test 'contains'
        item = self.get_test_item()
        item.subject = item.subject[2:8] + 'aA' + item.subject[8:]
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            common_qs.filter(subject__contains=item.subject[2:14] + 'XXX').count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__contains=item.subject[2:14].lower()).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__contains=item.subject[2:14].upper()).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__contains=item.subject[2:14]).count(),
            1
        )
        self.bulk_delete(ids)

        # Test 'icontains'
        item = self.get_test_item()
        item.subject = item.subject[2:8] + 'aA' + item.subject[8:]
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            common_qs.filter(subject__icontains=item.subject[2:14] + 'XXX').count(),
            0
        )
        self.assertIn(
            common_qs.filter(subject__icontains=item.subject[2:14].lower()).count(),
            (0, 1)  # icontains search is broken on some EWS versions
        )
        self.assertIn(
            common_qs.filter(subject__icontains=item.subject[2:14].upper()).count(),
            (0, 1)  # icontains search is broken on some EWS versions
        )
        self.assertEqual(
            common_qs.filter(subject__icontains=item.subject[2:14]).count(),
            1
        )
        self.bulk_delete(ids)

        # Test 'startswith'
        item = self.get_test_item()
        item.subject = 'aA' + item.subject[2:]
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            common_qs.filter(subject__startswith='XXX' + item.subject[:12]).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__startswith=item.subject[:12].lower()).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__startswith=item.subject[:12].upper()).count(),
            0
        )
        self.assertEqual(
            common_qs.filter(subject__startswith=item.subject[:12]).count(),
            1
        )
        self.bulk_delete(ids)

        # Test 'istartswith'
        item = self.get_test_item()
        item.subject = 'aA' + item.subject[2:]
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            common_qs.filter(subject__istartswith='XXX' + item.subject[:12]).count(),
            0
        )
        self.assertIn(
            common_qs.filter(subject__istartswith=item.subject[:12].lower()).count(),
            (0, 1)  # istartswith search is broken on some EWS versions
        )
        self.assertIn(
            common_qs.filter(subject__istartswith=item.subject[:12].upper()).count(),
            (0, 1)  # istartswith search is broken on some EWS versions
        )
        self.assertEqual(
            common_qs.filter(subject__istartswith=item.subject[:12]).count(),
            1
        )
        self.bulk_delete(ids)

    def test_filter_with_querystring(self):
        # QueryString is only supported from Exchange 2010
        with self.assertRaises(NotImplementedError):
            Q('Subject:XXX').to_xml(self.test_folder, version=mock_version(build=EXCHANGE_2007),
                                    applies_to=Restriction.ITEMS)

        # We don't allow QueryString in combination with other restrictions
        with self.assertRaises(ValueError):
            self.test_folder.filter('Subject:XXX', foo='bar')
        with self.assertRaises(ValueError):
            self.test_folder.filter('Subject:XXX').filter(foo='bar')
        with self.assertRaises(ValueError):
            self.test_folder.filter(foo='bar').filter('Subject:XXX')

        item = self.get_test_item()
        item.subject = get_random_string(length=8, spaces=False, special=False)
        item.save()
        # For some reason, the querystring search doesn't work instantly. We may have to wait for up to 60 seconds.
        # I'm too impatient for that, so also allow empty results. This makes the test almost worthless but I blame EWS.
        # Also, some servers are misconfigured and don't support querystrings at all. Don't fail on that.
        try:
            self.assertIn(
                self.test_folder.filter('Subject:%s' % item.subject).count(),
                (0, 1)
            )
        except ErrorInternalServerError as e:
            self.assertIn('AQS parser has been removed from Windows 2016 Server Core', e.args[0])

    def test_complex_fields(self):
        # Test that complex fields can be fetched using only(). This is a test for #141.
        item = self.get_test_item().save()
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if f.name in ('optional_attendees', 'required_attendees', 'resources'):
                    continue
                if f.is_read_only:
                    continue
                if f.name == 'reminder_due_by':
                    # EWS sets a default value if it is not set on insert. Ignore
                    continue
                if f.name == 'mime_content':
                    # This will change depending on other contents fields
                    continue
                old = getattr(item, f.name)
                # Test field as single element in only()
                fresh_item = self.test_folder.all().only(f.name).get(categories__contains=item.categories)
                new = getattr(fresh_item, f.name)
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))
                # Test field as one of the elements in only()
                fresh_item = self.test_folder.all().only('subject', f.name).get(categories__contains=item.categories)
                new = getattr(fresh_item, f.name)
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))

    def test_text_body(self):
        if self.account.version.build < EXCHANGE_2013:
            self.skipTest('Exchange version too old')
        item = self.get_test_item()
        item.body = 'X' * 500  # Make body longer than the normal 256 char text field limit
        item.save()
        fresh_item = self.test_folder.filter(categories__contains=item.categories).only('text_body')[0]
        self.assertEqual(fresh_item.text_body, item.body)

    def test_only_fields(self):
        item = self.get_test_item().save()
        item = self.test_folder.get(categories__contains=item.categories)
        self.assertIsInstance(item, self.ITEM_CLASS)
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                self.assertTrue(hasattr(item, f.name))
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if f.name in ('optional_attendees', 'required_attendees', 'resources'):
                    continue
                if f.name == 'reminder_due_by' and not item.reminder_is_set:
                    # We delete the due date if reminder is not set
                    continue
                if f.is_read_only:
                    continue
                self.assertIsNotNone(getattr(item, f.name), (f, getattr(item, f.name)))
        only_fields = ('subject', 'body', 'categories')
        item = self.test_folder.all().only(*only_fields).get(categories__contains=item.categories)
        self.assertIsInstance(item, self.ITEM_CLASS)
        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                self.assertTrue(hasattr(item, f.name))
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if f.name in only_fields:
                    self.assertIsNotNone(getattr(item, f.name), (f.name, getattr(item, f.name)))
                elif f.is_required:
                    v = getattr(item, f.name)
                    if f.name == 'attachments':
                        self.assertEqual(v, [], (f.name, v))
                    elif f.default is None:
                        self.assertIsNone(v, (f.name, v))
                    else:
                        self.assertEqual(v, f.default, (f.name, v))

    def test_export_and_upload(self):
        # 15 new items which we will attempt to export and re-upload
        items = [self.get_test_item().save() for _ in range(15)]
        ids = [(i.id, i.changekey) for i in items]
        # re-fetch items because there will be some extra fields added by the server
        items = list(self.account.fetch(items))

        # Try exporting and making sure we get the right response
        export_results = self.account.export(items)
        self.assertEqual(len(items), len(export_results))
        for result in export_results:
            self.assertIsInstance(result, str)

        # Try reuploading our results
        upload_results = self.account.upload([(self.test_folder, data) for data in export_results])
        self.assertEqual(len(items), len(upload_results), (items, upload_results))
        for result in upload_results:
            # Must be a completely new ItemId
            self.assertIsInstance(result, tuple)
            self.assertNotIn(result, ids)

        # Check the items uploaded are the same as the original items
        def to_dict(item):
            dict_item = {}
            # fieldnames is everything except the ID so we'll use it to compare
            for f in self.ITEM_CLASS.FIELDS:
                # datetime_created and last_modified_time aren't copied, but instead are added to the new item after
                # uploading. This means mime_content and size can also change. Items also get new IDs on upload. And
                # meeting_count values are dependent on contents of current calendar. Form query strings contain the
                # item ID and will also change.
                if f.name in {'_id', 'first_occurrence', 'last_occurrence', 'datetime_created',
                              'last_modified_time', 'mime_content', 'size', 'conversation_id',
                              'adjacent_meeting_count', 'conflicting_meeting_count',
                              'web_client_read_form_query_string', 'web_client_edit_form_query_string'}:
                    continue
                dict_item[f.name] = getattr(item, f.name)
                if f.name == 'attachments':
                    # Attachments get new IDs on upload. Wipe them here so we can compare the other fields
                    for a in dict_item[f.name]:
                        a.attachment_id = None
            return dict_item

        uploaded_items = sorted([to_dict(item) for item in self.account.fetch(upload_results)],
                                key=lambda i: i['subject'])
        original_items = sorted([to_dict(item) for item in items], key=lambda i: i['subject'])
        self.assertListEqual(original_items, uploaded_items)

    def test_export_with_error(self):
        # 15 new items which we will attempt to export and re-upload
        items = [self.get_test_item().save() for _ in range(15)]
        # Use id tuples for export here because deleting an item clears it's
        #  id.
        ids = [(item.id, item.changekey) for item in items]
        # Delete one of the items, this will cause an error
        items[3].delete()

        export_results = self.account.export(ids)
        self.assertEqual(len(items), len(export_results))
        for idx, result in enumerate(export_results):
            if idx == 3:
                # If it is the one returning the error
                self.assertIsInstance(result, ErrorItemNotFound)
            else:
                self.assertIsInstance(result, str)

        # Clean up after yourself
        del ids[3]  # Sending the deleted one through will cause an error

    def test_archive(self):
        item = self.get_test_item(folder=self.test_folder).save()
        item_id, changekey = item.archive(to_folder=self.account.trash)
        self.account.root.get(id=item_id, changekey=changekey)

    def test_item_attachments(self):
        item = self.get_test_item(folder=self.test_folder)
        item.attachments = []

        attached_item1 = self.get_test_item(folder=self.test_folder)
        attached_item1.attachments = []
        attached_item1.save()
        attachment1 = ItemAttachment(name='attachment1', item=attached_item1)
        item.attach(attachment1)

        self.assertEqual(len(item.attachments), 1)
        item.save()
        fresh_item = self.get_item_by_id(item)
        self.assertEqual(len(fresh_item.attachments), 1)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'attachment1')
        self.assertIsInstance(fresh_attachments[0].item, self.ITEM_CLASS)

        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                # Normalize some values we don't control
                if f.is_read_only:
                    continue
                if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                    # Timezone fields will (and must) be populated automatically from the timestamp
                    continue
                if isinstance(f, ExtendedPropertyField):
                    # Attachments don't have these values. It may be possible to request it if we can find the FieldURI
                    continue
                if f.name == 'is_read':
                    # This is always true for item attachments?
                    continue
                if f.name == 'reminder_due_by':
                    # EWS sets a default value if it is not set on insert. Ignore
                    continue
                if f.name == 'mime_content':
                    # This will change depending on other contents fields
                    continue
                old_val = getattr(attached_item1, f.name)
                new_val = getattr(fresh_attachments[0].item, f.name)
                if f.is_list:
                    old_val, new_val = set(old_val or ()), set(new_val or ())
                self.assertEqual(old_val, new_val, (f.name, old_val, new_val))

        # Test attach on saved object
        attached_item2 = self.get_test_item(folder=self.test_folder)
        attached_item2.attachments = []
        attached_item2.save()
        attachment2 = ItemAttachment(name='attachment2', item=attached_item2)
        item.attach(attachment2)

        self.assertEqual(len(item.attachments), 2)
        fresh_item = self.get_item_by_id(item)
        self.assertEqual(len(fresh_item.attachments), 2)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'attachment1')
        self.assertIsInstance(fresh_attachments[0].item, self.ITEM_CLASS)

        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                # Normalize some values we don't control
                if f.is_read_only:
                    continue
                if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                    # Timezone fields will (and must) be populated automatically from the timestamp
                    continue
                if isinstance(f, ExtendedPropertyField):
                    # Attachments don't have these values. It may be possible to request it if we can find the FieldURI
                    continue
                if f.name == 'reminder_due_by':
                    # EWS sets a default value if it is not set on insert. Ignore
                    continue
                if f.name == 'is_read':
                    # This is always true for item attachments?
                    continue
                if f.name == 'mime_content':
                    # This will change depending on other contents fields
                    continue
                old_val = getattr(attached_item1, f.name)
                new_val = getattr(fresh_attachments[0].item, f.name)
                if f.is_list:
                    old_val, new_val = set(old_val or ()), set(new_val or ())
                self.assertEqual(old_val, new_val, (f.name, old_val, new_val))

        self.assertEqual(fresh_attachments[1].name, 'attachment2')
        self.assertIsInstance(fresh_attachments[1].item, self.ITEM_CLASS)

        for f in self.ITEM_CLASS.FIELDS:
            # Normalize some values we don't control
            if f.is_read_only:
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if isinstance(f, ExtendedPropertyField):
                # Attachments don't have these values. It may be possible to request it if we can find the FieldURI
                continue
            if f.name == 'reminder_due_by':
                # EWS sets a default value if it is not set on insert. Ignore
                continue
            if f.name == 'is_read':
                # This is always true for item attachments?
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            old_val = getattr(attached_item2, f.name)
            new_val = getattr(fresh_attachments[1].item, f.name)
            if f.is_list:
                old_val, new_val = set(old_val or ()), set(new_val or ())
            self.assertEqual(old_val, new_val, (f.name, old_val, new_val))

        # Test detach
        item.detach(attachment2)
        self.assertTrue(attachment2.attachment_id is None)
        self.assertTrue(attachment2.parent_item is None)
        fresh_item = self.get_item_by_id(item)
        self.assertEqual(len(fresh_item.attachments), 1)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)

        for f in self.ITEM_CLASS.FIELDS:
            with self.subTest(f=f):
                # Normalize some values we don't control
                if f.is_read_only:
                    continue
                if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                    # Timezone fields will (and must) be populated automatically from the timestamp
                    continue
                if isinstance(f, ExtendedPropertyField):
                    # Attachments don't have these values. It may be possible to request it if we can find the FieldURI
                    continue
                if f.name == 'reminder_due_by':
                    # EWS sets a default value if it is not set on insert. Ignore
                    continue
                if f.name == 'is_read':
                    # This is always true for item attachments?
                    continue
                if f.name == 'mime_content':
                    # This will change depending on other contents fields
                    continue
                old_val = getattr(attached_item1, f.name)
                new_val = getattr(fresh_attachments[0].item, f.name)
                if f.is_list:
                    old_val, new_val = set(old_val or ()), set(new_val or ())
                self.assertEqual(old_val, new_val, (f.name, old_val, new_val))

        # Test attach with non-saved item
        attached_item3 = self.get_test_item(folder=self.test_folder)
        attached_item3.attachments = []
        attachment3 = ItemAttachment(name='attachment2', item=attached_item3)
        item.attach(attachment3)
        item.detach(attachment3)
