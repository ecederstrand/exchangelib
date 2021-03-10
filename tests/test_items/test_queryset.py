import time
import warnings

from exchangelib.folders import Inbox, FolderCollection
from exchangelib.items import Message, SHALLOW, ASSOCIATED
from exchangelib.queryset import QuerySet, DoesNotExist, MultipleObjectsReturned

from .test_basics import BaseItemTest


class ItemQuerySetTest(BaseItemTest):
    TEST_FOLDER = 'inbox'
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message

    def test_querysets(self):
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Item %s' % i
            item.save()
            test_items.append(item)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        test_cat = self.categories[0]
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs),
            {('Item 0', test_cat), ('Item 1', test_cat), ('Item 2', test_cat), ('Item 3', test_cat)}
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.none()],
            []
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.filter(subject__startswith='Item 2')],
            [('Item 2', test_cat)]
        )
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs.exclude(subject__startswith='Item 2')),
            {('Item 0', test_cat), ('Item 1', test_cat), ('Item 3', test_cat)}
        )
        self.assertEqual(
            set((i.subject, i.categories) for i in qs.only('subject')),
            {('Item 0', None), ('Item 1', None), ('Item 2', None), ('Item 3', None)}
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.order_by('subject')],
            [('Item 0', test_cat), ('Item 1', test_cat), ('Item 2', test_cat), ('Item 3', test_cat)]
        )
        self.assertEqual(  # Test '-some_field' syntax for reverse sorting
            [(i.subject, i.categories[0]) for i in qs.order_by('-subject')],
            [('Item 3', test_cat), ('Item 2', test_cat), ('Item 1', test_cat), ('Item 0', test_cat)]
        )
        self.assertEqual(  # Test ordering on a field that we don't need to fetch
            [(i.subject, i.categories[0]) for i in qs.order_by('-subject').only('categories')],
            [(None, test_cat), (None, test_cat), (None, test_cat), (None, test_cat)]
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.order_by('subject').reverse()],
            [('Item 3', test_cat), ('Item 2', test_cat), ('Item 1', test_cat), ('Item 0', test_cat)]
        )
        with self.assertRaises(ValueError):
            list(qs.values([]))
        self.assertEqual(
            list(qs.order_by('subject').values('subject')),
            [{'subject': 'Item 0'}, {'subject': 'Item 1'}, {'subject': 'Item 2'}, {'subject': 'Item 3'}]
        )

        # Test .values() in combinations of 'id' and 'changekey', which are handled specially
        self.assertEqual(
            list(qs.order_by('subject').values('id')),
            [{'id': i.id} for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values('changekey')),
            [{'changekey': i.changekey} for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values('id', 'changekey')),
            [{k: getattr(i, k) for k in ('id', 'changekey')} for i in test_items]
        )

        self.assertEqual(
            set(i for i in qs.values_list('subject')),
            {('Item 0',), ('Item 1',), ('Item 2',), ('Item 3',)}
        )

        # Test .values_list() in combinations of 'id' and 'changekey', which are handled specially
        self.assertEqual(
            list(qs.order_by('subject').values_list('id')),
            [(i.id,) for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values_list('changekey')),
            [(i.changekey,) for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values_list('id', 'changekey')),
            [(i.id, i.changekey) for i in test_items]
        )

        self.assertEqual(
            set(i.subject for i in qs.only('subject')),
            {'Item 0', 'Item 1', 'Item 2', 'Item 3'}
        )

        # Test .only() in combinations of 'id' and 'changekey', which are handled specially
        self.assertEqual(
            list((i.id,) for i in qs.order_by('subject').only('id')),
            [(i.id,) for i in test_items]
        )
        self.assertEqual(
            list((i.changekey,) for i in qs.order_by('subject').only('changekey')),
            [(i.changekey,) for i in test_items]
        )
        self.assertEqual(
            list((i.id, i.changekey) for i in qs.order_by('subject').only('id', 'changekey')),
            [(i.id, i.changekey) for i in test_items]
        )

        with self.assertRaises(ValueError):
            list(qs.values_list('id', 'changekey', flat=True))
        with self.assertRaises(AttributeError):
            list(qs.values_list('id', xxx=True))
        self.assertEqual(
            list(qs.order_by('subject').values_list('id', flat=True)),
            [i.id for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values_list('changekey', flat=True)),
            [i.changekey for i in test_items]
        )
        self.assertEqual(
            set(i for i in qs.values_list('subject', flat=True)),
            {'Item 0', 'Item 1', 'Item 2', 'Item 3'}
        )
        self.assertEqual(
            qs.values_list('subject', flat=True).get(subject='Item 2'),
            'Item 2'
        )
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs.exclude(subject__startswith='Item 2')),
            {('Item 0', test_cat), ('Item 1', test_cat), ('Item 3', test_cat)}
        )
        # Test that we can sort on a field that we don't want
        self.assertEqual(
            [i.categories[0] for i in qs.only('categories').order_by('subject')],
            [test_cat, test_cat, test_cat, test_cat]
        )
        # Test iterator
        with warnings.catch_warnings():
            # iterator() is deprecated but we still want to test it. Silence the DeprecationWarning
            warnings.simplefilter("ignore")
            self.assertEqual(
                set((i.subject, i.categories[0]) for i in qs.iterator()),
                {('Item 0', test_cat), ('Item 1', test_cat), ('Item 2', test_cat), ('Item 3', test_cat)}
            )
            # Test that iterator() preserves the result format
            self.assertEqual(
                set((i[0], i[1][0]) for i in qs.values_list('subject', 'categories').iterator()),
                {('Item 0', test_cat), ('Item 1', test_cat), ('Item 2', test_cat), ('Item 3', test_cat)}
            )
        self.assertEqual(qs.get(subject='Item 3').subject, 'Item 3')
        with self.assertRaises(DoesNotExist):
            qs.get(subject='Item XXX')
        with self.assertRaises(MultipleObjectsReturned):
            qs.get(subject__startswith='Item')
        # len() and count()
        self.assertEqual(qs.count(), 4)
        # Indexing and slicing
        self.assertTrue(isinstance(qs[0], self.ITEM_CLASS))
        self.assertEqual(len(list(qs[1:3])), 2)
        self.assertEqual(qs.count(), 4)
        with self.assertRaises(IndexError):
            print(qs[99999])
        # Exists
        self.assertEqual(qs.exists(), True)
        self.assertEqual(qs.filter(subject='Test XXX').exists(), False)
        self.assertEqual(
            qs.filter(subject__startswith='Item').delete(),
            [True, True, True, True]
        )

    def test_queryset_failure(self):
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        with self.assertRaises(ValueError):
            qs.order_by('XXX')
        with self.assertRaises(ValueError):
            qs.values('XXX')
        with self.assertRaises(ValueError):
            qs.values_list('XXX')
        with self.assertRaises(ValueError):
            qs.only('XXX')
        with self.assertRaises(ValueError):
            qs.reverse()  # We can't reverse when we haven't defined an order yet

    def test_cached_queryset_corner_cases(self):
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Item %s' % i
            item.save()
            test_items.append(item)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories).order_by('subject')
        for _ in qs:
            # Build up the cache
            pass
        with self.assertRaises(MultipleObjectsReturned):
            qs.get()  # Get with a full cache
        self.assertEqual(qs[2].subject, 'Item 2')  # Index with a full cache
        self.assertEqual(qs[-2].subject, 'Item 2')  # Negative index with a full cache
        qs.delete()  # Delete with a full cache
        self.assertEqual(qs.count(), 0)  # QuerySet is empty after delete
        self.assertEqual(list(qs.none()), [])

    def test_queryset_get_by_id(self):
        item = self.get_test_item().save()
        with self.assertRaises(ValueError):
            list(self.test_folder.filter(id__in=[item.id]))
        with self.assertRaises(ValueError):
            list(self.test_folder.get(id=item.id, changekey=item.changekey, subject='XXX'))
        with self.assertRaises(ValueError):
            list(self.test_folder.get(id=None, changekey=item.changekey))

        # Test a simple get()
        get_item = self.test_folder.get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertEqual(item.body, get_item.body)

        # Test get() with ID only
        get_item = self.test_folder.get(id=item.id)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertEqual(item.body, get_item.body)
        get_item = self.test_folder.get(id=item.id, changekey=None)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertEqual(item.body, get_item.body)

        # Test a get() from queryset
        get_item = self.test_folder.all().get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertEqual(item.body, get_item.body)

        # Test a get() with only()
        get_item = self.test_folder.all().only('subject').get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertIsNone(get_item.body)

    def test_paging(self):
        # Test that paging services work correctly. Default EWS paging size is 1000 items. Our default is 100 items.
        items = []
        for _ in range(11):
            i = self.get_test_item()
            del i.attachments[:]
            items.append(i)
        self.test_folder.bulk_create(items=items)
        ids = self.test_folder.filter(categories__contains=self.categories).values_list('id', 'changekey')
        ids.page_size = 10
        self.bulk_delete(ids)

    def test_slicing(self):
        # Test that slicing works correctly
        items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Subj %s' % i
            del item.attachments[:]
            items.append(item)
        self.test_folder.bulk_create(items=items)
        qs = self.test_folder.filter(categories__contains=self.categories).only('subject').order_by('subject')

        # Test positive index
        self.assertEqual(
            qs._copy_self()[0].subject,
            'Subj 0'
        )
        # Test positive index
        self.assertEqual(
            qs._copy_self()[3].subject,
            'Subj 3'
        )
        # Test negative index
        self.assertEqual(
            qs._copy_self()[-2].subject,
            'Subj 2'
        )
        # Test positive slice
        self.assertEqual(
            [i.subject for i in qs._copy_self()[0:2]],
            ['Subj 0', 'Subj 1']
        )
        # Test positive slice
        self.assertEqual(
            [i.subject for i in qs._copy_self()[2:4]],
            ['Subj 2', 'Subj 3']
        )
        # Test positive open slice
        self.assertEqual(
            [i.subject for i in qs._copy_self()[:2]],
            ['Subj 0', 'Subj 1']
        )
        # Test positive open slice
        self.assertEqual(
            [i.subject for i in qs._copy_self()[2:]],
            ['Subj 2', 'Subj 3']
        )
        # Test negative slice
        self.assertEqual(
            [i.subject for i in qs._copy_self()[-3:-1]],
            ['Subj 1', 'Subj 2']
        )
        # Test negative slice
        self.assertEqual(
            [i.subject for i in qs._copy_self()[1:-1]],
            ['Subj 1', 'Subj 2']
        )
        # Test negative open slice
        self.assertEqual(
            [i.subject for i in qs._copy_self()[:-2]],
            ['Subj 0', 'Subj 1']
        )
        # Test negative open slice
        self.assertEqual(
            [i.subject for i in qs._copy_self()[-2:]],
            ['Subj 2', 'Subj 3']
        )
        # Test positive slice with step
        self.assertEqual(
            [i.subject for i in qs._copy_self()[0:4:2]],
            ['Subj 0', 'Subj 2']
        )
        # Test negative slice with step
        self.assertEqual(
            [i.subject for i in qs._copy_self()[4:0:-2]],
            ['Subj 3', 'Subj 1']
        )

    def test_delete_via_queryset(self):
        self.get_test_item().save()
        qs = self.test_folder.filter(categories__contains=self.categories)
        self.assertEqual(qs.count(), 1)
        qs.delete()
        self.assertEqual(qs.count(), 0)

    def test_send_via_queryset(self):
        self.get_test_item().save()
        qs = self.test_folder.filter(categories__contains=self.categories)
        to_folder = self.account.sent
        to_folder_qs = to_folder.filter(categories__contains=self.categories)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(to_folder_qs.count(), 0)
        qs.send(copy_to_folder=to_folder)
        time.sleep(5)  # Requests are supposed to be transactional, but apparently not...
        self.assertEqual(qs.count(), 0)
        self.assertEqual(to_folder_qs.count(), 1)

    def test_send_with_no_copy_via_queryset(self):
        self.get_test_item().save()
        qs = self.test_folder.filter(categories__contains=self.categories)
        to_folder = self.account.sent
        to_folder_qs = to_folder.filter(categories__contains=self.categories)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(to_folder_qs.count(), 0)
        qs.send(save_copy=False)
        time.sleep(5)  # Requests are supposed to be transactional, but apparently not...
        self.assertEqual(qs.count(), 0)
        self.assertEqual(to_folder_qs.count(), 0)

    def test_copy_via_queryset(self):
        self.get_test_item().save()
        qs = self.test_folder.filter(categories__contains=self.categories)
        to_folder = self.account.trash
        to_folder_qs = to_folder.filter(categories__contains=self.categories)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(to_folder_qs.count(), 0)
        qs.copy(to_folder=to_folder)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(to_folder_qs.count(), 1)

    def test_move_via_queryset(self):
        self.get_test_item().save()
        qs = self.test_folder.filter(categories__contains=self.categories)
        to_folder = self.account.trash
        to_folder_qs = to_folder.filter(categories__contains=self.categories)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(to_folder_qs.count(), 0)
        qs.move(to_folder=to_folder)
        self.assertEqual(qs.count(), 0)
        self.assertEqual(to_folder_qs.count(), 1)

    def test_mark_as_junk_via_queryset(self):
        self.get_test_item().save()
        qs = self.test_folder.filter(categories__contains=self.categories)
        qs.mark_as_junk(is_junk=False, move_item=False)
        self.assertEqual(self.test_folder.filter(categories__contains=self.categories).count(), 1)
        qs.mark_as_junk(is_junk=True, move_item=False)
        self.assertEqual(self.test_folder.filter(categories__contains=self.categories).count(), 1)
        qs.mark_as_junk(is_junk=True, move_item=True)
        self.assertEqual(self.account.junk.filter(categories__contains=self.categories).count(), 1)
        self.account.junk.filter(categories__contains=self.categories).mark_as_junk(is_junk=False, move_item=True)
        self.assertEqual(self.account.inbox.filter(categories__contains=self.categories).count(), 1)

    def test_archive_via_queryset(self):
        self.get_test_item().save()
        qs = self.test_folder.filter(categories__contains=self.categories)
        to_folder = self.account.trash
        qs.archive(to_folder=to_folder)
        self.assertEqual(qs.count(), 0)
        self.assertEqual(to_folder.filter(categories__contains=self.categories).count(), 1)

    def test_depth(self):
        self.assertGreaterEqual(self.test_folder.all().depth(ASSOCIATED).count(), 0)
        self.assertGreaterEqual(self.test_folder.all().depth(SHALLOW).count(), 0)

    def test_empty_in_sequence(self):
        # 'Q(foo_in=[])' should always match nothing. We interpret it to mean "is foo contained in the empty set?"
        # which is always false.
        item = self.get_test_item().save()
        qs = self.test_folder.filter(categories__contains=self.categories)
        self.assertEqual(qs.filter(subject__in=[item.subject]).count(), 1)
        self.assertEqual(qs.filter(subject__in=[]).count(), 0)
