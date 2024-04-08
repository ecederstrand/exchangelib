import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from exchangelib.attachments import FileAttachment
from exchangelib.errors import ErrorItemNotFound
from exchangelib.folders import Inbox
from exchangelib.items import Message, ReplyToItem
from exchangelib.queryset import DoesNotExist
from exchangelib.version import EXCHANGE_2010_SP2, Version

from ..common import get_random_string
from .test_basics import CommonItemTest


class MessagesTest(CommonItemTest):
    # Just test one of the Message-type folders
    TEST_FOLDER = "inbox"
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message
    INCOMING_MESSAGE_TIMEOUT = 60

    def get_incoming_message(self, subject):
        t1 = time.monotonic()
        while True:
            t2 = time.monotonic()
            if t2 - t1 > self.INCOMING_MESSAGE_TIMEOUT:
                self.skipTest(f"Too bad. Gave up in {self.id()} waiting for the incoming message to show up")
            try:
                return self.account.inbox.get(subject=subject)
            except DoesNotExist:
                time.sleep(5)

    def test_send(self):
        # Test that we can send (only) Message items
        item = self.get_test_item(folder=None)
        item.send()
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)
        self.assertEqual(self.test_folder.filter(categories__contains=item.categories).count(), 0)

    def test_send_pre_2013(self):
        # Test < Exchange 2013 fallback for attachments and send-only mode
        item = self.get_test_item()
        item.account = self.get_account()
        item.folder = item.account.inbox
        item.attach(FileAttachment(name="file_attachment", content=b"file_attachment"))
        item.account.version = Version(EXCHANGE_2010_SP2)
        item.send(save_copy=False)
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)

    def test_send_no_copy(self):
        item = self.get_test_item(folder=None)
        item.send(save_copy=False)
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)

    def test_send_and_save(self):
        # Test that we can send_and_save Message items
        item = self.get_test_item()
        item.send_and_save()
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)
        time.sleep(5)  # Requests are supposed to be transactional, but apparently not...
        # Also, the sent item may be followed by an automatic message with the same category
        self.assertGreaterEqual(self.test_folder.filter(categories__contains=item.categories).count(), 1)

        # Test update, although it makes little sense
        item = self.get_test_item()
        item.save()
        item.send_and_save()
        time.sleep(5)  # Requests are supposed to be transactional, but apparently not...
        # Also, the sent item may be followed by an automatic message with the same category
        self.assertGreaterEqual(self.test_folder.filter(categories__contains=item.categories).count(), 1)

    def test_send_draft(self):
        item = self.get_test_item()
        item.folder = self.account.drafts
        item.is_draft = True
        item.save()  # Save a draft
        item.send()  # Send the draft
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)
        self.assertEqual(item.folder, self.account.sent)
        self.assertEqual(self.test_folder.filter(categories__contains=item.categories).count(), 0)

    def test_send_and_copy_to_folder(self):
        item = self.get_test_item()
        item.send(save_copy=True, copy_to_folder=self.account.sent)  # Send the draft and save to the sent folder
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)
        self.assertEqual(item.folder, self.account.sent)
        time.sleep(5)  # Requests are supposed to be transactional, but apparently not...
        self.assertEqual(self.account.sent.filter(categories__contains=item.categories).count(), 1)

    def test_reply(self):
        # Test that we can reply to a Message item. EWS only allows items that have been sent to receive a reply
        item = self.get_test_item(folder=None)
        item.send()  # get_test_item() sets the to_recipients to the test account
        sent_item = self.get_incoming_message(item.subject)
        new_subject = (f"Re: {sent_item.subject}")[:255]
        sent_item.reply(subject=new_subject, body="Hello reply", to_recipients=[item.author])
        self.assertEqual(self.account.sent.filter(subject=new_subject).count(), 1)

    def test_create_reply(self):
        # Test that we can save a reply without sending it
        item = self.get_test_item(folder=None)
        item.send()
        sent_item = self.get_incoming_message(item.subject)
        new_subject = (f"Re: {sent_item.subject}")[:255]
        with self.assertRaises(ValueError) as e:
            tmp = sent_item.author
            try:
                sent_item.author = None
                sent_item.create_reply(subject=new_subject, body="Hello reply").save(self.account.drafts)
            finally:
                sent_item.author = tmp
        self.assertEqual(e.exception.args[0], "'to_recipients' must be set when message has no 'author'")
        sent_item.create_reply(subject=new_subject, body="Hello reply", to_recipients=[item.author]).save(
            self.account.drafts
        )
        self.assertEqual(self.account.drafts.filter(subject=new_subject).count(), 1)
        # Test with no to_recipients
        sent_item.create_reply(subject=new_subject, body="Hello reply").save(self.account.drafts)
        self.assertEqual(self.account.drafts.filter(subject=new_subject).count(), 2)

    def test_reply_all(self):
        with self.assertRaises(TypeError) as e:
            ReplyToItem(account="XXX")
        self.assertEqual(e.exception.args[0], "'account' 'XXX' must be of type <class 'exchangelib.account.Account'>")

        # Test that to_recipients only has one entry even when we are both the sender and the receiver
        item = self.get_test_item(folder=None)
        item.id, item.changekey = 123, 456
        reply_item = item.create_reply_all(subject="", body="")
        self.assertEqual(reply_item.to_recipients, item.to_recipients)
        self.assertEqual(reply_item.to_recipients, item.to_recipients)
        self.assertEqual(reply_item.to_recipients, item.to_recipients)

        # Test that we can reply-all a Message item. EWS only allows items that have been sent to receive a reply
        item = self.get_test_item(folder=None)
        item.send()
        sent_item = self.get_incoming_message(item.subject)
        new_subject = f"Re: {sent_item.subject}"[:255]
        sent_item.reply_all(subject=new_subject, body="Hello reply")
        self.assertEqual(self.account.sent.filter(subject=new_subject).count(), 1)

    def test_forward(self):
        # Test that we can forward a Message item. EWS only allows items that have been sent to receive a reply
        item = self.get_test_item(folder=None)
        item.send()
        sent_item = self.get_incoming_message(item.subject)
        new_subject = (f"Re: {sent_item.subject}")[:255]
        sent_item.forward(subject=new_subject, body="Hello reply", to_recipients=[item.author])
        self.assertEqual(self.account.sent.filter(subject=new_subject).count(), 1)

    def test_create_forward(self):
        # Test that we can forward a Message item. EWS only allows items that have been sent to receive a reply
        item = self.get_test_item(folder=None)
        item.send()
        sent_item = self.get_incoming_message(item.subject)
        new_subject = (f"Re: {sent_item.subject}")[:255]
        forward_item = sent_item.create_forward(subject=new_subject, body="Hello reply", to_recipients=[item.author])
        with self.assertRaises(AttributeError) as e:
            forward_item.send(save_copy=False, copy_to_folder=self.account.sent)
        self.assertEqual(e.exception.args[0], "'save_copy' must be True when 'copy_to_folder' is set")
        forward_item.send()
        self.assertEqual(self.account.sent.filter(subject=new_subject).count(), 1)

    def test_mark_as_junk(self):
        # Test that we can mark a Message item as junk and non-junk, and that the message goes to the junk forlder and
        # back to the the inbox.
        item = self.get_test_item().save()
        item.mark_as_junk(is_junk=False, move_item=False)
        self.assertEqual(item.folder, self.test_folder)
        self.assertEqual(self.test_folder.get(categories__contains=self.categories).id, item.id)
        item.mark_as_junk(is_junk=True, move_item=False)
        self.assertEqual(item.folder, self.test_folder)
        self.assertEqual(self.test_folder.get(categories__contains=self.categories).id, item.id)
        # Does not work in O365
        # item.mark_as_junk(is_junk=True, move_item=True)
        # self.assertEqual(item.folder, self.account.junk)
        # self.assertEqual(self.account.junk.get(categories__contains=self.categories).id, item.id)
        item.mark_as_junk(is_junk=False, move_item=True)
        self.assertEqual(item.folder, self.account.inbox)
        self.assertEqual(self.account.inbox.get(categories__contains=self.categories).id, item.id)

    def test_mime_content(self):
        # Tests the 'mime_content' field
        subject = get_random_string(16)
        msg = MIMEMultipart()
        msg["From"] = self.account.primary_smtp_address
        msg["To"] = self.account.primary_smtp_address
        msg["Subject"] = subject
        body = "MIME test mail"
        msg.attach(MIMEText(body, "plain", _charset="utf-8"))
        mime_content = msg.as_bytes()
        self.ITEM_CLASS(
            folder=self.test_folder,
            to_recipients=[self.account.primary_smtp_address],
            mime_content=mime_content,
            categories=self.categories,
        ).save()
        self.assertEqual(self.test_folder.get(subject=subject).body, body)

    def test_invalid_kwargs_on_send(self):
        # Only Message class has the send() method
        item = self.get_test_item()
        item.account = None
        with self.assertRaises(ValueError):
            item.send()  # Must have account on send
        item = self.get_test_item()
        item.save()
        with self.assertRaises(TypeError) as e:
            item.send(copy_to_folder="XXX", save_copy=True)  # Invalid folder
        self.assertEqual(
            e.exception.args[0],
            "'saved_item_folder' 'XXX' must be of type (<class 'exchangelib.folders.base.BaseFolder'>, "
            "<class 'exchangelib.properties.FolderId'>)",
        )
        item_id, changekey = item.id, item.changekey
        item.delete()
        item.id, item.changekey = item_id, changekey
        with self.assertRaises(ErrorItemNotFound):
            item.send()  # Item disappeared
        item = self.get_test_item()
        with self.assertRaises(AttributeError):
            item.send(copy_to_folder=self.account.trash, save_copy=False)  # Inconsistent args
