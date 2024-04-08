from ..errors import (
    ErrorAccessDenied,
    ErrorFolderNotFound,
    ErrorInvalidOperation,
    ErrorItemNotFound,
    ErrorNoPublicFolderReplicaAvailable,
)
from ..util import MNS, create_element
from .common import EWSAccountService, folder_ids_element, parse_folder_elem, shape_element


class GetFolder(EWSAccountService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getfolder-operation"""

    SERVICE_NAME = "GetFolder"
    element_container_name = f"{{{MNS}}}Folders"
    ERRORS_TO_CATCH_IN_RESPONSE = EWSAccountService.ERRORS_TO_CATCH_IN_RESPONSE + (
        ErrorAccessDenied,
        ErrorFolderNotFound,
        ErrorNoPublicFolderReplicaAvailable,
        ErrorInvalidOperation,
        ErrorItemNotFound,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.folders = []  # A hack to communicate parsing args to _elems_to_objs()

    def call(self, folders, additional_fields, shape):
        """Take a folder ID and returns the full information for that folder.

        :param folders: a list of Folder objects
        :param additional_fields: the extra fields that should be returned with the folder, as FieldPath objects
        :param shape: The set of attributes to return

        :return: XML elements for the folders, in stable order
        """
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        self.folders = list(folders)  # Convert to a list, in case 'folders' is a generator. We're iterating twice.
        return self._elems_to_objs(
            self._chunked_get_elements(
                self.get_payload,
                items=self.folders,
                additional_fields=additional_fields,
                shape=shape,
            )
        )

    def _elems_to_objs(self, elems):
        for folder, elem in zip(self.folders, elems):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield parse_folder_elem(elem=elem, folder=folder, account=self.account)

    def get_payload(self, folders, additional_fields, shape):
        payload = create_element(f"m:{self.SERVICE_NAME}")
        payload.append(
            shape_element(
                tag="m:FolderShape", shape=shape, additional_fields=additional_fields, version=self.account.version
            )
        )
        payload.append(folder_ids_element(folders=folders, version=self.account.version))
        return payload
