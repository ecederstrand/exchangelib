from exchangelib import Q, Message, ExtendedProperty
from exchangelib.errors import ErrorDeleteDistinguishedFolder, ErrorObjectTypeChanged, DoesNotExist, \
    MultipleObjectsReturned
from exchangelib.folders import Calendar, DeletedItems, Drafts, Inbox, Outbox, SentItems, JunkEmail, Messages, Tasks, \
    Contacts, Folder, RecipientCache, GALContacts, System, AllContacts, MyContactsExtended, Reminders, Favorites, \
    AllItems, ConversationSettings, Friends, RSSFeeds, Sharing, IMContactList, QuickContacts, Journal, Notes, \
    SyncIssues, MyContacts, ToDoSearch, FolderCollection, DistinguishedFolderId, Files, \
    DefaultFoldersChangeHistory, PassThroughSearchResults, SmsAndChatsSync, GraphAnalytics, Signal, \
    PdpProfileV2Secured, VoiceMail, FolderQuerySet, SingleFolderQuerySet, SHALLOW, RootOfHierarchy
from exchangelib.properties import Mailbox, InvalidField
from exchangelib.services import GetFolder

from .common import EWSTest, get_random_string


class FolderTest(EWSTest):
    def test_folders(self):
        for f in self.account.root.walk():
            if isinstance(f, System):
                # No access to system folder, apparently
                continue
            f.test_access()
        # Test shortcuts
        for f, cls in (
                (self.account.trash, DeletedItems),
                (self.account.drafts, Drafts),
                (self.account.inbox, Inbox),
                (self.account.outbox, Outbox),
                (self.account.sent, SentItems),
                (self.account.junk, JunkEmail),
                (self.account.contacts, Contacts),
                (self.account.tasks, Tasks),
                (self.account.calendar, Calendar),
        ):
            with self.subTest(f=f, cls=cls):
                self.assertIsInstance(f, cls)
                f.test_access()
                # Test item field lookup
                self.assertEqual(f.get_item_field_by_fieldname('subject').name, 'subject')
                with self.assertRaises(ValueError):
                    f.get_item_field_by_fieldname('XXX')

    def test_find_folders(self):
        folders = list(FolderCollection(account=self.account, folders=[self.account.root]).find_folders())
        self.assertGreater(len(folders), 40, sorted(f.name for f in folders))

    def test_find_folders_with_restriction(self):
        # Exact match
        folders = list(FolderCollection(account=self.account, folders=[self.account.root])
                       .find_folders(q=Q(name='Top of Information Store')))
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))
        # Startswith
        folders = list(FolderCollection(account=self.account, folders=[self.account.root])
                       .find_folders(q=Q(name__startswith='Top of ')))
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))
        # Wrong case
        folders = list(FolderCollection(account=self.account, folders=[self.account.root])
                       .find_folders(q=Q(name__startswith='top of ')))
        self.assertEqual(len(folders), 0, sorted(f.name for f in folders))
        # Case insensitive
        folders = list(FolderCollection(account=self.account, folders=[self.account.root])
                       .find_folders(q=Q(name__istartswith='top of ')))
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

    def test_get_folders(self):
        folders = list(FolderCollection(account=self.account, folders=[self.account.root]).get_folders())
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

        # Test that GetFolder can handle FolderId instances
        folders = list(FolderCollection(account=self.account, folders=[DistinguishedFolderId(
            id=Inbox.DISTINGUISHED_FOLDER_ID,
            mailbox=Mailbox(email_address=self.account.primary_smtp_address)
        )]).get_folders())
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

    def test_get_folders_with_distinguished_id(self):
        # Test that we return an Inbox instance and not a generic Messages or Folder instance when we call GetFolder
        # with a DistinguishedFolderId instance with an ID of Inbox.DISTINGUISHED_FOLDER_ID.
        inbox = list(GetFolder(account=self.account).call(
            folders=[DistinguishedFolderId(
                id=Inbox.DISTINGUISHED_FOLDER_ID,
                mailbox=Mailbox(email_address=self.account.primary_smtp_address))
            ],
            shape='IdOnly',
            additional_fields=[],
        ))[0]
        self.assertIsInstance(inbox, Inbox)

    def test_folder_grouping(self):
        # If you get errors here, you probably need to fill out [folder class].LOCALIZED_NAMES for your locale.
        for f in self.account.root.walk():
            with self.subTest(f=f):
                if isinstance(f, (
                        Messages, DeletedItems, AllContacts, MyContactsExtended, Sharing, Favorites, SyncIssues, MyContacts
                )):
                    self.assertEqual(f.folder_class, 'IPF.Note')
                elif isinstance(f, GALContacts):
                    self.assertEqual(f.folder_class, 'IPF.Contact.GalContacts')
                elif isinstance(f, RecipientCache):
                    self.assertEqual(f.folder_class, 'IPF.Contact.RecipientCache')
                elif isinstance(f, Contacts):
                    self.assertEqual(f.folder_class, 'IPF.Contact')
                elif isinstance(f, Calendar):
                    self.assertEqual(f.folder_class, 'IPF.Appointment')
                elif isinstance(f, (Tasks, ToDoSearch)):
                    self.assertEqual(f.folder_class, 'IPF.Task')
                elif isinstance(f, Reminders):
                    self.assertEqual(f.folder_class, 'Outlook.Reminder')
                elif isinstance(f, AllItems):
                    self.assertEqual(f.folder_class, 'IPF')
                elif isinstance(f, ConversationSettings):
                    self.assertEqual(f.folder_class, 'IPF.Configuration')
                elif isinstance(f, Files):
                    self.assertEqual(f.folder_class, 'IPF.Files')
                elif isinstance(f, Friends):
                    self.assertEqual(f.folder_class, 'IPF.Note')
                elif isinstance(f, RSSFeeds):
                    self.assertEqual(f.folder_class, 'IPF.Note.OutlookHomepage')
                elif isinstance(f, IMContactList):
                    self.assertEqual(f.folder_class, 'IPF.Contact.MOC.ImContactList')
                elif isinstance(f, QuickContacts):
                    self.assertEqual(f.folder_class, 'IPF.Contact.MOC.QuickContacts')
                elif isinstance(f, Journal):
                    self.assertEqual(f.folder_class, 'IPF.Journal')
                elif isinstance(f, Notes):
                    self.assertEqual(f.folder_class, 'IPF.StickyNote')
                elif isinstance(f, DefaultFoldersChangeHistory):
                    self.assertEqual(f.folder_class, 'IPM.DefaultFolderHistoryItem')
                elif isinstance(f, PassThroughSearchResults):
                    self.assertEqual(f.folder_class, 'IPF.StoreItem.PassThroughSearchResults')
                elif isinstance(f, SmsAndChatsSync):
                    self.assertEqual(f.folder_class, 'IPF.SmsAndChatsSync')
                elif isinstance(f, GraphAnalytics):
                    self.assertEqual(f.folder_class, 'IPF.StoreItem.GraphAnalytics')
                elif isinstance(f, Signal):
                    self.assertEqual(f.folder_class, 'IPF.StoreItem.Signal')
                elif isinstance(f, PdpProfileV2Secured):
                    self.assertEqual(f.folder_class, 'IPF.StoreItem.PdpProfileSecured')
                elif isinstance(f, VoiceMail):
                    self.assertEqual(f.folder_class, 'IPF.Note.Microsoft.Voicemail')
                else:
                    self.assertIn(f.folder_class, (None, 'IPF'), (f.name, f.__class__.__name__, f.folder_class))
                    self.assertIsInstance(f, Folder)

    def test_counts(self):
        # Test count values on a folder
        f = Folder(parent=self.account.inbox, name=get_random_string(16)).save()
        f.refresh()

        self.assertEqual(f.total_count, 0)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 0)
        # Create some items
        items = []
        for i in range(3):
            subject = 'Test Subject %s' % i
            item = Message(account=self.account, folder=f, is_read=False, subject=subject, categories=self.categories)
            item.save()
            items.append(item)
        # Refresh values and see that total_count and unread_count changes
        f.refresh()
        self.assertEqual(f.total_count, 3)
        self.assertEqual(f.unread_count, 3)
        self.assertEqual(f.child_folder_count, 0)
        for i in items:
            i.is_read = True
            i.save()
        # Refresh values and see that unread_count changes
        f.refresh()
        self.assertEqual(f.total_count, 3)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 0)
        self.bulk_delete(items)
        # Refresh values and see that total_count changes
        f.refresh()
        self.assertEqual(f.total_count, 0)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 0)
        # Create some subfolders
        subfolders = []
        for i in range(3):
            subfolders.append(Folder(parent=f, name=get_random_string(16)).save())
        # Refresh values and see that child_folder_count changes
        f.refresh()
        self.assertEqual(f.total_count, 0)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 3)
        for sub_f in subfolders:
            sub_f.delete()
        # Refresh values and see that child_folder_count changes
        f.refresh()
        self.assertEqual(f.total_count, 0)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 0)
        f.delete()

    def test_refresh(self):
        # Test that we can refresh folders
        for f in self.account.root.walk():
            with self.subTest(f=f):
                if isinstance(f, System):
                    # Can't refresh the 'System' folder for some reason
                    continue
                old_values = {}
                for field in f.FIELDS:
                    old_values[field.name] = getattr(f, field.name)
                    if field.name in ('account', 'id', 'changekey', 'parent_folder_id'):
                        # These are needed for a successful refresh()
                        continue
                    if field.is_read_only:
                        continue
                    setattr(f, field.name, self.random_val(field))
                f.refresh()
                for field in f.FIELDS:
                    if field.name == 'changekey':
                        # folders may change while we're testing
                        continue
                    if field.is_read_only:
                        # count values may change during the test
                        continue
                    self.assertEqual(getattr(f, field.name), old_values[field.name], (f, field.name))

        # Test refresh of root
        all_folders = sorted(f.name for f in self.account.root.walk())
        self.account.root.refresh()
        self.assertIsNone(self.account.root._subfolders)
        self.assertEqual(
            sorted(f.name for f in self.account.root.walk()),
            all_folders
        )

        folder = Folder()
        with self.assertRaises(ValueError):
            folder.refresh()  # Must have root folder
        folder.root = self.account.root
        with self.assertRaises(ValueError):
            folder.refresh()  # Must have an id

    def test_parent(self):
        self.assertEqual(
            self.account.calendar.parent.name,
            'Top of Information Store'
        )
        self.assertEqual(
            self.account.calendar.parent.parent.name,
            'root'
        )

    def test_children(self):
        self.assertIn(
            'Top of Information Store',
            [c.name for c in self.account.root.children]
        )

    def test_parts(self):
        self.assertEqual(
            [p.name for p in self.account.calendar.parts],
            ['root', 'Top of Information Store', self.account.calendar.name]
        )

    def test_absolute(self):
        self.assertEqual(
            self.account.calendar.absolute,
            '/root/Top of Information Store/' + self.account.calendar.name
        )

    def test_walk(self):
        self.assertGreaterEqual(len(list(self.account.root.walk())), 20)
        self.assertGreaterEqual(len(list(self.account.contacts.walk())), 2)

    def test_tree(self):
        self.assertTrue(self.account.root.tree().startswith('root'))

    def test_glob(self):
        self.assertGreaterEqual(len(list(self.account.root.glob('*'))), 5)
        self.assertEqual(len(list(self.account.contacts.glob('GAL*'))), 1)
        self.assertEqual(len(list(self.account.contacts.glob('gal*'))), 1)  # Test case-insensitivity
        self.assertGreaterEqual(len(list(self.account.contacts.glob('/'))), 5)
        self.assertGreaterEqual(len(list(self.account.contacts.glob('../*'))), 5)
        self.assertEqual(len(list(self.account.root.glob('**/%s' % self.account.contacts.name))), 1)
        self.assertEqual(len(list(self.account.root.glob('Top of*/%s' % self.account.contacts.name))), 1)

    def test_collection_filtering(self):
        self.assertGreaterEqual(self.account.root.tois.children.all().count(), 0)
        self.assertGreaterEqual(self.account.root.tois.walk().all().count(), 0)
        self.assertGreaterEqual(self.account.root.tois.glob('*').all().count(), 0)

    def test_empty_collections(self):
        self.assertEqual(self.account.trash.children.all().count(), 0)
        self.assertEqual(self.account.trash.walk().all().count(), 0)
        self.assertEqual(self.account.trash.glob('XXX').all().count(), 0)
        self.assertEqual(list(self.account.trash.glob('XXX').get_folders()), [])
        self.assertEqual(list(self.account.trash.glob('XXX').find_folders()), [])

    def test_div_navigation(self):
        self.assertEqual(
            (self.account.root / 'Top of Information Store' / self.account.calendar.name).id,
            self.account.calendar.id
        )
        self.assertEqual(
            (self.account.root / 'Top of Information Store' / '..').id,
            self.account.root.id
        )
        self.assertEqual(
            (self.account.root / '.').id,
            self.account.root.id
        )

    def test_double_div_navigation(self):
        self.account.root.refresh()  # Clear the cache

        # Test normal navigation
        self.assertEqual(
            (self.account.root // 'Top of Information Store' // self.account.calendar.name).id,
            self.account.calendar.id
        )
        self.assertIsNone(self.account.root._subfolders)

        # Test parent ('..') syntax. Should not work
        with self.assertRaises(ValueError) as e:
            _ = self.account.root // 'Top of Information Store' // '..'
        self.assertEqual(e.exception.args[0], 'Cannot get parent without a folder cache')
        self.assertIsNone(self.account.root._subfolders)

        # Test self ('.') syntax
        self.assertEqual(
            (self.account.root // '.').id,
            self.account.root.id
        )
        self.assertIsNone(self.account.root._subfolders)

    def test_extended_properties(self):
        # Test extended properties on folders and folder roots. This extended prop gets the size (in bytes) of a folder
        class FolderSize(ExtendedProperty):
            property_tag = 0x0e08
            property_type = 'Integer'

        try:
            Folder.register('size', FolderSize)
            self.account.inbox.refresh()
            self.assertGreater(self.account.inbox.size, 0)
        finally:
            Folder.deregister('size')

        try:
            RootOfHierarchy.register('size', FolderSize)
            self.account.root.refresh()
            self.assertGreater(self.account.root.size, 0)
        finally:
            RootOfHierarchy.deregister('size')

        # Register is only allowed on Folder and RootOfHierarchy classes
        with self.assertRaises(TypeError):
            self.account.calendar.register(FolderSize)
        with self.assertRaises(TypeError):
            self.account.root.register(FolderSize)

    def test_create_update_empty_delete(self):
        f = Messages(parent=self.account.inbox, name=get_random_string(16))
        f.save()
        self.assertIsNotNone(f.id)
        self.assertIsNotNone(f.changekey)

        new_name = get_random_string(16)
        f.name = new_name
        f.save()
        f.refresh()
        self.assertEqual(f.name, new_name)

        with self.assertRaises(ErrorObjectTypeChanged):
            # FolderClass may not be changed
            f.folder_class = get_random_string(16)
            f.save(update_fields=['folder_class'])

        # Create a subfolder
        Messages(parent=f, name=get_random_string(16)).save()
        self.assertEqual(len(list(f.children)), 1)
        f.empty()
        self.assertEqual(len(list(f.children)), 1)
        f.empty(delete_sub_folders=True)
        self.assertEqual(len(list(f.children)), 0)

        # Create a subfolder again, and delete it by wiping
        Messages(parent=f, name=get_random_string(16)).save()
        self.assertEqual(len(list(f.children)), 1)
        f.wipe()
        self.assertEqual(len(list(f.children)), 0)

        f.delete()
        with self.assertRaises(ValueError):
            # No longer has an ID
            f.refresh()

        # Delete all subfolders of inbox
        for c in self.account.inbox.children:
            c.delete()

        with self.assertRaises(ErrorDeleteDistinguishedFolder):
            self.account.inbox.delete()

    def test_generic_folder(self):
        f = Folder(parent=self.account.inbox, name=get_random_string(16))
        f.save()
        f.name = get_random_string(16)
        f.save()
        f.delete()

    def test_folder_query_set(self):
        # Create a folder hierarchy and test a folder queryset
        #
        # -f0
        #  - f1
        #  - f2
        #    - f21
        #    - f22
        f0 = Folder(parent=self.account.inbox, name=get_random_string(16)).save()
        f1 = Folder(parent=f0, name=get_random_string(16)).save()
        f2 = Folder(parent=f0, name=get_random_string(16)).save()
        f21 = Folder(parent=f2, name=get_random_string(16)).save()
        f22 = Folder(parent=f2, name=get_random_string(16)).save()
        folder_qs = SingleFolderQuerySet(account=self.account, folder=f0)
        try:
            # Test all()
            self.assertSetEqual(
                set(f.name for f in folder_qs.all()),
                {f.name for f in (f1, f2, f21, f22)}
            )

            # Test only()
            self.assertSetEqual(
                set(f.name for f in folder_qs.only('name').all()),
                {f.name for f in (f1, f2, f21, f22)}
            )
            self.assertSetEqual(
                set(f.child_folder_count for f in folder_qs.only('name').all()),
                {None}
            )
            # Test depth()
            self.assertSetEqual(
                set(f.name for f in folder_qs.depth(SHALLOW).all()),
                {f.name for f in (f1, f2)}
            )

            # Test filter()
            self.assertSetEqual(
                set(f.name for f in folder_qs.filter(name=f1.name)),
                {f.name for f in (f1,)}
            )
            self.assertSetEqual(
                set(f.name for f in folder_qs.filter(name__in=[f1.name, f2.name])),
                {f.name for f in (f1, f2)}
            )

            # Test get()
            self.assertEqual(
                folder_qs.get(name=f2.name).child_folder_count,
                2
            )
            self.assertEqual(
                folder_qs.filter(name=f2.name).get().child_folder_count,
                2
            )
            self.assertEqual(
                folder_qs.only('name').get(name=f2.name).name,
                f2.name
            )
            self.assertEqual(
                folder_qs.only('name').get(name=f2.name).child_folder_count,
                None
            )
            with self.assertRaises(DoesNotExist):
                folder_qs.get(name=get_random_string(16))
            with self.assertRaises(MultipleObjectsReturned):
                folder_qs.get()
        finally:
            f0.wipe()
            f0.delete()

    def test_folder_query_set_failures(self):
        with self.assertRaises(ValueError):
            FolderQuerySet('XXX')
        fld_qs = SingleFolderQuerySet(account=self.account, folder=self.account.inbox)
        with self.assertRaises(InvalidField):
            fld_qs.only('XXX')
        with self.assertRaises(InvalidField):
            list(fld_qs.filter(XXX='XXX'))
