from ..items import CalendarItem, Contact, Message, Task, DistributionList, MeetingRequest, MeetingResponse, \
    MeetingCancellation, ITEM_CLASSES, ASSOCIATED
from ..version import EXCHANGE_2010_SP1, EXCHANGE_2013, EXCHANGE_2013_SP1
from .base import Folder
from .collections import FolderCollection


class Calendar(Folder):
    """An interface for the Exchange calendar"""
    DISTINGUISHED_FOLDER_ID = 'calendar'
    CONTAINER_CLASS = 'IPF.Appointment'
    supported_item_models = (CalendarItem,)

    LOCALIZED_NAMES = {
        'da_DK': ('Kalender',),
        'de_DE': ('Kalender',),
        'en_US': ('Calendar',),
        'es_ES': ('Calendario',),
        'fr_CA': ('Calendrier',),
        'nl_NL': ('Agenda',),
        'ru_RU': ('Календарь',),
        'sv_SE': ('Kalender',),
        'zh_CN': ('日历',),
    }
    __slots__ = tuple()

    def view(self, *args, **kwargs):
        return FolderCollection(account=self.account, folders=[self]).view(*args, **kwargs)


class DeletedItems(Folder):
    DISTINGUISHED_FOLDER_ID = 'deleteditems'
    CONTAINER_CLASS = 'IPF.Note'
    supported_item_models = ITEM_CLASSES

    LOCALIZED_NAMES = {
        'da_DK': ('Slettet post',),
        'de_DE': ('Gelöschte Elemente',),
        'en_US': ('Deleted Items',),
        'es_ES': ('Elementos eliminados',),
        'fr_CA': ('Éléments supprimés',),
        'nl_NL': ('Verwijderde items',),
        'ru_RU': ('Удаленные',),
        'sv_SE': ('Borttaget',),
        'zh_CN': ('已删除邮件',),
    }
    __slots__ = tuple()


class Messages(Folder):
    CONTAINER_CLASS = 'IPF.Note'
    supported_item_models = (Message, MeetingRequest, MeetingResponse, MeetingCancellation)
    __slots__ = tuple()


class Drafts(Messages):
    DISTINGUISHED_FOLDER_ID = 'drafts'

    LOCALIZED_NAMES = {
        'da_DK': ('Kladder',),
        'de_DE': ('Entwürfe',),
        'en_US': ('Drafts',),
        'es_ES': ('Borradores',),
        'fr_CA': ('Brouillons',),
        'nl_NL': ('Concepten',),
        'ru_RU': ('Черновики',),
        'sv_SE': ('Utkast',),
        'zh_CN': ('草稿',),
    }
    __slots__ = tuple()


class Inbox(Messages):
    DISTINGUISHED_FOLDER_ID = 'inbox'

    LOCALIZED_NAMES = {
        'da_DK': ('Indbakke',),
        'de_DE': ('Posteingang',),
        'en_US': ('Inbox',),
        'es_ES': ('Bandeja de entrada',),
        'fr_CA': ('Boîte de réception',),
        'nl_NL': ('Postvak IN',),
        'ru_RU': ('Входящие',),
        'sv_SE': ('Inkorgen',),
        'zh_CN': ('收件箱',),
    }
    __slots__ = tuple()


class Outbox(Messages):
    DISTINGUISHED_FOLDER_ID = 'outbox'

    LOCALIZED_NAMES = {
        'da_DK': ('Udbakke',),
        'de_DE': ('Postausgang',),
        'en_US': ('Outbox',),
        'es_ES': ('Bandeja de salida',),
        'fr_CA': (u"Boîte d'envoi",),
        'nl_NL': ('Postvak UIT',),
        'ru_RU': ('Исходящие',),
        'sv_SE': ('Utkorgen',),
        'zh_CN': ('发件箱',),
    }
    __slots__ = tuple()


class SentItems(Messages):
    DISTINGUISHED_FOLDER_ID = 'sentitems'

    LOCALIZED_NAMES = {
        'da_DK': ('Sendt post',),
        'de_DE': ('Gesendete Elemente',),
        'en_US': ('Sent Items',),
        'es_ES': ('Elementos enviados',),
        'fr_CA': ('Éléments envoyés',),
        'nl_NL': ('Verzonden items',),
        'ru_RU': ('Отправленные',),
        'sv_SE': ('Skickat',),
        'zh_CN': ('已发送邮件',),
    }
    __slots__ = tuple()


class JunkEmail(Messages):
    DISTINGUISHED_FOLDER_ID = 'junkemail'

    LOCALIZED_NAMES = {
        'da_DK': ('Uønsket e-mail',),
        'de_DE': ('Junk-E-Mail',),
        'en_US': ('Junk E-mail',),
        'es_ES': ('Correo no deseado',),
        'fr_CA': ('Courrier indésirables',),
        'nl_NL': ('Ongewenste e-mail',),
        'ru_RU': ('Нежелательная почта',),
        'sv_SE': ('Skräppost',),
        'zh_CN': ('垃圾邮件',),
    }
    __slots__ = tuple()


class Tasks(Folder):
    DISTINGUISHED_FOLDER_ID = 'tasks'
    CONTAINER_CLASS = 'IPF.Task'
    supported_item_models = (Task,)

    LOCALIZED_NAMES = {
        'da_DK': ('Opgaver',),
        'de_DE': ('Aufgaben',),
        'en_US': ('Tasks',),
        'es_ES': ('Tareas',),
        'fr_CA': ('Tâches',),
        'nl_NL': ('Taken',),
        'ru_RU': ('Задачи',),
        'sv_SE': ('Uppgifter',),
        'zh_CN': ('任务',),
    }
    __slots__ = tuple()


class Contacts(Folder):
    DISTINGUISHED_FOLDER_ID = 'contacts'
    CONTAINER_CLASS = 'IPF.Contact'
    supported_item_models = (Contact, DistributionList)

    LOCALIZED_NAMES = {
        'da_DK': ('Kontaktpersoner',),
        'de_DE': ('Kontakte',),
        'en_US': ('Contacts',),
        'es_ES': ('Contactos',),
        'fr_CA': ('Contacts',),
        'nl_NL': ('Contactpersonen',),
        'ru_RU': ('Контакты',),
        'sv_SE': ('Kontakter',),
        'zh_CN': ('联系人',),
    }
    __slots__ = tuple()


class WellknownFolder(Folder):
    """A base class to use until we have a more specific folder implementation for this folder"""
    supported_item_models = ITEM_CLASSES
    __slots__ = tuple()


class AdminAuditLogs(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'adminauditlogs'
    supported_from = EXCHANGE_2013
    get_folder_allowed = False
    __slots__ = tuple()


class ArchiveDeletedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archivedeleteditems'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class ArchiveInbox(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiveinbox'
    supported_from = EXCHANGE_2013_SP1
    __slots__ = tuple()


class ArchiveMsgFolderRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archivemsgfolderroot'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsdeletions'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class ArchiveRecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemspurges'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class ArchiveRecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsroot'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class ArchiveRecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsversions'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class Conflicts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'conflicts'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class ConversationHistory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'conversationhistory'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class Directory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'directory'
    supported_from = EXCHANGE_2013_SP1
    __slots__ = tuple()


class Favorites(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'favorites'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class IMContactList(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Contact.MOC.ImContactList'
    DISTINGUISHED_FOLDER_ID = 'imcontactlist'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class Journal(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Journal'
    DISTINGUISHED_FOLDER_ID = 'journal'
    __slots__ = tuple()


class LocalFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'localfailures'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class MsgFolderRoot(WellknownFolder):
    """Also known as the 'Top of Information Store' folder"""
    DISTINGUISHED_FOLDER_ID = 'msgfolderroot'
    LOCALIZED_NAMES = {
        'zh_CN': ('信息存储顶部',),
    }
    __slots__ = tuple()


class MyContacts(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'mycontacts'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class Notes(WellknownFolder):
    CONTAINER_CLASS = 'IPF.StickyNote'
    DISTINGUISHED_FOLDER_ID = 'notes'
    LOCALIZED_NAMES = {
        'da_DK': ('Noter',),
    }
    __slots__ = tuple()


class PeopleConnect(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'peopleconnect'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class QuickContacts(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Contact.MOC.QuickContacts'
    DISTINGUISHED_FOLDER_ID = 'quickcontacts'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class RecipientCache(Contacts):
    DISTINGUISHED_FOLDER_ID = 'recipientcache'
    CONTAINER_CLASS = 'IPF.Contact.RecipientCache'
    supported_from = EXCHANGE_2013

    LOCALIZED_NAMES = {}
    __slots__ = tuple()


class RecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsdeletions'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class RecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemspurges'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class RecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsroot'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class RecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsversions'
    supported_from = EXCHANGE_2010_SP1
    __slots__ = tuple()


class SearchFolders(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'searchfolders'
    __slots__ = tuple()


class ServerFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'serverfailures'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class SyncIssues(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'syncissues'
    supported_from = EXCHANGE_2013
    __slots__ = tuple()


class ToDoSearch(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Task'
    DISTINGUISHED_FOLDER_ID = 'todosearch'
    supported_from = EXCHANGE_2013

    LOCALIZED_NAMES = {
        None: ('To-Do Search',),
    }
    __slots__ = tuple()


class VoiceMail(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'voicemail'
    CONTAINER_CLASS = 'IPF.Note.Microsoft.Voicemail'
    LOCALIZED_NAMES = {
        None: ('Voice Mail',),
    }
    __slots__ = tuple()


class NonDeleteableFolderMixin:
    @property
    def is_deleteable(self):
        return False


class AllContacts(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'

    LOCALIZED_NAMES = {
        None: ('AllContacts',),
    }
    __slots__ = tuple()


class AllItems(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF'

    LOCALIZED_NAMES = {
        None: ('AllItems',),
    }
    __slots__ = tuple()


class Audits(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Audits',),
    }
    get_folder_allowed = False
    __slots__ = tuple()


class CalendarLogging(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Calendar Logging',),
    }
    __slots__ = tuple()


class CommonViews(NonDeleteableFolderMixin, Folder):
    DEFAULT_ITEM_TRAVERSAL_DEPTH = ASSOCIATED
    LOCALIZED_NAMES = {
        None: ('Common Views',),
    }
    __slots__ = tuple()


class ConversationSettings(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Configuration'
    LOCALIZED_NAMES = {
        'da_DK': ('Indstillinger for samtalehandlinger',),
    }
    __slots__ = tuple()


class DefaultFoldersChangeHistory(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPM.DefaultFolderHistoryItem'
    LOCALIZED_NAMES = {
        None: ('DefaultFoldersChangeHistory',),
    }
    __slots__ = tuple()


class DeferredAction(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Deferred Action',),
    }
    __slots__ = tuple()


class ExchangeSyncData(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('ExchangeSyncData',),
    }
    __slots__ = tuple()


class Files(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Files'

    LOCALIZED_NAMES = {
        'da_DK': ('Filer',),
    }
    __slots__ = tuple()


class FreebusyData(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Freebusy Data',),
    }
    __slots__ = tuple()


class Friends(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'

    LOCALIZED_NAMES = {
        'de_DE': ('Bekannte',),
    }
    __slots__ = tuple()


class GALContacts(NonDeleteableFolderMixin, Contacts):
    DISTINGUISHED_FOLDER_ID = None
    CONTAINER_CLASS = 'IPF.Contact.GalContacts'

    LOCALIZED_NAMES = {
        None: ('GAL Contacts',),
    }
    __slots__ = tuple()


class GraphAnalytics(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.StoreItem.GraphAnalytics'
    LOCALIZED_NAMES = {
        None: ('GraphAnalytics',),
    }
    __slots__ = tuple()


class Location(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Location',),
    }
    __slots__ = tuple()


class MailboxAssociations(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('MailboxAssociations',),
    }
    __slots__ = tuple()


class MyContactsExtended(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'
    LOCALIZED_NAMES = {
        None: ('MyContactsExtended',),
    }
    __slots__ = tuple()


class ParkedMessages(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = None
    LOCALIZED_NAMES = {
        None: ('ParkedMessages',),
    }
    __slots__ = tuple()


class PassThroughSearchResults(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.StoreItem.PassThroughSearchResults'
    LOCALIZED_NAMES = {
        None: ('Pass-Through Search Results',),
    }
    __slots__ = tuple()


class PdpProfileV2Secured(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.StoreItem.PdpProfileSecured'
    LOCALIZED_NAMES = {
        None: ('PdpProfileV2Secured',),
    }
    __slots__ = tuple()


class Reminders(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'Outlook.Reminder'
    LOCALIZED_NAMES = {
        'da_DK': ('Påmindelser',),
    }
    __slots__ = tuple()


class RSSFeeds(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Note.OutlookHomepage'
    LOCALIZED_NAMES = {
        None: ('RSS Feeds',),
    }
    __slots__ = tuple()


class Schedule(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Schedule',),
    }
    __slots__ = tuple()


class Sharing(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Note'
    LOCALIZED_NAMES = {
        None: ('Sharing',),
    }
    __slots__ = tuple()


class Shortcuts(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Shortcuts',),
    }
    __slots__ = tuple()


class Signal(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.StoreItem.Signal'
    LOCALIZED_NAMES = {
        None: ('Signal',),
    }
    __slots__ = tuple()


class SmsAndChatsSync(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.SmsAndChatsSync'
    LOCALIZED_NAMES = {
        None: ('SmsAndChatsSync',),
    }
    __slots__ = tuple()


class SpoolerQueue(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Spooler Queue',),
    }
    __slots__ = tuple()


class System(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('System',),
    }
    get_folder_allowed = False
    __slots__ = tuple()


class TemporarySaves(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('TemporarySaves',),
    }
    __slots__ = tuple()


class Views(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Views',),
    }
    __slots__ = tuple()


class WorkingSet(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: ('Working Set',),
    }
    __slots__ = tuple()


# Folders that return 'ErrorDeleteDistinguishedFolder' when we try to delete them. I can't find any official docs
# listing these folders.
NON_DELETEABLE_FOLDERS = [
    AllContacts,
    AllItems,
    Audits,
    CalendarLogging,
    CommonViews,
    ConversationSettings,
    DefaultFoldersChangeHistory,
    DeferredAction,
    ExchangeSyncData,
    FreebusyData,
    Files,
    Friends,
    GALContacts,
    GraphAnalytics,
    Location,
    MailboxAssociations,
    MyContactsExtended,
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
    TemporarySaves,
    Views,
    WorkingSet,
]

WELLKNOWN_FOLDERS_IN_ROOT = [
    AdminAuditLogs,
    Calendar,
    Conflicts,
    Contacts,
    ConversationHistory,
    DeletedItems,
    Directory,
    Drafts,
    Favorites,
    IMContactList,
    Inbox,
    Journal,
    JunkEmail,
    LocalFailures,
    MsgFolderRoot,
    MyContacts,
    Notes,
    Outbox,
    PeopleConnect,
    QuickContacts,
    RecipientCache,
    RecoverableItemsDeletions,
    RecoverableItemsPurges,
    RecoverableItemsRoot,
    RecoverableItemsVersions,
    SearchFolders,
    SentItems,
    ServerFailures,
    SyncIssues,
    Tasks,
    ToDoSearch,
    VoiceMail,
]

WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT = [
    ArchiveDeletedItems,
    ArchiveInbox,
    ArchiveMsgFolderRoot,
    ArchiveRecoverableItemsDeletions,
    ArchiveRecoverableItemsPurges,
    ArchiveRecoverableItemsRoot,
    ArchiveRecoverableItemsVersions,
]
