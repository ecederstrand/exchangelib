import abc
from .. import errors as errors
from ..attachments import AttachmentId as AttachmentId
from ..credentials import BaseOAuth2Credentials as BaseOAuth2Credentials, IMPERSONATION as IMPERSONATION
from ..errors import EWSWarning as EWSWarning, ErrorBatchProcessingStopped as ErrorBatchProcessingStopped, ErrorCannotDeleteObject as ErrorCannotDeleteObject, ErrorCannotDeleteTaskOccurrence as ErrorCannotDeleteTaskOccurrence, ErrorCorruptData as ErrorCorruptData, ErrorExceededConnectionCount as ErrorExceededConnectionCount, ErrorIncorrectSchemaVersion as ErrorIncorrectSchemaVersion, ErrorInternalServerTransientError as ErrorInternalServerTransientError, ErrorInvalidChangeKey as ErrorInvalidChangeKey, ErrorInvalidIdMalformed as ErrorInvalidIdMalformed, ErrorInvalidRequest as ErrorInvalidRequest, ErrorInvalidSchemaVersionForMailboxVersion as ErrorInvalidSchemaVersionForMailboxVersion, ErrorInvalidServerVersion as ErrorInvalidServerVersion, ErrorItemCorrupt as ErrorItemCorrupt, ErrorItemNotFound as ErrorItemNotFound, ErrorItemSave as ErrorItemSave, ErrorMailRecipientNotFound as ErrorMailRecipientNotFound, ErrorMessageSizeExceeded as ErrorMessageSizeExceeded, ErrorMimeContentConversionFailed as ErrorMimeContentConversionFailed, ErrorRecurrenceHasNoOccurrence as ErrorRecurrenceHasNoOccurrence, ErrorServerBusy as ErrorServerBusy, ErrorTimeoutExpired as ErrorTimeoutExpired, ErrorTooManyObjectsOpened as ErrorTooManyObjectsOpened, InvalidTypeError as InvalidTypeError, MalformedResponseError as MalformedResponseError, SOAPError as SOAPError, SessionPoolMinSizeReached as SessionPoolMinSizeReached, TransportError as TransportError
from ..folders import BaseFolder as BaseFolder, Folder as Folder, RootOfHierarchy as RootOfHierarchy
from ..items import BaseItem as BaseItem
from ..properties import BaseItemId as BaseItemId, ExceptionFieldURI as ExceptionFieldURI, ExtendedFieldURI as ExtendedFieldURI, FieldURI as FieldURI, FolderId as FolderId, IndexedFieldURI as IndexedFieldURI, ItemId as ItemId
from ..transport import DEFAULT_ENCODING as DEFAULT_ENCODING
from ..util import DummyResponse as DummyResponse, ENS as ENS, MNS as MNS, ParseError as ParseError, SOAPNS as SOAPNS, TNS as TNS, add_xml_child as add_xml_child, chunkify as chunkify, create_element as create_element, get_xml_attr as get_xml_attr, ns_translation as ns_translation, post_ratelimited as post_ratelimited, set_xml_value as set_xml_value, to_xml as to_xml, xml_to_str as xml_to_str
from ..version import SupportedVersionClassMixIn as SupportedVersionClassMixIn, Version as Version
from _typeshed import Incomplete

log: Incomplete

class EWSService(SupportedVersionClassMixIn, metaclass=abc.ABCMeta):
    CHUNK_SIZE: int
    SERVICE_NAME: Incomplete
    element_container_name: Incomplete
    returns_elements: bool
    ERRORS_TO_CATCH_IN_RESPONSE: Incomplete
    WARNINGS_TO_CATCH_IN_RESPONSE = ErrorBatchProcessingStopped
    WARNINGS_TO_IGNORE_IN_RESPONSE: Incomplete
    NO_VALID_SERVER_VERSIONS = ErrorInvalidServerVersion
    NS_MAP: Incomplete
    chunk_size: Incomplete
    protocol: Incomplete
    timeout: Incomplete
    streaming: bool
    def __init__(self, protocol, chunk_size: Incomplete | None = None, timeout: Incomplete | None = None) -> None: ...
    def __del__(self) -> None: ...
    def get(self, expect_result: bool = True, **kwargs): ...
    def parse(self, xml): ...
    def wrap(self, content, api_version: Incomplete | None = None): ...
    def stop_streaming(self) -> None: ...
    @classmethod
    def supported_api_versions(cls): ...

class EWSAccountService(EWSService, metaclass=abc.ABCMeta):
    NO_VALID_SERVER_VERSIONS = ErrorInvalidSchemaVersionForMailboxVersion
    prefer_affinity: bool
    account: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...

class EWSPagingService(EWSAccountService):
    PAGE_SIZE: int
    paging_container_name: Incomplete
    page_size: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...

def to_item_id(item, item_cls): ...
def shape_element(tag, shape, additional_fields, version): ...
def folder_ids_element(folders, version, tag: str = 'm:FolderIds'): ...
def item_ids_element(items, version, tag: str = 'm:ItemIds'): ...
def attachment_ids_element(items, version, tag: str = 'm:AttachmentIds'): ...
def parse_folder_elem(elem, folder): ...
