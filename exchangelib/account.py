from logging import getLogger
from locale import getlocale

from cached_property import threaded_cached_property

from .autodiscover import discover
from .credentials import DELEGATE, IMPERSONATION
from .errors import ErrorFolderNotFound, ErrorAccessDenied
from .folders import Root, Calendar, DeletedItems, Drafts, Inbox, Outbox, SentItems, JunkEmail, Tasks, Contacts, \
    RecoverableItemsRoot, RecoverableItemsDeletions, Folder, Item, SHALLOW, DEEP, WELLKNOWN_FOLDERS, HARD_DELETE, \
    AUTO_RESOLVE, SEND_TO_NONE, SAVE_ONLY, SEND_AND_SAVE_COPY, SEND_ONLY, SPECIFIED_OCCURRENCE_ONLY, \
    DELETE_TYPE_CHOICES, MESSAGE_DISPOSITION_CHOICES, CONFLICT_RESOLUTION_CHOICES, AFFECTED_TASK_OCCURRENCES_CHOICES, \
    SEND_MEETING_INVITATIONS_CHOICES, SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES, \
    SEND_MEETING_CANCELLATIONS_CHOICES, ItemId
from .services import ExportItems, UploadItems
from .protocol import Protocol
from .services import GetItem, CreateItem, UpdateItem, DeleteItem, MoveItem, SendItem
from .util import get_domain, peek

log = getLogger(__name__)


class Account:
    """
    Models an Exchange server user account. The primary key for an account is its PrimarySMTPAddress
    """
    def __init__(self, primary_smtp_address, fullname=None, access_type=None, autodiscover=False, credentials=None,
                 config=None, verify_ssl=True, locale=None):
        if '@' not in primary_smtp_address:
            raise ValueError("primary_smtp_address '%s' is not an email address" % primary_smtp_address)
        self.primary_smtp_address = primary_smtp_address
        self.fullname = fullname
        self.locale = locale or getlocale()
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
        has_tois = False
        for folder in folders:
            if folder.name == 'Top of Information Store':
                has_tois = True
                folders = folder.get_folders(depth=SHALLOW)
                break
        if not has_tois:
            # We need to dig deeper. Get everything.
            folders = self.root.get_folders(depth=DEEP)
        _folders = dict((m, []) for m in WELLKNOWN_FOLDERS.values())
        for f in folders:
            _folders[f.__class__].append(f)
        return _folders

    def _get_default_folder(self, fld_class):
        try:
            # Get the default folder
            log.debug('Testing default %s folder with GetFolder', fld_class.__name__)
            return fld_class.get_distinguished(account=self)
        except ErrorAccessDenied:
            # Maybe we just don't have GetFolder access? Try FindItems instead
            log.debug('Testing default %s folder with FindItem', fld_class.__name__)
            fld = fld_class(self)
            fld.filter(subject='DUMMY')
            return fld
        except ErrorFolderNotFound as e:
            # There's no folder named fld_class.DISTINGUISHED_FOLDER_ID. Try to guess which folder is the default.
            # Exchange makes this unnecessarily difficult.
            log.debug('Searching default %s folder in full folder list', fld_class.__name__)
            flds = []
            for folder in self.folders[fld_class]:
                # Apparently default folder names can be renamed to a set of localized names using a PowerShell command:
                # https://technet.microsoft.com/da-dk/library/dd351103(v=exchg.160).aspx
                #
                # Search for a folder wth a localized name. This is a hack because I can't find a way to get the
                # default Calendar, Inbox, etc. folders without looking at the folder name, which could be localized.
                #
                # TODO: fld_class.LOCALIZED_NAMES is most definitely neither complete nor authoritative
                if folder.name.title() in fld_class.LOCALIZED_NAMES.get(self.locale, []):
                    flds.append(folder)
            if not flds:
                # There was no folder with a localized name. Use the distinguished folder instead.
                for folder in self.folders[fld_class]:
                    if folder.is_distinguished:
                        flds.append(folder)
            if not flds:
                raise ErrorFolderNotFound('No useable default %s folders' % fld_class.__name__) from e
            assert len(flds) == 1, 'Multiple possible default %s folders: %s' % (
                fld_class.__name__, [str(f) for f in flds])
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

    def export(self, ids):
        """
        Return export strings of the given items

        Arguments:
        'ids' is an iterable containing ItemId objects for what we want to export

        Returns:
        A list of tuples with two elements:
            0: An ItemId, the id of the object
            1: A string, the exported representation of the object
        """
        return [(id_, export) for id_, export in zip(ids, ExportItems(self).call(ids))]

    def upload(self, data, folders):
        """
        Adds objects retrieved from export into the given folders

        Arguments:
        'data' is an iterable containing the string outputs of exports
        'folders' is an equal lengthed iterable containing the folder that each item is to be inserted in

        Returns:
        A list of ItemIds of the new items inserted

        Example:
        account.upload(["AABBCC...", "XXYYZZ...", "ABCXYZ..."],
                       [account.inbox, account.inbox, account.calendar])
        -> [ItemId(...), ItemId(...), ItemId(...)]
        """
        merged_data = ((folder, data_str) for folder, data_str in zip(folders, data))
        upload_ids = UploadItems(self).call(merged_data)

        return [ItemId(id=item_id, changekey=change_key) for item_id, change_key in upload_ids]

    def bulk_create(self, folder, items, message_disposition=SAVE_ONLY, send_meeting_invitations=SEND_TO_NONE):
        """
        Creates new items in the folder. 'items' is an iterable of Item objects. Returns a list of (id, changekey)
        tuples in the same order as the input.
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
        return list(map(
            Item.id_from_xml,
            CreateItem(account=self).call(
                items=items,
                folder=folder,
                message_disposition=message_disposition,
                send_meeting_invitations=send_meeting_invitations,
            )
        ))

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
        return list(map(
            Item.id_from_xml,
            UpdateItem(account=self).call(
                items=items,
                conflict_resolution=conflict_resolution,
                message_disposition=message_disposition,
                send_meeting_invitations_or_cancellations=send_meeting_invitations_or_cancellations,
                suppress_read_receipts=suppress_read_receipts,
            )
        ))

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
        is_empty, ids = peek(ids)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'items' is empty. Allow
            # empty 'items' and return early.
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
        return list(SendItem(account=self).call(items=ids, save_item_to_folder=save_copy,
                                                saved_item_folder=copy_to_folder))

    def bulk_move(self, ids, to_folder):
        # Move items to another folder. Returns new IDs for the items that were moved
        assert isinstance(to_folder, Folder)
        return list(map(
            Item.id_from_xml,
            MoveItem(account=self).call(items=ids, to_folder=to_folder)
        ))

    def fetch(self, ids, folder=None, only_fields=None):
        # 'folder' is used for validating only_fields
        # 'only_fields' specifies which fields to fetch, instead of all possible fields.
        validation_folder = folder or Folder  # Use a folder type that supports all item types
        is_empty, ids = peek(ids)
        if is_empty:
            # We accept generators, so it's not always convenient for caller to know up-front if 'items' is empty. Allow
            # empty 'items' and return early.
            return []
        if only_fields:
            allowed_field_names = validation_folder.allowed_field_names()
            for f in only_fields:
                assert f in allowed_field_names
        else:
            only_fields = validation_folder.allowed_field_names()
        items = GetItem(account=self).call(items=ids, folder=validation_folder, additional_fields=only_fields)
        return list(map(
            lambda i: validation_folder.item_model_from_tag(i.tag).from_xml(elem=i, account=self, folder=folder),
            items
        ))

    def __str__(self):
        txt = '%s' % self.primary_smtp_address
        if self.fullname:
            txt += ' (%s)' % self.fullname
        return txt
