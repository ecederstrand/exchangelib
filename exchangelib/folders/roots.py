from __future__ import unicode_literals

import logging

from future.utils import python_2_unicode_compatible
from six import text_type

from ..errors import ErrorAccessDenied, ErrorFolderNotFound, ErrorNoPublicFolderReplicaAvailable, ErrorItemNotFound, \
    ErrorInvalidOperation
from ..fields import PermissionSetField, EffectiveRightsField
from ..version import EXCHANGE_2007_SP1, EXCHANGE_2010_SP1, EXCHANGE_2016
from .collections import FolderCollection
from .base import BaseFolder
from .known_folders import MsgFolderRoot, NON_DELETEABLE_FOLDERS, WELLKNOWN_FOLDERS_IN_ROOT, \
    WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT
from .queryset import SingleFolderQuerySet, SHALLOW, DEEP

log = logging.getLogger(__name__)


@python_2_unicode_compatible
class RootOfHierarchy(BaseFolder):
    """Base class for folders that implement the root of a folder hierarchy"""

    # A list of wellknown, or "distinguished", folders that are belong in this folder hierarchy. See
    # https://docs.microsoft.com/en-us/dotnet/api/microsoft.exchange.webservices.data.wellknownfoldername
    # and https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/distinguishedfolderid
    # 'RootOfHierarchy' subclasses must not be in this list.
    WELLKNOWN_FOLDERS = []
    TRAVERSAL_DEPTH = DEEP

    LOCAL_FIELDS = [
        PermissionSetField('permission_set', field_uri='folder:PermissionSet', supported_from=EXCHANGE_2007_SP1,
                           deprecated_from=EXCHANGE_2016),
        EffectiveRightsField('effective_rights', field_uri='folder:EffectiveRights', is_read_only=True,
                             supported_from=EXCHANGE_2007_SP1),
    ]
    FIELDS = BaseFolder.FIELDS + LOCAL_FIELDS
    __slots__ = tuple(f.name for f in LOCAL_FIELDS) + ('_account', '_subfolders')

    # A special folder that acts as the top of a folder hierarchy. Finds and caches subfolders at arbitrary depth.
    def __init__(self, **kwargs):
        self._account = kwargs.pop('account', None)  # A pointer back to the account holding the folder hierarchy
        super(RootOfHierarchy, self).__init__(**kwargs)
        self._subfolders = None  # See self._folders_map()

    @property
    def account(self):
        return self._account

    @property
    def root(self):
        return self

    @property
    def parent(self):
        return None

    def refresh(self):
        self._subfolders = None
        super(RootOfHierarchy, self).refresh()

    def get_folder(self, folder_id):
        return self._folders_map.get(folder_id, None)

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
        try:
            del self._folders_map[folder.id]
        except KeyError:
            pass

    def clear_cache(self):
        self._subfolders = None

    def get_children(self, folder):
        for f in self._folders_map.values():
            if not f.parent:
                continue
            if f.parent.id == folder.id:
                yield f

    @classmethod
    def get_distinguished(cls, account):
        """Gets the distinguished folder for this folder class"""
        if not cls.DISTINGUISHED_FOLDER_ID:
            raise ValueError('Class %s must have a DISTINGUISHED_FOLDER_ID value' % cls)
        try:
            return cls.resolve(
                account=account,
                folder=cls(account=account, name=cls.DISTINGUISHED_FOLDER_ID, is_distinguished=True)
            )
        except ErrorFolderNotFound:
            raise ErrorFolderNotFound('Could not find distinguished folder %s' % cls.DISTINGUISHED_FOLDER_ID)

    def get_default_folder(self, folder_cls):
        # Returns the distinguished folder instance of type folder_cls belonging to this account. If no distinguished
        # folder was found, try as best we can to return the default folder of type 'folder_cls'
        if not folder_cls.DISTINGUISHED_FOLDER_ID:
            raise ValueError("'folder_cls' %s must have a DISTINGUISHED_FOLDER_ID value" % folder_cls)
        # Use cached distinguished folder instance, but only if cache has already been prepped. This is an optimization
        # for accessing e.g. 'account.contacts' without fetching all folders of the account.
        if self._subfolders:
            for f in self._folders_map.values():
                # Require exact class, to not match subclasses, e.g. RecipientCache instead of Contacts
                if f.__class__ == folder_cls and f.is_distinguished:
                    log.debug('Found cached distinguished %s folder', folder_cls)
                    return f
        try:
            log.debug('Requesting distinguished %s folder explicitly', folder_cls)
            return folder_cls.get_distinguished(root=self)
        except ErrorAccessDenied:
            # Maybe we just don't have GetFolder access? Try FindItems instead
            log.debug('Testing default %s folder with FindItem', folder_cls)
            fld = folder_cls(root=self, name=folder_cls.DISTINGUISHED_FOLDER_ID, is_distinguished=True)
            fld.test_access()
            return self._folders_map.get(fld.id, fld)  # Use cached instance if available
        except ErrorFolderNotFound:
            # The Exchange server does not return a distinguished folder of this type
            pass
        raise ErrorFolderNotFound('No useable default %s folders' % folder_cls)

    @property
    def _folders_map(self):
        if self._subfolders is not None:
            return self._subfolders

        # Map root, and all subfolders of root, at arbitrary depth by folder ID. First get distinguished folders, so we
        # are sure to apply the correct Folder class, then fetch all subfolders of this root.
        folders_map = {self.id: self}
        distinguished_folders = [
            cls(root=self, name=cls.DISTINGUISHED_FOLDER_ID, is_distinguished=True)
            for cls in self.WELLKNOWN_FOLDERS
            if cls.get_folder_allowed and cls.supports_version(self.account.version)
        ]
        for f in FolderCollection(account=self.account, folders=distinguished_folders).resolve():
            if isinstance(f, (ErrorFolderNotFound, ErrorNoPublicFolderReplicaAvailable)):
                # This is just a distinguished folder the server does not have
                continue
            if isinstance(f, ErrorInvalidOperation):
                # This is probably a distinguished folder the server does not have. We previously tested the exact
                # error message (f.value), but some Exchange servers return localized error messages, so that's not
                # possible to do reliably.
                continue
            if isinstance(f, ErrorItemNotFound):
                # Another way of telling us that this is a distinguished folder the server does not have
                continue
            if isinstance(f, ErrorAccessDenied):
                # We may not have GetFolder access, either to this folder or at all
                continue
            if isinstance(f, Exception):
                raise f
            folders_map[f.id] = f
        for f in SingleFolderQuerySet(account=self.account, folder=self).depth(self.TRAVERSAL_DEPTH).all():
            if isinstance(f, ErrorAccessDenied):
                # We may not have FindFolder access, or GetFolder access, either to this folder or at all
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
    def folder_cls_from_folder_name(cls, folder_name, locale):
        """Returns the folder class that matches a localized folder name.

        locale is a string, e.g. 'da_DK'
        """
        for folder_cls in cls.WELLKNOWN_FOLDERS + NON_DELETEABLE_FOLDERS:
            if folder_name.lower() in folder_cls.localized_names(locale):
                return folder_cls
        raise KeyError()

    def __repr__(self):
        # Let's not create an infinite loop when printing self.root
        return self.__class__.__name__ + \
               repr((self.account, '[self]', self.name, self.total_count, self.unread_count, self.child_folder_count,
                     self.folder_class, self.id, self.changekey))


class Root(RootOfHierarchy):
    """The root of the standard folder hierarchy"""
    DISTINGUISHED_FOLDER_ID = 'root'
    WELLKNOWN_FOLDERS = WELLKNOWN_FOLDERS_IN_ROOT
    __slots__ = tuple()

    @property
    def tois(self):
        # 'Top of Information Store' is a folder available in some Exchange accounts. It usually contains the
        # distinguished folders belonging to the account (inbox, calendar, trash etc.).
        return self.get_default_folder(MsgFolderRoot)

    def get_default_folder(self, folder_cls):
        try:
            return super(Root, self).get_default_folder(folder_cls)
        except ErrorFolderNotFound:
            pass

        # Try to pick a suitable default folder. we do this by:
        #  1. Searching the full folder list for a folder with the distinguished folder name
        #  2. Searching TOIS for a direct child folder of the same type that is marked as distinguished
        #  3. Searching TOIS for a direct child folder of the same type that is has a localized name
        #  4. Searching root for a direct child folder of the same type that is marked as distinguished
        #  5. Searching root for a direct child folder of the same type that is has a localized name
        log.debug('Searching default %s folder in full folder list', folder_cls)

        for f in self._folders_map.values():
            # Require exact class to not match e.g. RecipientCache instead of Contacts
            if f.__class__ == folder_cls and f.has_distinguished_name:
                log.debug('Found cached %s folder with default distinguished name', folder_cls)
                return f

        # Try direct children of TOIS first. TOIS might not exist.
        try:
            return self._get_candidate(folder_cls=folder_cls, folder_coll=self.tois.children)
        except ErrorFolderNotFound:
            # No candidates, or TOIS does ot exist
            pass

        # No candidates in TOIS. Try direct children of root.
        return self._get_candidate(folder_cls=folder_cls, folder_coll=self.children)

    def _get_candidate(self, folder_cls, folder_coll):
        # Get a single the folder of the same type in folder_coll
        same_type = [f for f in folder_coll if f.__class__ == folder_cls]
        are_distinguished = [f for f in same_type if f.is_distinguished]
        if are_distinguished:
            candidates = are_distinguished
        else:
            candidates = [f for f in same_type if f.name.lower() in folder_cls.localized_names(self.account.locale)]
        if candidates:
            if len(candidates) > 1:
                raise ValueError(
                    'Multiple possible default %s folders: %s' % (folder_cls, [text_type(f.name) for f in candidates])
                )
            if candidates[0].is_distinguished:
                log.debug('Found cached distinguished %s folder', folder_cls)
            else:
                log.debug('Found cached %s folder with localized name', folder_cls)
            return candidates[0]
        raise ErrorFolderNotFound('No useable default %s folders' % folder_cls)


class PublicFoldersRoot(RootOfHierarchy):
    """The root of the public folders hierarchy. Not available on all mailboxes"""
    DISTINGUISHED_FOLDER_ID = 'publicfoldersroot'
    TRAVERSAL_DEPTH = SHALLOW
    supported_from = EXCHANGE_2007_SP1
    __slots__ = tuple()

    def get_children(self, folder):
        # EWS does not allow deep traversal of public folders, so self._folders_map will only populate the top-level
        # subfolders. To traverse public folders at arbitrary depth, we need to get child folders on demand.

        # Let's check if this folder already has any cached children. If so, assume we can just return those.
        children = list(super(PublicFoldersRoot, self).get_children(folder=folder))
        if children:
            # Return a generator like our parent does
            for f in children:
                yield f
            return

        # Also return early if the server told us that there are no child folders.
        if folder.child_folder_count == 0:
            return

        children_map = {}
        try:
            for f in SingleFolderQuerySet(account=self.account, folder=folder).depth(depth=self.TRAVERSAL_DEPTH).all():
                if isinstance(f, Exception):
                    raise f
                children_map[f.id] = f
        except ErrorAccessDenied:
            # No access to this folder
            pass

        # Let's update the cache atomically, to avoid partial reads of the cache.
        self._subfolders.update(children_map)

        # Child folders have been cached now. Try super().get_children() again.
        for f in super(PublicFoldersRoot, self).get_children(folder=folder):
            yield f


class ArchiveRoot(RootOfHierarchy):
    """The root of the archive folders hierarchy. Not available on all mailboxes"""
    DISTINGUISHED_FOLDER_ID = 'archiveroot'
    supported_from = EXCHANGE_2010_SP1
    WELLKNOWN_FOLDERS = WELLKNOWN_FOLDERS_IN_ARCHIVE_ROOT
    __slots__ = tuple()
