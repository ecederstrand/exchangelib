import logging
from contextlib import suppress
from decimal import Decimal

from .errors import InvalidEnumValue
from .ewsdatetime import EWSDateTime
from .properties import EWSElement, ExtendedFieldURI
from .util import (
    TNS,
    add_xml_child,
    create_element,
    get_xml_attr,
    get_xml_attrs,
    is_iterable,
    set_xml_value,
    value_to_xml_text,
    xml_text_to_value,
)

log = logging.getLogger(__name__)


class ExtendedProperty(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/extendedproperty"""

    ELEMENT_NAME = "ExtendedProperty"

    # Enum values: https://docs.microsoft.com/en-us/dotnet/api/exchangewebservices.distinguishedpropertysettype
    DISTINGUISHED_SETS = {
        "Address",
        "Appointment",
        "CalendarAssistant",
        "Common",
        "InternetHeaders",
        "Meeting",
        "PublicStrings",
        "Sharing",
        "Task",
        "UnifiedMessaging",
    }
    # Enum values: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/extendedfielduri
    # The following types cannot be used for setting or getting (see docs) and are thus not very useful here:
    # 'Error'
    # 'Null'
    # 'Object'
    # 'ObjectArray'
    PROPERTY_TYPES = {
        "ApplicationTime",
        "Binary",
        "BinaryArray",
        "Boolean",
        "CLSID",
        "CLSIDArray",
        "Currency",
        "CurrencyArray",
        "Double",
        "DoubleArray",
        "Float",
        "FloatArray",
        "Integer",
        "IntegerArray",
        "Long",
        "LongArray",
        "Short",
        "ShortArray",
        "SystemTime",
        "SystemTimeArray",
        "String",
        "StringArray",
    }

    # Translation table between common distinguished_property_set_id and property_set_id values. See
    # https://docs.microsoft.com/en-us/office/client-developer/outlook/mapi/commonly-used-property-sets
    # ID values must be lowercase.
    DISTINGUISHED_SET_NAME_TO_ID_MAP = {
        "Address": "00062004-0000-0000-c000-000000000046",
        "AirSync": "71035549-0739-4dcb-9163-00f0580dbbdf",
        "Appointment": "00062002-0000-0000-c000-000000000046",
        "Common": "00062008-0000-0000-c000-000000000046",
        "InternetHeaders": "00020386-0000-0000-c000-000000000046",
        "Log": "0006200a-0000-0000-c000-000000000046",
        "Mapi": "00020328-0000-0000-c000-000000000046",
        "Meeting": "6ed8da90-450b-101b-98da-00aa003f1305",
        "Messaging": "41f28f13-83f4-4114-a584-eedb5a6b0bff",
        "Note": "0006200e-0000-0000-c000-000000000046",
        "PostRss": "00062041-0000-0000-c000-000000000046",
        "PublicStrings": "00020329-0000-0000-c000-000000000046",
        "Remote": "00062014-0000-0000-c000-000000000046",
        "Report": "00062013-0000-0000-c000-000000000046",
        "Sharing": "00062040-0000-0000-c000-000000000046",
        "Task": "00062003-0000-0000-c000-000000000046",
        "UnifiedMessaging": "4442858e-a9e3-4e80-b900-317a210cc15b",
    }
    DISTINGUISHED_SET_ID_TO_NAME_MAP = {v: k for k, v in DISTINGUISHED_SET_NAME_TO_ID_MAP.items()}

    distinguished_property_set_id = None
    property_set_id = None
    property_tag = None  # hex integer (e.g. 0x8000) or string ('0x8000')
    property_name = None
    property_id = None  # integer as hex-formatted int (e.g. 0x8000) or normal int (32768)
    property_type = ""

    __slots__ = ("value",)

    def __init__(self, *args, **kwargs):
        if not kwargs:
            # Allow to set attributes without keyword
            kwargs = dict(zip(self._slots_keys, args))
        self.value = kwargs.pop("value")
        super().__init__(**kwargs)

    @classmethod
    def validate_cls(cls):
        # Validate values of class attributes and their inter-dependencies
        cls._validate_distinguished_property_set_id()
        cls._validate_property_set_id()
        cls._validate_property_tag()
        cls._validate_property_name()
        cls._validate_property_id()
        cls._validate_property_type()

    @classmethod
    def _validate_distinguished_property_set_id(cls):
        if cls.distinguished_property_set_id:
            if any([cls.property_set_id, cls.property_tag]):
                raise ValueError(
                    "When 'distinguished_property_set_id' is set, 'property_set_id' and 'property_tag' must be None"
                )
            if not any([cls.property_id, cls.property_name]):
                raise ValueError(
                    "When 'distinguished_property_set_id' is set, 'property_id' or 'property_name' must also be set"
                )
            if cls.distinguished_property_set_id not in cls.DISTINGUISHED_SETS:
                raise InvalidEnumValue(
                    "distinguished_property_set_id", cls.distinguished_property_set_id, cls.DISTINGUISHED_SETS
                )

    @classmethod
    def _validate_property_set_id(cls):
        if cls.property_set_id:
            if any([cls.distinguished_property_set_id, cls.property_tag]):
                raise ValueError(
                    "When 'property_set_id' is set, 'distinguished_property_set_id' and 'property_tag' must be None"
                )
            if not any([cls.property_id, cls.property_name]):
                raise ValueError("When 'property_set_id' is set, 'property_id' or 'property_name' must also be set")

    @classmethod
    def _validate_property_tag(cls):
        if cls.property_tag:
            if any([cls.distinguished_property_set_id, cls.property_set_id, cls.property_name, cls.property_id]):
                raise ValueError("When 'property_tag' is set, only 'property_type' must be set")
            if 0x8000 <= cls.property_tag_as_int() <= 0xFFFE:
                raise ValueError(
                    f"'property_tag' value {cls.property_tag_as_hex()!r} is reserved for custom properties"
                )

    @classmethod
    def _validate_property_name(cls):
        if cls.property_name:
            if any([cls.property_id, cls.property_tag]):
                raise ValueError("When 'property_name' is set, 'property_id' and 'property_tag' must be None")
            if not any([cls.distinguished_property_set_id, cls.property_set_id]):
                raise ValueError(
                    "When 'property_name' is set, 'distinguished_property_set_id' or 'property_set_id' must also be set"
                )

    @classmethod
    def _validate_property_id(cls):
        if cls.property_id:
            if any([cls.property_name, cls.property_tag]):
                raise ValueError("When 'property_id' is set, 'property_name' and 'property_tag' must be None")
            if not any([cls.distinguished_property_set_id, cls.property_set_id]):
                raise ValueError(
                    "When 'property_id' is set, 'distinguished_property_set_id' or 'property_set_id' must also be set"
                )

    @classmethod
    def _validate_property_type(cls):
        if cls.property_type not in cls.PROPERTY_TYPES:
            raise InvalidEnumValue("property_type", cls.property_type, cls.PROPERTY_TYPES)

    def clean(self, version=None):
        self.validate_cls()
        python_type = self.python_type()
        if self.is_array_type():
            if not is_iterable(self.value):
                raise TypeError(f"Field {self.__class__.__name__!r} value {self.value!r} must be of type {list}")
            for v in self.value:
                if not isinstance(v, python_type):
                    raise TypeError(f"Field {self.__class__.__name__!r} list value {v!r} must be of type {python_type}")
        else:
            if not isinstance(self.value, python_type):
                raise TypeError(f"Field {self.__class__.__name__!r} value {self.value!r} must be of type {python_type}")

    @classmethod
    def _normalize_obj(cls, obj):
        # Sometimes, EWS will helpfully translate a 'distinguished_property_set_id' value to a 'property_set_id' value
        # and vice versa. Align these values on an ExtendedFieldURI instance.
        try:
            obj.property_set_id = cls.DISTINGUISHED_SET_NAME_TO_ID_MAP[obj.distinguished_property_set_id]
        except KeyError:
            with suppress(KeyError):
                obj.distinguished_property_set_id = cls.DISTINGUISHED_SET_ID_TO_NAME_MAP[obj.property_set_id]
        return obj

    @classmethod
    def is_property_instance(cls, elem):
        """Return whether an 'ExtendedProperty' element matches the definition for this class. Extended property fields
        do not have a name, so we must match on the cls.property_* attributes to match a field in the request with a
        field in the response.
        """
        # We can't use ExtendedFieldURI.from_xml(). It clears the XML element but we may not want to consume it here.
        kwargs = {
            f.name: f.from_xml(elem=elem.find(ExtendedFieldURI.response_tag()), account=None)
            for f in ExtendedFieldURI.FIELDS
        }
        xml_obj = ExtendedFieldURI(**kwargs)
        cls_obj = cls.as_object()
        return cls._normalize_obj(cls_obj) == cls._normalize_obj(xml_obj)

    @classmethod
    def from_xml(cls, elem, account):
        # Gets value of this specific ExtendedProperty from a list of 'ExtendedProperty' XML elements
        python_type = cls.python_type()
        if cls.is_array_type():
            values = elem.find(f"{{{TNS}}}Values")
            return [
                xml_text_to_value(value=val, value_type=python_type) for val in get_xml_attrs(values, f"{{{TNS}}}Value")
            ]
        extended_field_value = xml_text_to_value(value=get_xml_attr(elem, f"{{{TNS}}}Value"), value_type=python_type)
        if python_type == str and not extended_field_value:
            # For string types, we want to return the empty string instead of None if the element was
            # actually found, but there was no XML value. For other types, it would be more problematic
            # to make that distinction, e.g. return False for bool, 0 for int, etc.
            return ""
        return extended_field_value

    def to_xml(self, version):
        if self.is_array_type():
            values = create_element("t:Values")
            for v in self.value:
                add_xml_child(values, "t:Value", v)
            return values
        return set_xml_value(create_element("t:Value"), self.value, version=version)

    @classmethod
    def is_array_type(cls):
        return cls.property_type.endswith("Array")

    @classmethod
    def property_tag_as_int(cls):
        if isinstance(cls.property_tag, str):
            return int(cls.property_tag, base=16)
        return cls.property_tag

    @classmethod
    def property_tag_as_hex(cls):
        return hex(cls.property_tag) if isinstance(cls.property_tag, int) else cls.property_tag

    @classmethod
    def python_type(cls):
        # Return the best equivalent for a Python type for the property type of this class
        base_type = cls.property_type[:-5] if cls.is_array_type() else cls.property_type
        return {
            "ApplicationTime": Decimal,
            "Binary": bytes,
            "Boolean": bool,
            "CLSID": str,
            "Currency": int,
            "Double": Decimal,
            "Float": Decimal,
            "Integer": int,
            "Long": int,
            "Short": int,
            "SystemTime": EWSDateTime,
            "String": str,
        }[base_type]

    @classmethod
    def as_object(cls):
        # Return an object we can use to match with the incoming object from XML
        return ExtendedFieldURI(
            distinguished_property_set_id=cls.distinguished_property_set_id,
            property_set_id=cls.property_set_id.lower() if cls.property_set_id else None,
            property_tag=cls.property_tag_as_hex(),
            property_name=cls.property_name,
            property_id=value_to_xml_text(cls.property_id) if cls.property_id else None,
            property_type=cls.property_type,
        )


class ExternId(ExtendedProperty):
    """This is a custom extended property defined by us. It's useful for synchronization purposes, to attach a unique ID
    from an external system.
    """

    property_set_id = "c11ff724-aa03-4555-9952-8fa248a11c3e"  # This is arbitrary. We just want a unique UUID.
    property_name = "External ID"
    property_type = "String"


class Flag(ExtendedProperty):
    """This property returns None for Not Flagged messages, 1 for Completed messages and 2 for Flagged messages.

    For a description of each status, see:
    https://docs.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-oxoflag/eda9fd25-6407-4cec-9e62-26e4f9d6a098
    """

    property_tag = 0x1090
    property_type = "Integer"
