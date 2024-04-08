import abc
import datetime
import logging
import warnings
from contextlib import suppress
from decimal import Decimal, InvalidOperation
from importlib import import_module

from .errors import InvalidTypeError
from .ewsdatetime import UTC, EWSDate, EWSDateTime, EWSTimeZone, NaiveDateTimeNotAllowed, UnknownTimeZone
from .util import (
    TNS,
    create_element,
    get_xml_attr,
    get_xml_attrs,
    is_iterable,
    set_xml_value,
    value_to_xml_text,
    xml_text_to_value,
)
from .version import EXCHANGE_2013, SupportedVersionInstanceMixIn

log = logging.getLogger(__name__)


# DayOfWeekIndex enum. See
# https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/dayofweekindex
FIRST = "First"
SECOND = "Second"
THIRD = "Third"
FOURTH = "Fourth"
LAST = "Last"
WEEK_NUMBERS = (FIRST, SECOND, THIRD, FOURTH, LAST)

# Month enum
JANUARY = "January"
FEBRUARY = "February"
MARCH = "March"
APRIL = "April"
MAY = "May"
JUNE = "June"
JULY = "July"
AUGUST = "August"
SEPTEMBER = "September"
OCTOBER = "October"
NOVEMBER = "November"
DECEMBER = "December"
MONTHS = (JANUARY, FEBRUARY, MARCH, APRIL, MAY, JUNE, JULY, AUGUST, SEPTEMBER, OCTOBER, NOVEMBER, DECEMBER)

# Weekday enum
MONDAY = "Monday"
TUESDAY = "Tuesday"
WEDNESDAY = "Wednesday"
THURSDAY = "Thursday"
FRIDAY = "Friday"
SATURDAY = "Saturday"
SUNDAY = "Sunday"
WEEKDAY_NAMES = (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY)

# Used for weekday recurrences except weekly recurrences. E.g. for "First WeekendDay in March"
DAY = "Day"
WEEK_DAY = "Weekday"  # Non-weekend day
WEEKEND_DAY = "WeekendDay"
EXTRA_WEEKDAY_OPTIONS = (DAY, WEEK_DAY, WEEKEND_DAY)

# DaysOfWeek enum: See
# https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/daysofweek-daysofweektype
WEEKDAYS = WEEKDAY_NAMES + EXTRA_WEEKDAY_OPTIONS


class InvalidField(ValueError):
    """Used when a field name does not match any defined fields."""


class InvalidFieldForVersion(ValueError):
    """Used when a field is not supported on the given Exchange version."""


class InvalidChoiceForVersion(ValueError):
    """Used when a value is not valid for an enum-type field."""


def split_field_path(field_path):
    """Split a string path into its field, label and subfield parts.

    :param field_path:

    :return Examples:
      'start' -> ('start', None, None)
      'phone_numbers__PrimaryPhone' -> ('phone_numbers', 'PrimaryPhone', None)
      'physical_addresses__Home__street' -> ('physical_addresses', 'Home', 'street')
    """
    if not isinstance(field_path, str):
        raise InvalidTypeError("field_path", field_path, str)
    search_parts = field_path.split("__")
    field = search_parts[0]
    try:
        label = search_parts[1]
    except IndexError:
        label = None
    try:
        subfield = search_parts[2]
    except IndexError:
        subfield = None
    return field, label, subfield


def resolve_field_path(field_path, folder, strict=True):
    """Take the name of a field, or '__'-delimited path to a subfield, and return the corresponding Field object,
    label and SubField object.
    """
    from .indexed_properties import MultiFieldIndexedElement, SingleFieldIndexedElement

    fieldname, label, subfield_name = split_field_path(field_path)
    field = folder.get_item_field_by_fieldname(fieldname)
    subfield = None
    if isinstance(field, IndexedField):
        if strict and not label:
            raise ValueError(
                f"IndexedField path {field_path!r} must specify label, e.g. "
                f"'{fieldname}__{field.value_cls.get_field_by_fieldname('label').default}'"
            )
        valid_labels = field.value_cls.get_field_by_fieldname("label").supported_choices(version=folder.account.version)
        if label and label not in valid_labels:
            raise ValueError(
                f"Label {label!r} on IndexedField path {field_path!r} must be one of {sorted(valid_labels)}"
            )
        if issubclass(field.value_cls, MultiFieldIndexedElement):
            if strict and not subfield_name:
                raise ValueError(
                    f"IndexedField path {field_path!r} must specify subfield, e.g. "
                    f"'{fieldname}__{label}__{field.value_cls.FIELDS[1].name}'"
                )

            if subfield_name:
                try:
                    subfield = field.value_cls.get_field_by_fieldname(subfield_name)
                except ValueError:
                    field_names = ", ".join(
                        f.name for f in field.value_cls.supported_fields(version=folder.account.version)
                    )
                    raise ValueError(
                        f"Subfield {subfield_name!r} on IndexedField path {field_path!r} "
                        f"must be one of {sorted(field_names)}"
                    )
        else:
            if not issubclass(field.value_cls, SingleFieldIndexedElement):
                raise InvalidTypeError("field.value_cls", field.value_cls, SingleFieldIndexedElement)
            if subfield_name:
                raise ValueError(
                    f"IndexedField path {field_path!r} must not specify subfield, e.g. just {fieldname}__{label}'"
                )
            subfield = field.value_cls.value_field(version=folder.account.version)
    else:
        if label or subfield_name:
            raise ValueError(f"Field path {field_path!r} must not specify label or subfield, e.g. just {fieldname!r}")
    return field, label, subfield


class FieldPath:
    """Holds values needed to point to a single field. For indexed properties, we allow setting either field,
    field and label, or field, label and subfield. This allows pointing to either the full indexed property set, a
    property with a specific label, or a particular subfield field on that property.
    """

    def __init__(self, field, label=None, subfield=None):
        """

        :param field: A FieldURIField or ExtendedPropertyField instance
        :param label: a str
        :param subfield: A SubField instance
        """
        # 'label' and 'subfield' are only used for IndexedField fields
        self.field = field
        self.label = label
        self.subfield = subfield

    @classmethod
    def from_string(cls, field_path, folder, strict=False):
        field, label, subfield = resolve_field_path(field_path, folder=folder, strict=strict)
        return cls(field=field, label=label, subfield=subfield)

    def get_value(self, item):
        # For indexed properties, get either the full property set, the property with matching label, or a particular
        # subfield.
        if self.label:
            for sub_item in getattr(item, self.field.name):
                if sub_item.label == self.label:
                    if self.subfield:
                        return getattr(sub_item, self.subfield.name)
                    return sub_item
            return None  # No item with this label
        return getattr(item, self.field.name)

    def get_sort_value(self, item):
        # For fields that allow values of different types, we need to return a value that is
        val = self.get_value(item)
        if isinstance(self.field, DateOrDateTimeField) and isinstance(val, EWSDate):
            return item.date_to_datetime(field_name=self.field.name)
        return val

    def to_xml(self):
        if isinstance(self.field, IndexedField):
            if not self.label or not self.subfield:
                raise ValueError(f"Field path for indexed field {self.field.name!r} is missing label and/or subfield")
            return self.subfield.field_uri_xml(field_uri=self.field.field_uri, label=self.label)
        return self.field.field_uri_xml()

    def expand(self, version):
        # If this path does not point to a specific subfield on an indexed property, return all the possible path
        # combinations for this field path.
        if isinstance(self.field, IndexedField):
            labels = (
                [self.label]
                if self.label
                else self.field.value_cls.get_field_by_fieldname("label").supported_choices(version=version)
            )
            subfields = [self.subfield] if self.subfield else self.field.value_cls.supported_fields(version=version)
            for label in labels:
                for subfield in subfields:
                    yield FieldPath(field=self.field, label=label, subfield=subfield)
        else:
            yield self

    @property
    def path(self):
        if self.label:
            from .indexed_properties import SingleFieldIndexedElement

            if issubclass(self.field.value_cls, SingleFieldIndexedElement) or not self.subfield:
                return f"{self.field.name}__{self.label}"
            return f"{self.field.name}__{self.label}__{self.subfield.name}"
        return self.field.name

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __str__(self):
        return self.path

    def __repr__(self):
        return self.__class__.__name__ + repr((self.field, self.label, self.subfield))

    def __hash__(self):
        return hash((self.field, self.label, self.subfield))


class FieldOrder:
    """Holds values needed to call server-side sorting on a single field path."""

    def __init__(self, field_path, reverse=False):
        """

        :param field_path: A FieldPath instance
        :param reverse: A bool
        """
        self.field_path = field_path
        self.reverse = reverse

    @classmethod
    def from_string(cls, field_path, folder):
        return cls(
            field_path=FieldPath.from_string(field_path=field_path.lstrip("-"), folder=folder, strict=True),
            reverse=field_path.startswith("-"),
        )

    def to_xml(self):
        field_order = create_element("t:FieldOrder", attrs=dict(Order="Descending" if self.reverse else "Ascending"))
        field_order.append(self.field_path.to_xml())
        return field_order


class Field(SupportedVersionInstanceMixIn, metaclass=abc.ABCMeta):
    """Holds information related to an item field."""

    value_cls = None
    is_list = False
    # Is the field a complex EWS type? Quoting the EWS FindItem docs:
    #
    #   The FindItem operation returns only the first 512 bytes of any streamable property. For Unicode, it returns
    #   the first 255 characters by using a null-terminated Unicode string. It does not return any of the message
    #   body formats or the recipient lists.
    #
    is_complex = False

    def __init__(
        self,
        name=None,
        is_required=False,
        is_required_after_save=False,
        is_read_only=False,
        is_read_only_after_send=False,
        is_searchable=True,
        is_attribute=False,
        default=None,
        *args,
        **kwargs,
    ):
        self.name = name  # Usually set by the EWSMeta metaclass
        self.default = default  # Default value if none is given
        self.is_required = is_required
        # Some fields cannot be deleted on update. Default to True if 'is_required' is set
        self.is_required_after_save = is_required or is_required_after_save
        self.is_read_only = is_read_only
        # Set this for fields that raise ErrorInvalidPropertyUpdateSentMessage on update after send. Default to True
        # if 'is_read_only' is set
        self.is_read_only_after_send = is_read_only or is_read_only_after_send
        # Define whether the field can be used in a QuerySet. For some reason, EWS disallows searching on some fields,
        # instead throwing ErrorInvalidValueForProperty
        self.is_searchable = is_searchable
        # When true, this field is treated as an XML attribute instead of an element
        self.is_attribute = is_attribute
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if version and not self.supports_version(version):
            raise InvalidFieldForVersion(
                f"Field {self.name!r} does not support EWS builds prior to {self.supported_from} (server has {version})"
            )
        if value is None:
            if self.is_required and self.default is None:
                raise ValueError(f"{self.name!r} is a required field with no default")
            return self.default
        if self.is_list:
            if not is_iterable(value):
                raise TypeError(f"Field {self.name!r} value {value!r} must be of type {list}")
            for v in value:
                if not isinstance(v, self.value_cls):
                    raise TypeError(f"Field {self.name!r} value {v!r} must be of type {self.value_cls}")
                if hasattr(v, "clean"):
                    v.clean(version=version)
        else:
            if not isinstance(value, self.value_cls):
                raise TypeError(f"Field {self.name!r} value {value!r} must be of type {self.value_cls}")
            if hasattr(value, "clean"):
                value.clean(version=version)
        return value

    @abc.abstractmethod
    def from_xml(self, elem, account):
        """Read a value from the given element"""

    @abc.abstractmethod
    def to_xml(self, value, version):
        """Convert this field to an XML element"""

    def __eq__(self, other):
        return hash(self) == hash(other)

    @abc.abstractmethod
    def __hash__(self):
        """Field instances must be hashable"""

    def __repr__(self):
        args_str = ", ".join(
            f"{f}={getattr(self, f)!r}" for f in ("name", "value_cls", "is_list", "is_complex", "default")
        )
        return f"{self.__class__.__name__}({args_str})"


class FieldURIField(Field):
    """A field that has a FieldURI value in EWS. This means it's value is contained in an XML element or attribute. It
    may additionally be a label for searching, filtering and limiting fields. In that case, the FieldURI format will be
    'itemtype:FieldName'
    """

    def __init__(self, *args, **kwargs):
        self.field_uri = kwargs.pop("field_uri", None)
        self.namespace = kwargs.pop("namespace", TNS)
        super().__init__(*args, **kwargs)
        # See all valid FieldURI values at
        # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/fielduri
        # The field_uri has a prefix when the FieldURI points to an Item field.
        if self.field_uri is None:
            self.field_uri_postfix = None
        elif ":" in self.field_uri:
            self.field_uri_postfix = self.field_uri.split(":")[1]
        else:
            self.field_uri_postfix = self.field_uri

    def _get_val_from_elem(self, elem):
        if self.is_attribute:
            return elem.get(self.field_uri) or None
        return get_xml_attr(elem, self.response_tag())

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                return xml_text_to_value(val, self.value_cls)
            except (ValueError, InvalidOperation):
                log.warning("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        return set_xml_value(field_elem, value, version=version)

    def field_uri_xml(self):
        from .properties import FieldURI

        if not self.field_uri:
            raise ValueError(f"'field_uri' value is missing on field '{self.name}'")
        return FieldURI(field_uri=self.field_uri).to_xml(version=None)

    def request_tag(self):
        if not self.field_uri_postfix:
            raise ValueError(f"'field_uri_postfix' value is missing on field '{self.name}'")
        return f"t:{self.field_uri_postfix}"

    def response_tag(self):
        if not self.field_uri_postfix:
            raise ValueError(f"'field_uri_postfix' value is missing on field '{self.name}'")
        return f"{{{self.namespace}}}{self.field_uri_postfix}"

    def __hash__(self):
        return hash(self.field_uri)


class BooleanField(FieldURIField):
    """A field that handles boolean values."""

    value_cls = bool


class IntegerField(FieldURIField):
    """A field that handles integer values."""

    value_cls = int

    def __init__(self, *args, **kwargs):
        self.min = kwargs.pop("min", None)
        self.max = kwargs.pop("max", None)
        super().__init__(*args, **kwargs)

    def _clean_single_value(self, v):
        if self.min is not None and v < self.min:
            raise ValueError(f"Value {v!r} on field {self.name!r} must be greater than {self.min}")
        if self.max is not None and v > self.max:
            raise ValueError(f"Value {v!r} on field {self.name!r} must be less than {self.max}")

    def clean(self, value, version=None):
        value = super().clean(value, version=version)
        if value is not None:
            if self.is_list:
                for v in value:
                    self._clean_single_value(v)
            else:
                self._clean_single_value(value)
        return value


class DecimalField(IntegerField):
    """A field that handles decimal values."""

    value_cls = Decimal


class EnumField(IntegerField):
    """A field type where you can enter either the 1-based index in an enum (tuple), or the enum value. Values will be
    stored internally as integers but output in XML as strings.
    """

    def __init__(self, *args, **kwargs):
        self.enum = kwargs.pop("enum")
        # Set different min/max defaults than IntegerField
        if "max" in kwargs:
            raise AttributeError("EnumField does not support the 'max' attribute")
        kwargs["min"] = kwargs.pop("min", 1)
        kwargs["max"] = kwargs["min"] + len(self.enum) - 1
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if self.is_list:
            value = list(value)  # Convert to something we can index
            for i, v in enumerate(value):
                if isinstance(v, str):
                    if v not in self.enum:
                        raise ValueError(f"List value {v!r} on field {self.name!r} must be one of {sorted(self.enum)}")
                    value[i] = self.enum.index(v) + 1
            if not value:
                raise ValueError(f"Value {value!r} on field {self.name!r} must not be empty")
            if len(value) > len(set(value)):
                raise ValueError(f"List entries {value!r} on field {self.name!r} must be unique")
        else:
            if isinstance(value, str):
                if value not in self.enum:
                    raise ValueError(f"Value {value!r} on field {self.name!r} must be one of {sorted(self.enum)}")
                value = self.enum.index(value) + 1
        return super().clean(value, version=version)

    def as_string(self, value):
        # Converts an integer in the enum to its equivalent string
        if self.is_list:
            return [self.enum[v - 1] for v in sorted(value)]
        return self.enum[value - 1]

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                if self.is_list:
                    return [self.enum.index(v) + 1 for v in val.split(" ")]
                return self.enum.index(val) + 1
            except ValueError:
                log.warning("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        if self.is_list:
            return set_xml_value(field_elem, " ".join(self.as_string(value)), version=version)
        return set_xml_value(field_elem, self.as_string(value), version=version)


class EnumListField(EnumField):
    """Like EnumField, but for lists of enum values."""

    is_list = True


class WeekdaysField(EnumListField):
    """Like EnumListField, allow a single value instead of a 1-element list."""

    def clean(self, value, version=None):
        if isinstance(value, (int, str)):
            value = [value]
        return super().clean(value, version)


class EnumAsIntField(EnumField):
    """Like EnumField, but communicates values with EWS in integers."""

    def from_xml(self, elem, account):
        return super(EnumField, self).from_xml(elem=elem, account=account)

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        return set_xml_value(field_elem, value, version=version)


class AppointmentStateField(IntegerField):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/appointmentstate"""

    NONE = "None"
    MEETING = "Meeting"
    RECEIVED = "Received"
    CANCELLED = "Canceled"
    STATES = {
        NONE: 0x0000,
        MEETING: 0x0001,
        RECEIVED: 0x0002,
        CANCELLED: 0x0004,
    }

    def from_xml(self, elem, account):
        val = super().from_xml(elem=elem, account=account)
        if val is None:
            return val
        return tuple(name for name, mask in self.STATES.items() if bool(val & mask))


class Base64Field(FieldURIField):
    """A field that handles binary data and automatically Base64 encodes and decodes the data."""

    value_cls = bytes
    is_complex = True

    def __init__(self, *args, **kwargs):
        if "is_searchable" not in kwargs:
            kwargs["is_searchable"] = False
        super().__init__(*args, **kwargs)


class MimeContentField(Base64Field):
    """Like Base64Field. This element has an optional 'CharacterSet' attribute, but it specifies the encoding of the
    base64-encoded string (which doesn't make sense since base64-encoded strings are always ASCII). We ignore it here
    because the decoded data could be in some other encoding, specified in the "Content-Type" HTTP header.
    """


class DateField(FieldURIField):
    """A field that handles date values."""

    value_cls = EWSDate

    def clean(self, value, version=None):
        # Allow plain datetime.date values as input
        if type(value) is datetime.date:
            value = self.value_cls.from_date(value)
        return super().clean(value=value, version=version)


class DateTimeBackedDateField(DateField):
    """A field that acts like a date, but where values are sent to EWS as EWSDateTime."""

    def __init__(self, *args, **kwargs):
        # Not all fields assume a default time of 00:00, so make this configurable
        self._default_time = kwargs.pop("default_time", datetime.time(0, 0))
        super().__init__(*args, **kwargs)
        # Create internal field to handle datetime-only logic
        self._datetime_field = DateTimeField(*args, **kwargs)

    def date_to_datetime(self, value):
        return self._datetime_field.value_cls.combine(value, self._default_time).replace(tzinfo=UTC)

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None and len(val) == 25:
            # This is a datetime string with timezone info, e.g. '2021-03-01T21:55:54+00:00'. We don't want to have
            # datetime values converted to UTC before converting to date. EWSDateTime.from_string() insists on
            # converting to UTC, but we don't have an EWSTimeZone we can convert the timezone info to. Instead, parse
            # the string with .fromisoformat().
            return datetime.datetime.fromisoformat(val).date()
        # Revert to default parsing of datetime strings
        res = self._datetime_field.from_xml(elem=elem, account=account)
        if res is None:
            return res
        return res.date()

    def to_xml(self, value, version):
        # Convert date to datetime
        value = self.date_to_datetime(value)
        return self._datetime_field.to_xml(value=value, version=version)


class TimeField(FieldURIField):
    """A field that handles time values."""

    value_cls = datetime.time

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            with suppress(ValueError):
                if ":" in val:
                    # Assume a string of the form HH:MM:SS
                    return datetime.datetime.strptime(val, "%H:%M:%S").time()
                # Assume an integer in minutes since midnight
                return (datetime.datetime(2000, 1, 1) + datetime.timedelta(minutes=int(val))).time()
        return self.default


class TimeDeltaField(FieldURIField):
    """A field that handles timedelta values."""

    value_cls = datetime.timedelta

    def __init__(self, *args, **kwargs):
        self.min = kwargs.pop("min", datetime.timedelta(0))
        self.max = kwargs.pop("max", datetime.timedelta(days=1))
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if self.min is not None and value < self.min:
            raise ValueError(f"Value {value!r} on field {self.name!r} must be greater than {self.min}")
        if self.max is not None and value > self.max:
            raise ValueError(f"Value {value!r} on field {self.name!r} must be less than {self.max}")
        return super().clean(value, version=version)


class DateTimeField(FieldURIField):
    """A field that handles datetime values."""

    value_cls = EWSDateTime

    def clean(self, value, version=None):
        if isinstance(value, datetime.datetime):
            if not value.tzinfo:
                raise ValueError(f"Value {value!r} on field {self.name!r} must be timezone aware")
            if type(value) is datetime.datetime:
                value = self.value_cls.from_datetime(value)
        return super().clean(value, version=version)

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                return self.value_cls.from_string(val)
            except ValueError as e:
                if isinstance(e, NaiveDateTimeNotAllowed):
                    # We encountered a naive datetime
                    if account:
                        # Convert to timezone-aware datetime using the default timezone of the account
                        tz = account.default_timezone
                        log.info("Found naive datetime %s on field %s. Assuming timezone %s", e.local_dt, self.name, tz)
                        return e.local_dt.replace(tzinfo=tz)
                    # There's nothing we can do but return the naive date. It's better than assuming e.g. UTC.
                    log.warning("Returning naive datetime %s on field %s", e.local_dt, self.name)
                    return e.local_dt
                log.info("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default


class DateOrDateTimeField(DateTimeField):
    """This field can handle both EWSDate and EWSDateTime. Used for calendar items where 'start' and 'end'
    values are conceptually dates when the calendar item is an all-day event, but datetimes in all other cases, and
    for recurrences where the returned 'start' and 'end' values may be either dates or datetimes depending on whether
    the recurring item is a task or a calendar item.

    For all-day calendar items, we assume both start and end dates are inclusive.

    For filtering kwarg validation and other places where we must decide on a specific class, we settle on datetime.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Create internal field to handle date-only logic
        self._date_field = DateField(*args, **kwargs)

    def clean(self, value, version=None):
        # Most calendar items will contain datetime values. We can't access the is_all_day value here, so CalendarItem
        # must handle that sanity check.
        if type(value) in (EWSDate, datetime.date):
            return self._date_field.clean(value=value, version=version)
        return super().clean(value=value, version=version)

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None and len(val) == 16:
            # This is a date format with timezone info, as sent by task recurrences. Eg: '2006-01-09+01:00'
            return self._date_field.from_xml(elem=elem, account=account)
        return super().from_xml(elem=elem, account=account)


class TimeZoneField(FieldURIField):
    """A field that handles timezone values."""

    value_cls = EWSTimeZone

    def clean(self, value, version=None):
        # Allow other timezone implementations as input
        if value is not None:
            value = self.value_cls.from_timezone(value)
        return super().clean(value=value, version=version)

    def from_xml(self, elem, account):
        field_elem = elem.find(self.response_tag())
        if field_elem is not None:
            tz_id = field_elem.get("Id") or field_elem.get("Name")
            try:
                return self.value_cls.from_ms_id(tz_id)
            except UnknownTimeZone:
                warnings.warn(
                    f"""\
Cannot convert value {tz_id!r} on field {self.name!r} to type {self.value_cls.__name__!r} (unknown timezone ID).
You can fix this by adding a custom entry into the timezone translation map:

from exchangelib.winzone import MS_TIMEZONE_TO_IANA_MAP, CLDR_TO_MS_TIMEZONE_MAP

# Replace "Some_Region/Some_Location" with a reasonable value from CLDR_TO_MS_TIMEZONE_MAP.keys()
MS_TIMEZONE_TO_IANA_MAP[{tz_id!r}] = "Some_Region/Some_Location"

# Your code here"""
                )
                return None
        return self.default

    def to_xml(self, value, version):
        attrs = dict(Id=value.ms_id)
        if value.ms_name:
            attrs["Name"] = value.ms_name
        return create_element(self.request_tag(), attrs=attrs)


class TextField(FieldURIField):
    """A field that stores a string value with no length limit."""

    value_cls = str
    is_complex = True


class TextListField(TextField):
    """Like TextField, but for lists of text."""

    is_list = True

    def __init__(self, *args, **kwargs):
        self.list_elem_name = kwargs.pop("list_elem_name", "String")
        super().__init__(*args, **kwargs)

    def list_elem_request_tag(self):
        return f"t:{self.list_elem_name}"

    def list_elem_response_tag(self):
        return f"{{{self.namespace}}}{self.list_elem_name}"

    def from_xml(self, elem, account):
        iter_elem = elem.find(self.response_tag())
        if iter_elem is not None:
            return get_xml_attrs(iter_elem, self.list_elem_response_tag())
        return self.default

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        for v in value:
            field_elem.append(set_xml_value(create_element(self.list_elem_request_tag()), v, version=version))
        return field_elem


class MessageField(TextField):
    """A field that handles the Message element."""

    INNER_ELEMENT_NAME = "Message"

    def from_xml(self, elem, account):
        reply = elem.find(self.response_tag())
        if reply is None:
            return None
        message = reply.find(f"{{{TNS}}}{self.INNER_ELEMENT_NAME}")
        if message is None:
            return None
        return message.text

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        message = create_element(f"t:{self.INNER_ELEMENT_NAME}")
        message.text = value
        return set_xml_value(field_elem, message, version=version)


class CharField(TextField):
    """A field that stores a string value with a limited length."""

    is_complex = False

    def __init__(self, *args, **kwargs):
        self.max_length = kwargs.pop("max_length", 255)
        if not 1 <= self.max_length <= 255:
            # A field supporting messages longer than 255 chars should be TextField
            raise ValueError("'max_length' must be in the range 1-255")
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        value = super().clean(value, version=version)
        if value is not None and len(value) > self.max_length:
            raise ValueError(f"{self.name!r} value {value!r} exceeds length {self.max_length}")
        return value


class IdField(CharField):
    """A field to hold the 'Id' and 'Changekey' attributes on 'ItemId' type items. There is no guaranteed max length,
    but we can assume 512 bytes in practice. See
    https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/ews-identifiers-in-exchange
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_length = 512  # This is above the normal 255 limit, but this is actually an attribute, not a field
        self.is_searchable = False
        self.is_attribute = True


class CharListField(TextListField):
    """Like TextListField, but for string values with a limited length."""

    def __init__(self, *args, **kwargs):
        self.max_length = kwargs.pop("max_length", 255)
        if not 1 <= self.max_length <= 255:
            # A field supporting messages longer than 255 chars should be TextField
            raise ValueError("'max_length' must be in the range 1-255")
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        value = super().clean(value, version=version)
        if value is not None:
            for v in value:
                if len(v) > self.max_length:
                    raise ValueError(f"{self.name!r} value {v!r} exceeds length {self.max_length}")
        return value


class URIField(TextField):
    """Helper to mark strings that must conform to xsd:anyURI.
    If we want a URI validator, see https://stackoverflow.com/questions/14466585/is-this-regex-correct-for-xsdanyuri
    """


class EmailAddressField(CharField):
    """A helper class used for email address string that we can use for email validation."""


class CultureField(CharField):
    """Helper to mark strings that are # RFC 1766 culture values."""


class Choice(SupportedVersionInstanceMixIn):
    """Implement versioned choices for the ChoiceField field."""

    def __init__(self, value, *args, **kwargs):
        self.value = value
        super().__init__(*args, **kwargs)


class ChoiceField(CharField):
    """Like CharField, but restricts the value to a limited set of strings."""

    def __init__(self, *args, **kwargs):
        self.choices = kwargs.pop("choices")
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        value = super().clean(value, version=version)
        if value is None:
            return None
        valid_choices = [c.value for c in self.choices]
        if version:
            valid_choices_for_version = self.supported_choices(version=version)
            if value in valid_choices_for_version:
                return value
            if value in valid_choices:
                raise InvalidChoiceForVersion(
                    f"Choice {self.name!r} only supports server versions from {self.supported_from or '*'} to "
                    f"{self.deprecated_from or '*'} (server has {version})"
                )
        else:
            if value in valid_choices:
                return value
        raise ValueError(f"Invalid choice {value!r} for field {self.name!r}. Valid choices are {sorted(valid_choices)}")

    def supported_choices(self, version):
        return tuple(c.value for c in self.choices if c.supports_version(version))


FREE_BUSY_CHOICES = [
    Choice("Free"),
    Choice("Tentative"),
    Choice("Busy"),
    Choice("OOF"),
    Choice("NoData"),
    Choice("WorkingElsewhere", supported_from=EXCHANGE_2013),
]


class FreeBusyStatusField(ChoiceField):
    """Like ChoiceField, but specifically for Free/Busy values."""

    def __init__(self, *args, **kwargs):
        kwargs["choices"] = set(FREE_BUSY_CHOICES)
        super().__init__(*args, **kwargs)


class BodyField(TextField):
    """A TextField with specific requirements for the Item body."""

    def __init__(self, *args, **kwargs):
        from .properties import Body

        self.value_cls = Body
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if value is not None and not isinstance(value, self.value_cls):
            value = self.value_cls(value)
        return super().clean(value, version=version)

    def from_xml(self, elem, account):
        from .properties import Body, HTMLBody

        field_elem = elem.find(self.response_tag())
        val = None if field_elem is None else field_elem.text or None
        if val is not None:
            body_type = field_elem.get("BodyType")
            return {Body.body_type: Body, HTMLBody.body_type: HTMLBody}[body_type](val)
        return self.default

    def to_xml(self, value, version):
        from .properties import Body, HTMLBody

        body_type = {
            Body: Body.body_type,
            HTMLBody: HTMLBody.body_type,
        }[type(value)]
        field_elem = create_element(self.request_tag(), attrs=dict(BodyType=body_type))
        return set_xml_value(field_elem, value, version=version)


class EWSElementField(FieldURIField):
    """A generic field for any EWSElement object."""

    def __init__(self, *args, **kwargs):
        self._value_cls = kwargs.pop("value_cls")
        if "namespace" not in kwargs:
            kwargs["namespace"] = self.value_cls.NAMESPACE
        super().__init__(*args, **kwargs)

    @property
    def value_cls(self):
        if isinstance(self._value_cls, str):
            # Support 'value_cls' as string to allow self-referencing classes. The class must be importable from the
            # top-level module.
            self._value_cls = getattr(import_module(self.__module__.split(".")[0]), self._value_cls)
        return self._value_cls

    def from_xml(self, elem, account):
        if self.is_list:
            iter_elem = elem.find(self.response_tag())
            if iter_elem is not None:
                return [
                    self.value_cls.from_xml(elem=e, account=account)
                    for e in iter_elem.findall(self.value_cls.response_tag())
                ]
        else:
            if self.field_uri is None:
                sub_elem = elem.find(self.value_cls.response_tag())
            else:
                sub_elem = elem.find(self.response_tag())
            if sub_elem is not None:
                return self.value_cls.from_xml(elem=sub_elem, account=account)
        return self.default

    def to_xml(self, value, version):
        if self.field_uri is None:
            return value.to_xml(version=version)
        field_elem = create_element(self.request_tag())
        return set_xml_value(field_elem, value, version=version)


class EWSElementListField(EWSElementField):
    """Like EWSElementField, but for lists of EWSElement objects."""

    is_list = True
    is_complex = True


class TransitionListField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import BaseTransition

        kwargs["value_cls"] = BaseTransition
        super().__init__(*args, **kwargs)

    def from_xml(self, elem, account):
        iter_elem = elem.find(self.response_tag()) if self.field_uri else elem
        if iter_elem is not None:
            return [
                self.value_cls.transition_model_from_tag(e.tag).from_xml(elem=e, account=account) for e in iter_elem
            ]
        return self.default


class AssociatedCalendarItemIdField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .properties import AssociatedCalendarItemId

        kwargs["value_cls"] = AssociatedCalendarItemId
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return value.to_xml(version=version)


class RecurrenceField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .recurrence import Recurrence

        kwargs["value_cls"] = Recurrence
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return value.to_xml(version=version)


class TaskRecurrenceField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .recurrence import TaskRecurrence

        kwargs["value_cls"] = TaskRecurrence
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return value.to_xml(version=version)


class ReferenceItemIdField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .properties import ReferenceItemId

        kwargs["value_cls"] = ReferenceItemId
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return value.to_xml(version=version)


class OccurrenceField(EWSElementField):
    is_complex = True


class OccurrenceListField(OccurrenceField):
    is_list = True


class MessageHeaderField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import MessageHeader

        kwargs["value_cls"] = MessageHeader
        super().__init__(*args, **kwargs)


class BaseEmailField(EWSElementField, metaclass=abc.ABCMeta):
    """Base class for EWSElement classes that have an 'email_address' field that we want to provide helpers for."""

    is_complex = True  # FindItem only returns the name, not the email address

    def clean(self, value, version=None):
        if isinstance(value, str):
            value = self.value_cls(email_address=value)
        return super().clean(value, version=version)

    def from_xml(self, elem, account):
        if self.field_uri is None:
            sub_elem = elem.find(self.value_cls.response_tag())
        else:
            sub_elem = elem.find(self.response_tag())
        if sub_elem is not None:
            if self.field_uri is not None:
                # We want the nested Mailbox, not the wrapper element
                nested_elem = sub_elem.find(self.value_cls.response_tag())
                if nested_elem is None:
                    raise ValueError(
                        f"Expected XML element {self.value_cls.response_tag()!r} missing on field {self.name!r}"
                    )
                return self.value_cls.from_xml(elem=nested_elem, account=account)
            return self.value_cls.from_xml(elem=sub_elem, account=account)
        return self.default


class EmailField(BaseEmailField):
    def __init__(self, *args, **kwargs):
        from .properties import Email

        kwargs["value_cls"] = Email
        super().__init__(*args, **kwargs)


class RecipientAddressField(BaseEmailField):
    def __init__(self, *args, **kwargs):
        from .properties import RecipientAddress

        kwargs["value_cls"] = RecipientAddress
        super().__init__(*args, **kwargs)


class MailboxField(BaseEmailField):
    def __init__(self, *args, **kwargs):
        from .properties import Mailbox

        kwargs["value_cls"] = Mailbox
        super().__init__(*args, **kwargs)


class MailboxListField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import Mailbox

        kwargs["value_cls"] = Mailbox
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if value is not None:
            value = [self.value_cls(email_address=s) if isinstance(s, str) else s for s in value]
        return super().clean(value, version=version)


class AddressListField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import Address

        kwargs["value_cls"] = Address
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if value is not None:
            value = [self.value_cls(email_address=s) if isinstance(s, str) else s for s in value]
        return super().clean(value, version=version)


class MemberListField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import Member

        kwargs["value_cls"] = Member
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        from .properties import Mailbox

        if value is not None:
            value = [self.value_cls(mailbox=Mailbox(email_address=s)) if isinstance(s, str) else s for s in value]
        return super().clean(value, version=version)


class AttendeesField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import Attendee

        kwargs["value_cls"] = Attendee
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        from .properties import Mailbox

        if value is not None:
            value = [
                self.value_cls(mailbox=Mailbox(email_address=s), response_type="Accept") if isinstance(s, str) else s
                for s in value
            ]
        return super().clean(value, version=version)


class AttachmentField(EWSElementListField):
    """A field for item attachments."""

    def __init__(self, *args, **kwargs):
        from .attachments import Attachment

        kwargs["value_cls"] = Attachment
        super().__init__(*args, **kwargs)

    def from_xml(self, elem, account):
        from .attachments import FileAttachment, ItemAttachment

        iter_elem = elem.find(self.response_tag())
        # Look for both FileAttachment and ItemAttachment
        if iter_elem is not None:
            attachments = []
            for att_type in (ItemAttachment, FileAttachment):
                attachments.extend(
                    [att_type.from_xml(elem=e, account=account) for e in iter_elem.findall(att_type.response_tag())]
                )
            return attachments
        return self.default


class LabelField(ChoiceField):
    """A field to hold the label on an IndexedElement."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_attribute = True

    def from_xml(self, elem, account):
        return elem.get(self.field_uri)


class SubField(Field):
    """A field to hold the value on an IndexedElement."""

    namespace = TNS
    value_cls = str

    def from_xml(self, elem, account):
        return elem.text

    def to_xml(self, value, version):
        return value

    @staticmethod
    def field_uri_xml(field_uri, label):
        from .properties import IndexedFieldURI

        return IndexedFieldURI(field_uri=field_uri, field_index=label).to_xml(version=None)

    def clean(self, value, version=None):
        value = super().clean(value, version=version)
        if self.is_required and not value:
            raise ValueError(f"Value for subfield {self.name!r} must be non-empty")
        return value

    def __hash__(self):
        return hash(self.name)


class EmailSubField(SubField):
    """A field to hold the value on an SingleFieldIndexedElement."""

    value_cls = str

    def from_xml(self, elem, account):
        return elem.text or elem.get("Name")  # Sometimes elem.text is empty. Exchange saves the same in 'Name' attr


class NamedSubField(SubField):
    """A field to hold the value on an MultiFieldIndexedElement."""

    value_cls = str

    def __init__(self, *args, **kwargs):
        self.field_uri = kwargs.pop("field_uri")
        if ":" in self.field_uri:
            raise ValueError("'field_uri' value must not contain a colon")
        super().__init__(*args, **kwargs)

    def from_xml(self, elem, account):
        field_elem = elem.find(self.response_tag())
        val = None if field_elem is None else field_elem.text or None
        if val is not None:
            return val
        return self.default

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        return set_xml_value(field_elem, value, version=version)

    def field_uri_xml(self, field_uri, label):
        from .properties import IndexedFieldURI

        return IndexedFieldURI(field_uri=f"{field_uri}:{self.field_uri}", field_index=label).to_xml(version=None)

    def request_tag(self):
        return f"t:{self.field_uri}"

    def response_tag(self):
        return f"{{{self.namespace}}}{self.field_uri}"


class IndexedField(EWSElementField, metaclass=abc.ABCMeta):
    """A base class for all indexed fields."""

    PARENT_ELEMENT_NAME = None

    def __init__(self, *args, **kwargs):
        from .indexed_properties import IndexedElement

        value_cls = kwargs["value_cls"]
        if not issubclass(value_cls, IndexedElement):
            raise TypeError(f"'value_cls' {value_cls!r} must be a subclass of type {IndexedElement}")
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return set_xml_value(create_element(f"t:{self.PARENT_ELEMENT_NAME}"), value, version=version)

    def response_tag(self):
        return f"{{{self.namespace}}}{self.PARENT_ELEMENT_NAME}"

    def __hash__(self):
        return hash(self.field_uri)


class EmailAddressesField(IndexedField):
    is_list = True
    is_complex = True

    PARENT_ELEMENT_NAME = "EmailAddresses"

    def __init__(self, *args, **kwargs):
        from .indexed_properties import EmailAddress

        kwargs["value_cls"] = EmailAddress
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if value is not None:
            default_labels = self.value_cls.LABEL_CHOICES
            if len(value) > len(default_labels):
                raise ValueError(f"This field can handle at most {len(default_labels)} values (value: {value})")
            tmp = []
            for s, default_label in zip(value, default_labels):
                if not isinstance(s, str):
                    tmp.append(s)
                    continue
                tmp.append(self.value_cls(email=s, label=default_label))
            value = tmp
        return super().clean(value, version=version)


class PhoneNumberField(IndexedField):
    is_list = True
    is_complex = True

    PARENT_ELEMENT_NAME = "PhoneNumbers"

    def __init__(self, *args, **kwargs):
        from .indexed_properties import PhoneNumber

        kwargs["value_cls"] = PhoneNumber
        super().__init__(*args, **kwargs)


class PhysicalAddressField(IndexedField):
    is_list = True
    is_complex = True

    PARENT_ELEMENT_NAME = "PhysicalAddresses"

    def __init__(self, *args, **kwargs):
        from .indexed_properties import PhysicalAddress

        kwargs["value_cls"] = PhysicalAddress
        super().__init__(*args, **kwargs)


class ExtendedPropertyField(Field):
    is_complex = True

    def __init__(self, *args, **kwargs):
        self.value_cls = kwargs.pop("value_cls")
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if value is None:
            if self.is_required:
                raise ValueError(f"{self.name!r} is a required field")
            return self.default
        if not isinstance(value, self.value_cls):
            # Allow keeping ExtendedProperty field values as their simple Python type, but run clean() anyway
            tmp = self.value_cls(value)
            tmp.clean(version=version)
            return value
        value.clean(version=version)
        return value

    def field_uri_xml(self):
        from .properties import ExtendedFieldURI

        cls = self.value_cls
        return ExtendedFieldURI(
            distinguished_property_set_id=cls.distinguished_property_set_id,
            property_set_id=cls.property_set_id.lower() if cls.property_set_id else None,
            property_tag=cls.property_tag_as_hex(),
            property_name=cls.property_name,
            property_id=value_to_xml_text(cls.property_id) if cls.property_id else None,
            property_type=cls.property_type,
        ).to_xml(version=None)

    def from_xml(self, elem, account):
        extended_properties = elem.findall(self.value_cls.response_tag())
        for extended_property in extended_properties:
            if self.value_cls.is_property_instance(extended_property):
                return self.value_cls.from_xml(elem=extended_property, account=account)
        return self.default

    def to_xml(self, value, version):
        extended_property = create_element(self.value_cls.request_tag())
        set_xml_value(extended_property, self.field_uri_xml(), version=version)
        if isinstance(value, self.value_cls):
            return set_xml_value(extended_property, value, version=version)
        # Allow keeping ExtendedProperty field values as their simple Python type
        return set_xml_value(extended_property, self.value_cls(value), version=version)

    def __hash__(self):
        return hash(self.name)


class ExtendedPropertyListField(ExtendedPropertyField):
    is_list = True


class ItemField(FieldURIField):
    @property
    def value_cls(self):
        from .items import Item

        return Item

    def from_xml(self, elem, account):
        from .items import ITEM_CLASSES

        for item_cls in ITEM_CLASSES:
            item_elem = elem.find(item_cls.response_tag())
            if item_elem is not None:
                return item_cls.from_xml(elem=item_elem, account=account)
        return None

    def to_xml(self, value, version):
        # We don't want to wrap in an Item element
        return value.to_xml(version=version)


class UnknownEntriesField(CharListField):
    def list_elem_tag(self):
        return f"{{{self.namespace}}}UnknownEntry"


class PermissionSetField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .properties import PermissionSet

        kwargs["value_cls"] = PermissionSet
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return value.to_xml(version=version)


class EffectiveRightsField(EWSElementField):
    def __init__(self, *args, **kwargs):
        from .properties import EffectiveRights

        kwargs["value_cls"] = EffectiveRights
        super().__init__(*args, **kwargs)


class RoutingTypeField(ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs["choices"] = {Choice("SMTP"), Choice("EX")}
        kwargs["default"] = "SMTP"
        super().__init__(*args, **kwargs)


class IdElementField(EWSElementField):
    def __init__(self, *args, **kwargs):
        kwargs["is_searchable"] = False
        kwargs["is_read_only"] = True
        super().__init__(*args, **kwargs)


class TypeValueField(FieldURIField):
    """This field type has no value_cls because values may have many types."""

    TYPES_MAP = {
        "Boolean": bool,
        "Integer32": int,
        "UnsignedInteger32": int,
        "Integer64": int,
        "UnsignedInteger64": int,
        # Python doesn't have a single-byte type to represent 'Byte'
        "ByteArray": bytes,
        "String": str,
        "StringArray": str,  # A list of strings
        "DateTime": EWSDateTime,
    }
    TYPES_MAP_REVERSED = {
        bool: "Boolean",
        int: "Integer64",
        # Python doesn't have a single-byte type to represent 'Byte'
        bytes: "ByteArray",
        str: "String",
        datetime.datetime: "DateTime",
        EWSDateTime: "DateTime",
    }

    @classmethod
    def get_type(cls, value):
        if isinstance(value, bytes) and len(value) == 1:
            # This is a single byte. Translate it to the 'Byte' type
            return "Byte"
        if is_iterable(value):
            # We don't allow generators as values, so keep the logic simple
            try:
                first = next(iter(value))
            except StopIteration:
                first = None
            value_type = f"{cls.TYPES_MAP_REVERSED[type(first)]}Array"
            if value_type not in cls.TYPES_MAP:
                raise ValueError(f"{value!r} is not a supported type")
            return value_type
        return cls.TYPES_MAP_REVERSED[type(value)]

    @classmethod
    def is_array_type(cls, value_type):
        return value_type == "StringArray"

    def clean(self, value, version=None):
        if value is None:
            if self.is_required and self.default is None:
                raise ValueError(f"{self.name!r} is a required field with no default")
            return self.default
        return value

    def from_xml(self, elem, account):
        field_elem = elem.find(self.response_tag())
        if field_elem is None:
            return self.default
        value_type_str = get_xml_attr(field_elem, f"{{{TNS}}}Type")
        value = get_xml_attr(field_elem, f"{{{TNS}}}Value")
        if value_type_str == "Byte":
            try:
                # The value is an unsigned integer in the range 0 -> 255. Convert it to a single byte
                return xml_text_to_value(value, int).to_bytes(1, "little", signed=False)
            except OverflowError as e:
                log.warning("Invalid byte value %r (%e)", value, e)
                return None
        value_type = self.TYPES_MAP[value_type_str]
        if self.is_array_type(value_type_str):
            return tuple(xml_text_to_value(value=v, value_type=value_type) for v in value.split(" "))
        return xml_text_to_value(value=value, value_type=value_type)

    def to_xml(self, value, version):
        value_type_str = self.get_type(value)
        if value_type_str == "Byte":
            # A single byte is encoded to an unsigned integer in the range 0 -> 255
            value = int.from_bytes(value, byteorder="little", signed=False)
        elif is_iterable(value):
            value = " ".join(value_to_xml_text(v) for v in value)
        field_elem = create_element(self.request_tag())
        field_elem.append(set_xml_value(create_element("t:Type"), value_type_str, version=version))
        field_elem.append(set_xml_value(create_element("t:Value"), value, version=version))
        return field_elem


class DictionaryField(FieldURIField):
    value_cls = dict

    def from_xml(self, elem, account):
        from .properties import DictionaryEntry

        iter_elem = elem.find(self.response_tag())
        if iter_elem is not None:
            entries = [
                DictionaryEntry.from_xml(elem=e, account=account)
                for e in iter_elem.findall(DictionaryEntry.response_tag())
            ]
            return {e.key: e.value for e in entries}
        return self.default

    def clean(self, value, version=None):
        if isinstance(value, dict):
            cleaned = {}
            for k, v in value.items():
                if type(k) is datetime.datetime:
                    k = EWSDateTime.from_datetime(k)
                if type(v) is datetime.datetime:
                    v = EWSDateTime.from_datetime(v)
                cleaned[k] = v
            value = cleaned
        return super().clean(value=value, version=version)

    def to_xml(self, value, version):
        from .properties import DictionaryEntry

        field_elem = create_element(self.request_tag())
        entries = [DictionaryEntry(key=k, value=v) for k, v in value.items()]
        return set_xml_value(field_elem, entries, version=version)


class PersonaPhoneNumberField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .properties import PhoneNumber

        kwargs["value_cls"] = PhoneNumber
        super().__init__(*args, **kwargs)


class BodyContentAttributedValueField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .properties import BodyContentAttributedValue

        kwargs["value_cls"] = BodyContentAttributedValue
        super().__init__(*args, **kwargs)


class StringAttributedValueField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import StringAttributedValue

        kwargs["value_cls"] = StringAttributedValue
        super().__init__(*args, **kwargs)


class PhoneNumberAttributedValueField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import PhoneNumberAttributedValue

        kwargs["value_cls"] = PhoneNumberAttributedValue
        super().__init__(*args, **kwargs)


class EmailAddressAttributedValueField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import EmailAddressAttributedValue

        kwargs["value_cls"] = EmailAddressAttributedValue
        super().__init__(*args, **kwargs)


class PostalAddressAttributedValueField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import PostalAddressAttributedValue

        kwargs["value_cls"] = PostalAddressAttributedValue
        super().__init__(*args, **kwargs)


class GenericEventListField(EWSElementField):
    """A list field that can contain all subclasses of Event."""

    is_list = True

    @property
    def _event_types_map(self):
        return {v.response_tag(): v for v in self.value_classes}

    def __init__(self, *args, **kwargs):
        from .properties import (
            CopiedEvent,
            CreatedEvent,
            DeletedEvent,
            FreeBusyChangedEvent,
            ModifiedEvent,
            MovedEvent,
            NewMailEvent,
            StatusEvent,
        )

        kwargs["value_cls"] = None  # Parent class requires this kwarg
        kwargs["namespace"] = None  # Parent class requires this kwarg
        super().__init__(*args, **kwargs)
        self.value_classes = (
            CopiedEvent,
            CreatedEvent,
            DeletedEvent,
            ModifiedEvent,
            MovedEvent,
            NewMailEvent,
            StatusEvent,
            FreeBusyChangedEvent,
        )

    def from_xml(self, elem, account):
        events = []
        for event in elem:
            # This may or may not be an event element. Could also be other child elements of Notification
            try:
                value_cls = self._event_types_map[event.tag]
            except KeyError:
                continue
            events.append(value_cls.from_xml(elem=event, account=account))
        return events or self.default


FLAG_ACTION_CHOICES = [
    Choice("Any"),
    Choice("Call"),
    Choice("DoNotForward"),
    Choice("FollowUp"),
    Choice("FYI"),
    Choice("Forward"),
    Choice("NoResponseNecessary"),
    Choice("Read"),
    Choice("Reply"),
    Choice("ReplyToAll"),
    Choice("Review"),
]


class FlaggedForActionField(ChoiceField):
    """
    A field specifies the flag for action value that
    must appear on incoming messages in order for the condition
    or exception to apply.
    """

    def __init__(self, *args, **kwargs):
        kwargs["choices"] = FLAG_ACTION_CHOICES
        super().__init__(*args, **kwargs)


IMPORTANCE_CHOICES = [
    Choice("Low"),
    Choice("Normal"),
    Choice("High"),
]


class ImportanceField(ChoiceField):
    """
    A field that describes the importance of an item or
    the aggregated importance of all items in a conversation
    in the current folder.
    """

    def __init__(self, *args, **kwargs):
        kwargs["choices"] = IMPORTANCE_CHOICES
        super().__init__(*args, **kwargs)


SENSITIVITY_CHOICES = [
    Choice("Normal"),
    Choice("Personal"),
    Choice("Private"),
    Choice("Confidential"),
]


class SensitivityField(ChoiceField):
    """A field that indicates the sensitivity level of an item."""

    def __init__(self, *args, **kwargs):
        kwargs["choices"] = SENSITIVITY_CHOICES
        super().__init__(*args, **kwargs)


class FolderActionField(EWSElementField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        from .folders import DistinguishedFolderId, Folder

        if isinstance(value, Folder):
            folder_id = value.to_id()
            if isinstance(folder_id, DistinguishedFolderId):
                value = self.value_cls(distinguished_folder_id=folder_id)
            else:
                value = self.value_cls(folder_id=folder_id)
        return super().clean(value, version=version)
