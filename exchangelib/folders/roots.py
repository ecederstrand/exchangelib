import logging
from contextlib import suppress
from threading import Lock

from ..errors import ErrorAccessDenied, ErrorFolderNotFound, ErrorInvalidOperation
from ..fields import EffectiveRightsField
from ..properties import DistinguishedFolderId, EWSMeta, Mailbox
from ..version import EXCHANGE_2007_SP1, EXCHANGE_2010_SP1
from .base import BaseFolder
from .collections import FolderCollection
from .known_folders import (
    MISC_FOLDERS,
    NON_DELETABLE_FOLDERS,
    WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT,
    WELLKNOWN_FOLDERS_IN_ROOT,
    MsgFolderRoot,
)
from .queryset import MISSING_FOLDER_ERRORS, SHALLOW, SingleFolderQuerySet

log = logging.getLogger(__name__)


class RootOfHierarchy(BaseFolder, metaclass=EWSMeta):
    """Base class for folders that implement the root of a folder hierarchy."""

    # A list of wellknown, or "distinguished", folders that are belong in this folder hierarchy. See
    # https://docs.microsoft.com/en-us/dotnet/api/microsoft.exchange.webservices.data.wellknownfoldername
    # and https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/distinguishedfolderid
    # 'RootOfHierarchy' subclasses must not be in this list.
    WELLKNOWN_FOLDERS = []

    # This folder type also has 'folder:PermissionSet' on some server versions, but requesting it sometimes causes
    # 'ErrorAccessDenied', as reported by some users. Ignore it entirely for root folders - it's usefulness is
    # deemed minimal at best.
    effective_rights = EffectiveRightsField(
        field_uri="folder:EffectiveRights", is_read_only=True, supported_from=EXCHANGE_2007_SP1
    )

    __slots__ = "_account", "_subfolders", "_subfolders_lock"

    # A special folder that acts as the top of a folder hierarchy. Finds and caches sub-folders at arbitrary depth.
    def __init__(self, **kwargs):
        self._account = kwargs.pop("account", None)  # A pointer back to the account holding the folder hierarchy
        super().__init__(**kwargs)
        self._subfolders = None  # See self._folders_map()
        self._subfolders_lock = Lock()

    @property
    def account(self):
        return self._account

    @property
    def root(self):
        return self

    @property
    def parent(self):
        return None

    @classmethod
    def register(cls, *args, **kwargs):
        if cls is not RootOfHierarchy:
            raise TypeError("For folder roots, custom fields must be registered on the RootOfHierarchy class")
        return super().register(*args, **kwargs)

    @classmethod
    def deregister(cls, *args, **kwargs):
        if cls is not RootOfHierarchy:
            raise TypeError("For folder roots, custom fields must be registered on the RootOfHierarchy class")
        return super().deregister(*args, **kwargs)

    def get_folder(self, folder):
        if not folder.id:
            raise ValueError("'folder' must have an ID")
        return self._folders_map.get(folder.id)

    def add_folder(self, folder):
        if not folder.id:
            raise ValueError("'folder' must have an ID")
        self._folders_map[folder.id] = folder

    def update_folder(self, folder):
        if not folder.id:
            raise ValueError("'folder' must have an ID")
        self._folders_map[folder.id] = folder

    def remove_folder(self, folder):
        if not folder.id:
            raise ValueError("'folder' must have an ID")
        with suppress(KeyError):
            del self._folders_map[folder.id]

    def clear_cache(self):
        with self._subfolders_lock:
            self._subfolders = None

    def get_children(self, folder):
        for f in self._folders_map.values():
            if not f.parent:
                continue
            if f.parent.id == folder.id:
                yield f

    @classmethod
    def get_distinguished(cls, account):
        """Get the distinguished folder for this folder class.

        :param account:
        """
        if not cls.DISTINGUISHED_FOLDER_ID:
            raise ValueError(f"Class {cls} must have a DISTINGUISHED_FOLDER_ID value")
        try:
            return cls.resolve(
                account=account,
                folder=DistinguishedFolderId(
                    id=cls.DISTINGUISHED_FOLDER_ID,
                    mailbox=Mailbox(email_address=account.primary_smtp_address),
                ),
            )
        except MISSING_FOLDER_ERRORS:
            raise ErrorFolderNotFound(f"Could not find distinguished folder {cls.DISTINGUISHED_FOLDER_ID}")

    def get_default_folder(self, folder_cls):
        """Return the distinguished folder instance of type folder_cls belonging to this account. If no distinguished
        folder was found, try as best we can to return the default folder of type 'folder_cls'
        """
        if not folder_cls.DISTINGUISHED_FOLDER_ID:
            raise ValueError(f"'folder_cls' {folder_cls} must have a DISTINGUISHED_FOLDER_ID value")
        # Use cached distinguished folder instance, but only if cache has already been prepped. This is an optimization
        # for accessing e.g. 'account.contacts' without fetching all folders of the account.
        if self._subfolders is not None:
            for f in self._folders_map.values():
                # Require exact class, to not match subclasses, e.g. RecipientCache instead of Contacts
                if f.__class__ == folder_cls and f.is_distinguished:
                    log.debug("Found cached distinguished %s folder", folder_cls)
                    return f
        try:
            log.debug("Requesting distinguished %s folder explicitly", folder_cls)
            return folder_cls.get_distinguished(account=self.account)
        except ErrorAccessDenied:
            # Maybe we just don't have GetFolder access? Try FindItem instead
            log.debug("Testing default %s folder with FindItem", folder_cls)
            fld = folder_cls(
                root=self,
                _distinguished_id=DistinguishedFolderId(
                    id=folder_cls.DISTINGUISHED_FOLDER_ID,
                    mailbox=Mailbox(email_address=self.account.primary_smtp_address),
                ),
            )
            fld.test_access()
            return self._folders_map.get(fld.id, fld)  # Use cached instance if available
        except MISSING_FOLDER_ERRORS:
            # The Exchange server does not return a distinguished folder of this type
            pass
        raise ErrorFolderNotFound(f"No usable default {folder_cls} folders")

    @property
    def _folders_map(self):
        if self._subfolders is not None:
            return self._subfolders

        with self._subfolders_lock:
            # Map root, and all sub-folders of root, at arbitrary depth by folder ID. First get distinguished folders,
            # so we are sure to apply the correct Folder class, then fetch all sub-folders of this root.
            folders_map = {self.id: self}
            distinguished_folders = [
                DistinguishedFolderId(
                    id=cls.DISTINGUISHED_FOLDER_ID,
                    mailbox=Mailbox(email_address=self.account.primary_smtp_address),
                )
                for cls in self.WELLKNOWN_FOLDERS
                if cls.get_folder_allowed and cls.supports_version(self.account.version)
            ]
            for f in FolderCollection(account=self.account, folders=distinguished_folders).resolve():
                if isinstance(f, MISSING_FOLDER_ERRORS):
                    # This is just a distinguished folder the server does not have
                    continue
                if isinstance(f, ErrorInvalidOperation):
                    # This is probably a distinguished folder the server does not have. We previously tested the exact
                    # error message (f.value), but some Exchange servers return localized error messages, so that's not
                    # possible to do reliably.
                    continue
                if isinstance(f, ErrorAccessDenied):
                    # We may not have GetFolder access, either to this folder or at all
                    continue
                if isinstance(f, Exception):
                    raise f
                folders_map[f.id] = f
            for f in (
                SingleFolderQuerySet(account=self.account, folder=self).depth(self.DEFAULT_FOLDER_TRAVERSAL_DEPTH).all()
            ):
                if isinstance(f, ErrorAccessDenied):
                    # We may not have FindFolder access, or GetFolder access, either to this folder or at all
                    continue
                if isinstance(f, MISSING_FOLDER_ERRORS):
                    # We were unlucky. The folder disappeared between the FindFolder and the GetFolder calls
                    continue
                if isinstance(f, Exception):
                    raise f
                if f.id in folders_map:
                    # Already exists. Probably a distinguished folder
                    continue
                folders_map[f.id] = f
            self._subfolders = folders_map
            return folders_map

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = cls._kwargs_from_elem(elem=elem, account=account)
        cls._clear(elem)
        return cls(account=account, **kwargs)

    @classmethod
    def folder_cls_from_folder_name(cls, folder_name, folder_class, locale):
        """Return the folder class that matches a localized folder name. Take into account the 'folder_class' of the
        folder, to not identify an 'IPF.Note' folder as a 'Calendar' class just because it's called e.g. 'Kalender' and
        the locale is 'da_DK'.

        Some folders, e.g. `System`, don't define a `folder_class`. For these folders, we match on localized folder name
        if the folder class does not have its 'CONTAINER_CLASS' set.

        :param folder_name:
        :param folder_class:
        :param locale: a string, e.g. 'da_DK'
        """
        for folder_cls in cls.WELLKNOWN_FOLDERS + NON_DELETABLE_FOLDERS + MISC_FOLDERS:
            if folder_cls.CONTAINER_CLASS != folder_class:
                continue
            if folder_name.lower() not in folder_cls.localized_names(locale):
                continue
            return folder_cls
        raise KeyError()

    def __getstate__(self):
        # The lock cannot be pickled
        state = {k: getattr(self, k) for k in self._slots_keys}
        del state["_subfolders_lock"]
        return state

    def __setstate__(self, state):
        # Restore the lock
        for k in self._slots_keys:
            setattr(self, k, state.get(k))
        self._subfolders_lock = Lock()

    def __repr__(self):
        # Let's not create an infinite loop when printing self.root
        return self.__class__.__name__ + repr(
            (
                self.account,
                "[self]",
                self.name,
                self.total_count,
                self.unread_count,
                self.child_folder_count,
                self.folder_class,
                self.id,
                self.changekey,
            )
        )


class Root(RootOfHierarchy):
    """The root of the standard folder hierarchy."""

    DISTINGUISHED_FOLDER_ID = "root"
    WELLKNOWN_FOLDERS = WELLKNOWN_FOLDERS_IN_ROOT

    @property
    def tois(self):
        # 'Top of Information Store' is a folder available in some Exchange accounts. It usually contains the
        # distinguished folders belonging to the account (inbox, calendar, trash etc.).
        return self.get_default_folder(MsgFolderRoot)

    def get_default_folder(self, folder_cls):
        with suppress(MISSING_FOLDER_ERRORS):
            return super().get_default_folder(folder_cls)

        # Try to pick a suitable default folder. we do this by:
        #  1. Searching the full folder list for a folder with the distinguished folder name
        #  2. Searching TOIS for a direct child folder of the same type that is marked as distinguished
        #  3. Searching TOIS for a direct child folder of the same type that has a localized name
        #  4. Searching root for a direct child folder of the same type that is marked as distinguished
        #  5. Searching root for a direct child folder of the same type that has a localized name
        log.debug("Searching default %s folder in full folder list", folder_cls)

        for f in self._folders_map.values():
            # Require exact type, to avoid matching with subclasses (e.g. RecipientCache and Contacts)
            if f.__class__ == folder_cls and f.has_distinguished_name:
                log.debug("Found cached %s folder with default distinguished name", folder_cls)
                return f

        # Try direct children of TOIS first, unless we're trying to get the TOIS folder
        if folder_cls != MsgFolderRoot:
            with suppress(MISSING_FOLDER_ERRORS):
                return self._get_candidate(folder_cls=folder_cls, folder_coll=self.tois.children)
            # No candidates, or TOIS does not exist, or we don't have access to TOIS

        # Finally, try direct children of root
        return self._get_candidate(folder_cls=folder_cls, folder_coll=self.children)

    def _get_candidate(self, folder_cls, folder_coll):
        # Look for a single useful folder of type folder_cls in folder_coll
        same_type = [f for f in folder_coll if f.__class__ == folder_cls]
        are_distinguished = [f for f in same_type if f.is_distinguished]
        if are_distinguished:
            candidates = are_distinguished
        else:
            candidates = [f for f in same_type if f.name.lower() in folder_cls.localized_names(self.account.locale)]
        if not candidates:
            raise ErrorFolderNotFound(f"No usable default {folder_cls} folders")
        if len(candidates) > 1:
            raise ValueError(f"Multiple possible default {folder_cls} folders: {[f.name for f in candidates]}")
        candidate = candidates[0]
        if candidate.is_distinguished:
            log.debug("Found distinguished %s folder", folder_cls)
        else:
            log.debug("Found %s folder with localized name %s", folder_cls, candidate.name)
        return candidate


class PublicFoldersRoot(RootOfHierarchy):
    """The root of the public folder hierarchy. Not available on all mailboxes."""

    DISTINGUISHED_FOLDER_ID = "publicfoldersroot"
    DEFAULT_FOLDER_TRAVERSAL_DEPTH = SHALLOW
    supported_from = EXCHANGE_2007_SP1

    def get_children(self, folder):
        # EWS does not allow deep traversal of public folders, so self._folders_map will only populate the top-level
        # subfolders. To traverse public folders at arbitrary depth, we need to get child folders on demand.

        # Let's check if this folder already has any cached children. If so, assume we can just return those.
        children = list(super().get_children(folder=folder))
        if children:
            # Return a generator like our parent does
            yield from children
            return

        # Also return early if the server told us that there are no child folders.
        if folder.child_folder_count == 0:
            return

        children_map = {}
        with suppress(ErrorAccessDenied):
            for f in (
                SingleFolderQuerySet(account=self.account, folder=folder)
                .depth(self.DEFAULT_FOLDER_TRAVERSAL_DEPTH)
                .all()
            ):
                if isinstance(f, MISSING_FOLDER_ERRORS):
                    # We were unlucky. The folder disappeared between the FindFolder and the GetFolder calls
                    continue
                if isinstance(f, Exception):
                    raise f
                children_map[f.id] = f

        # Let's update the cache atomically, to avoid partial reads of the cache.
        with self._subfolders_lock:
            self._subfolders.update(children_map)

        # Child folders have been cached now. Try super().get_children() again.
        yield from super().get_children(folder=folder)


class ArchiveRoot(RootOfHierarchy):
    """The root of the archive folders hierarchy. Not available on all mailboxes."""

    DISTINGUISHED_FOLDER_ID = "archiveroot"
    supported_from = EXCHANGE_2010_SP1
    WELLKNOWN_FOLDERS = WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT
