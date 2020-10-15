from exchangelib.errors import ErrorItemNotFound
from exchangelib.folders import Inbox
from exchangelib.items import Message

from .test_basics import BaseItemTest


class ItemHelperTest(BaseItemTest):
    TEST_FOLDER = 'inbox'
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message

    def test_save_with_update_fields(self):
        item = self.get_test_item()
        with self.assertRaises(ValueError):
            item.save(update_fields=['subject'])  # update_fields does not work on item creation
        item.save()
        item.subject = 'XXX'
        item.body = 'YYY'
        item.save(update_fields=['subject'])
        item.refresh()
        self.assertEqual(item.subject, 'XXX')
        self.assertNotEqual(item.body, 'YYY')

        # Test invalid 'update_fields' input
        with self.assertRaises(ValueError) as e:
            item.save(update_fields=['xxx'])
        self.assertEqual(
            e.exception.args[0],
            "Field name(s) 'xxx' are not valid for a '%s' item" % self.ITEM_CLASS.__name__
        )
        with self.assertRaises(ValueError) as e:
            item.save(update_fields='subject')
        self.assertEqual(
            e.exception.args[0],
            "Field name(s) 's', 'u', 'b', 'j', 'e', 'c', 't' are not valid for a '%s' item" % self.ITEM_CLASS.__name__
        )

    def test_soft_delete(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        self.account.recoverable_items_deletions.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        item_id = (item.id, item.changekey)
        # Soft delete
        item.soft_delete()
        for e in self.account.fetch(ids=[item_id]):
            # It's gone from the test folder
            self.assertIsInstance(e, ErrorItemNotFound)
        # Really gone, not just changed ItemId
        self.assertEqual(self.test_folder.filter(categories__contains=item.categories).count(), 0)
        self.assertEqual(self.account.trash.filter(categories__contains=item.categories).count(), 0)
        # But we can find it in the recoverable items folder
        self.assertEqual(
            self.account.recoverable_items_deletions.filter(categories__contains=item.categories).count(), 1
        )

    def test_move_to_trash(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        item_id = (item.id, item.changekey)
        # Move to trash
        item.move_to_trash()
        for e in self.account.fetch(ids=[item_id]):
            # Not in the test folder anymore
            self.assertIsInstance(e, ErrorItemNotFound)
        # Really gone, not just changed ItemId
        self.assertEqual(self.test_folder.filter(categories__contains=item.categories).count(), 0)
        # Test that the item moved to trash
        item = self.account.trash.get(categories__contains=item.categories)
        moved_item = self.get_item_by_id(item)
        # The item was copied, so the ItemId has changed. Let's compare the subject instead
        self.assertEqual(item.subject, moved_item.subject)

    def test_copy(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        # Copy to trash. We use trash because it can contain all item types.
        copy_item_id, copy_changekey = item.copy(to_folder=self.account.trash)
        # Test that the item still exists in the folder
        self.assertEqual(self.test_folder.filter(categories__contains=item.categories).count(), 1)
        # Test that the copied item exists in trash
        copied_item = self.account.trash.get(categories__contains=item.categories)
        self.assertNotEqual(item.id, copied_item.id)
        self.assertNotEqual(item.changekey, copied_item.changekey)
        self.assertEqual(copy_item_id, copied_item.id)
        self.assertEqual(copy_changekey, copied_item.changekey)

    def test_move(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        item_id = (item.id, item.changekey)
        # Move to trash. We use trash because it can contain all item types. This changes the ItemId
        item.move(to_folder=self.account.trash)
        for e in self.account.fetch(ids=[item_id]):
            # original item ID no longer exists
            self.assertIsInstance(e, ErrorItemNotFound)
        # Test that the item moved to trash
        self.assertEqual(self.test_folder.filter(categories__contains=item.categories).count(), 0)
        moved_item = self.account.trash.get(categories__contains=item.categories)
        self.assertEqual(item.id, moved_item.id)
        self.assertEqual(item.changekey, moved_item.changekey)

    def test_refresh(self):
        # Test that we can refresh items, and that refresh fails if the item no longer exists on the server
        item = self.get_test_item().save()
        orig_subject = item.subject
        item.subject = 'XXX'
        item.refresh()
        self.assertEqual(item.subject, orig_subject)
        item.delete()
        with self.assertRaises(ValueError):
            # Item no longer has an ID
            item.refresh()
