from .errors import InvalidEnumValue as InvalidEnumValue
from .fields import DateTimeBackedDateField as DateTimeBackedDateField, FieldPath as FieldPath, InvalidField as InvalidField
from .util import create_element as create_element, is_iterable as is_iterable, value_to_xml_text as value_to_xml_text, xml_to_str as xml_to_str
from .version import EXCHANGE_2010 as EXCHANGE_2010, EXCHANGE_2013 as EXCHANGE_2013
from _typeshed import Incomplete

log: Incomplete

class Q:
    AND: str
    OR: str
    NOT: str
    NEVER: str
    CONN_TYPES: Incomplete
    EQ: str
    NE: str
    GT: str
    GTE: str
    LT: str
    LTE: str
    EXACT: str
    IEXACT: str
    CONTAINS: str
    ICONTAINS: str
    STARTSWITH: str
    ISTARTSWITH: str
    EXISTS: str
    OP_TYPES: Incomplete
    CONTAINS_OPS: Incomplete
    LOOKUP_RANGE: str
    LOOKUP_IN: str
    LOOKUP_NOT: str
    LOOKUP_GT: str
    LOOKUP_GTE: str
    LOOKUP_LT: str
    LOOKUP_LTE: str
    LOOKUP_EXACT: str
    LOOKUP_IEXACT: str
    LOOKUP_CONTAINS: str
    LOOKUP_ICONTAINS: str
    LOOKUP_STARTSWITH: str
    LOOKUP_ISTARTSWITH: str
    LOOKUP_EXISTS: str
    LOOKUP_TYPES: Incomplete
    conn_type: Incomplete
    field_path: Incomplete
    op: Incomplete
    value: Incomplete
    query_string: Incomplete
    children: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...
    def reduce(self) -> None: ...
    def clean(self, version) -> None: ...
    def is_leaf(self): ...
    def is_empty(self): ...
    def is_never(self): ...
    def expr(self): ...
    def to_xml(self, folders, version, applies_to): ...
    def xml_elem(self, folders, version, applies_to): ...
    def __and__(self, other): ...
    def __or__(self, other): ...
    def __invert__(self): ...
    def __eq__(self, other): ...
    def __hash__(self): ...

class Restriction:
    FOLDERS: str
    ITEMS: str
    RESTRICTION_TYPES: Incomplete
    q: Incomplete
    folders: Incomplete
    applies_to: Incomplete
    def __init__(self, q, folders, applies_to) -> None: ...
    def to_xml(self, version): ...
