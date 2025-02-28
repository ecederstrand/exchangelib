import abc
from ..util import MNS as MNS, create_element as create_element
from .common import EWSAccountService as EWSAccountService, add_xml_child as add_xml_child, folder_ids_element as folder_ids_element
from _typeshed import Incomplete
from collections.abc import Generator

class Subscribe(EWSAccountService, metaclass=abc.ABCMeta):
    SERVICE_NAME: str
    EVENT_TYPES: Incomplete
    subscription_request_elem_tag: Incomplete

class SubscribeToPull(Subscribe):
    subscription_request_elem_tag: str
    prefer_affinity: bool
    def call(self, folders, event_types, watermark, timeout) -> Generator[Incomplete, Incomplete]: ...
    def get_payload(self, folders, event_types, watermark, timeout): ...

class SubscribeToPush(Subscribe):
    subscription_request_elem_tag: str
    def call(self, folders, event_types, watermark, status_frequency, url) -> Generator[Incomplete, Incomplete]: ...
    def get_payload(self, folders, event_types, watermark, status_frequency, url): ...

class SubscribeToStreaming(Subscribe):
    subscription_request_elem_tag: str
    prefer_affinity: bool
    def call(self, folders, event_types) -> Generator[Incomplete, Incomplete]: ...
    def get_payload(self, folders, event_types): ...
