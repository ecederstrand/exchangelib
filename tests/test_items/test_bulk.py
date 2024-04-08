import datetime
import time

from exchangelib.errors import ErrorInvalidChangeKey, ErrorInvalidIdMalformed, ErrorItemNotFound
from exchangelib.fields import FieldPath
from exchangelib.folders import Calendar, Folder, Inbox
from exchangelib.items import SAVE_ONLY, SEND_AND_SAVE_COPY, SEND_ONLY, BulkCreateResult, CalendarItem, Item, Message
from exchangelib.services import CreateItem

from .test_basics import BaseItemTest


class BulkMethodTest(BaseItemTest):
    TEST_FOLDER = "inbox"
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message

    def test_fetch(self):
        item = self.get_test_item()
        self.test_folder.bulk_create(items=[item, item])
        ids = self.test_folder.filter(categories__contains=item.categories)
        items = list(self.account.fetch(ids=ids))
        for item in items:
            self.assertIsInstance(item, self.ITEM_CLASS)
        self.assertEqual(len(items), 2)

        items = list(self.account.fetch(ids=ids, only_fields=["subject"]))
        self.assertEqual(len(items), 2)

        items = list(self.account.fetch(ids=ids, only_fields=[FieldPath.from_string("subject", self.test_folder)]))
        self.assertEqual(len(items), 2)

        items = list(self.account.fetch(ids=ids, only_fields=["id", "changekey"]))
        self.assertEqual(len(items), 2)

    def test_bulk_create(self):
        item = self.get_test_item()
        res = self.test_folder.bulk_create(items=[item, item])
        self.assertEqual(len(res), 2)
        for r in res:
            self.assertIsInstance(r, BulkCreateResult)

    def test_no_account(self):
        # Test bulk operations on items with no self.account
        item = self.get_test_item()
        item.account = None
        res = self.test_folder.bulk_create(items=[item])[0]
        item.id, item.changekey = res.id, res.changekey
        item.account = None
        self.assertEqual(list(self.account.fetch(ids=[item]))[0].id, item.id)
        item.account = None
        res = self.account.bulk_update(items=[(item, ("subject",))])[0]
        item.id, item.changekey = res
        item.account = None
        res = self.account.bulk_copy(ids=[item], to_folder=self.account.trash)[0]
        item.id, item.changekey = res
        item.account = None
        res = self.account.bulk_move(ids=[item], to_folder=self.test_folder)[0]
        item.id, item.changekey = res
        item.account = None
        self.assertEqual(self.account.bulk_delete(ids=[item]), [True])
        item = self.get_test_item().save()
        item.account = None
        self.assertEqual(self.account.bulk_send(ids=[item]), [True])

    def test_empty_args(self):
        # We allow empty sequences for these methods
        self.assertEqual(self.test_folder.bulk_create(items=[]), [])
        self.assertEqual(list(self.account.fetch(ids=[])), [])
        self.assertEqual(self.account.bulk_create(folder=self.test_folder, items=[]), [])
        self.assertEqual(self.account.bulk_update(items=[]), [])
        self.assertEqual(self.account.bulk_delete(ids=[]), [])
        self.assertEqual(self.account.bulk_send(ids=[]), [])
        self.assertEqual(self.account.bulk_copy(ids=[], to_folder=self.account.trash), [])
        self.assertEqual(self.account.bulk_move(ids=[], to_folder=self.account.trash), [])
        self.assertEqual(self.account.upload(data=[]), [])
        self.assertEqual(self.account.export(items=[]), [])

    def test_qs_args(self):
        # We allow querysets for these methods
        qs = self.test_folder.none()
        self.assertEqual(list(self.account.fetch(ids=qs)), [])
        with self.assertRaises(ValueError):
            # bulk_create() does not allow queryset input
            self.account.bulk_create(folder=self.test_folder, items=qs)
        with self.assertRaises(ValueError):
            # bulk_update() does not allow queryset input
            self.account.bulk_update(items=qs)
        self.assertEqual(self.account.bulk_delete(ids=qs), [])
        self.assertEqual(self.account.bulk_send(ids=qs), [])
        self.assertEqual(self.account.bulk_copy(ids=qs, to_folder=self.account.trash), [])
        self.assertEqual(self.account.bulk_move(ids=qs, to_folder=self.account.trash), [])
        self.assertEqual(self.account.upload(data=qs), [])
        self.assertEqual(self.account.export(items=qs), [])

    def test_no_kwargs(self):
        self.assertEqual(self.test_folder.bulk_create([]), [])
        self.assertEqual(list(self.account.fetch([])), [])
        self.assertEqual(self.account.bulk_create(self.test_folder, []), [])
        self.assertEqual(self.account.bulk_update([]), [])
        self.assertEqual(self.account.bulk_delete([]), [])
        self.assertEqual(self.account.bulk_send([]), [])
        self.assertEqual(self.account.bulk_copy([], to_folder=self.account.trash), [])
        self.assertEqual(self.account.bulk_move([], to_folder=self.account.trash), [])
        self.assertEqual(self.account.upload([]), [])
        self.assertEqual(self.account.export([]), [])

    def test_invalid_bulk_args(self):
        # Test bulk_create
        with self.assertRaises(ValueError):
            # Folder must belong to account
            self.account.bulk_create(folder=Folder(root=None), items=[1])
        with self.assertRaises(AttributeError):
            # Must have folder on save
            self.account.bulk_create(folder=None, items=[1], message_disposition=SAVE_ONLY)
        # Test that we can send_and_save with a default folder
        self.account.bulk_create(folder=None, items=[], message_disposition=SEND_AND_SAVE_COPY)
        with self.assertRaises(AttributeError):
            # Must not have folder on send-only
            self.account.bulk_create(folder=self.test_folder, items=[1], message_disposition=SEND_ONLY)

        # Test bulk_update
        with self.assertRaises(ValueError):
            # Cannot update in send-only mode
            self.account.bulk_update(items=[1], message_disposition=SEND_ONLY)

    def test_bulk_failure(self):
        # Test that bulk_* can handle EWS errors and return the errors in order without losing non-failure results
        items1 = [self.get_test_item().save() for _ in range(3)]
        items1[1].changekey = "XXX"
        for i, res in enumerate(self.account.bulk_delete(items1)):
            if i == 1:
                self.assertIsInstance(res, ErrorInvalidChangeKey)
            else:
                self.assertEqual(res, True)
        items2 = [self.get_test_item().save() for _ in range(3)]
        items2[1].id = "AAAA=="
        for i, res in enumerate(self.account.bulk_delete(items2)):
            if i == 1:
                self.assertIsInstance(res, ErrorInvalidIdMalformed)
            else:
                self.assertEqual(res, True)
        items3 = [self.get_test_item().save() for _ in range(3)]
        items3[1].id = items1[0].id
        for i, res in enumerate(self.account.fetch(items3)):
            if i == 1:
                self.assertIsInstance(res, ErrorItemNotFound)
            else:
                self.assertIsInstance(res, Item)

    def test_bulk_create_with_no_result(self):
        # Some CreateItem responses do not contain the ID of the created items. See issue#984
        xml = b"""\
<?xml version='1.0' encoding='utf-8'?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Header>
    <h:ServerVersionInfo
    xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"
    xmlns="http://schemas.microsoft.com/exchange/services/2006/types"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" MajorVersion="15" MinorVersion="0" Version="V2_23"/>
  </s:Header>
  <s:Body
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <m:CreateItemResponse
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
      <m:ResponseMessages>
        <m:CreateItemResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:Items/>
        </m:CreateItemResponseMessage>
        <m:CreateItemResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:Items/>
        </m:CreateItemResponseMessage>
      </m:ResponseMessages>
    </m:CreateItemResponse>
  </s:Body>
</s:Envelope>"""
        ws = CreateItem(account=self.account)
        self.assertListEqual(list(ws.parse(xml)), [True, True])


class CalendarBulkMethodTest(BaseItemTest):
    TEST_FOLDER = "calendar"
    FOLDER_CLASS = Calendar
    ITEM_CLASS = CalendarItem

    def test_no_account(self):
        # Test corner cases with bulk operations on items with no self.account
        item = self.get_test_item()
        item.recurrence = None
        item.is_all_day = True
        item.start, item.end = datetime.date(2020, 1, 1), datetime.date(2020, 1, 2)
        item.account = None
        res = self.test_folder.bulk_create(items=[item])[0]
        item.id, item.changekey = res.id, res.changekey
        item.account = None
        self.account.bulk_update(items=[(item, ("start",))])


class MessagesBulkMethodTest(BaseItemTest):
    TEST_FOLDER = "inbox"
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message

    def test_bulk_send(self):
        with self.assertRaises(AttributeError):
            self.account.bulk_send(ids=[], save_copy=False, copy_to_folder=self.account.trash)
        item = self.get_test_item()
        item.save()
        for res in self.account.bulk_send(ids=[item]):
            self.assertEqual(res, True)
        time.sleep(10)  # Requests are supposed to be transactional, but apparently not...
        # By default, sent items are placed in the sent folder
        self.assertEqual(self.account.sent.filter(categories__contains=item.categories).count(), 1)
