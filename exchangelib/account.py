# coding=utf-8
from __future__ import unicode_literals

from collections import defaultdict
from locale import getlocale
from logging import getLogger

from cached_property import threaded_cached_property
from future.utils import raise_from, python_2_unicode_compatible
from six import text_type, string_types

from .autodiscover import discover
from .credentials import DELEGATE, IMPERSONATION
from .errors import ErrorFolderNotFound, ErrorAccessDenied
from .folders import Root, Calendar, DeletedItems, Drafts, Inbox, Outbox, SentItems, JunkEmail, Tasks, Contacts, \
    RecoverableItemsRoot, RecoverableItemsDeletions, Folder, Item, SHALLOW, DEEP, HARD_DELETE, \
    AUTO_RESOLVE, SEND_TO_NONE, SAVE_ONLY, SEND_AND_SAVE_COPY, SEND_ONLY, SPECIFIED_OCCURRENCE_ONLY, \
    DELETE_TYPE_CHOICES, MESSAGE_DISPOSITION_CHOICES, CONFLICT_RESOLUTION_CHOICES, AFFECTED_TASK_OCCURRENCES_CHOICES, \
    SEND_MEETING_INVITATIONS_CHOICES, SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES, \
    SEND_MEETING_CANCELLATIONS_CHOICES
from .protocol import Protocol
from .queryset import QuerySet
from .services import ExportItems, UploadItems, GetItem, CreateItem, UpdateItem, DeleteItem, MoveItem, SendItem
from .util import get_domain, peek

log = getLogger(__name__)


@python_2_unicode_compatible
class Account(object):
    """
    Models an Exchange server user account. The primary key for an account is its PrimarySMTPAddress
    """

    def __init__(self, primary_smtp_address, fullname=None, access_type=None, autodiscover=False, credentials=None,
                 config=None, verify_ssl=True, locale=None):
        if '@' not in primary_smtp_address:
            raise ValueError("primary_smtp_address '%s' is not an email address" % primary_smtp_address)
        self.primary_smtp_address = primary_smtp_address
        self.fullname = fullname
        self.locale = locale or getlocale()[0] or None  # get_locale() might not be able to determine the locale
        if self.locale is not None:
            assert isinstance(self.locale, string_types)
        # Assume delegate access if individual credentials are provided. Else, assume service user with impersonation
        self.access_type = access_type or (DELEGATE if credentials else IMPERSONATION)
        assert self.access_type in (DELEGATE, IMPERSONATION)
        if autodiscover:
            if not credentials:
                raise AttributeError('autodiscover requires credentials')
            self.primary_smtp_address, self.protocol = discover(email=self.primary_smtp_address,
                                                                credentials=credentials, verify_ssl=verify_ssl)
            if config:
                raise AttributeError('config is ignored when autodiscover is active')
        else:
            if not config:
                raise AttributeError('non-autodiscover requires a config')
            self.protocol = config.protocol
        # We may need to override the default server version on a per-account basis because Microsoft may report one
        # server version up-front but delegate account requests to an older backend server.
        self.version = self.protocol.version
        self.root = Root.get_distinguished(account=self)

        assert isinstance(self.protocol, Protocol)
        log.debug('Added account: %s', self)

    @threaded_cached_property
    def folders(self):
        # 'Top of Information Store' is a folder available in some Exchange accounts. It only contains folders
        # owned by the account.
        folders = self.root.get_folders(depth=SHALLOW)  # Start by searching top-level folders.
        for folder in folders:
            if folder.name == 'Top of Information Store':
                folders = folder.get_folders(depth=SHALLOW)
                break
        else:
            # We need to dig deeper. Get everything.
            folders = self.root.get_folders(depth=DEEP)
        mapped_folders = defaultdict(list)
        for f in folders:
            mapped_folders[f.__class__].append(f)
        return mapped_folders

    def _get_default_folder(self, fld_class):
        try:
            # Get the default folder
            log.debug('Testing default %s folder with GetFolder', fld_class.__name__)
            return fld_class.get_distinguished(account=self)
        except ErrorAccessDenied:
            # Maybe we just don't have GetFolder access? Try FindItems instead
            log.debug('Testing default %s folder with FindItem', fld_class.__name__)
            fld = fld_class(account=self)  # Creates a folder instance with default distinguished folder name
            list(fld.filter(subject='DUMMY'))  # Test if the folder exists
            return fld
        except ErrorFolderNotFound as e:
            # There's no folder named fld_class.DISTINGUISHED_FOLDER_ID. Try to guess which folder is the default.
            # Exchange makes this unnecessarily difficult.
            log.debug('Searching default %s folder in full folder list', fld_class.__name__)
            flds = self.folders[fld_class]
            if not flds:
                raise_from(ErrorFolderNotFound('No useable default %s folders' % fld_class.__name__), e)
            assert len(flds) == 1, 'Multiple possible default %s folders: %s' % (
                fld_class.__name__, [text_type(f) for f in flds])
            return flds[0]

    @threaded_cached_property
    def calendar(self):
        # If the account contains a shared calendar from a different user, that calendar will be in the folder list.
        # Attempt not to return one of those. An account may not always have a calendar called "Calendar", but a
        # Calendar folder with a localized name instead. Return that, if it's available.
        return self._get_default_folder(Calendar)

    @threaded_cached_property
    def trash(self):
        return self._get_default_folder(DeletedItems)

    @threaded_cached_property
    def drafts(self):
        return self._get_default_folder(Drafts)

    @threaded_cached_property
    def inbox(self):
        return self._get_default_folder(Inbox)

    @threaded_cached_property
    def outbox(self):
        return self._get_default_folder(Outbox)

    @threaded_cached_property
    def sent(self):
        return self._get_default_folder(SentItems)

    @threaded_cached_property
    def junk(self):
        return self._get_default_folder(JunkEmail)

    @threaded_cached_property
    def tasks(self):
        return self._get_default_folder(Tasks)

    @threaded_cached_property
    def contacts(self):
        return self._get_default_folder(Contacts)

    @threaded_cached_property
    def recoverable_items_root(self):
        return self._get_default_folder(RecoverableItemsRoot)

    @threaded_cached_property
    def recoverable_deleted_items(self):
        return self._get_default_folder(RecoverableItemsDeletions)

    @property
    def domain(self):
        return get_domain(self.primary_smtp_address)

    def export(self, items):
        """
        Return export strings of the given items

        Arguments:
        'items' is an iterable containing the Items we want to export

        Returns:
        A list strings, the exported representation of the object
        """
        is_empty, items = peek(items)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'items' is empty. Allow
            # empty 'items' and return early.
            return []
        return list(ExportItems(self).call(items))

    def upload(self, upload_data):
        """
        Adds objects retrieved from export into the given folders

        Arguments:
        'upload_data' is an iterable of tuples containing the folder we want to upload the data to and the
            string outputs of exports.

        Returns:
        A list of tuples with the new ids and changekeys

        Example:
        account.upload([(account.inbox, "AABBCC..."),
                        (account.inbox, "XXYYZZ..."),
                        (account.calendar, "ABCXYZ...")])
        -> [("idA", "changekey"), ("idB", "changekey"), ("idC", "changekey")]
        """
        is_empty, upload_data = peek(upload_data)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'upload_data' is empty.
            # Allow empty 'upload_data' and return early.
            return []
        return list(UploadItems(self).call(upload_data))

    def bulk_create(self, folder, items, message_disposition=SAVE_ONLY, send_meeting_invitations=SEND_TO_NONE):
        """
        Creates new items in 'folder'. 'items' is an iterable of Item objects. Returns a list of Item objects
        in the same order as the input. The returned Item objects only contain item_id and changekey of the created
        item, and item_id on any attachments that were also created.
        'message_disposition' is only applicable to Message items.
        'send_meeting_invitations' is only applicable to CalendarItem items.
        """
        assert message_disposition in MESSAGE_DISPOSITION_CHOICES
        assert send_meeting_invitations in SEND_MEETING_INVITATIONS_CHOICES
        if folder is not None:
            assert isinstance(folder, Folder)
            if folder.account != self:
                raise ValueError('"Folder must belong to this account')
        if message_disposition == SAVE_ONLY and folder is None:
            raise AttributeError("Folder must be supplied when in send-only mode")
        if message_disposition == SEND_AND_SAVE_COPY and folder is None:
            folder = self.sent  # 'Sent' is default EWS behaviour
        if message_disposition == SEND_ONLY and folder is not None:
            raise AttributeError("Folder must be None in send-ony mode")
        # bulk_create() on a queryset does not make sense because it returns items that have already been created
        assert not isinstance(items, QuerySet)
        log.debug(
            'Adding items for %s (folder %s, message_disposition: %s, send_meeting_invitations: %s)',
            self,
            folder,
            message_disposition,
            send_meeting_invitations,
        )
        is_empty, items = peek(items)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'items' is empty. Allow
            # empty 'items' and return early.
            return []
        return list(
            folder.item_model_from_tag(i.tag).from_xml(elem=i, account=self, folder=folder)
            for i in CreateItem(account=self).call(
                items=items,
                folder=folder,
                message_disposition=message_disposition,
                send_meeting_invitations=send_meeting_invitations,
            )
        )

    def bulk_update(self, items, conflict_resolution=AUTO_RESOLVE, message_disposition=SAVE_ONLY,
                    send_meeting_invitations_or_cancellations=SEND_TO_NONE, suppress_read_receipts=True):
        """
        Updates items in the folder. 'items' is a dict containing:

            Key: An Item object (calendar item, message, task or contact)
            Value: a list of attributes that have changed on this object

        'message_disposition' is only applicable to Message items.
        'send_meeting_invitations_or_cancellations' is only applicable to CalendarItem items.
        'suppress_read_receipts' is only supported from Exchange 2013.
        """
        assert conflict_resolution in CONFLICT_RESOLUTION_CHOICES
        assert message_disposition in MESSAGE_DISPOSITION_CHOICES
        assert send_meeting_invitations_or_cancellations in SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES
        assert suppress_read_receipts in (True, False)
        if message_disposition == SEND_ONLY:
            raise ValueError('Cannot send-only existing objects. Use SendItem service instead')
        # bulk_update() on a queryset does not make sense because there would be no opportunity to alter the items. In
        # fact, it could be dangerous if the queryset is contains an '.only()'. This would wipe out certain fields
        # entirely.
        assert not isinstance(items, QuerySet)
        log.debug(
            'Updating items for %s (conflict_resolution %s, message_disposition: %s, send_meeting_invitations: %s)',
            self,
            conflict_resolution,
            message_disposition,
            send_meeting_invitations_or_cancellations,
        )
        is_empty, items = peek(items)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'items' is empty. Allow
            # empty 'items' and return early.
            return []
        return list(
            Item.id_from_xml(i)
            for i in UpdateItem(account=self).call(
                items=items,
                conflict_resolution=conflict_resolution,
                message_disposition=message_disposition,
                send_meeting_invitations_or_cancellations=send_meeting_invitations_or_cancellations,
                suppress_read_receipts=suppress_read_receipts,
            )
        )

    def bulk_delete(self, ids, delete_type=HARD_DELETE, send_meeting_cancellations=SEND_TO_NONE,
                    affected_task_occurrences=SPECIFIED_OCCURRENCE_ONLY, suppress_read_receipts=True):
        """
        Deletes items.
        'ids' is an iterable of either (item_id, changekey) tuples or Item objects.
        'send_meeting_cancellations' is only applicable to CalendarItem items.
        'affected_task_occurrences' is only applicable for recurring Task items.
        'suppress_read_receipts' is only supported from Exchange 2013.
        """
        assert delete_type in DELETE_TYPE_CHOICES
        assert send_meeting_cancellations in SEND_MEETING_CANCELLATIONS_CHOICES
        assert affected_task_occurrences in AFFECTED_TASK_OCCURRENCES_CHOICES
        assert suppress_read_receipts in (True, False)
        log.debug(
            'Deleting items for %s (delete_type: %s, send_meeting_invitations: %s, affected_task_occurences: %s)',
            self,
            delete_type,
            send_meeting_cancellations,
            affected_task_occurrences,
        )
        # 'ids' could be an unevaluated QuerySet, e.g. if we ended up here via `some_folder.filter(...).delete()`. In
        # that case, we want to use its iterator. Otherwise, peek() will start a count() which is wasteful because we
        # need the item IDs immediately afterwards. iterator() will only do the bare minimum.
        if isinstance(ids, QuerySet):
            ids = ids.iterator()
        is_empty, ids = peek(ids)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'ids' is empty. Allow
            # empty 'ids' and return early.
            return []
        return list(DeleteItem(account=self).call(
            items=ids,
            delete_type=delete_type,
            send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences,
            suppress_read_receipts=suppress_read_receipts,
        ))

    def bulk_send(self, ids, save_copy=True, copy_to_folder=None):
        # Send existing draft messages. If requested, save a copy in 'copy_to_folder'
        if copy_to_folder and not save_copy:
            raise AttributeError("'save_copy' must be True when 'copy_to_folder' is set")
        if save_copy and not copy_to_folder:
            copy_to_folder = self.sent  # 'Sent' is default EWS behaviour
        # 'ids' could be an unevaluated QuerySet, e.g. if we ended up here via `bulk_send(some_folder.filter(...))`. In
        # that case, we want to use its iterator. Otherwise, peek() will start a count() which is wasteful because we
        # need the item IDs immediately afterwards. iterator() will only do the bare minimum.
        if isinstance(ids, QuerySet):
            ids = ids.iterator()
        is_empty, ids = peek(ids)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'ids' is empty. Allow
            # empty 'ids' and return early.
            return []
        return list(SendItem(account=self).call(items=ids, save_item_to_folder=save_copy,
                                                saved_item_folder=copy_to_folder))

    def bulk_move(self, ids, to_folder):
        # Move items to another folder. Returns new IDs for the items that were moved
        assert isinstance(to_folder, Folder)
        # 'ids' could be an unevaluated QuerySet, e.g. if we ended up here via `bulk_move(some_folder.filter(...))`. In
        # that case, we want to use its iterator. Otherwise, peek() will start a count() which is wasteful because we
        # need the item IDs immediately afterwards. iterator() will only do the bare minimum.
        if isinstance(ids, QuerySet):
            ids = ids.iterator()
        is_empty, ids = peek(ids)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'ids' is empty. Allow
            # empty 'ids' and return early.
            return []
        return list(
            Item.id_from_xml(i)
            for i in MoveItem(account=self).call(items=ids, to_folder=to_folder)
        )

    def fetch(self, ids, folder=None, only_fields=None):
        # 'folder' is used for validating only_fields
        # 'only_fields' specifies which fields to fetch, instead of all possible fields.
        validation_folder = folder or Folder  # Default to a folder type that supports all item types
        # 'ids' could be an unevaluated QuerySet, e.g. if we ended up here via `fetch(ids=some_folder.filter(...))`. In
        # that case, we want to use its iterator. Otherwise, peek() will start a count() which is wasteful because we
        # need the item IDs immediately afterwards. iterator() will only do the bare minimum.
        if isinstance(ids, QuerySet):
            ids = ids.iterator()
        is_empty, ids = peek(ids)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'ids' is empty. Allow
            # empty 'ids' and return early.
            return
        if only_fields:
            allowed_field_names = validation_folder.allowed_field_names()
            for f in only_fields:
                assert f in allowed_field_names
        else:
            only_fields = validation_folder.allowed_field_names()
        for i in GetItem(account=self).call(items=ids, folder=validation_folder, additional_fields=only_fields):
            yield validation_folder.item_model_from_tag(i.tag).from_xml(elem=i, account=self, folder=folder)

    def __str__(self):
        txt = '%s' % self.primary_smtp_address
        if self.fullname:
            txt += ' (%s)' % self.fullname
        return txt
