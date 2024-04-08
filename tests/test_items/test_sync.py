import time

from exchangelib.errors import ErrorInvalidSubscription, ErrorSubscriptionNotFound, MalformedResponseError
from exchangelib.folders import FolderCollection, Inbox
from exchangelib.items import Message
from exchangelib.properties import (
    CreatedEvent,
    DeletedEvent,
    ItemId,
    ModifiedEvent,
    MovedEvent,
    Notification,
    StatusEvent,
)
from exchangelib.services import GetStreamingEvents, SendNotification, SubscribeToPull
from exchangelib.util import PrettyXmlHandler

from ..common import get_random_string
from .test_basics import BaseItemTest


class SyncTest(BaseItemTest):
    TEST_FOLDER = "inbox"
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message

    def test_subscribe_invalid_kwargs(self):
        with self.assertRaises(ValueError) as e:
            self.account.inbox.subscribe_to_pull(event_types=["XXX"])
        self.assertEqual(
            e.exception.args[0], f"'event_types' values must consist of values in {SubscribeToPull.EVENT_TYPES}"
        )
        with self.assertRaises(ValueError) as e:
            self.account.inbox.subscribe_to_pull(event_types=[])
        self.assertEqual(e.exception.args[0], "'event_types' must not be empty")

    def test_pull_subscribe(self):
        self.account.affinity_cookie = None
        with self.account.inbox.pull_subscription() as (subscription_id, watermark):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        # Test with watermark
        with self.account.inbox.pull_subscription(watermark=watermark) as (subscription_id, watermark):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        # Context manager already unsubscribed us
        with self.assertRaises(ErrorSubscriptionNotFound):
            self.account.inbox.unsubscribe(subscription_id)
        # Test via folder collection
        with self.account.root.tois.children.pull_subscription() as (subscription_id, watermark):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        with self.assertRaises(ErrorSubscriptionNotFound):
            self.account.root.tois.children.unsubscribe(subscription_id)
        # Affinity cookie is not always sent by the server for pull subscriptions

    def test_pull_subscribe_from_account(self):
        self.account.affinity_cookie = None
        with self.account.pull_subscription() as (subscription_id, watermark):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        # Test with watermark
        with self.account.pull_subscription(watermark=watermark) as (subscription_id, watermark):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        # Context manager already unsubscribed us
        with self.assertRaises(ErrorSubscriptionNotFound):
            self.account.unsubscribe(subscription_id)
        # Test without watermark
        with self.account.pull_subscription() as (subscription_id, watermark):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        with self.assertRaises(ErrorSubscriptionNotFound):
            self.account.unsubscribe(subscription_id)
        # Affinity cookie is not always sent by the server for pull subscriptions

    def test_push_subscribe(self):
        with self.account.inbox.push_subscription(callback_url="https://example.com/foo") as (
            subscription_id,
            watermark,
        ):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        # Test with watermark
        with self.account.inbox.push_subscription(
            callback_url="https://example.com/foo",
            watermark=watermark,
        ) as (subscription_id, watermark):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        # Cannot unsubscribe. Must be done as response to callback URL request
        with self.assertRaises(ErrorInvalidSubscription):
            self.account.inbox.unsubscribe(subscription_id)
        # Test via folder collection
        with self.account.root.tois.children.push_subscription(callback_url="https://example.com/foo") as (
            subscription_id,
            watermark,
        ):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        with self.assertRaises(ErrorInvalidSubscription):
            self.account.root.tois.children.unsubscribe(subscription_id)

    def test_push_subscribe_from_account(self):
        with self.account.push_subscription(callback_url="https://example.com/foo") as (
            subscription_id,
            watermark,
        ):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        # Test with watermark
        with self.account.push_subscription(
            callback_url="https://example.com/foo",
            watermark=watermark,
        ) as (subscription_id, watermark):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        # Cannot unsubscribe. Must be done as response to callback URL request
        with self.assertRaises(ErrorInvalidSubscription):
            self.account.unsubscribe(subscription_id)
        # Test via folder collection
        with self.account.push_subscription(callback_url="https://example.com/foo") as (
            subscription_id,
            watermark,
        ):
            self.assertIsNotNone(subscription_id)
            self.assertIsNotNone(watermark)
        with self.assertRaises(ErrorInvalidSubscription):
            self.account.unsubscribe(subscription_id)

    def test_empty_folder_collection(self):
        self.assertEqual(FolderCollection(account=None, folders=[]).subscribe_to_pull(), None)
        self.assertEqual(FolderCollection(account=None, folders=[]).subscribe_to_push("http://example.com"), None)
        self.assertEqual(FolderCollection(account=None, folders=[]).subscribe_to_streaming(), None)

    def test_streaming_subscribe(self):
        self.account.affinity_cookie = None
        with self.account.inbox.streaming_subscription() as subscription_id:
            self.assertIsNotNone(subscription_id)
        # Context manager already unsubscribed us
        with self.assertRaises(ErrorSubscriptionNotFound):
            self.account.inbox.unsubscribe(subscription_id)
        # Test via folder collection
        with self.account.root.tois.children.streaming_subscription() as subscription_id:
            self.assertIsNotNone(subscription_id)
        with self.assertRaises(ErrorSubscriptionNotFound):
            self.account.root.tois.children.unsubscribe(subscription_id)

        # Test affinity cookie
        self.assertIsNotNone(self.account.affinity_cookie)

    def test_streaming_subscribe_from_account(self):
        self.account.affinity_cookie = None
        with self.account.streaming_subscription() as subscription_id:
            self.assertIsNotNone(subscription_id)
        # Context manager already unsubscribed us
        with self.assertRaises(ErrorSubscriptionNotFound):
            self.account.unsubscribe(subscription_id)
        # Test via folder collection
        with self.account.streaming_subscription() as subscription_id:
            self.assertIsNotNone(subscription_id)
        with self.assertRaises(ErrorSubscriptionNotFound):
            self.account.unsubscribe(subscription_id)

        # Test affinity cookie
        self.assertIsNotNone(self.account.affinity_cookie)

    def test_sync_folder_hierarchy(self):
        test_folder = self.get_test_folder().save()

        # Test that folder_sync_state is set after calling sync_hierarchy
        self.assertIsNone(test_folder.folder_sync_state)
        list(test_folder.sync_hierarchy())
        self.assertIsNotNone(test_folder.folder_sync_state)
        # Test non-default values
        list(test_folder.sync_hierarchy(only_fields=["name"]))

        # Test that we see a create event
        f1 = self.FOLDER_CLASS(parent=test_folder, name=get_random_string(8)).save()
        changes = list(test_folder.sync_hierarchy())
        self.assertEqual(len(changes), 1)
        change_type, f = changes[0]
        self.assertEqual(change_type, "create")
        self.assertEqual(f.id, f1.id)

        # Test that we see an update event
        f1.name = get_random_string(8)
        f1.save(update_fields=["name"])
        changes = list(test_folder.sync_hierarchy())
        self.assertEqual(len(changes), 1)
        change_type, f = changes[0]
        self.assertEqual(change_type, "update")
        self.assertEqual(f.id, f1.id)

        # Test that we see a delete event
        f1_id = f1.id
        f1.delete()
        changes = list(test_folder.sync_hierarchy())
        self.assertEqual(len(changes), 1)
        change_type, f = changes[0]
        self.assertEqual(change_type, "delete")
        self.assertEqual(f.id, f1_id)

    def test_sync_folder_items(self):
        test_folder = self.get_test_folder().save()

        with self.assertRaises(TypeError) as e:
            list(test_folder.sync_items(max_changes_returned="XXX"))
        self.assertEqual(e.exception.args[0], "'max_changes_returned' 'XXX' must be of type <class 'int'>")
        with self.assertRaises(ValueError) as e:
            list(test_folder.sync_items(max_changes_returned=-1))
        self.assertEqual(e.exception.args[0], "'max_changes_returned' -1 must be a positive integer")
        with self.assertRaises(ValueError) as e:
            list(test_folder.sync_items(sync_scope="XXX"))
        self.assertEqual(
            e.exception.args[0], "'sync_scope' 'XXX' must be one of ['NormalAndAssociatedItems', 'NormalItems']"
        )

        # Test that item_sync_state is set after calling sync_hierarchy
        self.assertIsNone(test_folder.item_sync_state)
        list(test_folder.sync_items())
        self.assertIsNotNone(test_folder.item_sync_state)
        # Test non-default values
        list(test_folder.sync_items(only_fields=["subject"]))
        list(test_folder.sync_items(sync_scope="NormalItems"))
        list(test_folder.sync_items(ignore=[ItemId(id="AAA=")]))

        # Test that we see a create event
        i1 = self.get_test_item(folder=test_folder).save()
        changes = list(test_folder.sync_items())
        self.assertEqual(len(changes), 1)
        change_type, i = changes[0]
        self.assertEqual(change_type, "create")
        self.assertEqual(i.id, i1.id)

        # Test that we see an update event
        i1.subject = get_random_string(8)
        i1.save(update_fields=["subject"])
        changes = list(test_folder.sync_items())
        self.assertEqual(len(changes), 1)
        change_type, i = changes[0]
        self.assertEqual(change_type, "update")
        self.assertEqual(i.id, i1.id)

        # Test that we see a read_flag_change event
        i1.is_read = not i1.is_read
        i1.save(update_fields=["is_read"])
        changes = list(test_folder.sync_items())
        self.assertEqual(len(changes), 1)
        change_type, (i, read_state) = changes[0]
        self.assertEqual(change_type, "read_flag_change")
        self.assertEqual(i.id, i1.id)
        self.assertEqual(read_state, i1.is_read)

        # Test that we see a delete event
        i1_id = i1.id
        i1.delete()
        changes = list(test_folder.sync_items())
        self.assertEqual(len(changes), 1)
        change_type, i = changes[0]
        self.assertEqual(change_type, "delete")
        self.assertEqual(i.id, i1_id)

    def _filter_events(self, notifications, event_cls, item_id):
        events = []
        watermark = None
        for notification in notifications:
            for e in notification.events:
                watermark = e.watermark
                if not isinstance(e, event_cls):
                    continue
                if item_id is None:
                    events.append(e)
                    continue
                if e.event_type == event_cls.ITEM:
                    if isinstance(e, MovedEvent) and e.old_item_id.id == item_id:
                        events.append(e)
                    elif e.item_id.id == item_id:
                        events.append(e)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertIsInstance(event, event_cls)
        return event, watermark

    def test_pull_notifications(self):
        # Test that we can create a pull subscription, make changes and see the events by calling .get_events()
        test_folder = self.account.drafts
        with test_folder.pull_subscription() as (subscription_id, watermark):
            notifications = list(test_folder.get_events(subscription_id, watermark))
            _, watermark = self._filter_events(notifications, StatusEvent, None)

            # Test that we see a create event
            i1 = self.get_test_item(folder=test_folder).save()
            time.sleep(5)  # For some reason, events do not trigger instantly
            notifications = list(test_folder.get_events(subscription_id, watermark))
            created_event, watermark = self._filter_events(notifications, CreatedEvent, i1.id)
            self.assertEqual(created_event.item_id.id, i1.id)

            # Test that we see an update event
            i1.subject = get_random_string(8)
            i1.save(update_fields=["subject"])
            time.sleep(5)  # For some reason, events do not trigger instantly
            notifications = list(test_folder.get_events(subscription_id, watermark))
            modified_event, watermark = self._filter_events(notifications, ModifiedEvent, i1.id)
            self.assertEqual(modified_event.item_id.id, i1.id)

            # Test that we see a delete event
            i1_id = i1.id
            i1.delete()
            time.sleep(5)  # For some reason, events do not trigger instantly
            notifications = list(test_folder.get_events(subscription_id, watermark))
            try:
                # On some servers, items are moved to the Recoverable Items on delete
                moved_event, watermark = self._filter_events(notifications, MovedEvent, i1_id)
                self.assertEqual(moved_event.old_item_id.id, i1_id)
            except AssertionError:
                deleted_event, watermark = self._filter_events(notifications, DeletedEvent, i1_id)
                self.assertEqual(deleted_event.item_id.id, i1_id)

    def test_streaming_notifications(self):
        # Test that we can create a streaming subscription, make changes and see the events by calling
        # .get_streaming_events()
        test_folder = self.account.drafts
        with test_folder.streaming_subscription() as subscription_id:
            # Test that we see a create event
            i1 = self.get_test_item(folder=test_folder).save()
            t1 = time.perf_counter()
            # Let's only wait for one notification so this test doesn't take forever. 'connection_timeout' is only
            # meant as a fallback.
            notifications = list(
                test_folder.get_streaming_events(subscription_id, connection_timeout=1, max_notifications_returned=1)
            )
            t2 = time.perf_counter()
            # Make sure we returned after 'max_notifications' instead of waiting for 'connection_timeout'
            self.assertLess(t2 - t1, 60)
            created_event, _ = self._filter_events(notifications, CreatedEvent, i1.id)
            self.assertEqual(created_event.item_id.id, i1.id)

            # Test that we see an update event
            i1.subject = get_random_string(8)
            i1.save(update_fields=["subject"])
            notifications = list(
                test_folder.get_streaming_events(subscription_id, connection_timeout=1, max_notifications_returned=1)
            )
            modified_event, _ = self._filter_events(notifications, ModifiedEvent, i1.id)
            self.assertEqual(modified_event.item_id.id, i1.id)

            # Test that we see a delete event
            i1_id = i1.id
            i1.delete()
            notifications = list(
                test_folder.get_streaming_events(subscription_id, connection_timeout=1, max_notifications_returned=1)
            )
            try:
                # On some servers, items are moved to the Recoverable Items on delete
                moved_event, _ = self._filter_events(notifications, MovedEvent, i1_id)
                self.assertEqual(moved_event.old_item_id.id, i1_id)
            except AssertionError:
                deleted_event, _ = self._filter_events(notifications, DeletedEvent, i1_id)
                self.assertEqual(deleted_event.item_id.id, i1_id)

    def test_streaming_with_other_calls(self):
        # Test that we can call other EWS operations while we have a streaming subscription open
        test_folder = self.account.drafts

        # Test calling GetItem while the streaming connection is still open. We need to bump the
        # connection count because the default count is 1 but we need 2 connections.
        q_size = self.account.protocol._session_pool.qsize()
        self.account.protocol._session_pool_maxsize += 1
        self.account.protocol.increase_poolsize()
        self.assertEqual(self.account.protocol._session_pool.qsize(), q_size + 1)
        try:
            with test_folder.streaming_subscription() as subscription_id:
                i1 = self.get_test_item(folder=test_folder).save()
                for notification in test_folder.get_streaming_events(
                    subscription_id, connection_timeout=1, max_notifications_returned=1
                ):
                    # We're using one session for streaming, and have one in reserve for the following service call.
                    self.assertEqual(self.account.protocol._session_pool.qsize(), q_size)
                    for e in notification.events:
                        if isinstance(e, CreatedEvent) and e.event_type == CreatedEvent.ITEM and e.item_id.id == i1.id:
                            test_folder.all().only("id").get(id=e.item_id.id)
        finally:
            self.account.protocol.decrease_poolsize()
            self.account.protocol._session_pool_maxsize -= 1
        self.assertEqual(self.account.protocol._session_pool.qsize(), q_size)

    def test_streaming_incomplete_generator_consumption(self):
        # Test that sessions are properly returned to the pool even when get_streaming_events() is not fully consumed.
        # The generator needs to be garbage collected to release its session.
        test_folder = self.account.drafts
        q_size = self.account.protocol._session_pool.qsize()
        self.account.protocol._session_pool_maxsize += 1
        self.account.protocol.increase_poolsize()
        self.assertEqual(self.account.protocol._session_pool.qsize(), q_size + 1)
        try:
            with test_folder.streaming_subscription() as subscription_id:
                # Generate an event and incompletely consume the generator
                self.get_test_item(folder=test_folder).save()
                it = test_folder.get_streaming_events(subscription_id, connection_timeout=1)
                _ = next(it)
                self.assertEqual(self.account.protocol._session_pool.qsize(), q_size)
                del it
                self.assertEqual(self.account.protocol._session_pool.qsize(), q_size + 1)
        finally:
            self.account.protocol.decrease_poolsize()
            self.account.protocol._session_pool_maxsize -= 1

    def test_streaming_invalid_subscription(self):
        # Test that we can get the failing subscription IDs from the response message
        test_folder = self.account.drafts

        # Test with empty list of subscription
        with self.assertRaises(ValueError) as e:
            list(test_folder.get_streaming_events([], connection_timeout=1, max_notifications_returned=1))
        self.assertEqual(e.exception.args[0], "'subscription_ids' must not be empty")

        # Test with bad connection_timeout
        with self.assertRaises(TypeError) as e:
            list(test_folder.get_streaming_events("AAA-", connection_timeout="XXX", max_notifications_returned=1))
        self.assertEqual(e.exception.args[0], "'connection_timeout' 'XXX' must be of type <class 'int'>")
        with self.assertRaises(ValueError) as e:
            list(test_folder.get_streaming_events("AAA-", connection_timeout=-1, max_notifications_returned=1))
        self.assertEqual(e.exception.args[0], "'connection_timeout' -1 must be a positive integer")

        # Test a single bad notification
        with self.assertRaises(ErrorInvalidSubscription) as e:
            list(test_folder.get_streaming_events("AAA-", connection_timeout=1, max_notifications_returned=1))
        self.assertEqual(e.exception.value, "Subscription is invalid. (subscription IDs: ['AAA-'])")

        # Test a combination of a good and a bad notification
        with self.assertRaises(ErrorInvalidSubscription) as e:
            with test_folder.streaming_subscription() as subscription_id:
                self.get_test_item(folder=test_folder).save()
                list(
                    test_folder.get_streaming_events(
                        ("AAA-", subscription_id), connection_timeout=1, max_notifications_returned=1
                    )
                )
        self.assertEqual(e.exception.value, "Subscription is invalid. (subscription IDs: ['AAA-'])")

    def test_push_message_parsing(self):
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope
        xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Header>
        <t:RequestServerVersion
                xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages" Version="Exchange2016"
                xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"/>
    </s:Header>
    <s:Body>
        <m:SendNotification
                xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
                xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
            <m:ResponseMessages>
                <m:SendNotificationResponseMessage ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:Notification>
                        <t:SubscriptionId>XXXXX=</t:SubscriptionId>
                        <t:PreviousWatermark>AAAAA=</t:PreviousWatermark>
                        <t:MoreEvents>false</t:MoreEvents>
                        <t:StatusEvent>
                            <t:Watermark>BBBBB=</t:Watermark>
                        </t:StatusEvent>
                    </m:Notification>
                </m:SendNotificationResponseMessage>
            </m:ResponseMessages>
        </m:SendNotification>
    </s:Body>
</s:Envelope>"""
        ws = SendNotification(protocol=None)
        self.assertListEqual(
            list(ws.parse(xml)),
            [
                Notification(
                    subscription_id="XXXXX=",
                    previous_watermark="AAAAA=",
                    more_events=False,
                    events=[StatusEvent(watermark="BBBBB=")],
                )
            ],
        )

    def test_push_message_responses(self):
        # Test SendNotification
        ws = SendNotification(protocol=None)
        with self.assertRaises(ValueError):
            # Invalid status
            ws.get_payload(status="XXX")
        self.assertEqual(
            PrettyXmlHandler().prettify_xml(ws.ok_payload()),
            b"""\
<?xml version='1.0' encoding='utf-8'?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Body>
    <m:SendNotificationResult>
      <m:SubscriptionStatus>OK</m:SubscriptionStatus>
    </m:SendNotificationResult>
  </s:Body>
</s:Envelope>
""",
        )
        self.assertEqual(
            PrettyXmlHandler().prettify_xml(ws.unsubscribe_payload()),
            b"""\
<?xml version='1.0' encoding='utf-8'?>
<s:Envelope
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Body>
    <m:SendNotificationResult>
      <m:SubscriptionStatus>Unsubscribe</m:SubscriptionStatus>
    </m:SendNotificationResult>
  </s:Body>
</s:Envelope>
""",
        )

    def test_get_streaming_events_connection_closed(self):
        # Test that we respect connection status
        xml = b"""\
<?xml version='1.0' encoding='utf-8'?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <m:GetStreamingEventsResponse
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
      <m:ResponseMessages>
        <m:GetStreamingEventsResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:ConnectionStatus>Closed</m:ConnectionStatus>
        </m:GetStreamingEventsResponseMessage>
      </m:ResponseMessages>
    </m:GetStreamingEventsResponse>
  </s:Body>
</s:Envelope>"""
        ws = GetStreamingEvents(account=self.account)
        self.assertEqual(ws.connection_status, None)
        list(ws.parse(xml))
        self.assertEqual(ws.connection_status, ws.CLOSED)

    def test_get_streaming_events_bad_response(self):
        # Test special error handling in this service. It's almost impossible to trigger a ParseError through the
        # DocumentYielder, so we test with a SOAP message without a body element.
        xml = b"""\
<?xml version='1.0' encoding='utf-8'?>
<s:Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">
</s:Envelope>"""
        with self.assertRaises(MalformedResponseError):
            list(GetStreamingEvents(account=self.account).parse(xml))
