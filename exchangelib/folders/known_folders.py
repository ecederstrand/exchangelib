from ..items import (
    ASSOCIATED,
    ITEM_CLASSES,
    CalendarItem,
    Contact,
    DistributionList,
    MeetingCancellation,
    MeetingRequest,
    MeetingResponse,
    Message,
    Task,
)
from ..properties import EWSMeta
from ..version import EXCHANGE_2010_SP1, EXCHANGE_2013, EXCHANGE_2013_SP1
from .base import Folder
from .collections import FolderCollection


class Birthdays(Folder):
    CONTAINER_CLASS = "IPF.Appointment.Birthday"
    LOCALIZED_NAMES = {
        "da_DK": ("Fødselsdage",),
    }


class CrawlerData(Folder):
    CONTAINER_CLASS = "IPF.StoreItem.CrawlerData"


class EventCheckPoints(Folder):
    CONTAINER_CLASS = "IPF.StoreItem.EventCheckPoints"


class FreeBusyCache(Folder):
    CONTAINER_CLASS = "IPF.StoreItem.FreeBusyCache"


class RecoveryPoints(Folder):
    CONTAINER_CLASS = "IPF.StoreItem.RecoveryPoints"


class SkypeTeamsMessages(Folder):
    CONTAINER_CLASS = "IPF.SkypeTeams.Message"
    LOCALIZED_NAMES = {
        None: ("Team-chat",),
    }


class SwssItems(Folder):
    CONTAINER_CLASS = "IPF.StoreItem.SwssItems"


class WellknownFolder(Folder, metaclass=EWSMeta):
    """Base class to use until we have a more specific folder implementation for this folder."""

    supported_item_models = ITEM_CLASSES


class Messages(WellknownFolder):
    CONTAINER_CLASS = "IPF.Note"
    supported_item_models = (Message, MeetingRequest, MeetingResponse, MeetingCancellation)


class Calendar(WellknownFolder):
    """An interface for the Exchange calendar."""

    DISTINGUISHED_FOLDER_ID = "calendar"
    CONTAINER_CLASS = "IPF.Appointment"
    supported_item_models = (CalendarItem,)
    LOCALIZED_NAMES = {
        "da_DK": ("Kalender",),
        "de_DE": ("Kalender",),
        "en_US": ("Calendar",),
        "es_ES": ("Calendario",),
        "fr_CA": ("Calendrier",),
        "nl_NL": ("Agenda",),
        "ru_RU": ("Календарь",),
        "sv_SE": ("Kalender",),
        "zh_CN": ("日历",),
    }

    def view(self, *args, **kwargs):
        return FolderCollection(account=self.account, folders=[self]).view(*args, **kwargs)


class Contacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "contacts"
    CONTAINER_CLASS = "IPF.Contact"
    supported_item_models = (Contact, DistributionList)
    LOCALIZED_NAMES = {
        "da_DK": ("Kontaktpersoner",),
        "de_DE": ("Kontakte",),
        "en_US": ("Contacts",),
        "es_ES": ("Contactos",),
        "fr_CA": ("Contacts",),
        "nl_NL": ("Contactpersonen",),
        "ru_RU": ("Контакты",),
        "sv_SE": ("Kontakter",),
        "zh_CN": ("联系人",),
    }


class DeletedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "deleteditems"
    CONTAINER_CLASS = "IPF.Note"
    supported_item_models = ITEM_CLASSES
    LOCALIZED_NAMES = {
        "da_DK": ("Slettet post",),
        "de_DE": ("Gelöschte Elemente",),
        "en_US": ("Deleted Items",),
        "es_ES": ("Elementos eliminados",),
        "fr_CA": ("Éléments supprimés",),
        "nl_NL": ("Verwijderde items",),
        "ru_RU": ("Удаленные",),
        "sv_SE": ("Borttaget",),
        "zh_CN": ("已删除邮件",),
    }


class Drafts(Messages):
    DISTINGUISHED_FOLDER_ID = "drafts"
    LOCALIZED_NAMES = {
        "da_DK": ("Kladder",),
        "de_DE": ("Entwürfe",),
        "en_US": ("Drafts",),
        "es_ES": ("Borradores",),
        "fr_CA": ("Brouillons",),
        "nl_NL": ("Concepten",),
        "ru_RU": ("Черновики",),
        "sv_SE": ("Utkast",),
        "zh_CN": ("草稿",),
    }


class Inbox(Messages):
    DISTINGUISHED_FOLDER_ID = "inbox"
    LOCALIZED_NAMES = {
        "da_DK": ("Indbakke",),
        "de_DE": ("Posteingang",),
        "en_US": ("Inbox",),
        "es_ES": ("Bandeja de entrada",),
        "fr_CA": ("Boîte de réception",),
        "nl_NL": ("Postvak IN",),
        "ru_RU": ("Входящие",),
        "sv_SE": ("Inkorgen",),
        "zh_CN": ("收件箱",),
    }


class JunkEmail(Messages):
    DISTINGUISHED_FOLDER_ID = "junkemail"
    LOCALIZED_NAMES = {
        "da_DK": ("Uønsket e-mail",),
        "de_DE": ("Junk-E-Mail",),
        "en_US": ("Junk E-mail",),
        "es_ES": ("Correo no deseado",),
        "fr_CA": ("Courrier indésirables",),
        "nl_NL": ("Ongewenste e-mail",),
        "ru_RU": ("Нежелательная почта",),
        "sv_SE": ("Skräppost",),
        "zh_CN": ("垃圾邮件",),
    }


class Outbox(Messages):
    DISTINGUISHED_FOLDER_ID = "outbox"
    LOCALIZED_NAMES = {
        "da_DK": ("Udbakke",),
        "de_DE": ("Postausgang",),
        "en_US": ("Outbox",),
        "es_ES": ("Bandeja de salida",),
        "fr_CA": ("Boîte d'envoi",),
        "nl_NL": ("Postvak UIT",),
        "ru_RU": ("Исходящие",),
        "sv_SE": ("Utkorgen",),
        "zh_CN": ("发件箱",),
    }


class SentItems(Messages):
    DISTINGUISHED_FOLDER_ID = "sentitems"
    LOCALIZED_NAMES = {
        "da_DK": ("Sendt post",),
        "de_DE": ("Gesendete Elemente",),
        "en_US": ("Sent Items",),
        "es_ES": ("Elementos enviados",),
        "fr_CA": ("Éléments envoyés",),
        "nl_NL": ("Verzonden items",),
        "ru_RU": ("Отправленные",),
        "sv_SE": ("Skickat",),
        "zh_CN": ("已发送邮件",),
    }


class Tasks(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "tasks"
    CONTAINER_CLASS = "IPF.Task"
    supported_item_models = (Task,)
    LOCALIZED_NAMES = {
        "da_DK": ("Opgaver",),
        "de_DE": ("Aufgaben",),
        "en_US": ("Tasks",),
        "es_ES": ("Tareas",),
        "fr_CA": ("Tâches",),
        "nl_NL": ("Taken",),
        "ru_RU": ("Задачи",),
        "sv_SE": ("Uppgifter",),
        "zh_CN": ("任务",),
    }


class AdminAuditLogs(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "adminauditlogs"
    supported_from = EXCHANGE_2013
    get_folder_allowed = False


class AllContacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "allcontacts"
    CONTAINER_CLASS = "IPF.Note"


class AllItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "allitems"
    CONTAINER_CLASS = "IPF"


class AllCategorizedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "allcategorizeditems"
    CONTAINER_CLASS = "IPF.Note"


class AllPersonMetadata(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "allpersonmetadata"
    CONTAINER_CLASS = "IPF.Note"


class ArchiveDeletedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "archivedeleteditems"
    supported_from = EXCHANGE_2010_SP1


class ArchiveInbox(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "archiveinbox"
    supported_from = EXCHANGE_2013_SP1


class ArchiveMsgFolderRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "archivemsgfolderroot"
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "archiverecoverableitemsdeletions"
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "archiverecoverableitemspurges"
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "archiverecoverableitemsroot"
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "archiverecoverableitemsversions"
    supported_from = EXCHANGE_2010_SP1


class Companies(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "companycontacts"
    CONTAINER_CLASS = "IPF.Contact.Company"
    supported_item_models = (Contact, DistributionList)
    LOCALIZED_NAMES = {
        "da_DK": ("Firmaer",),
    }


class Conflicts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "conflicts"
    supported_from = EXCHANGE_2013


class ConversationHistory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "conversationhistory"
    supported_from = EXCHANGE_2013


class Directory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "directory"
    supported_from = EXCHANGE_2013_SP1


class DlpPolicyEvaluation(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "dlppolicyevaluation"
    CONTAINER_CLASS = "IPF.StoreItem.DlpPolicyEvaluation"


class Favorites(WellknownFolder):
    CONTAINER_CLASS = "IPF.Note"
    DISTINGUISHED_FOLDER_ID = "favorites"
    supported_from = EXCHANGE_2013


class FolderMemberships(Folder):
    CONTAINER_CLASS = "IPF.Task"
    LOCALIZED_NAMES = {
        None: ("Folder Memberships",),
    }


class FromFavoriteSenders(WellknownFolder):
    CONTAINER_CLASS = "IPF.Note"
    DISTINGUISHED_FOLDER_ID = "fromfavoritesenders"
    LOCALIZED_NAMES = {
        "da_DK": ("Personer jeg kender",),
    }


class IMContactList(WellknownFolder):
    CONTAINER_CLASS = "IPF.Contact.MOC.ImContactList"
    DISTINGUISHED_FOLDER_ID = "imcontactlist"
    supported_from = EXCHANGE_2013


class Inference(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "inference"


class Journal(WellknownFolder):
    CONTAINER_CLASS = "IPF.Journal"
    DISTINGUISHED_FOLDER_ID = "journal"


class LocalFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "localfailures"
    supported_from = EXCHANGE_2013


class MsgFolderRoot(WellknownFolder):
    """Also known as the 'Top of Information Store' folder."""

    DISTINGUISHED_FOLDER_ID = "msgfolderroot"
    LOCALIZED_NAMES = {
        None: ("Top of Information Store",),
        "da_DK": ("Informationslagerets øverste niveau",),
        "zh_CN": ("信息存储顶部",),
    }


class MyContacts(WellknownFolder):
    CONTAINER_CLASS = "IPF.Note"
    DISTINGUISHED_FOLDER_ID = "mycontacts"
    supported_from = EXCHANGE_2013


class Notes(WellknownFolder):
    CONTAINER_CLASS = "IPF.StickyNote"
    DISTINGUISHED_FOLDER_ID = "notes"
    LOCALIZED_NAMES = {
        "da_DK": ("Noter",),
    }


class OneNotePagePreviews(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "onenotepagepreviews"


class PeopleCentricConversationBuddies(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "peoplecentricconversationbuddies"
    CONTAINER_CLASS = "IPF.Contact.PeopleCentricConversationBuddies"
    LOCALIZED_NAMES = {
        None: ("PeopleCentricConversation Buddies",),
    }


class PeopleConnect(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "peopleconnect"
    supported_from = EXCHANGE_2013


class QedcDefaultRetention(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "qedcdefaultretention"


class QedcLongRetention(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "qedclongretention"


class QedcMediumRetention(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "qedcmediumretention"


class QedcShortRetention(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "qedcshortretention"


class QuarantinedEmail(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "quarantinedemail"


class QuarantinedEmailDefaultCategory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "quarantinedemaildefaultcategory"


class QuickContacts(WellknownFolder):
    CONTAINER_CLASS = "IPF.Contact.MOC.QuickContacts"
    DISTINGUISHED_FOLDER_ID = "quickcontacts"
    supported_from = EXCHANGE_2013


class RecipientCache(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "recipientcache"
    CONTAINER_CLASS = "IPF.Contact.RecipientCache"
    supported_from = EXCHANGE_2013
    LOCALIZED_NAMES = {
        None: ("RecipientCache",),
    }


class RelevantContacts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "relevantcontacts"
    CONTAINER_CLASS = "IPF.Note"
    LOCALIZED_NAMES = {
        None: ("RelevantContacts",),
    }


class RecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "recoverableitemsdeletions"
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "recoverableitemspurges"
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "recoverableitemsroot"
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsSubstrateHolds(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "recoverableitemssubstrateholds"
    supported_from = EXCHANGE_2010_SP1
    LOCALIZED_NAMES = {
        None: ("SubstrateHolds",),
    }


class RecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "recoverableitemsversions"
    supported_from = EXCHANGE_2010_SP1


class SearchFolders(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "searchfolders"


class ServerFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "serverfailures"
    supported_from = EXCHANGE_2013


class SharePointNotifications(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "sharepointnotifications"


class ShortNotes(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "shortnotes"


class SyncIssues(WellknownFolder):
    CONTAINER_CLASS = "IPF.Note"
    DISTINGUISHED_FOLDER_ID = "syncissues"
    supported_from = EXCHANGE_2013


class TemporarySaves(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "temporarysaves"


class ToDoSearch(WellknownFolder):
    CONTAINER_CLASS = "IPF.Task"
    DISTINGUISHED_FOLDER_ID = "todosearch"
    supported_from = EXCHANGE_2013
    LOCALIZED_NAMES = {
        None: ("To-Do Search",),
    }


class UserCuratedContacts(WellknownFolder):
    CONTAINER_CLASS = "IPF.Note"
    DISTINGUISHED_FOLDER_ID = "usercuratedcontacts"


class VoiceMail(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = "voicemail"
    CONTAINER_CLASS = "IPF.Note.Microsoft.Voicemail"
    LOCALIZED_NAMES = {
        None: ("Voice Mail",),
    }


class NonDeletableFolder(Folder):
    """A mixin for non-wellknown folders than that are not deletable."""

    @property
    def is_deletable(self):
        return False


class ExternalContacts(NonDeletableFolder):
    DISTINGUISHED_FOLDER_ID = None
    CONTAINER_CLASS = "IPF.Contact"
    supported_item_models = (Contact, DistributionList)
    LOCALIZED_NAMES = {
        None: ("ExternalContacts",),
    }


class AllTodoTasks(NonDeletableFolder):
    DISTINGUISHED_FOLDER_ID = None
    CONTAINER_CLASS = "IPF.Task"
    supported_item_models = (Task,)
    LOCALIZED_NAMES = {
        None: ("AllTodoTasks",),
    }


class ApplicationData(NonDeletableFolder):
    CONTAINER_CLASS = "IPM.ApplicationData"


class Audits(NonDeletableFolder):
    get_folder_allowed = False


class CalendarLogging(NonDeletableFolder):
    LOCALIZED_NAMES = {
        None: ("Calendar Logging",),
    }


class CommonViews(NonDeletableFolder):
    DEFAULT_ITEM_TRAVERSAL_DEPTH = ASSOCIATED
    LOCALIZED_NAMES = {
        None: ("Common Views",),
    }


class ConversationSettings(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.Configuration"
    LOCALIZED_NAMES = {
        "da_DK": ("Indstillinger for samtalehandlinger",),
    }


class DefaultFoldersChangeHistory(NonDeletableFolder):
    CONTAINER_CLASS = "IPM.DefaultFolderHistoryItem"


class DeferredAction(NonDeletableFolder):
    LOCALIZED_NAMES = {
        None: ("Deferred Action",),
    }


class ExchangeSyncData(NonDeletableFolder):
    pass


class Files(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.Files"
    LOCALIZED_NAMES = {
        "da_DK": ("Filer",),
    }


class FreebusyData(NonDeletableFolder):
    LOCALIZED_NAMES = {
        None: ("Freebusy Data",),
    }


class Friends(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.Note"
    supported_item_models = (Contact, DistributionList)
    LOCALIZED_NAMES = {
        "de_DE": ("Bekannte",),
    }


class GALContacts(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.Contact.GalContacts"
    supported_item_models = (Contact, DistributionList)
    LOCALIZED_NAMES = {
        None: ("GAL Contacts",),
    }


class GraphAnalytics(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.StoreItem.GraphAnalytics"


class Location(NonDeletableFolder):
    pass


class MailboxAssociations(NonDeletableFolder):
    pass


class MyContactsExtended(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.Note"
    supported_item_models = (Contact, DistributionList)


class OrganizationalContacts(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.Contact.OrganizationalContacts"
    supported_item_models = (Contact, DistributionList)
    LOCALIZED_NAMES = {
        None: ("Organizational Contacts",),
    }


class ParkedMessages(NonDeletableFolder):
    CONTAINER_CLASS = None


class PassThroughSearchResults(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.StoreItem.PassThroughSearchResults"
    LOCALIZED_NAMES = {
        None: ("Pass-Through Search Results",),
    }


class PdpProfileV2Secured(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.StoreItem.PdpProfileSecured"


class Reminders(NonDeletableFolder):
    CONTAINER_CLASS = "Outlook.Reminder"
    LOCALIZED_NAMES = {
        "da_DK": ("Påmindelser",),
    }


class RSSFeeds(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.Note.OutlookHomepage"
    LOCALIZED_NAMES = {
        None: ("RSS Feeds",),
    }


class Schedule(NonDeletableFolder):
    pass


class Sharing(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.Note"


class Shortcuts(NonDeletableFolder):
    pass


class Signal(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.StoreItem.Signal"


class SmsAndChatsSync(NonDeletableFolder):
    CONTAINER_CLASS = "IPF.SmsAndChatsSync"


class SpoolerQueue(NonDeletableFolder):
    LOCALIZED_NAMES = {
        None: ("Spooler Queue",),
    }


class System(NonDeletableFolder):
    get_folder_allowed = False


class System1(NonDeletableFolder):
    get_folder_allowed = False


class Views(NonDeletableFolder):
    pass


class WorkingSet(NonDeletableFolder):
    LOCALIZED_NAMES = {
        None: ("Working Set",),
    }


# Folders that do not have a distinguished folder ID but return 'ErrorDeleteDistinguishedFolder' or
# 'ErrorCannotDeleteObject' when we try to delete them. I can't find any official docs listing these folders.
NON_DELETABLE_FOLDERS = [
    ApplicationData,
    AllTodoTasks,
    Audits,
    CalendarLogging,
    CommonViews,
    ConversationSettings,
    DefaultFoldersChangeHistory,
    DeferredAction,
    ExchangeSyncData,
    ExternalContacts,
    FreebusyData,
    Files,
    Friends,
    GALContacts,
    GraphAnalytics,
    Location,
    MailboxAssociations,
    MyContactsExtended,
    OrganizationalContacts,
    ParkedMessages,
    PassThroughSearchResults,
    PdpProfileV2Secured,
    Reminders,
    RSSFeeds,
    Schedule,
    Sharing,
    Shortcuts,
    Signal,
    SmsAndChatsSync,
    SpoolerQueue,
    System,
    System1,
    Views,
    WorkingSet,
]

# Folders that have a distinguished ID and are located in the root folder hierarchy
WELLKNOWN_FOLDERS_IN_ROOT = [
    AdminAuditLogs,
    AllCategorizedItems,
    AllContacts,
    AllItems,
    AllPersonMetadata,
    Calendar,
    Companies,
    Conflicts,
    Contacts,
    ConversationHistory,
    DeletedItems,
    Directory,
    DlpPolicyEvaluation,
    Drafts,
    Favorites,
    FromFavoriteSenders,
    IMContactList,
    Inference,
    Inbox,
    Journal,
    JunkEmail,
    LocalFailures,
    MsgFolderRoot,
    MyContacts,
    Notes,
    OneNotePagePreviews,
    Outbox,
    PeopleCentricConversationBuddies,
    PeopleConnect,
    QedcDefaultRetention,
    QedcLongRetention,
    QedcMediumRetention,
    QedcShortRetention,
    QuarantinedEmail,
    QuarantinedEmailDefaultCategory,
    QuickContacts,
    RecipientCache,
    RelevantContacts,
    RecoverableItemsDeletions,
    RecoverableItemsPurges,
    RecoverableItemsRoot,
    RecoverableItemsSubstrateHolds,
    RecoverableItemsVersions,
    SearchFolders,
    SentItems,
    ServerFailures,
    SharePointNotifications,
    ShortNotes,
    SyncIssues,
    Tasks,
    TemporarySaves,
    ToDoSearch,
    UserCuratedContacts,
    VoiceMail,
]

# Folders that have a distinguished ID and are located in the archive root folder hierarchy
WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT = [
    ArchiveDeletedItems,
    ArchiveInbox,
    ArchiveMsgFolderRoot,
    ArchiveRecoverableItemsDeletions,
    ArchiveRecoverableItemsPurges,
    ArchiveRecoverableItemsRoot,
    ArchiveRecoverableItemsVersions,
]

# Folders that do not have a distinguished ID but have their own container class
MISC_FOLDERS = [
    CrawlerData,
    EventCheckPoints,
    FolderMemberships,
    FreeBusyCache,
    RecoveryPoints,
    SwssItems,
    SkypeTeamsMessages,
    Birthdays,
]
