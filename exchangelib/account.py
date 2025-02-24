import locale as stdlib_locale
from logging import getLogger
from threading import Lock

from cached_property import threaded_cached_property

from .autodiscover import Autodiscovery
from .configuration import Configuration
from .credentials import ACCESS_TYPES, DELEGATE, IMPERSONATION
from .errors import InvalidEnumValue, InvalidTypeError, ResponseMessageError, UnknownTimeZone
from .ewsdatetime import UTC, EWSTimeZone
from .fields import FieldPath, TextField
from .folders import (
    AdminAuditLogs,
    ArchiveDeletedItems,
    ArchiveInbox,
    ArchiveMsgFolderRoot,
    ArchiveRecoverableItemsDeletions,
    ArchiveRecoverableItemsPurges,
    ArchiveRecoverableItemsRoot,
    ArchiveRecoverableItemsVersions,
    ArchiveRoot,
    Calendar,
    Conflicts,
    Contacts,
    ConversationHistory,
    DeletedItems,
    Directory,
    Drafts,
    Favorites,
    Folder,
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
    PublicFoldersRoot,
    QuickContacts,
    RecipientCache,
    RecoverableItemsDeletions,
    RecoverableItemsPurges,
    RecoverableItemsRoot,
    RecoverableItemsVersions,
    Root,
    SearchFolders,
    SentItems,
    ServerFailures,
    SyncIssues,
    Tasks,
    ToDoSearch,
    VoiceMail,
)
from .folders.collections import PullSubscription, PushSubscription, StreamingSubscription
from .items import ALL_OCCURRENCES, AUTO_RESOLVE, HARD_DELETE, ID_ONLY, SAVE_ONLY, SEND_TO_NONE
from .properties import EWSElement, Mailbox, Rule, SendingAs
from .protocol import Protocol
from .queryset import QuerySet
from .services import (
    ArchiveItem,
    CopyItem,
    CreateInboxRule,
    CreateItem,
    DeleteInboxRule,
    DeleteItem,
    ExportItems,
    GetDelegate,
    GetInboxRules,
    GetItem,
    GetMailTips,
    GetPersona,
    GetUserOofSettings,
    MarkAsJunk,
    MoveItem,
    SendItem,
    SetInboxRule,
    SetUserOofSettings,
    SubscribeToPull,
    SubscribeToPush,
    SubscribeToStreaming,
    Unsubscribe,
    UpdateItem,
    UploadItems,
)
from .util import get_domain, peek

log = getLogger(__name__)


class Identity(EWSElement):
    """Contains information that uniquely identifies an account. Currently only used for SOAP impersonation headers."""

    ELEMENT_NAME = "ConnectingSID"

    # We have multiple options for uniquely identifying the user. Here's a prioritized list in accordance with
    # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/connectingsid
    sid = TextField(field_uri="SID")
    upn = TextField(field_uri="PrincipalName")
    smtp_address = TextField(field_uri="SmtpAddress")  # The (non-)primary email address for the account
    primary_smtp_address = TextField(field_uri="PrimarySmtpAddress")  # The primary email address for the account


class Account:
    """Models an Exchange server user account."""

    def __init__(
        self,
        primary_smtp_address,
        fullname=None,
        access_type=None,
        autodiscover=False,
        credentials=None,
        config=None,
        locale=None,
        default_timezone=None,
    ):
        """

        :param primary_smtp_address: The primary email address associated with the account on the Exchange server
        :param fullname: The full name of the account. Optional. (Default value = None)
        :param access_type: The access type granted to 'credentials' for this account. Valid options are 'delegate'
            and 'impersonation'. 'delegate' is default if 'credentials' is set. Otherwise, 'impersonation' is default.
        :param autodiscover: Whether to look up the EWS endpoint automatically using the autodiscover protocol.
            (Default value = False)
        :param credentials: A Credentials object containing valid credentials for this account. (Default value = None)
        :param config: A Configuration object containing EWS endpoint information. Required if autodiscover is disabled
            (Default value = None)
        :param locale: The locale of the user, e.g. 'en_US'. Defaults to the locale of the host, if available.
        :param default_timezone: EWS may return some datetime values without timezone information. In this case, we will
            assume values to be in the provided timezone. Defaults to the timezone of the host.
        :return:
        """
        if "@" not in primary_smtp_address:
            raise ValueError(f"primary_smtp_address {primary_smtp_address!r} is not an email address")
        self.fullname = fullname
        # Assume delegate access if individual credentials are provided. Else, assume service user with impersonation
        self.access_type = access_type or (DELEGATE if credentials else IMPERSONATION)
        if self.access_type not in ACCESS_TYPES:
            raise InvalidEnumValue("access_type", self.access_type, ACCESS_TYPES)
        try:
            # get_locale() might not be able to determine the locale
            self.locale = locale or stdlib_locale.getlocale()[0] or None
        except ValueError as e:
            # getlocale() may throw ValueError if it fails to parse the system locale
            log.warning("Failed to get locale (%s)", e)
            self.locale = None
        if not isinstance(self.locale, (type(None), str)):
            raise InvalidTypeError("locale", self.locale, str)
        if default_timezone:
            try:
                self.default_timezone = EWSTimeZone.from_timezone(default_timezone)
            except TypeError:
                raise InvalidTypeError("default_timezone", default_timezone, EWSTimeZone)
        else:
            try:
                self.default_timezone = EWSTimeZone.localzone()
            except (ValueError, UnknownTimeZone) as e:
                # There is no translation from local timezone name to Windows timezone name, or e failed to find the
                # local timezone.
                log.warning("%s. Fallback to UTC", e.args[0])
                self.default_timezone = UTC
        if not isinstance(config, (Configuration, type(None))):
            raise InvalidTypeError("config", config, Configuration)
        if autodiscover:
            if config:
                auth_type, retry_policy, version, max_connections = (
                    config.auth_type,
                    config.retry_policy,
                    config.version,
                    config.max_connections,
                )
                if not credentials:
                    credentials = config.credentials
            else:
                auth_type, retry_policy, version, max_connections = None, None, None, None
            self.ad_response, self.protocol = Autodiscovery(
                email=primary_smtp_address, credentials=credentials
            ).discover()
            # Let's not use the auth_package hint from the AD response. It could be incorrect and we can just guess.
            self.protocol.config.auth_type = auth_type
            if retry_policy:
                self.protocol.config.retry_policy = retry_policy
            if version:
                self.protocol.config.version = version
            self.protocol.max_connections = max_connections
            primary_smtp_address = self.ad_response.autodiscover_smtp_address
        else:
            if not config:
                raise AttributeError("non-autodiscover requires a config")
            self.ad_response = None
            self.protocol = Protocol(config=config)

        # Other ways of identifying the account can be added later
        self.identity = Identity(primary_smtp_address=primary_smtp_address)

        # For maintaining affinity in e.g. subscriptions
        self.affinity_cookie = None

        self._version = None
        self._version_lock = Lock()
        log.debug("Added account: %s", self)

    @property
    def primary_smtp_address(self):
        return self.identity.primary_smtp_address

    @property
    def version(self):
        # We may need to override the default server version on a per-account basis because Microsoft may report one
        # server version up-front but delegate account requests to an older backend server. Create a new instance to
        # avoid changing the protocol version instance.
        if self._version:
            return self._version
        with self._version_lock:
            if self._version:
                return self._version
            self._version = self.protocol.version.copy()
            return self._version

    @version.setter
    def version(self, value):
        with self._version_lock:
            self._version = value

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
        return ArchiveRoot.get_distinguished(account=self)

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
        return PublicFoldersRoot.get_distinguished(account=self)

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
        return Root.get_distinguished(account=self)

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
        return GetUserOofSettings(account=self).get(
            mailbox=Mailbox(email_address=self.primary_smtp_address),
        )

    @oof_settings.setter
    def oof_settings(self, value):
        SetUserOofSettings(account=self).get(
            oof_settings=value,
            mailbox=Mailbox(email_address=self.primary_smtp_address),
        )

    def _consume_item_service(self, service_cls, items, chunk_size, kwargs):
        if isinstance(items, QuerySet):
            # We just want an iterator over the results
            items = iter(items)
        is_empty, items = peek(items)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'ids' is empty. Allow
            # empty 'ids' and return early.
            return
        kwargs["items"] = items
        yield from service_cls(account=self, chunk_size=chunk_size).call(**kwargs)

    def export(self, items, chunk_size=None):
        """Return export strings of the given items.

        :param items: An iterable containing the Items we want to export
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: A list of strings, the exported representation of the object
        """
        return list(self._consume_item_service(service_cls=ExportItems, items=items, chunk_size=chunk_size, kwargs={}))

    def upload(self, data, chunk_size=None):
        """Upload objects retrieved from an export to the given folders.

        :param data: An iterable of tuples containing the folder we want to upload the data to and the string outputs of
            exports. If you want to update items instead of create, the data must be a tuple of
            (ItemId, is_associated, data) values.
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: A list of tuples with the new ids and changekeys

          Example:
          account.upload([
              (account.inbox, "AABBCC..."),
              (account.inbox, (ItemId('AA', 'BB'), False, "XXYYZZ...")),
              (account.inbox, (('CC', 'DD'), None, "XXYYZZ...")),
              (account.calendar, "ABCXYZ..."),
          ])
          -> [("idA", "changekey"), ("idB", "changekey"), ("idC", "changekey")]
        """
        items = ((f, (None, False, d) if isinstance(d, str) else d) for f, d in data)
        return list(self._consume_item_service(service_cls=UploadItems, items=items, chunk_size=chunk_size, kwargs={}))

    def bulk_create(
        self, folder, items, message_disposition=SAVE_ONLY, send_meeting_invitations=SEND_TO_NONE, chunk_size=None
    ):
        """Create new items in 'folder'.

        :param folder: the folder to create the items in
        :param items: an iterable of Item objects
        :param message_disposition: only applicable to Message items. Possible values are specified in
            MESSAGE_DISPOSITION_CHOICES (Default value = SAVE_ONLY)
        :param send_meeting_invitations: only applicable to CalendarItem items. Possible values are specified in
            SEND_MEETING_INVITATIONS_CHOICES (Default value = SEND_TO_NONE)
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: a list of either BulkCreateResult or exception instances in the same order as the input. The returned
          BulkCreateResult objects are normal Item objects except they only contain the 'id' and 'changekey'
          of the created item, and the 'id' of any attachments that were also created.
        """
        if isinstance(items, QuerySet):
            # bulk_create() on a queryset does not make sense because it returns items that have already been created
            raise ValueError("Cannot bulk create items from a QuerySet")
        log.debug(
            "Adding items for %s (folder %s, message_disposition: %s, send_meeting_invitations: %s)",
            self,
            folder,
            message_disposition,
            send_meeting_invitations,
        )
        return list(
            self._consume_item_service(
                service_cls=CreateItem,
                items=items,
                chunk_size=chunk_size,
                kwargs=dict(
                    folder=folder,
                    message_disposition=message_disposition,
                    send_meeting_invitations=send_meeting_invitations,
                ),
            )
        )

    def bulk_update(
        self,
        items,
        conflict_resolution=AUTO_RESOLVE,
        message_disposition=SAVE_ONLY,
        send_meeting_invitations_or_cancellations=SEND_TO_NONE,
        suppress_read_receipts=True,
        chunk_size=None,
    ):
        """Bulk update existing items.

        :param items: a list of (Item, fieldnames) tuples, where 'Item' is an Item object, and 'fieldnames' is a list
            containing the attributes on this Item object that we want to be updated.
        :param conflict_resolution: Possible values are specified in CONFLICT_RESOLUTION_CHOICES
            (Default value = AUTO_RESOLVE)
        :param message_disposition: only applicable to Message items. Possible values are specified in
            MESSAGE_DISPOSITION_CHOICES (Default value = SAVE_ONLY)
        :param send_meeting_invitations_or_cancellations: only applicable to CalendarItem items. Possible values are
            specified in SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES (Default value = SEND_TO_NONE)
        :param suppress_read_receipts: nly supported from Exchange 2013. True or False (Default value = True)
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: a list of either (id, changekey) tuples or exception instances, in the same order as the input
        """
        # bulk_update() on a queryset does not make sense because there would be no opportunity to alter the items. In
        # fact, it could be dangerous if the queryset contains an '.only()'. This would wipe out certain fields
        # entirely.
        if isinstance(items, QuerySet):
            raise ValueError("Cannot bulk update on a queryset")
        log.debug(
            "Updating items for %s (conflict_resolution %s, message_disposition: %s, send_meeting_invitations: %s)",
            self,
            conflict_resolution,
            message_disposition,
            send_meeting_invitations_or_cancellations,
        )
        return list(
            self._consume_item_service(
                service_cls=UpdateItem,
                items=items,
                chunk_size=chunk_size,
                kwargs=dict(
                    conflict_resolution=conflict_resolution,
                    message_disposition=message_disposition,
                    send_meeting_invitations_or_cancellations=send_meeting_invitations_or_cancellations,
                    suppress_read_receipts=suppress_read_receipts,
                ),
            )
        )

    def bulk_delete(
        self,
        ids,
        delete_type=HARD_DELETE,
        send_meeting_cancellations=SEND_TO_NONE,
        affected_task_occurrences=ALL_OCCURRENCES,
        suppress_read_receipts=True,
        chunk_size=None,
    ):
        """Bulk delete items.

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param delete_type: the type of delete to perform. Possible values are specified in DELETE_TYPE_CHOICES
            (Default value = HARD_DELETE)
        :param send_meeting_cancellations: only applicable to CalendarItem. Possible values are specified in
            SEND_MEETING_CANCELLATIONS_CHOICES. (Default value = SEND_TO_NONE)
        :param affected_task_occurrences: only applicable for recurring Task items. Possible values are specified in
            AFFECTED_TASK_OCCURRENCES_CHOICES. (Default value = ALL_OCCURRENCES)
        :param suppress_read_receipts: only supported from Exchange 2013. True or False. (Default value = True)
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: a list of either True or exception instances, in the same order as the input
        """
        log.debug(
            "Deleting items for %s (delete_type: %s, send_meeting_invitations: %s, affected_task_occurrences: %s)",
            self,
            delete_type,
            send_meeting_cancellations,
            affected_task_occurrences,
        )
        return list(
            self._consume_item_service(
                service_cls=DeleteItem,
                items=ids,
                chunk_size=chunk_size,
                kwargs=dict(
                    delete_type=delete_type,
                    send_meeting_cancellations=send_meeting_cancellations,
                    affected_task_occurrences=affected_task_occurrences,
                    suppress_read_receipts=suppress_read_receipts,
                ),
            )
        )

    def bulk_send(self, ids, save_copy=True, copy_to_folder=None, chunk_size=None):
        """Send existing draft messages. If requested, save a copy in 'copy_to_folder'.

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param save_copy: If true, saves a copy of the message (Default value = True)
        :param copy_to_folder: If requested, save a copy of the message in this folder. Default is the Sent folder
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: Status for each send operation, in the same order as the input
        """
        if copy_to_folder and not save_copy:
            raise AttributeError("'save_copy' must be True when 'copy_to_folder' is set")
        if save_copy and not copy_to_folder:
            copy_to_folder = self.sent  # 'Sent' is default EWS behaviour
        return list(
            self._consume_item_service(
                service_cls=SendItem,
                items=ids,
                chunk_size=chunk_size,
                kwargs=dict(
                    saved_item_folder=copy_to_folder,
                ),
            )
        )

    def bulk_copy(self, ids, to_folder, chunk_size=None):
        """Copy items to another folder.

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param to_folder: The destination folder of the copy operation
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: Status for each send operation, in the same order as the input
        """
        return list(
            self._consume_item_service(
                service_cls=CopyItem,
                items=ids,
                chunk_size=chunk_size,
                kwargs=dict(
                    to_folder=to_folder,
                ),
            )
        )

    def bulk_move(self, ids, to_folder, chunk_size=None):
        """Move items to another folder.

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param to_folder: The destination folder of the copy operation
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: The new IDs of the moved items, in the same order as the input. If 'to_folder' is a public folder or a
          folder in a different mailbox, an empty list is returned.
        """
        return list(
            self._consume_item_service(
                service_cls=MoveItem,
                items=ids,
                chunk_size=chunk_size,
                kwargs=dict(
                    to_folder=to_folder,
                ),
            )
        )

    def bulk_archive(self, ids, to_folder, chunk_size=None):
        """Archive items to a folder in the archive mailbox. An archive mailbox must be enabled in order for this
        to work.

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param to_folder: The destination folder of the archive operation
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: A list containing True or an exception instance in stable order of the requested items
        """
        return list(
            self._consume_item_service(
                service_cls=ArchiveItem,
                items=ids,
                chunk_size=chunk_size,
                kwargs=dict(
                    to_folder=to_folder,
                ),
            )
        )

    def bulk_mark_as_junk(self, ids, is_junk, move_item, chunk_size=None):
        """Mark or un-mark message items as junk email and add or remove the sender from the blocked sender list.

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param is_junk: Whether the messages are junk or not
        :param move_item: Whether to move the messages to the junk folder or not
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

        :return: A list containing the new IDs of the moved items, if items were moved, or True, or an exception
          instance, in stable order of the requested items.
        """
        return list(
            self._consume_item_service(
                service_cls=MarkAsJunk,
                items=ids,
                chunk_size=chunk_size,
                kwargs=dict(
                    is_junk=is_junk,
                    move_item=move_item,
                ),
            )
        )

    def fetch(self, ids, folder=None, only_fields=None, chunk_size=None):
        """Fetch items by ID.

        :param ids: an iterable of either (id, changekey) tuples or Item objects.
        :param folder: used for validating 'only_fields' (Default value = None)
        :param only_fields: A list of string or FieldPath items specifying the fields to fetch. Default to all fields
        :param chunk_size: The number of items to send to the server in a single request (Default value = None)

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
                validation_folder.validate_item_field(field=field, version=self.version)
            # Remove ItemId and ChangeKey. We get them unconditionally
            additional_fields = {
                f for f in validation_folder.normalize_fields(fields=only_fields) if not f.field.is_attribute
            }
        # Always use IdOnly here, because AllProperties doesn't actually get *all* properties
        yield from self._consume_item_service(
            service_cls=GetItem,
            items=ids,
            chunk_size=chunk_size,
            kwargs=dict(
                additional_fields=additional_fields,
                shape=ID_ONLY,
            ),
        )

    def fetch_personas(self, ids):
        """Fetch personas by ID.

        :param ids: an iterable of either (id, changekey) tuples or Persona objects.
        :return: A generator of Persona objects, in the same order as the input
        """
        if isinstance(ids, QuerySet):
            # We just want an iterator over the results
            ids = iter(ids)
        is_empty, ids = peek(ids)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'ids' is empty. Allow
            # empty 'ids' and return early.
            return
        yield from GetPersona(account=self).call(personas=ids)

    @property
    def mail_tips(self):
        """See self.oof_settings about caching considerations."""
        return GetMailTips(protocol=self.protocol).get(
            sending_as=SendingAs(email_address=self.primary_smtp_address),
            recipients=[Mailbox(email_address=self.primary_smtp_address)],
            mail_tips_requested="All",
        )

    @property
    def delegates(self):
        """Return a list of DelegateUser objects representing the delegates that are set on this account."""
        return list(GetDelegate(account=self).call(user_ids=None, include_permissions=True))

    @property
    def rules(self):
        """Return a list of Rule objects representing the rules that are set on this account."""
        return list(GetInboxRules(account=self).call())

    def create_rule(self, rule: Rule):
        """Create an Inbox rule.

        :param rule: The rule to create. Must have at least 'display_name' set.
        :return: None if success, else raises an error.
        """
        CreateInboxRule(account=self).get(rule=rule, remove_outlook_rule_blob=True)
        # After creating the rule, query all rules,
        # find the rule that was just created, and return its ID.
        try:
            rule.id = {i.display_name: i for i in GetInboxRules(account=self).call()}[rule.display_name].id
        except KeyError:
            raise ResponseMessageError(f"Failed to create rule ({rule.display_name})!")

    def set_rule(self, rule: Rule):
        """Modify an Inbox rule.

        :param rule: The rule to set. Must have an ID.
        :return: None if success, else raises an error.
        """
        SetInboxRule(account=self).get(rule=rule)

    def delete_rule(self, rule: Rule):
        """Delete an Inbox rule.

        :param rule: The rule to delete. Must have an ID.
        :return: None if success, else raises an error.
        """
        if not rule.id:
            raise ValueError("Rule must have an ID")
        DeleteInboxRule(account=self).get(rule=rule)
        rule.id = None

    def subscribe_to_pull(self, event_types=None, watermark=None, timeout=60):
        """Create a pull subscription.

        :param event_types: List of event types to subscribe to. Possible values defined in SubscribeToPull.EVENT_TYPES
        :param watermark: An event bookmark as returned by some sync services
        :param timeout: Timeout of the subscription, in minutes. Timeout is reset when the server receives a
        GetEvents request for this subscription.
        :return: The subscription ID and a watermark
        """
        if event_types is None:
            event_types = SubscribeToPull.EVENT_TYPES
        return SubscribeToPull(account=self).get(
            folders=None,
            event_types=event_types,
            watermark=watermark,
            timeout=timeout,
        )

    def subscribe_to_push(self, callback_url, event_types=None, watermark=None, status_frequency=1):
        """Create a push subscription.

        :param callback_url: A client-defined URL that the server will call
        :param event_types: List of event types to subscribe to. Possible values defined in SubscribeToPush.EVENT_TYPES
        :param watermark: An event bookmark as returned by some sync services
        :param status_frequency: The frequency, in minutes, that the callback URL will be called with.
        :return: The subscription ID and a watermark
        """
        if event_types is None:
            event_types = SubscribeToPush.EVENT_TYPES
        return SubscribeToPush(account=self).get(
            folders=None,
            event_types=event_types,
            watermark=watermark,
            status_frequency=status_frequency,
            url=callback_url,
        )

    def subscribe_to_streaming(self, event_types=None):
        """Create a streaming subscription.

        :param event_types: List of event types to subscribe to. Possible values defined in SubscribeToPush.EVENT_TYPES
        :return: The subscription ID
        """
        if event_types is None:
            event_types = SubscribeToStreaming.EVENT_TYPES
        return SubscribeToStreaming(account=self).get(folders=None, event_types=event_types)

    def pull_subscription(self, **kwargs):
        return PullSubscription(target=self, **kwargs)

    def push_subscription(self, **kwargs):
        return PushSubscription(target=self, **kwargs)

    def streaming_subscription(self, **kwargs):
        return StreamingSubscription(target=self, **kwargs)

    def unsubscribe(self, subscription_id):
        """Unsubscribe. Only applies to pull and streaming notifications.

        :param subscription_id: A subscription ID as acquired by .subscribe_to_[pull|streaming]()
        :return: True

        This method doesn't need the current collection instance, but it makes sense to keep the method along the other
        sync methods.
        """
        return Unsubscribe(account=self).get(subscription_id=subscription_id)

    def __getstate__(self):
        # The lock cannot be pickled
        state = self.__dict__.copy()
        del state["_version_lock"]
        return state

    def __setstate__(self, state):
        # Restore the lock
        self.__dict__.update(state)
        self._version_lock = Lock()

    def __str__(self):
        if self.fullname:
            return f"{self.primary_smtp_address} ({self.fullname})"
        return self.primary_smtp_address
