from .errors import InvalidEnumValue as InvalidEnumValue
from .ewsdatetime import EWSDateTime as EWSDateTime
from .properties import EWSElement as EWSElement, ExtendedFieldURI as ExtendedFieldURI
from .util import TNS as TNS, add_xml_child as add_xml_child, create_element as create_element, get_xml_attr as get_xml_attr, get_xml_attrs as get_xml_attrs, is_iterable as is_iterable, set_xml_value as set_xml_value, value_to_xml_text as value_to_xml_text, xml_text_to_value as xml_text_to_value
from _typeshed import Incomplete

log: Incomplete

class ExtendedProperty(EWSElement):
    ELEMENT_NAME: str
    DISTINGUISHED_SETS: Incomplete
    PROPERTY_TYPES: Incomplete
    DISTINGUISHED_SET_NAME_TO_ID_MAP: Incomplete
    DISTINGUISHED_SET_ID_TO_NAME_MAP: Incomplete
    distinguished_property_set_id: Incomplete
    property_set_id: Incomplete
    property_tag: Incomplete
    property_name: Incomplete
    property_id: Incomplete
    property_type: str
    value: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    @classmethod
    def validate_cls(cls) -> None: ...
    def clean(self, version: Incomplete | None = None) -> None: ...
    @classmethod
    def is_property_instance(cls, elem): ...
    @classmethod
    def from_xml(cls, elem, account): ...
    def to_xml(self, version): ...
    @classmethod
    def is_array_type(cls): ...
    @classmethod
    def property_tag_as_int(cls): ...
    @classmethod
    def property_tag_as_hex(cls): ...
    @classmethod
    def python_type(cls): ...
    @classmethod
    def as_object(cls): ...

class ExternId(ExtendedProperty):
    property_set_id: str
    property_name: str
    property_type: str

class Flag(ExtendedProperty):
    property_tag: int
    property_type: str
