from ..errors import ErrorFolderExists
from ..util import MNS, create_element
from .common import EWSAccountService, folder_ids_element, parse_folder_elem, set_xml_value


class CreateFolder(EWSAccountService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/createfolder-operation"""

    SERVICE_NAME = "CreateFolder"
    element_container_name = f"{{{MNS}}}Folders"
    ERRORS_TO_CATCH_IN_RESPONSE = EWSAccountService.ERRORS_TO_CATCH_IN_RESPONSE + (ErrorFolderExists,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.folders = []  # A hack to communicate parsing args to _elems_to_objs()

    def call(self, parent_folder, folders):
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        self.folders = list(folders)  # Convert to a list, in case 'folders' is a generator. We're iterating twice.
        return self._elems_to_objs(
            self._chunked_get_elements(
                self.get_payload,
                items=self.folders,
                parent_folder=parent_folder,
            )
        )

    def _elems_to_objs(self, elems):
        for folder, elem in zip(self.folders, elems):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield parse_folder_elem(elem=elem, folder=folder, account=self.account)

    def get_payload(self, folders, parent_folder):
        payload = create_element(f"m:{self.SERVICE_NAME}")
        payload.append(
            folder_ids_element(folders=[parent_folder], version=self.account.version, tag="m:ParentFolderId")
        )
        folder_elems = create_element("m:Folders")
        for folder in folders:
            set_xml_value(folder_elems, folder, version=self.account.version)
        payload.append(folder_elems)
        return payload
