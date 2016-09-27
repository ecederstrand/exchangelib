from logging import getLogger

from .autodiscover import discover
from .credentials import DELEGATE, IMPERSONATION
from .errors import ErrorFolderNotFound, ErrorAccessDenied
from .folders import Root, Calendar, DeletedItems, Drafts, Inbox, Outbox, SentItems, JunkEmail, Tasks, Contacts, \
    RecoverableItemsRoot, RecoverableItemsDeletions, Item, SHALLOW, DEEP, WELLKNOWN_FOLDERS, HARD_DELETE, \
    AUTO_RESOLVE, SEND_TO_NONE, SAVE_ONLY, SPECIFIED_OCCURRENCE_ONLY, DELETE_TYPE_CHOICES, \
    CONFLICT_RESOLUTION_CHOICES, SEND_MEETING_CANCELLATIONS_CHOICES, AFFECTED_TASK_OCCURRENCES_CHOICES, \
    MESSAGE_DISPOSITION_CHOICES, SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES, ItemId
from .services import ExportItems, UploadItems
from .protocol import Protocol
from .services import DeleteItem, UpdateItem
from .util import get_domain, peek

log = getLogger(__name__)


class Account:
    """
    Models an Exchange server user account. The primary key for an account is its PrimarySMTPAddress
    """
    def __init__(self, primary_smtp_address, fullname=None, access_type=None, autodiscover=False, credentials=None,
                 config=None, verify_ssl=True, locale='da_DK'):
        if '@' not in primary_smtp_address:
            raise ValueError("primary_smtp_address '%s' is not an email address" % primary_smtp_address)
        self.primary_smtp_address = primary_smtp_address
        self.fullname = fullname
        self.locale = locale
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

    def export(self, ids):
        return [(id_, export) for id_, export in zip(ids, ExportItems(self.protocol).call(self, ids))]

    def upload(self, data, folders=None):
        if folders is None:
            # Assume folders is already alongside data already
            upload_ids = UploadItems(self.protocol).call(self, data)

        try:
            # Try assuming folders are iterable, and pair them with the data
            merged_data = ((folder, data_str) for folder, data_str in zip(folders, data))
        except TypeError:
            # If it raises a Type error it means we couldn't iterate over folders
            # Assume we only have one folder that we are applying to all data
            merged_data = ((folders, data_str) for data_str in data)
            upload_ids = UploadItems(self.protocol).call(self, merged_data)
        else:
            upload_ids = UploadItems(self.protocol).call(self, merged_data)

        return [ItemId(id=item_id, changekey=change_key) for item_id, change_key in upload_ids]

    @property
    def folders(self):
        if hasattr(self, '_folders'):
            return self._folders
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
        self._folders = dict((m, []) for m in WELLKNOWN_FOLDERS.values())
        for f in folders:
            self._folders[f.__class__].append(f)
        return self._folders

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

    @property
    def calendar(self):
        if hasattr(self, '_calendar'):
            return self._calendar
        # If the account contains a shared calendar from a different user, that calendar will be in the folder list.
        # Attempt not to return one of those. An account may not always have a calendar called "Calendar", but a
        # Calendar folder with a localized name instead. Return that, if it's available.
        self._calendar = self._get_default_folder(Calendar)
        return self._calendar

    @property
    def trash(self):
        if hasattr(self, '_trash'):
            return self._trash
        self._trash = self._get_default_folder(DeletedItems)
        return self._trash

    @property
    def drafts(self):
        if hasattr(self, '_drafts'):
            return self._drafts
        self._drafts = self._get_default_folder(Drafts)
        return self._drafts

    @property
    def inbox(self):
        if hasattr(self, '_inbox'):
            return self._inbox
        self._inbox = self._get_default_folder(Inbox)
        return self._inbox

    @property
    def outbox(self):
        if hasattr(self, '_outbox'):
            return self._outbox
        self._outbox = self._get_default_folder(Outbox)
        return self._outbox

    @property
    def sent(self):
        if hasattr(self, '_sent'):
            return self._sent
        self._sent = self._get_default_folder(SentItems)
        return self._sent

    @property
    def junk(self):
        if hasattr(self, '_junk'):
            return self._junk
        self._junk = self._get_default_folder(JunkEmail)
        return self._junk

    @property
    def tasks(self):
        if hasattr(self, '_tasks'):
            return self._tasks
        self._tasks = self._get_default_folder(Tasks)
        return self._tasks

    @property
    def contacts(self):
        if hasattr(self, '_contacts'):
            return self._contacts
        self._contacts = self._get_default_folder(Contacts)
        return self._contacts

    @property
    def recoverable_items_root(self):
        if hasattr(self, '_recoverable_items_root'):
            return self._recoverable_items_root
        self._recoverable_items_root = self._get_default_folder(RecoverableItemsRoot)
        return self._recoverable_items_root

    @property
    def recoverable_deleted_items(self):
        if hasattr(self, '_recoverable_deleted_items'):
            return self._recoverable_deleted_items
        self._recoverable_deleted_items = self._get_default_folder(RecoverableItemsDeletions)
        return self._recoverable_deleted_items

    @property
    def domain(self):
        return get_domain(self.primary_smtp_address)

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

    def __str__(self):
        txt = '%s' % self.primary_smtp_address
        if self.fullname:
            txt += ' (%s)' % self.fullname
        return txt
