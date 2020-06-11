from ..errors import ErrorFolderNotFound, ErrorNoPublicFolderReplicaAvailable, ErrorInvalidOperation
from ..util import create_element, MNS
from .common import EWSAccountService, EWSPooledMixIn, parse_folder_elem, create_folder_ids_element,\
    create_shape_element


class GetFolder(EWSAccountService, EWSPooledMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getfolder"""
    SERVICE_NAME = 'GetFolder'
    element_container_name = '{%s}Folders' % MNS
    ERRORS_TO_CATCH_IN_RESPONSE = EWSAccountService.ERRORS_TO_CATCH_IN_RESPONSE + (
        ErrorFolderNotFound, ErrorNoPublicFolderReplicaAvailable, ErrorInvalidOperation,
    )

    def call(self, folders, additional_fields, shape):
        """Takes a folder ID and returns the full information for that folder.

        Args:
          folders: a list of Folder objects
          additional_fields: the extra fields that should be returned with the folder, as FieldPath objects
          shape: The set of attributes to return

        Returns:
          XML elements for the folders, in stable order

        """
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        folders_list = list(folders)  # Convert to a list, in case 'folders' is a generator
        for folder, elem in zip(folders_list, self._pool_requests(
            payload_func=self.get_payload,
            items=folders,
            **dict(
                additional_fields=additional_fields,
                shape=shape,
            )
        )):
            yield parse_folder_elem(elem=elem, folder=folder, account=self.account)

    def get_payload(self, folders, additional_fields, shape):
        getfolder = create_element('m:%s' % self.SERVICE_NAME)
        foldershape = create_shape_element(
            tag='m:FolderShape', shape=shape, additional_fields=additional_fields, version=self.account.version
        )
        getfolder.append(foldershape)
        folder_ids = create_folder_ids_element(tag='m:FolderIds', folders=folders, version=self.account.version)
        getfolder.append(folder_ids)
        return getfolder
