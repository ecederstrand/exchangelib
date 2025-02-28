from ..attachments import FileAttachment as FileAttachment, ItemAttachment as ItemAttachment
from ..errors import InvalidEnumValue as InvalidEnumValue
from ..util import DummyResponse as DummyResponse, ElementNotFound as ElementNotFound, MNS as MNS, StreamingBase64Parser as StreamingBase64Parser, StreamingContentHandler as StreamingContentHandler, add_xml_child as add_xml_child, create_element as create_element, set_xml_value as set_xml_value
from .common import EWSAccountService as EWSAccountService, attachment_ids_element as attachment_ids_element
from _typeshed import Incomplete
from collections.abc import Generator

BODY_TYPE_CHOICES: Incomplete

class GetAttachment(EWSAccountService):
    SERVICE_NAME: str
    element_container_name: Incomplete
    cls_map: Incomplete
    def call(self, items, include_mime_content, body_type, filter_html_content, additional_fields): ...
    def get_payload(self, items, include_mime_content, body_type, filter_html_content, additional_fields): ...
    streaming: bool
    def stream_file_content(self, attachment_id) -> Generator[Incomplete, Incomplete]: ...
