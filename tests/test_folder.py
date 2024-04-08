from contextlib import suppress
from inspect import isclass
from unittest.mock import Mock

import requests_mock

import exchangelib.folders
import exchangelib.folders.known_folders
from exchangelib.errors import (
    DoesNotExist,
    ErrorCannotDeleteObject,
    ErrorCannotEmptyFolder,
    ErrorDeleteDistinguishedFolder,
    ErrorFolderExists,
    ErrorFolderNotFound,
    ErrorInvalidIdMalformed,
    ErrorItemNotFound,
    ErrorItemSave,
    ErrorNoPublicFolderReplicaAvailable,
    ErrorObjectTypeChanged,
    MultipleObjectsReturned,
)
from exchangelib.extended_properties import ExtendedProperty
from exchangelib.folders import (
    SHALLOW,
    AllCategorizedItems,
    AllContacts,
    AllItems,
    AllPersonMetadata,
    AllTodoTasks,
    ApplicationData,
    BaseFolder,
    Birthdays,
    Calendar,
    CommonViews,
    Companies,
    Contacts,
    ConversationSettings,
    CrawlerData,
    DefaultFoldersChangeHistory,
    DeletedItems,
    DistinguishedFolderId,
    DlpPolicyEvaluation,
    Drafts,
    EventCheckPoints,
    ExternalContacts,
    Favorites,
    Files,
    Folder,
    FolderCollection,
    FolderMemberships,
    FolderQuerySet,
    FreeBusyCache,
    Friends,
    FromFavoriteSenders,
    GALContacts,
    GraphAnalytics,
    IMContactList,
    Inbox,
    Journal,
    JunkEmail,
    Messages,
    MyContacts,
    MyContactsExtended,
    NonDeletableFolder,
    Notes,
    OrganizationalContacts,
    Outbox,
    PassThroughSearchResults,
    PdpProfileV2Secured,
    PeopleCentricConversationBuddies,
    PublicFoldersRoot,
    QuickContacts,
    RecipientCache,
    RecoveryPoints,
    RelevantContacts,
    Reminders,
    RootOfHierarchy,
    RSSFeeds,
    SentItems,
    Sharing,
    Signal,
    SingleFolderQuerySet,
    SkypeTeamsMessages,
    SmsAndChatsSync,
    SwssItems,
    SyncIssues,
    Tasks,
    ToDoSearch,
    UserCuratedContacts,
    VoiceMail,
    WellknownFolder,
)
from exchangelib.folders.known_folders import (
    MISC_FOLDERS,
    NON_DELETABLE_FOLDERS,
    WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT,
    WELLKNOWN_FOLDERS_IN_ROOT,
)
from exchangelib.items import Message
from exchangelib.properties import CalendarPermission, EffectiveRights, InvalidField, Mailbox, PermissionSet, UserId
from exchangelib.queryset import Q
from exchangelib.services import DeleteFolder, EmptyFolder, FindFolder, GetFolder
from exchangelib.version import EXCHANGE_2007, Version

from .common import (
    EWSTest,
    get_random_bool,
    get_random_byte,
    get_random_bytes,
    get_random_datetime,
    get_random_int,
    get_random_string,
)


def get_random_str_tuple(tuple_length, str_length):
    return tuple(get_random_string(str_length, spaces=False) for _ in range(tuple_length))


class FolderTest(EWSTest):
    def test_folders(self):
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
                self.assertEqual(f.get_item_field_by_fieldname("subject").name, "subject")
                with self.assertRaises(ValueError):
                    f.get_item_field_by_fieldname("XXX")

    def test_folder_failure(self):
        # Folders must have an ID
        with self.assertRaises(ValueError):
            self.account.root.get_folder(Folder())
        with self.assertRaises(ValueError):
            self.account.root.add_folder(Folder())
        with self.assertRaises(ValueError):
            self.account.root.update_folder(Folder())
        with self.assertRaises(ValueError):
            self.account.root.remove_folder(Folder())
        # Removing a non-existent folder is allowed
        self.account.root.remove_folder(Folder(id="XXX"))
        # Must be called on a distinguished folder class
        with self.assertRaises(ValueError):
            RootOfHierarchy.get_distinguished(account=self.account)
        with self.assertRaises(ValueError):
            self.account.root.get_default_folder(Folder)

        with suppress(ErrorFolderNotFound):
            with self.assertRaises(ValueError) as e:
                Folder(root=self.account.public_folders_root, parent=self.account.inbox)
            self.assertEqual(e.exception.args[0], "'parent.root' must match 'root'")
        with self.assertRaises(ValueError) as e:
            Folder(parent=self.account.inbox, parent_folder_id="XXX")
        self.assertEqual(e.exception.args[0], "'parent_folder_id' must match 'parent' ID")
        with self.assertRaises(TypeError) as e:
            Folder(root="XXX").clean()
        self.assertEqual(
            e.exception.args[0], "'root' 'XXX' must be of type <class 'exchangelib.folders.roots.RootOfHierarchy'>"
        )
        with self.assertRaises(ValueError) as e:
            Folder().save(update_fields=["name"])
        self.assertEqual(e.exception.args[0], "'update_fields' is only valid for updates")
        with self.assertRaises(ValueError) as e:
            Messages().validate_item_field("XXX", version=self.account.version)
        self.assertIn("'XXX' is not a valid field on", e.exception.args[0])
        with self.assertRaises(ValueError) as e:
            Folder.item_model_from_tag("XXX")
        self.assertEqual(e.exception.args[0], "Item type XXX was unexpected in a Folder folder")

    @requests_mock.mock(real_http=True)
    def test_public_folders_root(self, m):
        # Test account does not have a public folders root. Make a dummy query just to hit .get_children()
        with suppress(ErrorNoPublicFolderReplicaAvailable):
            self.assertGreaterEqual(
                len(list(PublicFoldersRoot(account=self.account).get_children(self.account.inbox))),
                0,
            )
        # Test public folders root with mocked responses
        get_public_folder_xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:GetFolderResponse xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                             xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
            <m:ResponseMessages>
                <m:GetFolderResponseMessage ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:Folders>
                        <t:Folder>
                            <t:FolderId Id="YAABdofPkAAA=" ChangeKey="AwAAABYAAABGDloItRzyTrAt+"/>
                            <t:FolderClass>IPF.Note</t:FolderClass>
                            <t:DisplayName>publicfoldersroot</t:DisplayName>
                        </t:Folder>
                    </m:Folders>
                </m:GetFolderResponseMessage>
            </m:ResponseMessages>
        </m:GetFolderResponse>
    </s:Body>
</s:Envelope>"""
        find_public_folder_children_xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:FindFolderResponse
                xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
            <m:ResponseMessages>
                <m:FindFolderResponseMessage ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:RootFolder IndexedPagingOffset="2" TotalItemsInView="2" IncludesLastItemInRange="true">
                        <t:Folders>
                            <t:Folder>
                                <t:FolderId Id="2BBBBxEAAAA=" ChangeKey="AQBBBBYBBBAGDloItRzyTrAt+"/>
                                <t:ParentFolderId Id="YAABdofPkAAA=" ChangeKey="AwAAABYAAABGDloItRzyTrAt+"/>
                                <t:FolderClass>IPF.Contact</t:FolderClass>
                                <t:DisplayName>Sample Contacts</t:DisplayName>
                                <t:ChildFolderCount>2</t:ChildFolderCount>
                                <t:TotalCount>0</t:TotalCount>
                                <t:UnreadCount>0</t:UnreadCount>
                            </t:Folder>
                            <t:Folder>
                                <t:FolderId Id="2AAAAxEAAAA=" ChangeKey="AQAAABYAAABGDloItRzyTrAt+"/>
                                <t:ParentFolderId Id="YAABdofPkAAA=" ChangeKey="AwAAABYAAABGDloItRzyTrAt+"/>
                                <t:FolderClass>IPF.Note</t:FolderClass>
                                <t:DisplayName>Sample Folder</t:DisplayName>
                                <t:ChildFolderCount>0</t:ChildFolderCount>
                                <t:TotalCount>0</t:TotalCount>
                                <t:UnreadCount>0</t:UnreadCount>
                            </t:Folder>
                        </t:Folders>
                    </m:RootFolder>
                </m:FindFolderResponseMessage>
            </m:ResponseMessages>
        </m:FindFolderResponse>
    </s:Body>
</s:Envelope>"""
        get_public_folder_children_xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:GetFolderResponse xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                             xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
            <m:ResponseMessages>
                <m:GetFolderResponseMessage ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:Folders>
                        <t:Folder>
                            <t:FolderId Id="2BBBBxEAAAA=" ChangeKey="AQBBBBYBBBAGDloItRzyTrAt+"/>
                            <t:FolderClass>IPF.Contact</t:FolderClass>
                            <t:DisplayName>Sample Contacts</t:DisplayName>
                        </t:Folder>
                        <t:Folder>
                            <t:FolderId Id="2AAAAxEAAAA=" ChangeKey="AQAAABYAAABGDloItRzyTrAt+"/>
                            <t:FolderClass>IPF.Note</t:FolderClass>
                            <t:DisplayName>Sample Folder</t:DisplayName>
                        </t:Folder>
                    </m:Folders>
                </m:GetFolderResponseMessage>
            </m:ResponseMessages>
        </m:GetFolderResponse>
    </s:Body>
</s:Envelope>"""
        m.post(
            self.account.protocol.service_endpoint,
            [
                dict(status_code=200, content=get_public_folder_xml),
                dict(status_code=200, content=find_public_folder_children_xml),
                dict(status_code=200, content=get_public_folder_children_xml),
            ],
        )
        # Test top-level .children
        self.assertListEqual(
            [f.name for f in self.account.public_folders_root.children], ["Sample Contacts", "Sample Folder"]
        )

        find_public_subfolder1_children_xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:FindFolderResponse
                xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
            <m:ResponseMessages>
                <m:FindFolderResponseMessage ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:RootFolder IndexedPagingOffset="2" TotalItemsInView="2" IncludesLastItemInRange="true">
                        <t:Folders>
                            <t:Folder>
                                <t:FolderId Id="YCCBdofPkCCC=" ChangeKey="AwCCCBYAAABGDloItRzyTrAt+"/>
                                <t:ParentFolderId Id="2BBBBxEAAAA=" ChangeKey="AQBBBBYBBBAGDloItRzyTrAt+"/>
                                <t:FolderClass>IPF.Contact</t:FolderClass>
                                <t:DisplayName>Sample Subfolder1</t:DisplayName>
                                <t:ChildFolderCount>0</t:ChildFolderCount>
                                <t:TotalCount>0</t:TotalCount>
                                <t:UnreadCount>0</t:UnreadCount>
                            </t:Folder>
                            <t:Folder>
                                <t:FolderId Id="2DDDDxEAAAA=" ChangeKey="AwDDDBYAAABGDloItRzyTrAt+"/>
                                <t:ParentFolderId Id="2BBBBxEAAAA=" ChangeKey="AQBBBBYBBBAGDloItRzyTrAt+"/>
                                <t:FolderClass>IPF.Note</t:FolderClass>
                                <t:DisplayName>Sample Subfolder2</t:DisplayName>
                                <t:ChildFolderCount>0</t:ChildFolderCount>
                                <t:TotalCount>0</t:TotalCount>
                                <t:UnreadCount>0</t:UnreadCount>
                            </t:Folder>
                        </t:Folders>
                    </m:RootFolder>
                </m:FindFolderResponseMessage>
            </m:ResponseMessages>
        </m:FindFolderResponse>
    </s:Body>
</s:Envelope>"""
        get_public_subfolder1_children_xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:GetFolderResponse xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                             xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
            <m:ResponseMessages>
                <m:GetFolderResponseMessage ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:Folders>
                        <t:Folder>
                            <t:FolderId Id="YCCBdofPkCCC=" ChangeKey="AwCCCBYAAABGDloItRzyTrAt+"/>
                            <t:FolderClass>IPF.Contact</t:FolderClass>
                            <t:DisplayName>Sample Subfolder1</t:DisplayName>
                        </t:Folder>
                        <t:Folder>
                            <t:FolderId Id="2DDDDxEAAAA=" ChangeKey="AwDDDBYAAABGDloItRzyTrAt+"/>
                            <t:FolderClass>IPF.Note</t:FolderClass>
                            <t:DisplayName>Sample Subfolder2</t:DisplayName>
                        </t:Folder>
                    </m:Folders>
                </m:GetFolderResponseMessage>
            </m:ResponseMessages>
        </m:GetFolderResponse>
    </s:Body>
</s:Envelope>"""
        find_public_subfolder2_children_xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:FindFolderResponse
                xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
            <m:ResponseMessages>
                <m:FindFolderResponseMessage ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:RootFolder IndexedPagingOffset="0" TotalItemsInView="0" IncludesLastItemInRange="true">
                        <t:Folders>
                        </t:Folders>
                    </m:RootFolder>
                </m:FindFolderResponseMessage>
            </m:ResponseMessages>
        </m:FindFolderResponse>
    </s:Body>
</s:Envelope>"""
        m.post(
            self.account.protocol.service_endpoint,
            [
                dict(status_code=200, content=find_public_subfolder1_children_xml),
                dict(status_code=200, content=get_public_subfolder1_children_xml),
                dict(status_code=200, content=find_public_subfolder2_children_xml),
            ],
        )
        # Test .get_children() on subfolders
        f_1 = self.account.public_folders_root / "Sample Contacts"
        f_2 = self.account.public_folders_root / "Sample Folder"
        self.assertListEqual(
            [f.name for f in self.account.public_folders_root.get_children(f_1)],
            ["Sample Subfolder1", "Sample Subfolder2"],
        )
        self.assertListEqual([f.name for f in self.account.public_folders_root.get_children(f_2)], [])

    def test_invalid_deletefolder_args(self):
        with self.assertRaises(ValueError) as e:
            DeleteFolder(account=self.account).call(
                folders=[],
                delete_type="XXX",
            )
        self.assertEqual(
            e.exception.args[0], "'delete_type' 'XXX' must be one of ['HardDelete', 'MoveToDeletedItems', 'SoftDelete']"
        )

    def test_invalid_emptyfolder_args(self):
        with self.assertRaises(ValueError) as e:
            EmptyFolder(account=self.account).call(
                folders=[],
                delete_type="XXX",
                delete_sub_folders=False,
            )
        self.assertEqual(
            e.exception.args[0], "'delete_type' 'XXX' must be one of ['HardDelete', 'MoveToDeletedItems', 'SoftDelete']"
        )

    def test_invalid_findfolder_args(self):
        with self.assertRaises(ValueError) as e:
            FindFolder(account=self.account).call(
                folders=["XXX"],
                additional_fields=None,
                restriction=None,
                shape="XXX",
                depth="Shallow",
                max_items=None,
                offset=None,
            )
        self.assertEqual(e.exception.args[0], "'shape' 'XXX' must be one of ['AllProperties', 'Default', 'IdOnly']")
        with self.assertRaises(ValueError) as e:
            FindFolder(account=self.account).call(
                folders=["XXX"],
                additional_fields=None,
                restriction=None,
                shape="IdOnly",
                depth="XXX",
                max_items=None,
                offset=None,
            )
        self.assertEqual(e.exception.args[0], "'depth' 'XXX' must be one of ['Deep', 'Shallow', 'SoftDeleted']")

    def test_find_folders(self):
        folders = list(FolderCollection(account=self.account, folders=[self.account.root]).find_folders())
        self.assertGreater(len(folders), 40, sorted(f.name for f in folders))

    def test_find_folders_multiple_roots(self):
        # Test failure on different roots
        with self.assertRaises(ValueError) as e:
            list(FolderCollection(account=self.account, folders=[Folder(root="A"), Folder(root="B")]).find_folders())
        self.assertIn("All folders must have the same root hierarchy", e.exception.args[0])

    def test_find_folders_compat(self):
        account = self.get_account()
        coll = FolderCollection(account=account, folders=[account.root])
        account.version = Version(EXCHANGE_2007)  # Need to set it after the last auto-config of version
        with self.assertRaises(NotImplementedError) as e:
            list(coll.find_folders(offset=1))
        self.assertEqual(e.exception.args[0], "'offset' is only supported for Exchange 2010 servers and later")

    def test_find_folders_with_restriction(self):
        # Exact match
        tois_folder_name = self.account.root.tois.name
        folders = list(
            FolderCollection(account=self.account, folders=[self.account.root]).find_folders(q=Q(name=tois_folder_name))
        )
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))
        # Startswith
        folders = list(
            FolderCollection(account=self.account, folders=[self.account.root]).find_folders(
                q=Q(name__startswith=tois_folder_name[:6])
            )
        )
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))
        # Wrong case
        folders = list(
            FolderCollection(account=self.account, folders=[self.account.root]).find_folders(
                q=Q(name__startswith=tois_folder_name[:6].lower())
            )
        )
        self.assertEqual(len(folders), 0, sorted(f.name for f in folders))
        # Case insensitive
        folders = list(
            FolderCollection(account=self.account, folders=[self.account.root]).find_folders(
                q=Q(name__istartswith=tois_folder_name[:6].lower())
            )
        )
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

    def test_get_folders(self):
        folders = list(FolderCollection(account=self.account, folders=[self.account.root]).get_folders())
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

        # Test that GetFolder can handle FolderId instances
        folders = list(
            FolderCollection(
                account=self.account,
                folders=[
                    DistinguishedFolderId(
                        id=Inbox.DISTINGUISHED_FOLDER_ID,
                        mailbox=Mailbox(email_address=self.account.primary_smtp_address),
                    )
                ],
            ).get_folders()
        )
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

    def test_get_folders_with_distinguished_id(self):
        # Test that we return an Inbox instance and not a generic Messages or Folder instance when we call GetFolder
        # with a DistinguishedFolderId instance with an ID of Inbox.DISTINGUISHED_FOLDER_ID.
        inbox_folder_id = DistinguishedFolderId(
            id=Inbox.DISTINGUISHED_FOLDER_ID,
            mailbox=Mailbox(email_address=self.account.primary_smtp_address),
        )
        inbox = list(
            GetFolder(account=self.account).call(
                folders=[inbox_folder_id],
                shape="IdOnly",
                additional_fields=[],
            )
        )[0]
        self.assertIsInstance(inbox, Inbox)

        # Test via SingleFolderQuerySet
        inbox = SingleFolderQuerySet(account=self.account, folder=inbox_folder_id).resolve()
        self.assertIsInstance(inbox, Inbox)

    def test_folder_grouping(self):
        # If you get errors here, you probably need to fill out [folder class].LOCALIZED_NAMES for your locale.
        for f in self.account.root.walk():
            with self.subTest(f=f):
                if f.is_distinguished:
                    self.assertIsNotNone(f.DISTINGUISHED_FOLDER_ID)
                else:
                    self.assertIsNone(f.DISTINGUISHED_FOLDER_ID)
            with self.subTest(f=f):
                if isinstance(
                    f,
                    (
                        Messages,
                        DeletedItems,
                        AllCategorizedItems,
                        AllContacts,
                        AllPersonMetadata,
                        MyContactsExtended,
                        Sharing,
                        Favorites,
                        FromFavoriteSenders,
                        RelevantContacts,
                        SyncIssues,
                        MyContacts,
                        UserCuratedContacts,
                    ),
                ):
                    self.assertEqual(f.folder_class, "IPF.Note")
                elif isinstance(f, ApplicationData):
                    self.assertEqual(f.folder_class, "IPM.ApplicationData")
                elif isinstance(f, CrawlerData):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.CrawlerData")
                elif isinstance(f, DlpPolicyEvaluation):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.DlpPolicyEvaluation")
                elif isinstance(f, FreeBusyCache):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.FreeBusyCache")
                elif isinstance(f, RecoveryPoints):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.RecoveryPoints")
                elif isinstance(f, SwssItems):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.SwssItems")
                elif isinstance(f, EventCheckPoints):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.EventCheckPoints")
                elif isinstance(f, PassThroughSearchResults):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.PassThroughSearchResults")
                elif isinstance(f, GraphAnalytics):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.GraphAnalytics")
                elif isinstance(f, Signal):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.Signal")
                elif isinstance(f, PdpProfileV2Secured):
                    self.assertEqual(f.folder_class, "IPF.StoreItem.PdpProfileSecured")
                elif isinstance(f, Companies):
                    self.assertEqual(f.folder_class, "IPF.Contact.Company")
                elif isinstance(f, OrganizationalContacts):
                    self.assertEqual(f.folder_class, "IPF.Contact.OrganizationalContacts")
                elif isinstance(f, PeopleCentricConversationBuddies):
                    self.assertEqual(f.folder_class, "IPF.Contact.PeopleCentricConversationBuddies")
                elif isinstance(f, GALContacts):
                    self.assertEqual(f.folder_class, "IPF.Contact.GalContacts")
                elif isinstance(f, RecipientCache):
                    self.assertEqual(f.folder_class, "IPF.Contact.RecipientCache")
                elif isinstance(f, IMContactList):
                    self.assertEqual(f.folder_class, "IPF.Contact.MOC.ImContactList")
                elif isinstance(f, QuickContacts):
                    self.assertEqual(f.folder_class, "IPF.Contact.MOC.QuickContacts")
                elif isinstance(f, (Contacts, ExternalContacts)):
                    self.assertEqual(f.folder_class, "IPF.Contact")
                elif isinstance(f, Birthdays):
                    self.assertEqual(f.folder_class, "IPF.Appointment.Birthday")
                elif isinstance(f, Calendar):
                    self.assertEqual(f.folder_class, "IPF.Appointment")
                elif isinstance(f, (Tasks, ToDoSearch, AllTodoTasks, FolderMemberships)):
                    self.assertEqual(f.folder_class, "IPF.Task")
                elif isinstance(f, Reminders):
                    self.assertEqual(f.folder_class, "Outlook.Reminder")
                elif isinstance(f, AllItems):
                    self.assertEqual(f.folder_class, "IPF")
                elif isinstance(f, ConversationSettings):
                    self.assertEqual(f.folder_class, "IPF.Configuration")
                elif isinstance(f, Files):
                    self.assertEqual(f.folder_class, "IPF.Files")
                elif isinstance(f, VoiceMail):
                    self.assertEqual(f.folder_class, "IPF.Note.Microsoft.Voicemail")
                elif isinstance(f, RSSFeeds):
                    self.assertEqual(f.folder_class, "IPF.Note.OutlookHomepage")
                elif isinstance(f, Friends):
                    self.assertEqual(f.folder_class, "IPF.Note")
                elif isinstance(f, Journal):
                    self.assertEqual(f.folder_class, "IPF.Journal")
                elif isinstance(f, Notes):
                    self.assertEqual(f.folder_class, "IPF.StickyNote")
                elif isinstance(f, DefaultFoldersChangeHistory):
                    self.assertEqual(f.folder_class, "IPM.DefaultFolderHistoryItem")
                elif isinstance(f, SkypeTeamsMessages):
                    self.assertEqual(f.folder_class, "IPF.SkypeTeams.Message")
                elif isinstance(f, SmsAndChatsSync):
                    self.assertEqual(f.folder_class, "IPF.SmsAndChatsSync")
                else:
                    self.assertIn(f.folder_class, (None, "IPF"), (f.name, f.__class__.__name__, f.folder_class))
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
            subject = f"Test Subject {i}"
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

    def test_case_sensitivity(self):
        # Test that the server does not case about folder name case
        upper_name = get_random_string(16).upper()
        lower_name = upper_name.lower()
        self.assertNotEqual(upper_name, lower_name)
        Folder(parent=self.account.inbox, name=upper_name).save()
        with self.assertRaises(ErrorFolderExists) as e:
            Folder(parent=self.account.inbox, name=lower_name).save()
        self.assertIn(f"Could not create folder '{lower_name}'", e.exception.args[0])

    def test_update(self):
        # Test that we can update folder attributes
        f = Folder(parent=self.account.inbox, name=get_random_string(16)).save()
        old_values = {}
        for field in f.FIELDS:
            if field.name in ("account", "id", "changekey", "folder_class", "parent_folder_id"):
                # These are needed for a successful refresh()
                continue
            if field.is_read_only:
                continue
            old_values[field.name] = getattr(f, field.name)
            new_val = self.random_val(field)
            setattr(f, field.name, new_val)
        f.save()
        f.refresh()
        for field_name, value in old_values.items():
            self.assertNotEqual(value, getattr(f, field_name))

    def test_refresh(self):
        # Test that we can refresh folders
        f = Folder(parent=self.account.inbox, name=get_random_string(16)).save()
        f.refresh()
        old_values = {}
        for field in f.FIELDS:
            old_values[field.name] = getattr(f, field.name)
            if field.name in ("account", "id", "changekey", "parent_folder_id"):
                # These are needed for a successful refresh()
                continue
            if field.is_read_only:
                continue
            setattr(f, field.name, self.random_val(field))
        f.refresh()
        for field in f.FIELDS:
            if field.name == "changekey":
                # folders may change while we're testing
                continue
            if field.is_read_only:
                # count values may change during the test
                continue
            self.assertEqual(getattr(f, field.name), old_values[field.name], (f, field.name))

        # Test refresh of root
        orig_name = self.account.root.name
        self.account.root.name = "xxx"
        self.account.root.refresh()
        self.assertEqual(self.account.root.name, orig_name)

        folder = Folder()
        with self.assertRaises(ValueError):
            folder.refresh()  # Must have root folder
        folder.root = self.account.root
        with self.assertRaises(ValueError):
            folder.refresh()  # Must have an id

    def test_parent(self):
        self.assertEqual(self.account.calendar.parent.name, self.account.root.tois.name)
        self.assertEqual(self.account.calendar.parent.parent.name, "root")
        # Setters
        parent = self.account.calendar.parent
        with self.assertRaises(TypeError) as e:
            self.account.calendar.parent = "XXX"
        self.assertEqual(
            e.exception.args[0], "'value' 'XXX' must be of type <class 'exchangelib.folders.base.BaseFolder'>"
        )
        self.account.calendar.parent = None
        self.account.calendar.parent = parent

        # Test self-referencing folder
        self.assertIsNone(Folder(id=self.account.inbox.id, parent=self.account.inbox).parent)

    def test_children(self):
        self.assertIn(self.account.root.tois.name, [c.name for c in self.account.root.children])

    def test_parts(self):
        self.assertEqual(
            [p.name for p in self.account.calendar.parts],
            ["root", self.account.root.tois.name, self.account.calendar.name],
        )

    def test_absolute(self):
        self.assertEqual(
            self.account.calendar.absolute, f"/root/{self.account.root.tois.name}/{self.account.calendar.name}"
        )

    def test_walk(self):
        self.assertGreaterEqual(len(list(self.account.root.walk())), 20)
        self.assertGreaterEqual(len(list(self.account.contacts.walk())), 2)

    def test_tree(self):
        self.assertTrue(self.account.root.tree().startswith("root"))

    def test_glob(self):
        self.assertGreaterEqual(len(list(self.account.root.glob("*"))), 5)
        self.assertEqual(len(list(self.account.contacts.glob("GAL*"))), 1)
        self.assertEqual(len(list(self.account.contacts.glob("gal*"))), 1)  # Test case-insensitivity
        self.assertGreaterEqual(len(list(self.account.contacts.glob("/"))), 5)
        self.assertGreaterEqual(len(list(self.account.contacts.glob("../*"))), 5)
        self.assertEqual(len(list(self.account.root.glob(f"**/{self.account.contacts.name}"))), 1)
        self.assertEqual(
            len(list(self.account.root.glob(f"{self.account.root.tois.name[:6]}*/{self.account.contacts.name}"))), 1
        )
        with self.assertRaises(ValueError) as e:
            list(self.account.root.glob("../*"))
        self.assertEqual(e.exception.args[0], "Already at top")

        # Test globbing with multiple levels of folders ('a/b/c')
        f1 = Folder(parent=self.account.inbox, name=get_random_string(16)).save()
        f2 = Folder(parent=f1, name=get_random_string(16)).save()
        f3 = Folder(parent=f2, name=get_random_string(16)).save()
        self.assertEqual(len(list(self.account.inbox.glob(f"{f1.name}/{f2.name}/{f3.name}"))), 1)

    def test_collection_filtering(self):
        self.assertGreaterEqual(self.account.root.tois.children.all().count(), 0)
        self.assertGreaterEqual(self.account.root.tois.walk().all().count(), 0)
        self.assertGreaterEqual(self.account.root.tois.glob("*").all().count(), 0)

    def test_empty_collections(self):
        self.assertEqual(self.account.trash.children.all().count(), 0)
        self.assertEqual(self.account.trash.walk().all().count(), 0)
        self.assertEqual(self.account.trash.glob("XXX").all().count(), 0)
        self.assertEqual(list(self.account.trash.glob("XXX").get_folders()), [])
        self.assertEqual(list(self.account.trash.glob("XXX").find_folders()), [])

    def test_div_navigation(self):
        self.assertEqual(
            (self.account.root / self.account.root.tois.name / self.account.calendar.name).id, self.account.calendar.id
        )
        self.assertEqual((self.account.root / self.account.root.tois.name / "..").id, self.account.root.id)
        self.assertEqual((self.account.root / ".").id, self.account.root.id)
        with self.assertRaises(ValueError) as e:
            _ = self.account.root / ".."
        self.assertEqual(e.exception.args[0], "Already at top")

        # Test invalid subfolder
        with self.assertRaises(ErrorFolderNotFound):
            _ = self.account.root / "XXX"

        # Test that we are case-insensitive
        self.assertNotEqual(self.account.root.tois.name, self.account.root.tois.name.upper())
        self.assertEqual((self.account.root / self.account.root.tois.name.upper()).id, self.account.root.tois.id)

    def test_double_div_navigation(self):
        self.account.root.clear_cache()  # Clear the cache

        # Test normal navigation
        self.assertEqual(
            (self.account.root // self.account.root.tois.name // self.account.calendar.name).id,
            self.account.calendar.id,
        )
        self.assertIsNone(self.account.root._subfolders)

        # Test parent ('..') syntax. Should not work
        with self.assertRaises(ValueError) as e:
            _ = self.account.root // self.account.root.tois.name // ".."
        self.assertEqual(e.exception.args[0], "Cannot get parent without a folder cache")
        self.assertIsNone(self.account.root._subfolders)

        # Test self ('.') syntax
        self.assertEqual((self.account.root // ".").id, self.account.root.id)

        # Test invalid subfolder
        with self.assertRaises(ErrorFolderNotFound):
            _ = self.account.root // "XXX"

        # Check that this didn't trigger caching
        self.assertIsNone(self.account.root._subfolders)

        # Test that we are case-insensitive
        self.assertNotEqual(self.account.root.tois.name, self.account.root.tois.name.upper())
        self.assertEqual((self.account.root // self.account.root.tois.name.upper()).id, self.account.root.tois.id)

    def test_extended_properties(self):
        # Test extended properties on folders and folder roots. This extended prop gets the size (in bytes) of a folder
        class FolderSize(ExtendedProperty):
            property_tag = 0x0E08
            property_type = "Long"

        try:
            Folder.register("size", FolderSize)
            self.account.inbox.refresh()
            self.assertGreater(self.account.inbox.size, 0)
        finally:
            Folder.deregister("size")

        try:
            RootOfHierarchy.register("size", FolderSize)
            self.account.root.refresh()
            self.assertGreater(self.account.root.size, 0)
        finally:
            RootOfHierarchy.deregister("size")

        # Register and deregister is only allowed on Folder and RootOfHierarchy classes
        with self.assertRaises(TypeError):
            self.account.calendar.register(FolderSize)
        with self.assertRaises(TypeError):
            self.account.calendar.deregister(FolderSize)
        with self.assertRaises(TypeError):
            self.account.root.register(FolderSize)
        with self.assertRaises(TypeError):
            self.account.root.deregister(FolderSize)

    def test_create_update_empty_delete(self):
        name = get_random_string(16)
        f = Messages(parent=self.account.inbox, name=name).save()
        with self.assertRaises(ErrorFolderExists):
            Messages(parent=self.account.inbox, name=name).save()
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
            f.save(update_fields=["folder_class"])

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

        item_id, changekey = f.id, f.changekey
        f.delete()
        with self.assertRaises(ValueError):
            # No longer has an ID
            f.refresh()

        with self.assertRaises(ErrorItemNotFound):
            f.id, f.changekey = item_id, changekey
            # Invalid ID
            f.save()

        with self.assertRaises(ErrorDeleteDistinguishedFolder):
            self.account.inbox.delete()

    def test_folder_type_guessing(self):
        old_locale = self.account.locale
        dk_locale = "da_DK"
        try:
            self.account.locale = dk_locale
            # Create a folder to contain the test
            f = Messages(parent=self.account.inbox, name=get_random_string(16)).save()
            # Create a subfolder with a misleading name
            misleading_name = Calendar.LOCALIZED_NAMES[dk_locale][0]
            Messages(parent=f, name=misleading_name).save()
            # Check that it's still detected as a Messages folder
            self.account.root.clear_cache()
            test_folder = f / misleading_name
            self.assertEqual(type(test_folder), Messages)
            self.assertEqual(test_folder.folder_class, Messages.CONTAINER_CLASS)
        finally:
            self.account.locale = old_locale

        # Also test folders that don't have a CONTAINER_CLASS
        f = self.account.root / "Common Views"
        self.assertIsInstance(f, CommonViews)

    def test_wipe_without_empty(self):
        name = get_random_string(16)
        f = Messages(parent=self.account.inbox, name=name).save()
        Messages(parent=f, name=get_random_string(16)).save()
        self.assertEqual(len(list(f.children)), 1)
        tmp = f.empty
        try:
            f.empty = Mock(side_effect=ErrorCannotEmptyFolder("XXX"))
            f.wipe()
        finally:
            f.empty = tmp

        self.assertEqual(len(list(f.children)), 0)

    def test_move(self):
        f1 = Folder(parent=self.account.inbox, name=get_random_string(16)).save()
        f2 = Folder(parent=self.account.inbox, name=get_random_string(16)).save()

        f1_id, f1_changekey, f1_parent = f1.id, f1.changekey, f1.parent
        with self.assertRaises(TypeError) as e:
            f1.move(to_folder="XXX")  # Must be folder instance
        self.assertEqual(
            e.exception.args[0],
            "'to_folder' 'XXX' must be of type (<class 'exchangelib.folders.base.BaseFolder'>, "
            "<class 'exchangelib.properties.FolderId'>)",
        )
        f1.move(f2)
        self.assertEqual(f1.id, f1_id)
        self.assertNotEqual(f1.changekey, f1_changekey)
        self.assertEqual(f1.parent, f2)
        self.assertNotEqual(f1.changekey, f1_parent)

        f1_id, f1_changekey, f1_parent = f1.id, f1.changekey, f1.parent
        f1.refresh()
        self.assertEqual(f1.id, f1_id)
        self.assertEqual(f1.parent, f2)
        self.assertNotEqual(f1.changekey, f1_parent)

        f1.delete()
        f2.delete()

    def test_generic_folder(self):
        f = Folder(parent=self.account.inbox, name=get_random_string(16))
        f.save()
        f.name = get_random_string(16)
        f.save()
        f.delete()

        self.assertEqual(Folder().has_distinguished_name, None)
        self.assertEqual(Inbox(name="XXX").has_distinguished_name, False)
        self.assertEqual(Inbox(name="Inbox").has_distinguished_name, True)
        self.assertEqual(Folder().is_deletable, True)
        self.assertEqual(Inbox().is_deletable, False)

    def test_non_deletable_folders(self):
        for f in self.account.root.walk():
            with self.subTest(item=f):
                if f.__class__ in NON_DELETABLE_FOLDERS + WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT + WELLKNOWN_FOLDERS_IN_ROOT:
                    self.assertEqual(f.is_deletable, False)
                    try:
                        f.delete()
                    except (ErrorDeleteDistinguishedFolder, ErrorCannotDeleteObject, ErrorItemNotFound):
                        pass
                else:
                    self.assertEqual(f.is_deletable, True)
                    # Don't attempt to delete. That could affect parallel tests

    def test_folder_collections(self):
        # Test that all custom folders are exposed in the top-level module
        top_level_classes = [
            cls
            for cls in vars(exchangelib.folders).values()
            if isclass(cls) and issubclass(cls, exchangelib.folders.BaseFolder)
        ]
        known_folder_classes = [
            cls
            for cls in vars(exchangelib.folders.known_folders).values()
            if isclass(cls) and issubclass(cls, exchangelib.folders.BaseFolder)
        ]
        for cls in known_folder_classes:
            with self.subTest(item=cls):
                self.assertIn(cls, top_level_classes)

        # Test that all custom folders are in one of the following folder collections
        all_cls = NON_DELETABLE_FOLDERS + WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT + WELLKNOWN_FOLDERS_IN_ROOT + MISC_FOLDERS
        for cls in top_level_classes:
            if not isclass(cls) or not issubclass(cls, BaseFolder):
                continue
            with self.subTest(item=cls):
                if cls in NON_DELETABLE_FOLDERS + [NonDeletableFolder]:
                    self.assertTrue(issubclass(cls, NonDeletableFolder))
                elif cls in WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT + WELLKNOWN_FOLDERS_IN_ROOT + [WellknownFolder, Messages]:
                    self.assertTrue(issubclass(cls, WellknownFolder))
                else:
                    self.assertFalse(issubclass(cls, WellknownFolder))
                    self.assertFalse(issubclass(cls, NonDeletableFolder))
            with self.subTest(item=cls):
                if cls in WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT + WELLKNOWN_FOLDERS_IN_ROOT:
                    self.assertIsNotNone(cls.DISTINGUISHED_FOLDER_ID)
                elif cls in (BaseFolder, Folder, WellknownFolder, RootOfHierarchy):
                    self.assertIsNone(cls.DISTINGUISHED_FOLDER_ID)
                elif issubclass(cls, RootOfHierarchy):
                    self.assertIsNotNone(cls.DISTINGUISHED_FOLDER_ID)
                else:
                    self.assertIsNone(cls.DISTINGUISHED_FOLDER_ID)
            with self.subTest(item=cls):
                if issubclass(cls, RootOfHierarchy) or cls in (
                    BaseFolder,
                    Folder,
                    WellknownFolder,
                    Messages,
                    NonDeletableFolder,
                ):
                    self.assertNotIn(cls, all_cls)
                else:
                    self.assertIn(cls, all_cls)

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
            self.assertSetEqual({f.name for f in folder_qs.all()}, {f.name for f in (f1, f2, f21, f22)})

            # Test only()
            self.assertSetEqual({f.name for f in folder_qs.only("name").all()}, {f.name for f in (f1, f2, f21, f22)})
            self.assertSetEqual({f.child_folder_count for f in folder_qs.only("name").all()}, {None})
            # Test depth()
            self.assertSetEqual({f.name for f in folder_qs.depth(SHALLOW).all()}, {f.name for f in (f1, f2)})

            # Test filter()
            self.assertSetEqual({f.name for f in folder_qs.filter(name=f1.name)}, {f.name for f in (f1,)})
            self.assertSetEqual(
                {f.name for f in folder_qs.filter(name__in=[f1.name, f2.name])}, {f.name for f in (f1, f2)}
            )

            # Test get()
            self.assertEqual(folder_qs.get(id=f2.id).name, f2.name)
            self.assertEqual(folder_qs.get(id=f2.id, changekey=f2.changekey).name, f2.name)
            self.assertEqual(folder_qs.get(name=f2.name).child_folder_count, 2)
            self.assertEqual(folder_qs.filter(name=f2.name).get().child_folder_count, 2)
            self.assertEqual(folder_qs.only("name").get(name=f2.name).name, f2.name)
            self.assertEqual(folder_qs.only("name").get(name=f2.name).child_folder_count, None)
            with self.assertRaises(DoesNotExist):
                folder_qs.get(name=get_random_string(16))
            with self.assertRaises(MultipleObjectsReturned):
                folder_qs.get()
        finally:
            f0.wipe()
            f0.delete()

    def test_folder_query_set_failures(self):
        with self.assertRaises(TypeError) as e:
            FolderQuerySet("XXX")
        self.assertEqual(
            e.exception.args[0],
            "'folder_collection' 'XXX' must be of type <class 'exchangelib.folders.collections.FolderCollection'>",
        )
        # Test FolderQuerySet._copy_cls()
        self.assertEqual(list(FolderQuerySet(FolderCollection(account=self.account, folders=[])).only("name")), [])
        fld_qs = SingleFolderQuerySet(account=self.account, folder=self.account.inbox)
        with self.assertRaises(InvalidField) as e:
            fld_qs.only("XXX")
        self.assertIn("Unknown field 'XXX' on folders", e.exception.args[0])
        with self.assertRaises(InvalidField) as e:
            list(fld_qs.filter(XXX="XXX"))
        self.assertIn("Unknown field path 'XXX' on folders", e.exception.args[0])
        # Test some exception paths
        with self.assertRaises(ErrorInvalidIdMalformed):
            SingleFolderQuerySet(account=self.account, folder=Folder(root=self.account.root, id="XXX")).get()

    def test_user_configuration(self):
        """Test that we can do CRUD operations on user configuration data."""
        # Create a test folder that we delete afterwards
        f = Messages(parent=self.account.inbox, name=get_random_string(16)).save()
        # The name must be fewer than 237 characters, can contain only the characters "A-Z", "a-z", "0-9", and ".",
        # and must not start with "IPM.Configuration"
        name = get_random_string(16, spaces=False, special=False)

        # Bad property
        with self.assertRaises(ValueError) as e:
            f.get_user_configuration(name=name, properties="XXX")
        self.assertEqual(
            e.exception.args[0],
            "'properties' 'XXX' must be one of ['All', 'BinaryData', 'Dictionary', 'Id', 'XmlData']",
        )

        # Should not exist yet
        with self.assertRaises(ErrorItemNotFound):
            f.get_user_configuration(name=name)

        # Create a config
        dictionary = {
            get_random_bool(): get_random_str_tuple(10, 2),
            get_random_int(): get_random_bool(),
            get_random_byte(): get_random_int(),
            get_random_bytes(16): get_random_byte(),
            get_random_string(8): get_random_bytes(16),
            get_random_datetime(tz=self.account.default_timezone): get_random_string(8),
            get_random_str_tuple(4, 4): get_random_datetime(tz=self.account.default_timezone),
        }
        xml_data = f"<foo>{get_random_string(16)}</foo>".encode("utf-8")
        binary_data = get_random_bytes(100)
        f.create_user_configuration(name=name, dictionary=dictionary, xml_data=xml_data, binary_data=binary_data)

        # Fetch and compare values
        config = f.get_user_configuration(name=name)
        self.assertEqual(config.dictionary, dictionary)
        self.assertEqual(config.xml_data, xml_data)
        self.assertEqual(config.binary_data, binary_data)

        # Cannot create one more with the same name
        with self.assertRaises(ErrorItemSave):
            f.create_user_configuration(name=name)

        # Does not exist on a different folder
        with self.assertRaises(ErrorItemNotFound):
            self.account.inbox.get_user_configuration(name=name)

        # Update the config
        f.update_user_configuration(
            name=name, dictionary={"bar": "foo", 456: "a", "b": True}, xml_data=b"<foo>baz</foo>", binary_data=b"YYY"
        )

        # Fetch again and compare values
        config = f.get_user_configuration(name=name)
        self.assertEqual(config.dictionary, {"bar": "foo", 456: "a", "b": True})
        self.assertEqual(config.xml_data, b"<foo>baz</foo>")
        self.assertEqual(config.binary_data, b"YYY")

        # Fetch again but only one property type
        config = f.get_user_configuration(name=name, properties="XmlData")
        self.assertEqual(config.dictionary, None)
        self.assertEqual(config.xml_data, b"<foo>baz</foo>")
        self.assertEqual(config.binary_data, None)

        # Delete the config
        f.delete_user_configuration(name=name)

        # We already deleted this config
        with self.assertRaises(ErrorItemNotFound):
            f.get_user_configuration(name=name)
        f.delete()

    def test_permissionset_effectiverights_parsing(self):
        # Test static XML since server may not have any permission sets or effective rights
        xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:GetFolderResponse xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                             xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
            <m:ResponseMessages>
                <m:GetFolderResponseMessage ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:Folders>
                        <t:CalendarFolder>
                            <t:FolderId Id="XXX" ChangeKey="YYY"/>
                            <t:ParentFolderId Id="ZZZ" ChangeKey="WWW"/>
                            <t:FolderClass>IPF.Appointment</t:FolderClass>
                            <t:DisplayName>My Calendar</t:DisplayName>
                            <t:TotalCount>1</t:TotalCount>
                            <t:ChildFolderCount>2</t:ChildFolderCount>
                            <t:EffectiveRights>
                                <t:CreateAssociated>true</t:CreateAssociated>
                                <t:CreateContents>true</t:CreateContents>
                                <t:CreateHierarchy>true</t:CreateHierarchy>
                                <t:Delete>true</t:Delete>
                                <t:Modify>true</t:Modify>
                                <t:Read>true</t:Read>
                                <t:ViewPrivateItems>false</t:ViewPrivateItems>
                            </t:EffectiveRights>
                            <t:PermissionSet>
                                <t:CalendarPermissions>
                                    <t:CalendarPermission>
                                        <t:UserId>
                                            <t:SID>SID1</t:SID>
                                            <t:PrimarySmtpAddress>user1@example.com</t:PrimarySmtpAddress>
                                            <t:DisplayName>User 1</t:DisplayName>
                                        </t:UserId>
                                        <t:CanCreateItems>false</t:CanCreateItems>
                                        <t:CanCreateSubFolders>false</t:CanCreateSubFolders>
                                        <t:IsFolderOwner>false</t:IsFolderOwner>
                                        <t:IsFolderVisible>true</t:IsFolderVisible>
                                        <t:IsFolderContact>false</t:IsFolderContact>
                                        <t:EditItems>None</t:EditItems>
                                        <t:DeleteItems>None</t:DeleteItems>
                                        <t:ReadItems>FullDetails</t:ReadItems>
                                        <t:CalendarPermissionLevel>Reviewer</t:CalendarPermissionLevel>
                                    </t:CalendarPermission>
                                    <t:CalendarPermission>
                                        <t:UserId>
                                            <t:SID>SID2</t:SID>
                                            <t:PrimarySmtpAddress>user2@example.com</t:PrimarySmtpAddress>
                                            <t:DisplayName>User 2</t:DisplayName>
                                        </t:UserId>
                                        <t:CanCreateItems>true</t:CanCreateItems>
                                        <t:CanCreateSubFolders>false</t:CanCreateSubFolders>
                                        <t:IsFolderOwner>false</t:IsFolderOwner>
                                        <t:IsFolderVisible>true</t:IsFolderVisible>
                                        <t:IsFolderContact>false</t:IsFolderContact>
                                        <t:EditItems>All</t:EditItems>
                                        <t:DeleteItems>All</t:DeleteItems>
                                        <t:ReadItems>FullDetails</t:ReadItems>
                                        <t:CalendarPermissionLevel>Editor</t:CalendarPermissionLevel>
                                    </t:CalendarPermission>
                                </t:CalendarPermissions>
                            </t:PermissionSet>
                        </t:CalendarFolder>
                    </m:Folders>
                </m:GetFolderResponseMessage>
            </m:ResponseMessages>
        </m:GetFolderResponse>
    </s:Body>
</s:Envelope>"""
        ws = GetFolder(account=self.account)
        ws.folders = [self.account.calendar]
        res = list(ws.parse(xml))
        self.assertEqual(len(res), 1)
        fld = res[0]
        self.assertEqual(
            fld.effective_rights,
            EffectiveRights(
                create_associated=True,
                create_contents=True,
                create_hierarchy=True,
                delete=True,
                modify=True,
                read=True,
                view_private_items=False,
            ),
        )
        self.assertEqual(
            fld.permission_set,
            PermissionSet(
                permissions=None,
                calendar_permissions=[
                    CalendarPermission(
                        can_create_items=False,
                        can_create_subfolders=False,
                        is_folder_owner=False,
                        is_folder_visible=True,
                        is_folder_contact=False,
                        edit_items="None",
                        delete_items="None",
                        read_items="FullDetails",
                        user_id=UserId(
                            sid="SID1",
                            primary_smtp_address="user1@example.com",
                            display_name="User 1",
                            distinguished_user=None,
                            external_user_identity=None,
                        ),
                        calendar_permission_level="Reviewer",
                    ),
                    CalendarPermission(
                        can_create_items=True,
                        can_create_subfolders=False,
                        is_folder_owner=False,
                        is_folder_visible=True,
                        is_folder_contact=False,
                        edit_items="All",
                        delete_items="All",
                        read_items="FullDetails",
                        user_id=UserId(
                            sid="SID2",
                            primary_smtp_address="user2@example.com",
                            display_name="User 2",
                            distinguished_user=None,
                            external_user_identity=None,
                        ),
                        calendar_permission_level="Editor",
                    ),
                ],
                unknown_entries=None,
            ),
        )

    def test_get_candidate(self):
        # _get_candidate is a private method, but it's really difficult to recreate a situation where it's used.
        f1 = Inbox(name="XXX")
        f2 = Inbox(name=Inbox.LOCALIZED_NAMES[self.account.locale][0])
        with self.assertRaises(ErrorFolderNotFound) as e:
            self.account.root._get_candidate(folder_cls=Inbox, folder_coll=[])
        self.assertEqual(
            e.exception.args[0], "No usable default <class 'exchangelib.folders.known_folders.Inbox'> folders"
        )
        self.assertEqual(self.account.root._get_candidate(folder_cls=Inbox, folder_coll=[f1]), f1)
        self.assertEqual(self.account.root._get_candidate(folder_cls=Inbox, folder_coll=[f2]), f2)
        with self.assertRaises(ValueError) as e:
            self.account.root._get_candidate(folder_cls=Inbox, folder_coll=[f1, f1])
        self.assertEqual(
            e.exception.args[0],
            "Multiple possible default <class 'exchangelib.folders.known_folders.Inbox'> folders: ['XXX', 'XXX']",
        )
