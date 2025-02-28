from .ewsdatetime import UTC as UTC
from .fields import Choice as Choice, ChoiceField as ChoiceField, DateTimeField as DateTimeField, MessageField as MessageField
from .properties import EWSElement as EWSElement, OutOfOffice as OutOfOffice
from .util import create_element as create_element, set_xml_value as set_xml_value
from _typeshed import Incomplete

class OofSettings(EWSElement):
    ELEMENT_NAME: str
    REQUEST_ELEMENT_NAME: str
    ENABLED: str
    SCHEDULED: str
    DISABLED: str
    STATE_CHOICES: Incomplete
    state: Incomplete
    external_audience: Incomplete
    start: Incomplete
    end: Incomplete
    internal_reply: Incomplete
    external_reply: Incomplete
    def clean(self, version: Incomplete | None = None) -> None: ...
    @classmethod
    def from_xml(cls, elem, account): ...
    def to_xml(self, version): ...
    def __hash__(self): ...
