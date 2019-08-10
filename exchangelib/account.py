# coding=utf-8
from __future__ import unicode_literals

from locale import getlocale
from logging import getLogger

from cached_property import threaded_cached_property
from future.utils import python_2_unicode_compatible
from six import string_types

from .autodiscover import discover
from .configuration import Configuration
from .credentials import DELEGATE, IMPERSONATION, ACCESS_TYPES
from .errors import UnknownTimeZone
from .ewsdatetime import EWSTimeZone, UTC
from .fields import FieldPath
from .folders import Folder, AdminAuditLogs, ArchiveDeletedItems, ArchiveInbox, ArchiveMsgFolderRoot, \
    ArchiveRecoverableItemsDeletions, ArchiveRecoverableItemsPurges, ArchiveRecoverableItemsRoot, \
    ArchiveRecoverableItemsVersions, ArchiveRoot, Calendar, Conflicts, Contacts, ConversationHistory, DeletedItems, \
    Directory, Drafts, Favorites, IMContactList, Inbox, Journal, JunkEmail, LocalFailures, MsgFolderRoot, MyContacts, \
    Notes, Outbox, PeopleConnect, PublicFoldersRoot, QuickContacts, RecipientCache, RecoverableItemsDeletions, \
    RecoverableItemsPurges, RecoverableItemsRoot, RecoverableItemsVersions, Root, SearchFolders, SentItems, \
    ServerFailures, SyncIssues, Tasks, ToDoSearch, VoiceMail
from .items import Item, BulkCreateResult, HARD_DELETE, \
    AUTO_RESOLVE, SEND_TO_NONE, SAVE_ONLY, SEND_AND_SAVE_COPY, SEND_ONLY, ALL_OCCURRENCIES, \
    DELETE_TYPE_CHOICES, MESSAGE_DISPOSITION_CHOICES, CONFLICT_RESOLUTION_CHOICES, AFFECTED_TASK_OCCURRENCES_CHOICES, \
    SEND_MEETING_INVITATIONS_CHOICES, SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES, \
    SEND_MEETING_CANCELLATIONS_CHOICES, ID_ONLY
from .properties import Mailbox, SendingAs
from .queryset import QuerySet
from .services import ExportItems, UploadItems, GetItem, CreateItem, UpdateItem, DeleteItem, MoveItem, SendItem, \
    CopyItem, GetUserOofSettings, SetUserOofSettings, GetMailTips, SyncFolderItems, SubscribePushFolder, SubscribeStreamingFolder, \
    UnsubscribeStreamingFolder, GetStreamingEvents, EVENT_TYPES
from .settings import OofSettings
from .util import get_domain, peek

log = getLogger(__name__)


@python_2_unicode_compatible
class Account(object):
    """Models an Exchange server user account. The primary key for an account is its PrimarySMTPAddress
    """
    def __init__(self, primary_smtp_address, fullname=None, access_type=None, autodiscover=False, credentials=None,
                 config=None, locale=None, default_timezone=None):
        """
        :param primary_smtp_address: The primary email address associated with the account on the Exchange server
        :param fullname: The full name of the account. Optional.
        :param access_type: The access type granted to 'credentials' for this account. Valid options are 'delegate'
        (default) and 'impersonation'.
        :param autodiscover: Whether to look up the EWS endpoint automatically using the autodiscover protocol.
        :param credentials: A Credentials object containing valid credentials for this account.
        :param config: A Configuration object containing EWS endpoint information. Required if autodiscover is disabled
        :param locale: The locale of the user, e.g. 'en_US'. Defaults to the locale of the host, if available.
        :param default_timezone: EWS may return some datetime values without timezone information. In this case, we will
        assume values to be in the provided timezone. Defaults to the timezone of the host.
        """
        if '@' not in primary_smtp_address:
            raise ValueError("primary_smtp_address %r is not an email address" % primary_smtp_address)
        self.primary_smtp_address = primary_smtp_address
        self.fullname = fullname
        # Assume delegate access if individual credentials are provided. Else, assume service user with impersonation
        self.access_type = access_type or (DELEGATE if credentials else IMPERSONATION)
        if self.access_type not in ACCESS_TYPES:
            raise ValueError("'access_type' %r must be one of %s" % (self.access_type, ACCESS_TYPES))
        try:
            self.locale = locale or getlocale()[0] or None  # get_locale() might not be able to determine the locale
        except ValueError as e:
            # getlocale() may throw ValueError if it fails to parse the system locale
            log.warning('Failed to get locale (%s)' % e)
            self.locale = None
        if self.locale is not None:
            if not isinstance(self.locale, string_types):
                raise ValueError("Expected 'locale' to be a string, got %r" % self.locale)
        try:
            self.default_timezone = default_timezone or EWSTimeZone.localzone()
        except (ValueError, UnknownTimeZone) as e:
            # There is no translation from local timezone name to Windows timezone name, or e failed to find the
            # local timezone.
            log.warning('%s. Fallback to UTC', e.args[0])
            self.default_timezone = UTC
        if not isinstance(self.default_timezone, EWSTimeZone):
            raise ValueError("Expected 'default_timezone' to be an EWSTimeZone, got %r" % self.default_timezone)
        if autodiscover:
            if not credentials:
                raise AttributeError('autodiscover requires credentials')
            if config:
                raise AttributeError('config is ignored when autodiscover is active')
            self.primary_smtp_address, self.protocol = discover(email=self.primary_smtp_address,
                                                                credentials=credentials)
        else:
            if not config:
                raise AttributeError('non-autodiscover requires a config')
            if not isinstance(config, Configuration):
                raise ValueError("Expected 'config' to be a Configuration, got %r" % config)
            self.protocol = config.protocol
        # We may need to override the default server version on a per-account basis because Microsoft may report one
        # server version up-front but delegate account requests to an older backend server.
        self.version = self.protocol.version
        log.debug('Added account: %s', self)

    @threaded_cached_property
    def admin_audit_logs(self):
        return self.root.get_default_folder(AdminAuditLogs)

    @threaded_cached_property
    def archive_deleted_items(self):
        return self.archive_root.get_default_folder(ArchiveDeletedItems)

    @threaded_cached_property
    def archive_inbox(self):
        return self.archive_root.get_default_folder(ArchiveInbox)

    @threaded_cached_property
    def archive_msg_folder_root(self):
        return self.archive_root.get_default_folder(ArchiveMsgFolderRoot)

    @threaded_cached_property
    def archive_recoverable_items_deletions(self):
        return self.archive_root.get_default_folder(ArchiveRecoverableItemsDeletions)

    @threaded_cached_property
    def archive_recoverable_items_purges(self):
        return self.archive_root.get_default_folder(ArchiveRecoverableItemsPurges)

    @threaded_cached_property
    def archive_recoverable_items_root(self):
        return self.archive_root.get_default_folder(ArchiveRecoverableItemsRoot)

    @threaded_cached_property
    def archive_recoverable_items_versions(self):
        return self.archive_root.get_default_folder(ArchiveRecoverableItemsVersions)

    @threaded_cached_property
    def archive_root(self):
        return ArchiveRoot.get_distinguished_root(account=self)

    @threaded_cached_property
    def calendar(self):
        # If the account contains a shared calendar from a different user, that calendar will be in the folder list.
        # Attempt not to return one of those. An account may not always have a calendar called "Calendar", but a
        # Calendar folder with a localized name instead. Return that, if it's available, but always prefer any
        # distinguished folder returned by the server.
        return self.root.get_default_folder(Calendar)

    @threaded_cached_property
    def conflicts(self):
        return self.root.get_default_folder(Conflicts)

    @threaded_cached_property
    def contacts(self):
        return self.root.get_default_folder(Contacts)

    @threaded_cached_property
    def conversation_history(self):
        return self.root.get_default_folder(ConversationHistory)

    @threaded_cached_property
    def directory(self):
        return self.root.get_default_folder(Directory)

    @threaded_cached_property
    def drafts(self):
        return self.root.get_default_folder(Drafts)

    @threaded_cached_property
    def favorites(self):
        return self.root.get_default_folder(Favorites)

    @threaded_cached_property
    def im_contact_list(self):
        return self.root.get_default_folder(IMContactList)

    @threaded_cached_property
    def inbox(self):
        return self.root.get_default_folder(Inbox)

    @threaded_cached_property
    def journal(self):
        return self.root.get_default_folder(Journal)

    @threaded_cached_property
    def junk(self):
        return self.root.get_default_folder(JunkEmail)

    @threaded_cached_property
    def local_failures(self):
        return self.root.get_default_folder(LocalFailures)

    @threaded_cached_property
    def msg_folder_root(self):
        return self.root.get_default_folder(MsgFolderRoot)

    @threaded_cached_property
    def my_contacts(self):
        return self.root.get_default_folder(MyContacts)

    @threaded_cached_property
    def notes(self):
        return self.root.get_default_folder(Notes)

    @threaded_cached_property
    def outbox(self):
        return self.root.get_default_folder(Outbox)

    @threaded_cached_property
    def people_connect(self):
        return self.root.get_default_folder(PeopleConnect)

    @threaded_cached_property
    def public_folders_root(self):
        return PublicFoldersRoot.get_distinguished_root(account=self)

    @threaded_cached_property
    def quick_contacts(self):
        return self.root.get_default_folder(QuickContacts)

    @threaded_cached_property
    def recipient_cache(self):
        return self.root.get_default_folder(RecipientCache)

    @threaded_cached_property
    def recoverable_items_deletions(self):
        return self.root.get_default_folder(RecoverableItemsDeletions)

    @threaded_cached_property
    def recoverable_items_purges(self):
        return self.root.get_default_folder(RecoverableItemsPurges)

    @threaded_cached_property
    def recoverable_items_root(self):
        return self.root.get_default_folder(RecoverableItemsRoot)

    @threaded_cached_property
    def recoverable_items_versions(self):
        return self.root.get_default_folder(RecoverableItemsVersions)

    @threaded_cached_property
    def root(self):
        return Root.get_distinguished_root(account=self)

    @threaded_cached_property
    def search_folders(self):
        return self.root.get_default_folder(SearchFolders)

    @threaded_cached_property
    def sent(self):
        return self.root.get_default_folder(SentItems)

    @threaded_cached_property
    def server_failures(self):
        return self.root.get_default_folder(ServerFailures)

    @threaded_cached_property
    def sync_issues(self):
        return self.root.get_default_folder(SyncIssues)

    @threaded_cached_property
    def tasks(self):
        return self.root.get_default_folder(Tasks)

    @threaded_cached_property
    def todo_search(self):
        return self.root.get_default_folder(ToDoSearch)

    @threaded_cached_property
    def trash(self):
        return self.root.get_default_folder(DeletedItems)

    @threaded_cached_property
    def voice_mail(self):
        return self.root.get_default_folder(VoiceMail)

    @property
    def domain(self):
        return get_domain(self.primary_smtp_address)

    @property
    def oof_settings(self):
        # We don't want to cache this property because then we can't easily get updates. 'threaded_cached_property'
        # supports the 'del self.oof_settings' syntax to invalidate the cache, but does not support custom setter
        # methods. Having a non-cached service call here goes against the assumption that properties are cheap, but the
        # alternative is to create get_oof_settings() and set_oof_settings(), and that's just too Java-ish for my taste.
        return GetUserOofSettings(account=self).call(
            mailbox=Mailbox(email_address=self.primary_smtp_address),
        )

    @oof_settings.setter
    def oof_settings(self, value):
        if not isinstance(value, OofSettings):
            raise ValueError("'value' %r must be an OofSettings instance" % value)
        SetUserOofSettings(account=self).call(
            mailbox=Mailbox(email_address=self.primary_smtp_address),
            oof_settings=value,
        )

    def _consume_item_service(self, service_cls, items, chunk_size, kwargs):
        # 'items' could be an unevaluated QuerySet, e.g. if we ended up here via `some_folder.filter(...).delete()`. In
        # that case, we want to use its iterator. Otherwise, peek() will start a count() which is wasteful because we
        # need the item IDs immediately afterwards. iterator() will only do the bare minimum.
        if isinstance(items, QuerySet):
            items = items.iterator()
        is_empty, items = peek(items)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'ids' is empty. Allow
            # empty 'ids' and return early.
            return
        kwargs['items'] = items
        for i in service_cls(account=self, chunk_size=chunk_size).call(**kwargs):
            yield i

    def export(self, items, chunk_size=None):
        """Return export strings of the given items

        :param items: An iterable containing the Items we want to export
        :param chunk_size: The number of items to send to the server in a single request

        :return A list of strings, the exported representation of the object
        """
        return list(
            self._consume_item_service(service_cls=ExportItems, items=items, chunk_size=chunk_size, kwargs=dict())
        )

    def upload(self, data, chunk_size=None):
        """Adds objects retrieved from export into the given folders

        :param data: An iterable of tuples containing the folder we want to upload the data to and the
            string outputs of exports.
        :param chunk_size: The number of items to send to the server in a single request

        :return A list of tuples with the new ids and changekeys

        Example:
        account.upload([(account.inbox, "AABBCC..."),
                        (account.inbox, "XXYYZZ..."),
                        (account.calendar, "ABCXYZ...")])
        -> [("idA", "changekey"), ("idB", "changekey"), ("idC", "changekey")]
        """
        is_empty, data = peek(data)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'upload_data' is empty.
            # Allow empty 'upload_data' and return early.
            return []
        return list(UploadItems(account=self, chunk_size=chunk_size).call(data=data))

    def bulk_create(self, folder, items, message_disposition=SAVE_ONLY, send_meeting_invitations=SEND_TO_NONE,
                    chunk_size=None):
        """Creates new items in 'folder'

        :param folder: the folder to create the items in
        :param items: an iterable of Item objects
        :param message_disposition: only applicable to Message items. Possible values are specified in
               MESSAGE_DISPOSITION_CHOICES
        :param send_meeting_invitations: only applicable to CalendarItem items. Possible values are specified in
               SEND_MEETING_INVITATIONS_CHOICES
        :param chunk_size: The number of items to send to the server in a single request
        :return: a list of either BulkCreateResult or exception instances in the same order as the input. The returned
                 BulkCreateResult objects are normal Item objects except they only contain the 'id' and 'changekey'
                 of the created item, and the 'id' of any attachments that were also created.
        """
        if message_disposition not in MESSAGE_DISPOSITION_CHOICES:
            raise ValueError("'message_disposition' %s must be one of %s" % (
                message_disposition, MESSAGE_DISPOSITION_CHOICES
            ))
        if send_meeting_invitations not in SEND_MEETING_INVITATIONS_CHOICES:
            raise ValueError("'send_meeting_invitations' %s must be one of %s" % (
                send_meeting_invitations, SEND_MEETING_INVITATIONS_CHOICES
            ))
        if folder is not None:
            if not isinstance(folder, Folder):
                raise ValueError("'folder' %r must be a Folder instance" % folder)
            if not folder.root or folder.root.account != self:
                raise ValueError('"Folder must belong to this account')
        if message_disposition == SAVE_ONLY and folder is None:
            raise AttributeError("Folder must be supplied when in save-only mode")
        if message_disposition == SEND_AND_SAVE_COPY and folder is None:
            folder = self.sent  # 'Sent' is default EWS behaviour
        if message_disposition == SEND_ONLY and folder is not None:
            raise AttributeError("Folder must be None in send-ony mode")
        if isinstance(items, QuerySet):
            # bulk_create() on a queryset does not make sense because it returns items that have already been created
            raise ValueError('Cannot bulk create items from a QuerySet')
        log.debug(
            'Adding items for %s (folder %s, message_disposition: %s, send_meeting_invitations: %s)',
            self,
            folder,
            message_disposition,
            send_meeting_invitations,
        )
        return list(
            i if isinstance(i, Exception)
            else BulkCreateResult.from_xml(elem=i, account=self)
            for i in self._consume_item_service(service_cls=CreateItem, items=items, chunk_size=chunk_size, kwargs=dict(
                folder=folder,
                message_disposition=message_disposition,
                send_meeting_invitations=send_meeting_invitations,
            ))
        )

    def bulk_update(self, items, conflict_resolution=AUTO_RESOLVE, message_disposition=SAVE_ONLY,
                    send_meeting_invitations_or_cancellations=SEND_TO_NONE, suppress_read_receipts=True,
                    chunk_size=None):
        """
        Bulk updates existing items

        :param items: a list of (Item, fieldnames) tuples, where 'Item' is an Item object, and 'fieldnames' is a list
                      containing the attributes on this Item object that we want to be updated.
        :param conflict_resolution: Possible values are specified in CONFLICT_RESOLUTION_CHOICES
        :param message_disposition: only applicable to Message items. Possible values are specified in
               MESSAGE_DISPOSITION_CHOICES
        :param send_meeting_invitations_or_cancellations: only applicable to CalendarItem items. Possible values are
               specified in SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES
        :param suppress_read_receipts: nly supported from Exchange 2013. True or False
        :param chunk_size: The number of items to send to the server in a single request

        :return: a list of either (id, changekey) tuples or exception instances, in the same order as the input
        """
        if conflict_resolution not in CONFLICT_RESOLUTION_CHOICES:
            raise ValueError("'conflict_resolution' %s must be one of %s" % (
                conflict_resolution, CONFLICT_RESOLUTION_CHOICES
            ))
        if message_disposition not in MESSAGE_DISPOSITION_CHOICES:
            raise ValueError("'message_disposition' %s must be one of %s" % (
                message_disposition, MESSAGE_DISPOSITION_CHOICES
            ))
        if send_meeting_invitations_or_cancellations not in SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES:
            raise ValueError("'send_meeting_invitations_or_cancellations' %s must be one of %s" % (
                send_meeting_invitations_or_cancellations, SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES
            ))
        if suppress_read_receipts not in (True, False):
            raise ValueError("'suppress_read_receipts' %s must be True or False" % suppress_read_receipts)
        if message_disposition == SEND_ONLY:
            raise ValueError('Cannot send-only existing objects. Use SendItem service instead')
        # bulk_update() on a queryset does not make sense because there would be no opportunity to alter the items. In
        # fact, it could be dangerous if the queryset contains an '.only()'. This would wipe out certain fields
        # entirely.
        if isinstance(items, QuerySet):
            raise ValueError('Cannot bulk update on a queryset')
        log.debug(
            'Updating items for %s (conflict_resolution %s, message_disposition: %s, send_meeting_invitations: %s)',
            self,
            conflict_resolution,
            message_disposition,
            send_meeting_invitations_or_cancellations,
        )
        return list(
            i if isinstance(i, Exception) else Item.id_from_xml(i)
            for i in self._consume_item_service(service_cls=UpdateItem, items=items, chunk_size=chunk_size, kwargs=dict(
                conflict_resolution=conflict_resolution,
                message_disposition=message_disposition,
                send_meeting_invitations_or_cancellations=send_meeting_invitations_or_cancellations,
                suppress_read_receipts=suppress_read_receipts,
            ))
        )

    def bulk_delete(self, ids, delete_type=HARD_DELETE, send_meeting_cancellations=SEND_TO_NONE,
                    affected_task_occurrences=ALL_OCCURRENCIES, suppress_read_receipts=True, chunk_size=None):
        """
        Bulk deletes items.

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param delete_type: the type of delete to perform. Possible values are specified in DELETE_TYPE_CHOICES
        :param send_meeting_cancellations: only applicable to CalendarItem. Possible values are specified in
               SEND_MEETING_CANCELLATIONS_CHOICES.
        :param affected_task_occurrences: only applicable for recurring Task items. Possible values are specified in
               AFFECTED_TASK_OCCURRENCES_CHOICES.
        :param suppress_read_receipts: only supported from Exchange 2013. True or False.
        :param chunk_size: The number of items to send to the server in a single request

        :return: a list of either True or exception instances, in the same order as the input
        """
        if delete_type not in DELETE_TYPE_CHOICES:
            raise ValueError("'delete_type' %s must be one of %s" % (
                delete_type, DELETE_TYPE_CHOICES
            ))
        if send_meeting_cancellations not in SEND_MEETING_CANCELLATIONS_CHOICES:
            raise ValueError("'send_meeting_cancellations' %s must be one of %s" % (
                send_meeting_cancellations, SEND_MEETING_CANCELLATIONS_CHOICES
            ))
        if affected_task_occurrences not in AFFECTED_TASK_OCCURRENCES_CHOICES:
            raise ValueError("'affected_task_occurrences' %s must be one of %s" % (
                affected_task_occurrences, AFFECTED_TASK_OCCURRENCES_CHOICES
            ))
        if suppress_read_receipts not in (True, False):
            raise ValueError("'suppress_read_receipts' %s must be True or False" % suppress_read_receipts)
        log.debug(
            'Deleting items for %s (delete_type: %s, send_meeting_invitations: %s, affected_task_occurences: %s)',
            self,
            delete_type,
            send_meeting_cancellations,
            affected_task_occurrences,
        )
        return list(
            self._consume_item_service(service_cls=DeleteItem, items=ids, chunk_size=chunk_size, kwargs=dict(
                delete_type=delete_type,
                send_meeting_cancellations=send_meeting_cancellations,
                affected_task_occurrences=affected_task_occurrences,
                suppress_read_receipts=suppress_read_receipts,
            ))
        )

    def bulk_send(self, ids, save_copy=True, copy_to_folder=None, chunk_size=None):
        """ Send existing draft messages. If requested, save a copy in 'copy_to_folder'

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param save_copy: If true, saves a copy of the message
        :param copy_to_folder: If requested, save a copy of the message in this folder. Default is the Sent folder
        :param chunk_size: The number of items to send to the server in a single request
        :return: Status for each send operation, in the same order as the input
        """
        if copy_to_folder and not save_copy:
            raise AttributeError("'save_copy' must be True when 'copy_to_folder' is set")
        if save_copy and not copy_to_folder:
            copy_to_folder = self.sent  # 'Sent' is default EWS behaviour
        return list(
            self._consume_item_service(service_cls=SendItem, items=ids, chunk_size=chunk_size, kwargs=dict(
                saved_item_folder=copy_to_folder,
            ))
        )

    def bulk_copy(self, ids, to_folder, chunk_size=None):
        """ Copy items to another folder

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param to_folder: The destination folder of the copy operation
        :param chunk_size: The number of items to send to the server in a single request
        :return: Status for each send operation, in the same order as the input
        """
        if not isinstance(to_folder, Folder):
            raise ValueError("'to_folder' %r must be a Folder instance" % to_folder)
        return list(
            i if isinstance(i, Exception) else Item.id_from_xml(i)
            for i in self._consume_item_service(service_cls=CopyItem, items=ids, chunk_size=chunk_size, kwargs=dict(
                to_folder=to_folder,
            ))
        )

    def bulk_move(self, ids, to_folder, chunk_size=None):
        """Move items to another folder

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param to_folder: The destination folder of the copy operation
        :param chunk_size: The number of items to send to the server in a single request
        :return: The new IDs of the moved items, in the same order as the input. If 'to_folder' is a public folder or a
        folder in a different mailbox, an empty list is returned.
        """
        if not isinstance(to_folder, Folder):
            raise ValueError("'to_folder' %r must be a Folder instance" % to_folder)
        return list(
            i if isinstance(i, Exception) else Item.id_from_xml(i)
            for i in self._consume_item_service(service_cls=MoveItem, items=ids, chunk_size=chunk_size, kwargs=dict(
                to_folder=to_folder,
            ))
        )

    def fetch(self, ids, folder=None, only_fields=None, chunk_size=None):
        """ Fetch items by ID

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param folder: used for validating 'only_fields'
        :param only_fields: A list of string or FieldPath items specifying the fields to fetch. Default to all fields
        :param chunk_size: The number of items to send to the server in a single request
        :return: A generator of Item objects, in the same order as the input
        """
        validation_folder = folder or Folder(root=self.root)  # Default to a folder type that supports all item types
        # 'ids' could be an unevaluated QuerySet, e.g. if we ended up here via `fetch(ids=some_folder.filter(...))`. In
        # that case, we want to use its iterator. Otherwise, peek() will start a count() which is wasteful because we
        # need the item IDs immediately afterwards. iterator() will only do the bare minimum.
        if only_fields is None:
            # We didn't restrict list of field paths. Get all fields from the server, including extended properties.
            additional_fields = {
                FieldPath(field=f) for f in validation_folder.allowed_item_fields(version=self.version)
            }
        else:
            for field in only_fields:
                validation_folder.validate_item_field(field=field)
            additional_fields = validation_folder.normalize_fields(fields=only_fields)
        # Always use IdOnly here, because AllProperties doesn't actually get *all* properties
        for i in self._consume_item_service(service_cls=GetItem, items=ids, chunk_size=chunk_size, kwargs=dict(
                additional_fields=additional_fields,
                shape=ID_ONLY,
        )):
            if isinstance(i, Exception):
                yield i
            else:
                item = validation_folder.item_model_from_tag(i.tag).from_xml(elem=i, account=self)
                yield item

    @property
    def mail_tips(self):
        """See self.oof_settings about caching considerations
        """
        # mail_tips_requested must be one of properties.MAIL_TIPS_TYPES
        res = list(GetMailTips(protocol=self.protocol).call(
            sending_as=SendingAs(email_address=self.primary_smtp_address),
            recipients=[Mailbox(email_address=self.primary_smtp_address)],
            mail_tips_requested='All',
        ))
        if len(res) != 1:
            raise ValueError('Expected result length 1, but got %s' % res)
        if isinstance(res[0], Exception):
            raise res[0]
        return res[0]

    def __str__(self):
        txt = '%s' % self.primary_smtp_address
        if self.fullname:
            txt += ' (%s)' % self.fullname
        return txt

    def sync(self, folder, max_changes):
        # Only use sync if sync_state is fully updated. First sync's with EWS will return (id, changekey) tuples
        # for ALL items until the cursor hits the end of the state. Subsequent calls will return only specific changes.
        # If you want to use sync, please ensure you re-use the sync_state properly (and persist it)
        if not isinstance(folder, Folder):
            raise ValueError('Cannot sync non-folder obj %r' % folder)
        for change in SyncFolderItems(account=self, folders=[folder]).call(folder.sync_state, None, max_changes):
            if isinstance(change, Exception):
                yield change
            else:
                item = folder.item_model_from_tag(change.tag).from_xml(elem=change, account=self)
                yield item

    def changes(self, folder):
        # More user friendly method. No need to worry about sync_states. Will return changes as they happen.
        if not isinstance(folder, Folder):
            raise ValueError('Cannot sync non-folder obj %r' % folder)

        is_first_sync = not folder.sync_state
        changes = []

        ret = list(self.sync(folder, 512))
        if len(ret) > 0:
            changes.extend(ret)
        while ret and len(ret) == 512:
            ret = list(self.sync(folder, 512))
            if len(ret) > 0:
                changes.extend(ret)
        return changes if not is_first_sync else []

    def stream(self, folder):
        # Subscribe for streaming notifications
        # Usage:
        # 1. Get subscription id for folder by calling stream
        # 2. Call events which will block until changes on the folder happen or timeout is hit
        # 3. Process changes and call unsubcribe with subscriptionId to end the subscription
        if not isinstance(folder, Folder):
            raise ValueError('Folder to subscribe to %r must be valid' % folder)
        for subscription_id in SubscribeStreamingFolder(account=self, folders=[folder]).call(events=EVENT_TYPES):
            yield subscription_id

    def events(self, subscription_ids):
        # Get streaming events - this will block until it hits timeout or enough data is accumulated
        # TODO: Add stream=True for GetStreamingEvents and figure out how to accumulate data on the socket
        for event in GetStreamingEvents(account=self).call(subscription_ids):
            if isinstance(event, Exception):
                yield event
            else:
                yield event

    def push(self, folder, callback_url):
        # Subscribe for push notifications from EWS to your server. Server must handle unsubcribe / re-use / validation
        if not isinstance(folder, Folder):
            raise ValueError('Folder to subscribe to %r must be valid' % folder)
        for subscription_id in SubscribePushFolder(account=self, folders=[folder]).call(events=EVENT_TYPES,
                                                                                       callback_url=callback_url):
            yield subscription_id

    def unsubscribe(self, subscription_id):
        # Unsubscribe from streaming notifications
        if not subscription_id:
            raise ValueError('Cannot unsubscribe without a subscription id')
        UnsubscribeStreamingFolder(account=self).call(subscription_id)
