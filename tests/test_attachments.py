from exchangelib.attachments import FileAttachment, ItemAttachment, AttachmentId
from exchangelib.errors import ErrorItemNotFound, ErrorInvalidIdMalformed
from exchangelib.folders import Inbox
from exchangelib.items import Item, Message
from exchangelib.services import GetAttachment
from exchangelib.util import chunkify, TNS

from .test_items.test_basics import BaseItemTest
from .common import get_random_string


class AttachmentsTest(BaseItemTest):
    TEST_FOLDER = 'inbox'
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message

    def test_attachment_failure(self):
        att1 = FileAttachment(name='my_file_1.txt', content='Hello from unicode æøå'.encode('utf-8'))
        att1.attachment_id = 'XXX'
        with self.assertRaises(ValueError):
            att1.attach()  # Cannot have an attachment ID
        att1.attachment_id = None
        with self.assertRaises(ValueError):
            att1.attach()  # Must have a parent item
        att1.parent_item = Item()
        with self.assertRaises(ValueError):
            att1.attach()  # Parent item must have an account
        att1.parent_item = None
        with self.assertRaises(ValueError):
            att1.detach()  # Must have an attachment ID
        att1.attachment_id = 'XXX'
        with self.assertRaises(ValueError):
            att1.detach()  # Must have a parent item
        att1.parent_item = Item()
        with self.assertRaises(ValueError):
            att1.detach()  # Parent item must have an account
        att1.parent_item = None
        att1.attachment_id = None

    def test_attachment_properties(self):
        binary_file_content = 'Hello from unicode æøå'.encode('utf-8')
        att1 = FileAttachment(name='my_file_1.txt', content=binary_file_content)
        self.assertIn("name='my_file_1.txt'", str(att1))
        att1.content = binary_file_content  # Test property setter
        self.assertEqual(att1.content, binary_file_content)  # Test property getter
        att1.attachment_id = 'xxx'
        self.assertEqual(att1.content, binary_file_content)  # Test property getter when attachment_id is set
        att1._content = None
        with self.assertRaises(ValueError):
            print(att1.content)  # Test property getter when we need to fetch the content

        attached_item1 = self.get_test_item(folder=self.test_folder)
        att2 = ItemAttachment(name='attachment1', item=attached_item1)
        self.assertIn("name='attachment1'", str(att2))
        att2.item = attached_item1  # Test property setter
        self.assertEqual(att2.item, attached_item1)  # Test property getter
        self.assertEqual(att2.item, attached_item1)  # Test property getter
        att2.attachment_id = 'xxx'
        self.assertEqual(att2.item, attached_item1)  # Test property getter when attachment_id is set
        att2._item = None
        with self.assertRaises(ValueError):
            print(att2.item)  # Test property getter when we need to fetch the item

    def test_file_attachments(self):
        item = self.get_test_item(folder=self.test_folder)

        # Test __init__(attachments=...) and attach() on new item
        binary_file_content = 'Hello from unicode æøå'.encode('utf-8')
        att1 = FileAttachment(name='my_file_1.txt', content=binary_file_content)
        self.assertEqual(len(item.attachments), 0)
        item.attach(att1)
        self.assertEqual(len(item.attachments), 1)
        item.save()
        fresh_item = self.get_item_by_id(item)
        self.assertEqual(len(fresh_item.attachments), 1)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'my_file_1.txt')
        self.assertEqual(fresh_attachments[0].content, binary_file_content)

        # Test raw call to service
        self.assertEqual(
            list(GetAttachment(account=item.account).call(
                items=[att1.attachment_id],
                include_mime_content=False)
            )[0].find('{%s}Content' % TNS).text,
            'SGVsbG8gZnJvbSB1bmljb2RlIMOmw7jDpQ==')

        # Test attach on saved object
        att2 = FileAttachment(name='my_file_2.txt', content=binary_file_content)
        self.assertEqual(len(item.attachments), 1)
        item.attach(att2)
        self.assertEqual(len(item.attachments), 2)
        fresh_item = self.get_item_by_id(item)
        self.assertEqual(len(fresh_item.attachments), 2)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'my_file_1.txt')
        self.assertEqual(fresh_attachments[0].content, binary_file_content)
        self.assertEqual(fresh_attachments[1].name, 'my_file_2.txt')
        self.assertEqual(fresh_attachments[1].content, binary_file_content)

        # Test detach
        item.detach(att1)
        self.assertTrue(att1.attachment_id is None)
        self.assertTrue(att1.parent_item is None)
        fresh_item = self.get_item_by_id(item)
        self.assertEqual(len(fresh_item.attachments), 1)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'my_file_2.txt')
        self.assertEqual(fresh_attachments[0].content, binary_file_content)

    def test_streaming_file_attachments(self):
        item = self.get_test_item(folder=self.test_folder)
        large_binary_file_content = get_random_string(2**10).encode('utf-8')
        large_att = FileAttachment(name='my_large_file.txt', content=large_binary_file_content)
        item.attach(large_att)
        item.save()

        # Test streaming file content
        fresh_item = self.get_item_by_id(item)
        with fresh_item.attachments[0].fp as fp:
            self.assertEqual(fp.read(), large_binary_file_content)

        # Test partial reads of streaming file content
        fresh_item = self.get_item_by_id(item)
        with fresh_item.attachments[0].fp as fp:
            chunked_reads = []
            buffer = fp.read(7)
            while buffer:
                chunked_reads.append(buffer)
                buffer = fp.read(7)
            self.assertListEqual(chunked_reads, list(chunkify(large_binary_file_content, 7)))

    def test_streaming_file_attachment_error(self):
        # Test that we can parse XML error responses in streaming mode.

        # Try to stram an attachment with malformed ID
        att = FileAttachment(
            parent_item=self.get_test_item(folder=self.test_folder),
            attachment_id=AttachmentId(id='AAMk='),
            name='dummy.txt',
            content=b'',
        )
        with self.assertRaises(ErrorInvalidIdMalformed):
            with att.fp as fp:
                fp.read()

        # Try to stream a non-existent attachment
        att.attachment_id.id = \
            'AAMkADQyYzZmYmUxLTJiYjItNDg2Ny1iMzNjLTIzYWE1NDgxNmZhNABGAAAAAADUebQDarW2Q7G2Ji8hKofPBwAl9iKCsfCfS' \
            'a9cmjh+JCrCAAPJcuhjAABioKiOUTCQRI6Q5sRzi0pJAAHnDV3CAAABEgAQAN0zlxDrzlxAteU+kt84qOM='
        with self.assertRaises(ErrorItemNotFound):
            with att.fp as fp:
                fp.read()

    def test_empty_file_attachment(self):
        item = self.get_test_item(folder=self.test_folder)
        att1 = FileAttachment(name='empty_file.txt', content=b'')
        item.attach(att1)
        item.save()
        fresh_item = self.get_item_by_id(item)
        self.assertEqual(
            fresh_item.attachments[0].content,
            b''
        )

    def test_both_attachment_types(self):
        item = self.get_test_item(folder=self.test_folder)
        attached_item = self.get_test_item(folder=self.test_folder).save()
        item_attachment = ItemAttachment(name='item_attachment', item=attached_item)
        file_attachment = FileAttachment(name='file_attachment', content=b'file_attachment')
        item.attach(item_attachment)
        item.attach(file_attachment)
        item.save()

        fresh_item = self.get_item_by_id(item)
        self.assertSetEqual(
            {a.name for a in fresh_item.attachments},
            {'item_attachment', 'file_attachment'}
        )

    def test_recursive_attachments(self):
        # Test that we can handle an item which has an attached item, which has an attached item...
        item = self.get_test_item(folder=self.test_folder)
        attached_item_level_1 = self.get_test_item(folder=self.test_folder)
        attached_item_level_2 = self.get_test_item(folder=self.test_folder)
        attached_item_level_3 = self.get_test_item(folder=self.test_folder)

        attached_item_level_3.save()
        attachment_level_3 = ItemAttachment(name='attached_item_level_3', item=attached_item_level_3)
        attached_item_level_2.attach(attachment_level_3)
        attached_item_level_2.save()
        attachment_level_2 = ItemAttachment(name='attached_item_level_2', item=attached_item_level_2)
        attached_item_level_1.attach(attachment_level_2)
        attached_item_level_1.save()
        attachment_level_1 = ItemAttachment(name='attached_item_level_1', item=attached_item_level_1)
        item.attach(attachment_level_1)
        item.save()

        self.assertEqual(
            item.attachments[0].item.attachments[0].item.attachments[0].item.subject,
            attached_item_level_3.subject
        )

        # Also test a fresh item
        new_item = self.test_folder.get(id=item.id, changekey=item.changekey)
        self.assertEqual(
            new_item.attachments[0].item.attachments[0].item.attachments[0].item.subject,
            attached_item_level_3.subject
        )

    def test_detach_all(self):
        # Make sure that we can detach all by passing item.attachments
        item = self.get_test_item(folder=self.test_folder).save()
        item.attach([FileAttachment(name='empty_file.txt', content=b'') for _ in range(6)])
        self.assertEqual(len(item.attachments), 6)
        item.detach(item.attachments)
        self.assertEqual(len(item.attachments), 0)

    def test_detach_with_refresh(self):
        # Make sure that we can detach after refresh
        item = self.get_test_item(folder=self.test_folder).save()
        item.attach(FileAttachment(name='empty_file.txt', content=b''))
        item.refresh()
        item.detach(item.attachments)
