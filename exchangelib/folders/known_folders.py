# coding=utf-8
from ..items import CalendarItem, Contact, Message, Task, DistributionList, MeetingRequest, MeetingResponse, \
    MeetingCancellation, CreateChange, UpdateChange, DeleteChange, ReadFlagChange, ITEM_CLASSES, ALL_ITEM_CLASSES
from ..version import EXCHANGE_2010_SP1, EXCHANGE_2013, EXCHANGE_2013_SP1
from .base import Folder
from .collections import FolderCollection


class Calendar(Folder):
    """
    An interface for the Exchange calendar
    """
    DISTINGUISHED_FOLDER_ID = 'calendar'
    CONTAINER_CLASS = 'IPF.Appointment'
    supported_item_models = (CalendarItem,)

    LOCALIZED_NAMES = {
        'da_DK': (u'Kalender',),
        'de_DE': (u'Kalender',),
        'en_US': (u'Calendar',),
        'es_ES': (u'Calendario',),
        'fr_CA': (u'Calendrier',),
        'nl_NL': (u'Agenda',),
        'ru_RU': (u'Календарь',),
        'sv_SE': (u'Kalender',),
        'zh_CN': (u'日历',),
    }

    def view(self, *args, **kwargs):
        return FolderCollection(account=self.root.account, folders=[self]).view(*args, **kwargs)


class DeletedItems(Folder):
    DISTINGUISHED_FOLDER_ID = 'deleteditems'
    CONTAINER_CLASS = 'IPF.Note'
    supported_item_models = ITEM_CLASSES

    LOCALIZED_NAMES = {
        'da_DK': (u'Slettet post',),
        'de_DE': (u'Gelöschte Elemente',),
        'en_US': (u'Deleted Items',),
        'es_ES': (u'Elementos eliminados',),
        'fr_CA': (u'Éléments supprimés',),
        'nl_NL': (u'Verwijderde items',),
        'ru_RU': (u'Удаленные',),
        'sv_SE': (u'Borttaget',),
        'zh_CN': (u'已删除邮件',),
    }


class Messages(Folder):
    CONTAINER_CLASS = 'IPF.Note'
    supported_item_models = (Message, MeetingRequest, MeetingResponse, MeetingCancellation, CreateChange,
                             UpdateChange, DeleteChange, ReadFlagChange)


class Drafts(Messages):
    DISTINGUISHED_FOLDER_ID = 'drafts'

    LOCALIZED_NAMES = {
        'da_DK': (u'Kladder',),
        'de_DE': (u'Entwürfe',),
        'en_US': (u'Drafts',),
        'es_ES': (u'Borradores',),
        'fr_CA': (u'Brouillons',),
        'nl_NL': (u'Concepten',),
        'ru_RU': (u'Черновики',),
        'sv_SE': (u'Utkast',),
        'zh_CN': (u'草稿',),
    }


class Inbox(Messages):
    DISTINGUISHED_FOLDER_ID = 'inbox'

    LOCALIZED_NAMES = {
        'da_DK': (u'Indbakke',),
        'de_DE': (u'Posteingang',),
        'en_US': (u'Inbox',),
        'es_ES': (u'Bandeja de entrada',),
        'fr_CA': (u'Boîte de réception',),
        'nl_NL': (u'Postvak IN',),
        'ru_RU': (u'Входящие',),
        'sv_SE': (u'Inkorgen',),
        'zh_CN': (u'收件箱',),
    }


class Outbox(Messages):
    DISTINGUISHED_FOLDER_ID = 'outbox'

    LOCALIZED_NAMES = {
        'da_DK': (u'Udbakke',),
        'de_DE': (u'Postausgang',),
        'en_US': (u'Outbox',),
        'es_ES': (u'Bandeja de salida',),
        'fr_CA': (u"Boîte d'envoi",),
        'nl_NL': (u'Postvak UIT',),
        'ru_RU': (u'Исходящие',),
        'sv_SE': (u'Utkorgen',),
        'zh_CN': (u'发件箱',),
    }


class SentItems(Messages):
    DISTINGUISHED_FOLDER_ID = 'sentitems'

    LOCALIZED_NAMES = {
        'da_DK': (u'Sendt post',),
        'de_DE': (u'Gesendete Elemente',),
        'en_US': (u'Sent Items',),
        'es_ES': (u'Elementos enviados',),
        'fr_CA': (u'Éléments envoyés',),
        'nl_NL': (u'Verzonden items',),
        'ru_RU': (u'Отправленные',),
        'sv_SE': (u'Skickat',),
        'zh_CN': (u'已发送邮件',),
    }


class JunkEmail(Messages):
    DISTINGUISHED_FOLDER_ID = 'junkemail'

    LOCALIZED_NAMES = {
        'da_DK': (u'Uønsket e-mail',),
        'de_DE': (u'Junk-E-Mail',),
        'en_US': (u'Junk E-mail',),
        'es_ES': (u'Correo no deseado',),
        'fr_CA': (u'Courrier indésirables',),
        'nl_NL': (u'Ongewenste e-mail',),
        'ru_RU': (u'Нежелательная почта',),
        'sv_SE': (u'Skräppost',),
        'zh_CN': (u'垃圾邮件',),
    }


class Tasks(Folder):
    DISTINGUISHED_FOLDER_ID = 'tasks'
    CONTAINER_CLASS = 'IPF.Task'
    supported_item_models = (Task,)

    LOCALIZED_NAMES = {
        'da_DK': (u'Opgaver',),
        'de_DE': (u'Aufgaben',),
        'en_US': (u'Tasks',),
        'es_ES': (u'Tareas',),
        'fr_CA': (u'Tâches',),
        'nl_NL': (u'Taken',),
        'ru_RU': (u'Задачи',),
        'sv_SE': (u'Uppgifter',),
        'zh_CN': (u'任务',),
    }


class Contacts(Folder):
    DISTINGUISHED_FOLDER_ID = 'contacts'
    CONTAINER_CLASS = 'IPF.Contact'
    supported_item_models = (Contact, DistributionList)

    LOCALIZED_NAMES = {
        'da_DK': (u'Kontaktpersoner',),
        'de_DE': (u'Kontakte',),
        'en_US': (u'Contacts',),
        'es_ES': (u'Contactos',),
        'fr_CA': (u'Contacts',),
        'nl_NL': (u'Contactpersonen',),
        'ru_RU': (u'Контакты',),
        'sv_SE': (u'Kontakter',),
        'zh_CN': (u'联系人',),
    }


class WellknownFolder(Folder):
    # Use this class until we have specific folder implementations
    supported_item_models = ITEM_CLASSES


class AdminAuditLogs(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'adminauditlogs'
    supported_from = EXCHANGE_2013
    get_folder_allowed = False


class ArchiveDeletedItems(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archivedeleteditems'
    supported_from = EXCHANGE_2010_SP1


class ArchiveInbox(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiveinbox'
    supported_from = EXCHANGE_2013_SP1


class ArchiveMsgFolderRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archivemsgfolderroot'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsdeletions'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemspurges'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsroot'
    supported_from = EXCHANGE_2010_SP1


class ArchiveRecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'archiverecoverableitemsversions'
    supported_from = EXCHANGE_2010_SP1


class Conflicts(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'conflicts'
    supported_from = EXCHANGE_2013


class ConversationHistory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'conversationhistory'
    supported_from = EXCHANGE_2013


class Directory(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'directory'
    supported_from = EXCHANGE_2013_SP1


class Favorites(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'favorites'
    supported_from = EXCHANGE_2013


class IMContactList(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Contact.MOC.ImContactList'
    DISTINGUISHED_FOLDER_ID = 'imcontactlist'
    supported_from = EXCHANGE_2013


class Journal(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Journal'
    DISTINGUISHED_FOLDER_ID = 'journal'


class LocalFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'localfailures'
    supported_from = EXCHANGE_2013


class MsgFolderRoot(WellknownFolder):
    # Also known as the 'Top of Information Store' folder
    DISTINGUISHED_FOLDER_ID = 'msgfolderroot'
    LOCALIZED_NAMES = {
        'zh_CN': (u'信息存储顶部',),
    }


class MyContacts(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'mycontacts'
    supported_from = EXCHANGE_2013


class Notes(WellknownFolder):
    CONTAINER_CLASS = 'IPF.StickyNote'
    DISTINGUISHED_FOLDER_ID = 'notes'
    LOCALIZED_NAMES = {
        'da_DK': (u'Noter',),
    }


class PeopleConnect(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'peopleconnect'
    supported_from = EXCHANGE_2013


class QuickContacts(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Contact.MOC.QuickContacts'
    DISTINGUISHED_FOLDER_ID = 'quickcontacts'
    supported_from = EXCHANGE_2013


class RecipientCache(Contacts):
    DISTINGUISHED_FOLDER_ID = 'recipientcache'
    CONTAINER_CLASS = 'IPF.Contact.RecipientCache'
    supported_from = EXCHANGE_2013

    LOCALIZED_NAMES = {}


class RecoverableItemsDeletions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsdeletions'
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsPurges(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemspurges'
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsRoot(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsroot'
    supported_from = EXCHANGE_2010_SP1


class RecoverableItemsVersions(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsversions'
    supported_from = EXCHANGE_2010_SP1


class SearchFolders(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'searchfolders'


class ServerFailures(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'serverfailures'
    supported_from = EXCHANGE_2013


class SyncIssues(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Note'
    DISTINGUISHED_FOLDER_ID = 'syncissues'
    supported_from = EXCHANGE_2013


class ToDoSearch(WellknownFolder):
    CONTAINER_CLASS = 'IPF.Task'
    DISTINGUISHED_FOLDER_ID = 'todosearch'
    supported_from = EXCHANGE_2013

    LOCALIZED_NAMES = {
        None: (u'To-Do Search',),
    }


class VoiceMail(WellknownFolder):
    DISTINGUISHED_FOLDER_ID = 'voicemail'
    CONTAINER_CLASS = 'IPF.Note.Microsoft.Voicemail'
    LOCALIZED_NAMES = {
        None: (u'Voice Mail',),
    }


class NonDeleteableFolderMixin(object):
    @property
    def is_deleteable(self):
        return False


class AllContacts(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'

    LOCALIZED_NAMES = {
        None: (u'AllContacts',),
    }


class AllItems(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF'

    LOCALIZED_NAMES = {
        None: (u'AllItems',),
    }


class Audits(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Audits',),
    }
    get_folder_allowed = False


class CalendarLogging(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Calendar Logging',),
    }


class CommonViews(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Common Views',),
    }


class ConversationSettings(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Configuration'
    LOCALIZED_NAMES = {
        'da_DK': (u'Indstillinger for samtalehandlinger',),
    }


class DefaultFoldersChangeHistory(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPM.DefaultFolderHistoryItem'
    LOCALIZED_NAMES = {
        None: (u'DefaultFoldersChangeHistory',),
    }


class DeferredAction(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Deferred Action',),
    }


class ExchangeSyncData(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'ExchangeSyncData',),
    }


class Files(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Files'

    LOCALIZED_NAMES = {
        'da_DK': (u'Filer',),
    }


class FreebusyData(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Freebusy Data',),
    }


class Friends(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'

    LOCALIZED_NAMES = {
        'de_DE': (u'Bekannte',),
    }


class GALContacts(NonDeleteableFolderMixin, Contacts):
    DISTINGUISHED_FOLDER_ID = None
    CONTAINER_CLASS = 'IPF.Contact.GalContacts'

    LOCALIZED_NAMES = {
        None: ('GAL Contacts',),
    }


class GraphAnalytics(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.StoreItem.GraphAnalytics'
    LOCALIZED_NAMES = {
        None: (u'GraphAnalytics',),
    }


class Location(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Location',),
    }


class MailboxAssociations(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'MailboxAssociations',),
    }


class MyContactsExtended(NonDeleteableFolderMixin, Contacts):
    CONTAINER_CLASS = 'IPF.Note'
    LOCALIZED_NAMES = {
        None: (u'MyContactsExtended',),
    }


class ParkedMessages(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = None
    LOCALIZED_NAMES = {
        None: (u'ParkedMessages',),
    }


class PassThroughSearchResults(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.StoreItem.PassThroughSearchResults'
    LOCALIZED_NAMES = {
        None: (u'Pass-Through Search Results',),
    }


class PdpProfileV2Secured(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.StoreItem.PdpProfileSecured'
    LOCALIZED_NAMES = {
        None: (u'PdpProfileV2Secured',),
    }


class Reminders(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'Outlook.Reminder'
    LOCALIZED_NAMES = {
        'da_DK': (u'Påmindelser',),
    }


class RSSFeeds(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Note.OutlookHomepage'
    LOCALIZED_NAMES = {
        None: (u'RSS Feeds',),
    }


class Schedule(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Schedule',),
    }


class Sharing(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.Note'
    LOCALIZED_NAMES = {
        None: (u'Sharing',),
    }


class Shortcuts(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Shortcuts',),
    }


class Signal(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.StoreItem.Signal'
    LOCALIZED_NAMES = {
        None: (u'Signal',),
    }


class SmsAndChatsSync(NonDeleteableFolderMixin, Folder):
    CONTAINER_CLASS = 'IPF.SmsAndChatsSync'
    LOCALIZED_NAMES = {
        None: (u'SmsAndChatsSync',),
    }


class SpoolerQueue(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Spooler Queue',),
    }


class System(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'System',),
    }
    get_folder_allowed = False


class TemporarySaves(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'TemporarySaves',),
    }


class Views(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Views',),
    }


class WorkingSet(NonDeleteableFolderMixin, Folder):
    LOCALIZED_NAMES = {
        None: (u'Working Set',),
    }


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
