from ..errors import InvalidEnumValue
from ..folders import Folder
from ..folders.queryset import FOLDER_TRAVERSAL_CHOICES
from ..items import SHAPE_CHOICES
from ..util import MNS, TNS, create_element
from ..version import EXCHANGE_2010
from .common import EWSPagingService, folder_ids_element, shape_element


class FindFolder(EWSPagingService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/findfolder-operation"""

    SERVICE_NAME = "FindFolder"
    element_container_name = f"{{{TNS}}}Folders"
    paging_container_name = f"{{{MNS}}}RootFolder"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root = None  # A hack to communicate parsing args to _elems_to_objs()

    def call(self, folders, additional_fields, restriction, shape, depth, max_items, offset):
        """Find sub-folders of a folder.

        :param folders: the folders to act on
        :param additional_fields: the extra fields that should be returned with the folder, as FieldPath objects
        :param restriction: Restriction object that defines the filters for the query
        :param shape: The set of attributes to return
        :param depth: How deep in the folder structure to search for folders
        :param max_items: The maximum number of items to return
        :param offset: the offset relative to the first item in the item collection. Usually 0.

        :return: XML elements for the matching folders
        """
        if shape not in SHAPE_CHOICES:
            raise InvalidEnumValue("shape", shape, SHAPE_CHOICES)
        if depth not in FOLDER_TRAVERSAL_CHOICES:
            raise InvalidEnumValue("depth", depth, FOLDER_TRAVERSAL_CHOICES)
        roots = {f.root for f in folders}
        if len(roots) != 1:
            raise ValueError(f"All folders must have the same root hierarchy ({roots})")
        self.root = roots.pop()
        return self._elems_to_objs(
            self._paged_call(
                payload_func=self.get_payload,
                max_items=max_items,
                folders=folders,
                **dict(
                    additional_fields=additional_fields,
                    restriction=restriction,
                    shape=shape,
                    depth=depth,
                    page_size=self.page_size,
                    offset=offset,
                ),
            )
        )

    def _elem_to_obj(self, elem):
        return Folder.from_xml_with_root(elem=elem, root=self.root)

    def get_payload(self, folders, additional_fields, restriction, shape, depth, page_size, offset=0):
        payload = create_element(f"m:{self.SERVICE_NAME}", attrs=dict(Traversal=depth))
        payload.append(
            shape_element(
                tag="m:FolderShape", shape=shape, additional_fields=additional_fields, version=self.account.version
            )
        )
        if self.account.version.build >= EXCHANGE_2010:
            indexed_page_folder_view = create_element(
                "m:IndexedPageFolderView",
                attrs=dict(MaxEntriesReturned=page_size, Offset=offset, BasePoint="Beginning"),
            )
            payload.append(indexed_page_folder_view)
        else:
            if offset != 0:
                raise NotImplementedError("'offset' is only supported for Exchange 2010 servers and later")
        if restriction:
            payload.append(restriction.to_xml(version=self.account.version))
        payload.append(folder_ids_element(folders=folders, version=self.protocol.version, tag="m:ParentFolderIds"))
        return payload
