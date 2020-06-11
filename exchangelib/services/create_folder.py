from ..util import create_element, set_xml_value, MNS
from .common import EWSAccountService, parse_folder_elem, create_folder_ids_element


class CreateFolder(EWSAccountService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/createfolder-operation"""
    SERVICE_NAME = 'CreateFolder'
    element_container_name = '{%s}Folders' % MNS

    def call(self, parent_folder, folders):
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        folders_list = list(folders)  # Convert to a list, in case 'folders' is a generator
        for folder, elem in zip(folders_list, self._get_elements(payload=self.get_payload(
                parent_folder=parent_folder, folders=folders
        ))):
            yield parse_folder_elem(elem=elem, folder=folder, account=self.account)

    def get_payload(self, parent_folder, folders):
        create_folder = create_element('m:%s' % self.SERVICE_NAME)
        parentfolderid = create_element('m:ParentFolderId')
        set_xml_value(parentfolderid, parent_folder, version=self.account.version)
        set_xml_value(create_folder, parentfolderid, version=self.account.version)
        folder_ids = create_folder_ids_element(tag='m:Folders', folders=folders, version=self.account.version)
        create_folder.append(folder_ids)
        return create_folder
