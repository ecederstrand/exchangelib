from .fields import Choice as Choice, EmailSubField as EmailSubField, LabelField as LabelField, NamedSubField as NamedSubField, SubField as SubField
from .properties import EWSElement as EWSElement, EWSMeta as EWSMeta
from _typeshed import Incomplete

log: Incomplete

class IndexedElement(EWSElement, metaclass=EWSMeta):
    LABEL_CHOICES: Incomplete

class SingleFieldIndexedElement(IndexedElement, metaclass=EWSMeta):
    @classmethod
    def value_field(cls, version): ...

class EmailAddress(SingleFieldIndexedElement):
    ELEMENT_NAME: str
    LABEL_CHOICES: Incomplete
    label: Incomplete
    email: Incomplete

class ImAddress(SingleFieldIndexedElement):
    ELEMENT_NAME: str
    LABEL_CHOICES: Incomplete
    label: Incomplete
    im_address: Incomplete

class PhoneNumber(SingleFieldIndexedElement):
    ELEMENT_NAME: str
    LABEL_CHOICES: Incomplete
    label: Incomplete
    phone_number: Incomplete

class MultiFieldIndexedElement(IndexedElement, metaclass=EWSMeta): ...

class PhysicalAddress(MultiFieldIndexedElement):
    ELEMENT_NAME: str
    LABEL_CHOICES: Incomplete
    label: Incomplete
    street: Incomplete
    city: Incomplete
    state: Incomplete
    country: Incomplete
    zipcode: Incomplete
    def clean(self, version: Incomplete | None = None) -> None: ...
