from ..items import ASSOCIATED as ASSOCIATED, CONTACT_ITEM_CLASSES as CONTACT_ITEM_CLASSES, CalendarItem as CalendarItem, ITEM_CLASSES as ITEM_CLASSES, MESSAGE_ITEM_CLASSES as MESSAGE_ITEM_CLASSES, TASK_ITEM_CLASSES as TASK_ITEM_CLASSES
from ..properties import EWSMeta as EWSMeta
from ..version import EXCHANGE_2010_SP1 as EXCHANGE_2010_SP1, EXCHANGE_2013 as EXCHANGE_2013, EXCHANGE_2013_SP1 as EXCHANGE_2013_SP1, EXCHANGE_O365 as EXCHANGE_O365
from .base import Folder as Folder
from .collections import FolderCollection as FolderCollection
from _typeshed import Incomplete

class Birthdays(Folder):
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class CrawlerData(Folder):
    CONTAINER_CLASS: str

class EventCheckPoints(Folder):
    CONTAINER_CLASS: str

class FreeBusyCache(Folder):
    CONTAINER_CLASS: str

class RecoveryPoints(Folder):
    CONTAINER_CLASS: str

class SkypeTeamsMessages(Folder):
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class SwssItems(Folder):
    CONTAINER_CLASS: str

class WellknownFolder(Folder, metaclass=EWSMeta):
    supported_item_models = ITEM_CLASSES

class AdminAuditLogs(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013
    get_folder_allowed: bool

class AllCategorizedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365

class AllContacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365

class AllItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365

class AllPersonMetadata(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365

class ArchiveDeletedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class ArchiveInbox(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013_SP1

class ArchiveMsgFolderRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class ArchiveRecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class ArchiveRecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class ArchiveRecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class ArchiveRecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class Calendar(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_item_models: Incomplete
    LOCALIZED_NAMES: Incomplete
    def view(self, *args, **kwargs): ...

class CompanyContacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365
    supported_item_models = CONTACT_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class Conflicts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013

class Contacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_item_models = CONTACT_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class ConversationHistory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013

class DeletedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_item_models = ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class Directory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013_SP1

class DlpPolicyEvaluation(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365

class Drafts(WellknownFolder):
    CONTAINER_CLASS: str
    DISTINGUISHED_FOLDER_ID: str
    supported_item_models = MESSAGE_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class Favorites(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_2013

class FolderMemberships(Folder):
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class FromFavoriteSenders(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365
    LOCALIZED_NAMES: Incomplete

class IMContactList(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_2013

class Inbox(WellknownFolder):
    CONTAINER_CLASS: str
    DISTINGUISHED_FOLDER_ID: str
    supported_item_models = MESSAGE_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class Inference(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class Journal(WellknownFolder):
    CONTAINER_CLASS: str
    DISTINGUISHED_FOLDER_ID: str

class JunkEmail(WellknownFolder):
    CONTAINER_CLASS: str
    DISTINGUISHED_FOLDER_ID: str
    supported_item_models = MESSAGE_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class LocalFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013

class Messages(WellknownFolder):
    CONTAINER_CLASS: str
    supported_item_models = MESSAGE_ITEM_CLASSES

class MsgFolderRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    LOCALIZED_NAMES: Incomplete

class MyContacts(WellknownFolder):
    CONTAINER_CLASS: str
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013

class Notes(WellknownFolder):
    CONTAINER_CLASS: str
    DISTINGUISHED_FOLDER_ID: str
    LOCALIZED_NAMES: Incomplete

class OneNotePagePreviews(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class Outbox(Messages):
    DISTINGUISHED_FOLDER_ID: str
    LOCALIZED_NAMES: Incomplete

class PeopleCentricConversationBuddies(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365
    LOCALIZED_NAMES: Incomplete

class PeopleConnect(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013

class QedcDefaultRetention(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class QedcLongRetention(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class QedcMediumRetention(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class QedcShortRetention(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class QuarantinedEmail(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class QuarantinedEmailDefaultCategory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class QuickContacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_2013

class RecipientCache(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_2013

class RelevantContacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365

class RecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class RecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class RecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class RecoverableItemsSubstrateHolds(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365
    LOCALIZED_NAMES: Incomplete

class RecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2010_SP1

class SearchFolders(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str

class SentItems(Messages):
    DISTINGUISHED_FOLDER_ID: str
    LOCALIZED_NAMES: Incomplete

class ServerFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013

class SharePointNotifications(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class ShortNotes(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class SyncIssues(WellknownFolder):
    CONTAINER_CLASS: str
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_2013

class Tasks(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_item_models = TASK_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class TemporarySaves(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    supported_from = EXCHANGE_O365

class ToDoSearch(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_2013
    LOCALIZED_NAMES: Incomplete

class UserCuratedContacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    supported_from = EXCHANGE_O365

class VoiceMail(WellknownFolder):
    DISTINGUISHED_FOLDER_ID: str
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class NonDeletableFolder(Folder):
    @property
    def is_deletable(self): ...

class AllTodoTasks(NonDeletableFolder):
    CONTAINER_CLASS: str
    supported_item_models = TASK_ITEM_CLASSES

class ApplicationData(NonDeletableFolder):
    CONTAINER_CLASS: str

class Audits(NonDeletableFolder):
    get_folder_allowed: bool

class CalendarLogging(NonDeletableFolder):
    LOCALIZED_NAMES: Incomplete

class CalendarSearchCache(NonDeletableFolder):
    CONTAINER_CLASS: str

class CommonViews(NonDeletableFolder):
    DEFAULT_ITEM_TRAVERSAL_DEPTH = ASSOCIATED
    LOCALIZED_NAMES: Incomplete

class ConversationSettings(NonDeletableFolder):
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class DefaultFoldersChangeHistory(NonDeletableFolder):
    CONTAINER_CLASS: str

class DeferredAction(NonDeletableFolder):
    LOCALIZED_NAMES: Incomplete

class ExchangeSyncData(NonDeletableFolder): ...

class ExternalContacts(NonDeletableFolder):
    CONTAINER_CLASS: str
    supported_item_models = CONTACT_ITEM_CLASSES

class Files(NonDeletableFolder):
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class FreebusyData(NonDeletableFolder):
    LOCALIZED_NAMES: Incomplete

class Friends(NonDeletableFolder):
    CONTAINER_CLASS: str
    supported_item_models = CONTACT_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class GALContacts(NonDeletableFolder):
    CONTAINER_CLASS: str
    supported_item_models = CONTACT_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class GraphAnalytics(NonDeletableFolder):
    CONTAINER_CLASS: str

class Location(NonDeletableFolder): ...
class MailboxAssociations(NonDeletableFolder): ...

class MyContactsExtended(NonDeletableFolder):
    CONTAINER_CLASS: str
    supported_item_models = CONTACT_ITEM_CLASSES

class OrganizationalContacts(NonDeletableFolder):
    CONTAINER_CLASS: str
    supported_item_models = CONTACT_ITEM_CLASSES
    LOCALIZED_NAMES: Incomplete

class ParkedMessages(NonDeletableFolder):
    CONTAINER_CLASS: Incomplete

class PassThroughSearchResults(NonDeletableFolder):
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class PersonMetadata(NonDeletableFolder):
    CONTAINER_CLASS: str

class PdpProfileV2Secured(NonDeletableFolder):
    CONTAINER_CLASS: str

class Reminders(NonDeletableFolder):
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class RSSFeeds(NonDeletableFolder):
    CONTAINER_CLASS: str
    LOCALIZED_NAMES: Incomplete

class Schedule(NonDeletableFolder): ...

class ShadowItems(NonDeletableFolder):
    CONTAINER_CLASS: str

class Sharing(NonDeletableFolder):
    CONTAINER_CLASS: str

class Shortcuts(NonDeletableFolder): ...

class Signal(NonDeletableFolder):
    CONTAINER_CLASS: str

class SmsAndChatsSync(NonDeletableFolder):
    CONTAINER_CLASS: str

class SpoolerQueue(NonDeletableFolder):
    LOCALIZED_NAMES: Incomplete

class System(NonDeletableFolder):
    get_folder_allowed: bool

class System1(NonDeletableFolder):
    get_folder_allowed: bool

class Views(NonDeletableFolder): ...

class WorkingSet(NonDeletableFolder):
    LOCALIZED_NAMES: Incomplete

NON_DELETABLE_FOLDERS: Incomplete
WELLKNOWN_FOLDERS_IN_ROOT: Incomplete
WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT: Incomplete
MISC_FOLDERS: Incomplete
