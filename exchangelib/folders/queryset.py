from copy import deepcopy
import logging
from ..properties import InvalidField
from ..queryset import DoesNotExist, MultipleObjectsReturned
from ..restriction import Q

# Traversal enums
SHALLOW = 'Shallow'
SOFT_DELETED = 'SoftDeleted'
DEEP = 'Deep'
FOLDER_TRAVERSAL_CHOICES = (SHALLOW, DEEP, SOFT_DELETED)


log = logging.getLogger(__name__)


class FolderQuerySet:
    """A QuerySet-like class for finding subfolders of a folder collection"""

    def __init__(self, folder_collection):
        from .collections import FolderCollection
        if not isinstance(folder_collection, FolderCollection):
            raise ValueError("'folder_collection' %r must be a FolderCollection instance" % folder_collection)
        self.folder_collection = folder_collection
        self.only_fields = None
        self._depth = None
        self.q = None

    def _copy_cls(self):
        return self.__class__(folder_collection=self.folder_collection)

    def _copy_self(self):
        """Chaining operations must make a copy of self before making any modifications"""
        new_qs = self._copy_cls()
        new_qs.only_fields = self.only_fields
        new_qs._depth = self._depth
        new_qs.q = None if self.q is None else deepcopy(self.q)
        return new_qs

    def only(self, *args):
        """Restrict the fields returned. 'name' and 'folder_class' are always returned.

        Args:
          *args: 

        Returns:

        """
        from .base import Folder
        # Subfolders will always be of class Folder
        all_fields = self.folder_collection.get_folder_fields(target_cls=Folder, is_complex=None)
        only_fields = []
        for arg in args:
            for field_path in all_fields:
                if field_path.field.name == arg:
                    only_fields.append(field_path)
                    break
            else:
                raise InvalidField("Unknown field %r on folders %s" % (arg, self.folder_collection.folders))
        new_qs = self._copy_self()
        new_qs.only_fields = only_fields
        return new_qs

    def depth(self, depth):
        """Specify the search depth (SHALLOW or DEEP)

        Args:
          depth: 

        Returns:

        """
        new_qs = self._copy_self()
        new_qs._depth = depth
        return new_qs

    def get(self, *args, **kwargs):
        """

        Args:
          *args: 
          **kwargs: 

        Returns:


        """
        if args or kwargs:
            folders = list(self.filter(*args, **kwargs))
        else:
            folders = list(self.all())
        if not folders:
            raise DoesNotExist('Could not find a child folder matching the query')
        if len(folders) != 1:
            raise MultipleObjectsReturned('Expected result length 1, but got %s' % folders)
        f = folders[0]
        if isinstance(f, Exception):
            raise f
        return f

    def all(self):
        """ """
        new_qs = self._copy_self()
        return new_qs

    def filter(self, *args, **kwargs):
        """Add restrictions to the folder search

        Args:
          *args: 
          **kwargs: 

        Returns:

        """
        new_qs = self._copy_self()
        q = Q(*args, **kwargs)
        new_qs.q = q if new_qs.q is None else new_qs.q & q
        return new_qs

    def __iter__(self):
        return self._query()

    def _query(self):
        from .base import Folder
        from .collections import FolderCollection
        if self.only_fields is None:
            # Subfolders will always be of class Folder
            non_complex_fields = self.folder_collection.get_folder_fields(target_cls=Folder, is_complex=False)
            complex_fields = self.folder_collection.get_folder_fields(target_cls=Folder, is_complex=True)
        else:
            non_complex_fields = set(f for f in self.only_fields if not f.field.is_complex)
            complex_fields = set(f for f in self.only_fields if f.field.is_complex)

        # First, fetch all non-complex fields using FindFolder. We do this because some folders do not support
        # GetFolder but we still want to get as much information as possible.
        folders = self.folder_collection.find_folders(q=self.q, depth=self._depth, additional_fields=non_complex_fields)
        if not complex_fields:
            for f in folders:
                yield f
            return

        # Fetch all properties for the found folders
        resolveable_folders = []
        for f in folders:
            if not f.get_folder_allowed:
                log.debug('GetFolder not allowed on folder %s. Non-complex fields must be fetched with FindFolder', f)
                yield f
            else:
                resolveable_folders.append(f)

        # Get the complex fields using GetFolder, for the folders that support it, and add the extra field values
        complex_folders = FolderCollection(
            account=self.folder_collection.account, folders=resolveable_folders
        ).get_folders(additional_fields=complex_fields)
        for f, complex_f in zip(resolveable_folders, complex_folders):
            if isinstance(f, Exception):
                yield f
                continue
            if isinstance(complex_f, Exception):
                yield complex_f
                continue
            # Add the extra field values to the folders we fetched with find_folders()
            if f.__class__ != complex_f.__class__:
                raise ValueError('Type mismatch: %s vs %s' % (f, complex_f))
            for complex_field in complex_fields:
                field_name = complex_field.field.name
                setattr(f, field_name, getattr(complex_f, field_name))
            yield f


class SingleFolderQuerySet(FolderQuerySet):
    """A helper class with simpler argument types"""

    def __init__(self, account, folder):
        from .collections import FolderCollection
        folder_collection = FolderCollection(account=account, folders=[folder])
        super().__init__(folder_collection=folder_collection)

    def _copy_cls(self):
        return self.__class__(account=self.folder_collection.account, folder=self.folder_collection.folders[0])
