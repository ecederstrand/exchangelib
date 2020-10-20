import abc
import base64
import binascii
from collections import OrderedDict
import datetime
from decimal import Decimal, InvalidOperation
from importlib import import_module
import logging

from .errors import ErrorInvalidServerVersion
from .ewsdatetime import EWSDateTime, EWSDate, EWSTimeZone, NaiveDateTimeNotAllowed, UnknownTimeZone, UTC
from .util import create_element, get_xml_attrs, set_xml_value, value_to_xml_text, is_iterable, safe_b64decode, TNS
from .version import Build, Version, EXCHANGE_2013

log = logging.getLogger(__name__)


# DayOfWeekIndex enum. See
# https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/dayofweekindex
FIRST = 'First'
SECOND = 'Second'
THIRD = 'Third'
FOURTH = 'Fourth'
LAST = 'Last'
WEEK_NUMBERS = (FIRST, SECOND, THIRD, FOURTH, LAST)

# Month enum
JANUARY = 'January'
FEBRUARY = 'February'
MARCH = 'March'
APRIL = 'April'
MAY = 'May'
JUNE = 'June'
JULY = 'July'
AUGUST = 'August'
SEPTEMBER = 'September'
OCTOBER = 'October'
NOVEMBER = 'November'
DECEMBER = 'December'
MONTHS = (JANUARY, FEBRUARY, MARCH, APRIL, MAY, JUNE, JULY, AUGUST, SEPTEMBER, OCTOBER, NOVEMBER, DECEMBER)

# Weekday enum
MONDAY = 'Monday'
TUESDAY = 'Tuesday'
WEDNESDAY = 'Wednesday'
THURSDAY = 'Thursday'
FRIDAY = 'Friday'
SATURDAY = 'Saturday'
SUNDAY = 'Sunday'
WEEKDAY_NAMES = (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY)

# Used for weekday recurrences except weekly recurrences. E.g. for "First WeekendDay in March"
DAY = 'Day'
WEEK_DAY = 'Weekday'  # Non-weekend day
WEEKEND_DAY = 'WeekendDay'
EXTRA_WEEKDAY_OPTIONS = (DAY, WEEK_DAY, WEEKEND_DAY)

# DaysOfWeek enum: See
# https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/daysofweek-daysofweektype
WEEKDAYS = WEEKDAY_NAMES + EXTRA_WEEKDAY_OPTIONS


def split_field_path(field_path):
    """

    Args:
      field_path:

    Returns:
      Examples:
      'start' -> ('start', None, None)
      'phone_numbers__PrimaryPhone' -> ('phone_numbers', 'PrimaryPhone', None)
      'physical_addresses__Home__street' -> ('physical_addresses', 'Home', 'street')

    """
    if not isinstance(field_path, str):
        raise ValueError("Field path %r must be a string" % field_path)
    search_parts = field_path.split('__')
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
    # Takes the name of a field, or '__'-delimited path to a subfield, and returns the corresponding Field object,
    # label and SubField object
    from .indexed_properties import SingleFieldIndexedElement, MultiFieldIndexedElement
    fieldname, label, subfieldname = split_field_path(field_path)
    field = folder.get_item_field_by_fieldname(fieldname)
    subfield = None
    if isinstance(field, IndexedField):
        if strict and not label:
            raise ValueError(
                "IndexedField path '%s' must specify label, e.g. '%s__%s'"
                % (field_path, fieldname, field.value_cls.get_field_by_fieldname('label').default)
            )
        valid_labels = field.value_cls.get_field_by_fieldname('label').supported_choices(
            version=folder.account.version
        )
        if label and label not in valid_labels:
            raise ValueError(
                "Label '%s' on IndexedField path '%s' must be one of %s"
                % (label, field_path, ', '.join(valid_labels))
            )
        if issubclass(field.value_cls, MultiFieldIndexedElement):
            if strict and not subfieldname:
                raise ValueError(
                    "IndexedField path '%s' must specify subfield, e.g. '%s__%s__%s'"
                    % (field_path, fieldname, label, field.value_cls.FIELDS[1].name)
                )

            if subfieldname:
                try:
                    subfield = field.value_cls.get_field_by_fieldname(subfieldname)
                except ValueError:
                    fnames = ', '.join(f.name for f in field.value_cls.supported_fields(
                        version=folder.account.version
                    ))
                    raise ValueError(
                        "Subfield '%s' on IndexedField path '%s' must be one of %s"
                        % (subfieldname, field_path, fnames)
                    )
        else:
            if not issubclass(field.value_cls, SingleFieldIndexedElement):
                raise ValueError("'field.value_cls' %r must be an SingleFieldIndexedElement instance" % field.value_cls)
            if subfieldname:
                raise ValueError(
                    "IndexedField path '%s' must not specify subfield, e.g. just '%s__%s'"
                    % (field_path, fieldname, label)
                )
            subfield = field.value_cls.value_field(version=folder.account.version)
    else:
        if label or subfieldname:
            raise ValueError(
                "Field path '%s' must not specify label or subfield, e.g. just '%s'"
                % (field_path, fieldname)
            )
    return field, label, subfield


class FieldPath:
    """Holds values needed to point to a single field. For indexed properties, we allow setting either field,
    field and label, or field, label and subfield. This allows pointing to either the full indexed property set, a
    property with a specific label, or a particular subfield field on that property.

    """

    def __init__(self, field, label=None, subfield=None):
        # 'label' and 'subfield' are only used for IndexedField fields
        if not isinstance(field, (FieldURIField, ExtendedPropertyField)):
            raise ValueError("'field' %r must be an FieldURIField, of ExtendedPropertyField instance" % field)
        if label and not isinstance(label, str):
            raise ValueError("'label' %r must be a %s instance" % (label, str))
        if subfield and not isinstance(subfield, SubField):
            raise ValueError("'subfield' %r must be a SubField instance" % subfield)
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
            for subitem in getattr(item, self.field.name):
                if subitem.label == self.label:
                    if self.subfield:
                        return getattr(subitem, self.subfield.name)
                    return subitem
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
                raise ValueError("Field path for indexed field '%s' is missing label and/or subfield" % self.field.name)
            return self.subfield.field_uri_xml(field_uri=self.field.field_uri, label=self.label)
        else:
            return self.field.field_uri_xml()

    def expand(self, version):
        # If this path does not point to a specific subfield on an indexed property, return all the possible path
        # combinations for this field path.
        if isinstance(self.field, IndexedField):
            labels = [self.label] if self.label \
                else self.field.value_cls.get_field_by_fieldname('label').supported_choices(version=version)
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
                return '%s__%s' % (self.field.name, self.label)
            return '%s__%s__%s' % (self.field.name, self.label, self.subfield.name)
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
    """Holds values needed to call server-side sorting on a single field path"""

    def __init__(self, field_path, reverse=False):
        if not isinstance(field_path, FieldPath):
            raise ValueError("'field_path' %r must be a FieldPath instance" % field_path)
        if not isinstance(reverse, bool):
            raise ValueError("'reverse' %r must be a boolean" % reverse)
        self.field_path = field_path
        self.reverse = reverse

    @classmethod
    def from_string(cls, field_path, folder):
        return cls(
            field_path=FieldPath.from_string(field_path=field_path.lstrip('-'), folder=folder, strict=True),
            reverse=field_path.startswith('-')
        )

    def to_xml(self):
        field_order = create_element('t:FieldOrder', attrs=dict(Order='Descending' if self.reverse else 'Ascending'))
        field_order.append(self.field_path.to_xml())
        return field_order


class Field(metaclass=abc.ABCMeta):
    """Holds information related to an item field"""
    value_cls = None
    is_list = False
    # Is the field a complex EWS type? Quoting the EWS FindItem docs:
    #
    #   The FindItem operation returns only the first 512 bytes of any streamable property. For Unicode, it returns
    #   the first 255 characters by using a null-terminated Unicode string. It does not return any of the message
    #   body formats or the recipient lists.
    #
    is_complex = False

    def __init__(self, name, is_required=False, is_required_after_save=False, is_read_only=False,
                 is_read_only_after_send=False, is_searchable=True, is_attribute=False, default=None,
                 supported_from=None, deprecated_from=None):
        self.name = name
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
        # The Exchange build when this field was introduced. When talking with versions prior to this version,
        # we will ignore this field.
        if supported_from is not None and not isinstance(supported_from, Build):
            raise ValueError("'supported_from' %r must be a Build instance" % supported_from)
        self.supported_from = supported_from
        # The Exchange build when this field was deprecated. When talking with versions at or later than this version,
        # we will ignore this field.
        if deprecated_from is not None and not isinstance(deprecated_from, Build):
            raise ValueError("'deprecated_from' %r must be a Build instance" % deprecated_from)
        self.deprecated_from = deprecated_from

    def clean(self, value, version=None):
        if version and not self.supports_version(version):
            raise ErrorInvalidServerVersion("Field '%s' does not support EWS builds prior to %s (server has %s)" % (
                self.name, self.supported_from, version))
        if value is None:
            if self.is_required and self.default is None:
                raise ValueError("'%s' is a required field with no default" % self.name)
            return self.default
        if self.is_list:
            if not is_iterable(value):
                raise ValueError("Field '%s' value %r must be a list" % (self.name, value))
            for v in value:
                if not isinstance(v, self.value_cls):
                    raise TypeError("Field '%s' value %r must be of type %s" % (self.name, v, self.value_cls))
                if hasattr(v, 'clean'):
                    v.clean(version=version)
        else:
            if not isinstance(value, self.value_cls):
                raise TypeError("Field '%s' value %r must be of type %s" % (self.name, value, self.value_cls))
            if hasattr(value, 'clean'):
                value.clean(version=version)
        return value

    @abc.abstractmethod
    def from_xml(self, elem, account):
        raise NotImplementedError()

    @abc.abstractmethod
    def to_xml(self, value, version):
        raise NotImplementedError()

    def supports_version(self, version):
        # 'version' is a Version instance, for convenience by callers
        if not isinstance(version, Version):
            raise ValueError("'version' %r must be a Version instance" % version)
        if self.supported_from and version.build < self.supported_from:
            return False
        if self.deprecated_from and version.build >= self.deprecated_from:
            return False
        return True

    def __eq__(self, other):
        return hash(self) == hash(other)

    @abc.abstractmethod
    def __hash__(self):
        raise NotImplementedError()

    def __repr__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join('%s=%r' % (f, getattr(self, f)) for f in (
            'name', 'value_cls', 'is_list', 'is_complex', 'default'))


class FieldURIField(Field):
    def __init__(self, *args, **kwargs):
        self.field_uri = kwargs.pop('field_uri', None)
        self.namespace = kwargs.pop('namespace', TNS)
        super().__init__(*args, **kwargs)
        # See all valid FieldURI values at
        # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/fielduri
        # The field_uri has a prefix when the FieldURI points to an Item field.
        if self.field_uri is None:
            self.field_uri_postfix = None
        elif ':' in self.field_uri:
            self.field_uri_postfix = self.field_uri.split(':')[1]
        else:
            self.field_uri_postfix = self.field_uri

    def _get_val_from_elem(self, elem):
        if self.is_attribute:
            return elem.get(self.field_uri)
        field_elem = elem.find(self.response_tag())
        return None if field_elem is None else field_elem.text or None

    def from_xml(self, elem, account):
        raise NotImplementedError()

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        return set_xml_value(field_elem, value, version=version)

    def field_uri_xml(self):
        from .properties import FieldURI
        if not self.field_uri:
            raise ValueError("'field_uri' value is missing")
        return FieldURI(field_uri=self.field_uri).to_xml(version=None)

    def request_tag(self):
        if not self.field_uri_postfix:
            raise ValueError("'field_uri_postfix' value is missing")
        return 't:%s' % self.field_uri_postfix

    def response_tag(self):
        if not self.field_uri_postfix:
            raise ValueError("'field_uri_postfix' value is missing")
        return '{%s}%s' % (self.namespace, self.field_uri_postfix)

    def __hash__(self):
        return hash(self.field_uri)


class BooleanField(FieldURIField):
    value_cls = bool

    def __init__(self, *args, **kwargs):
        self.true_val = kwargs.pop('true_val', 'true')
        self.false_val = kwargs.pop('false_val', 'false')
        super().__init__(*args, **kwargs)

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                return {
                    self.true_val: True,
                    self.false_val: False,
                }[val.lower()]
            except KeyError:
                log.warning("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default


class OnOffField(BooleanField):
    def __init__(self, *args, **kwargs):
        kwargs['true_val'] = 'on'
        kwargs['false_val'] = 'off'
        super().__init__(*args, **kwargs)


class IntegerField(FieldURIField):
    value_cls = int

    def __init__(self, *args, **kwargs):
        self.min = kwargs.pop('min', None)
        self.max = kwargs.pop('max', None)
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        value = super().clean(value, version=version)
        if value is not None:
            if self.is_list:
                for v in value:
                    if self.min is not None and v < self.min:
                        raise ValueError(
                            "Value %r on field '%s' must be greater than %s" % (v, self.name, self.min))
                    if self.max is not None and v > self.max:
                        raise ValueError("Value %r on field '%s' must be less than %s" % (v, self.name, self.max))
            else:
                if self.min is not None and value < self.min:
                    raise ValueError("Value %r on field '%s' must be greater than %s" % (value, self.name, self.min))
                if self.max is not None and value > self.max:
                    raise ValueError("Value %r on field '%s' must be less than %s" % (value, self.name, self.max))
        return value

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                return self.value_cls(val)
            except (ValueError, InvalidOperation):
                log.warning("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default


class DecimalField(IntegerField):
    value_cls = Decimal


class EnumField(IntegerField):
    """A field type where you can enter either the 1-based index in an enum (tuple), or the enum value. Values will be
    stored internally as integers but output in XML as strings.

    """

    def __init__(self, *args, **kwargs):
        self.enum = kwargs.pop('enum')
        # Set different min/max defaults than IntegerField
        if 'max' in kwargs:
            raise AttributeError("EnumField does not support the 'max' attribute")
        kwargs['min'] = kwargs.pop('min', 1)
        kwargs['max'] = kwargs['min'] + len(self.enum) - 1
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if self.is_list:
            value = list(value)  # Convert to something we can index
            for i, v in enumerate(value):
                if isinstance(v, str):
                    if v not in self.enum:
                        raise ValueError(
                            "List value '%s' on field '%s' must be one of %s" % (v, self.name, self.enum))
                    value[i] = self.enum.index(v) + 1
            if not value:
                raise ValueError("Value '%s' on field '%s' must not be empty" % (value, self.name))
            if len(value) > len(set(value)):
                raise ValueError("List entries '%s' on field '%s' must be unique" % (value, self.name))
        else:
            if isinstance(value, str):
                if value not in self.enum:
                    raise ValueError(
                        "Value '%s' on field '%s' must be one of %s" % (value, self.name, self.enum))
                value = self.enum.index(value) + 1
        return super().clean(value, version=version)

    def as_string(self, value):
        # Converts an integer in the enum to its equivalent string
        if isinstance(value, str):
            return value
        if self.is_list:
            return [self.enum[v - 1] for v in sorted(value)]
        return self.enum[value - 1]

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                if self.is_list:
                    return [self.enum.index(v) + 1 for v in val.split(' ')]
                return self.enum.index(val) + 1
            except ValueError:
                log.warning("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        if self.is_list:
            return set_xml_value(field_elem, ' '.join(self.as_string(value)), version=version)
        return set_xml_value(field_elem, self.as_string(value), version=version)


class EnumListField(EnumField):
    is_list = True


class EnumAsIntField(EnumField):
    """Like EnumField, but communicates values with EWS in integers"""

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                log.warning("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        return set_xml_value(field_elem, value, version=version)


class AppointmentStateField(IntegerField):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/appointmentstate
    NONE = 'None'
    MEETING = 'Meeting'
    RECEIVED = 'Received'
    CANCELLED = 'Cancelled'
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
    value_cls = bytes
    is_complex = True

    def __init__(self, *args, **kwargs):
        if 'is_searchable' not in kwargs:
            kwargs['is_searchable'] = False
        super().__init__(*args, **kwargs)

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                return safe_b64decode(val)
            except (TypeError, binascii.Error):
                log.warning("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        return set_xml_value(field_elem, base64.b64encode(value).decode('ascii'), version=version)


class MimeContentField(Base64Field):
    # This element has an optional 'CharacterSet' attribute, but it specifies the encoding of the base64-encoded
    # string (which doesn't make sense since base64 encoded strings are always ASCII). We ignore it here because
    # the decoded data could be in some other encoding, specified in the "Content-Type:" header.
    pass


class DateField(FieldURIField):
    value_cls = EWSDate

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                return self.value_cls.from_string(val)
            except ValueError:
                log.warning("Cannot convert value '%s' on field '%s' to type %s", val, self.name, self.value_cls)
                return None
        return self.default


class DateTimeBackedDateField(FieldURIField):
    # A field that acts like a date, but where values are sent to EWS as EWSDateTime.
    value_cls = datetime.date

    def __init__(self, *args, **kwargs):
        # Not all fields assume a default tim of 00:00, so make this configurable
        self._default_time = kwargs.pop('default_time', datetime.time(0, 0))
        super().__init__(*args, **kwargs)
        # Create internal field to handle datetime-only logic
        self._datetime_field = DateTimeField(*args, **kwargs)

    def date_to_datetime(self, value):
        return self._datetime_field.value_cls.combine(value, self._default_time).replace(tzinfo=UTC)

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None and len(val) == 25:
            # This is a datetime string with timezone info. We don't want to have datetime values converted to UTC
            # before converting to date. EWSDateTime.from_string() insists on converting to UTC, but we don't have an
            # EWSTimeZone we can convert the timezone info to. Instead, parse the string manually when we have a
            # datetime string with timezone info.
            return EWSDate.from_date(datetime.datetime.fromisoformat(val).date())
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
    value_cls = datetime.time

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                if ':' in val:
                    # Assume a string of the form HH:MM:SS
                    return datetime.datetime.strptime(val, '%H:%M:%S').time()
                else:
                    # Assume an integer in minutes since midnight
                    return (datetime.datetime(2000, 1, 1) + datetime.timedelta(minutes=int(val))).time()
            except ValueError:
                pass
        return self.default


class DateTimeField(FieldURIField):
    value_cls = EWSDateTime

    def clean(self, value, version=None):
        if value is not None and isinstance(value, self.value_cls) and not value.tzinfo:
            raise ValueError("Value '%s' on field '%s' must be timezone aware" % (value, self.name))
        return super().clean(value, version=version)

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            try:
                return self.value_cls.from_string(val)
            except ValueError as e:
                if isinstance(e, NaiveDateTimeNotAllowed):
                    # We encountered a naive datetime
                    local_dt = e.args[0]
                    if account:
                        # Convert to timezone-aware datetime using the default timezone of the account
                        tz = account.default_timezone
                        log.info('Found naive datetime %s on field %s. Assuming timezone %s', local_dt, self.name, tz)
                        return local_dt.replace(tzinfo=tz)
                    # There's nothing we can do but return the naive date. It's better than assuming e.g. UTC.
                    log.warning('Returning naive datetime %s on field %s', local_dt, self.name)
                    return local_dt
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
        if type(value) == EWSDate:
            return self._date_field.clean(value=value, version=version)
        return super().clean(value=value, version=version)

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None and len(val) == 16:
            # This is a date format with timezone info, as sent by task recurrences. Eg: '2006-01-09+01:00'
            return self._date_field.from_xml(elem=elem, account=account)
        return super().from_xml(elem=elem, account=account)


class TimeZoneField(FieldURIField):
    value_cls = EWSTimeZone

    def from_xml(self, elem, account):
        field_elem = elem.find(self.response_tag())
        if field_elem is not None:
            ms_id = field_elem.get('Id')
            ms_name = field_elem.get('Name')
            try:
                return self.value_cls.from_ms_id(ms_id or ms_name)
            except UnknownTimeZone:
                log.warning(
                    "Cannot convert value '%s' on field '%s' to type %s (unknown timezone ID)",
                    (ms_id or ms_name), self.name, self.value_cls
                )
                return None
        return self.default

    def to_xml(self, value, version):
        attrs = OrderedDict([('Id', value.ms_id)])
        if value.ms_name:
            attrs['Name'] = value.ms_name
        return create_element(self.request_tag(), attrs=attrs)


class TextField(FieldURIField):
    """A field that stores a string value with no length limit"""
    value_cls = str
    is_complex = True

    def from_xml(self, elem, account):
        val = self._get_val_from_elem(elem)
        if val is not None:
            return val
        return self.default


class TextListField(TextField):
    is_list = True

    def from_xml(self, elem, account):
        iter_elem = elem.find(self.response_tag())
        if iter_elem is not None:
            return get_xml_attrs(iter_elem, '{%s}String' % TNS)
        return self.default


class MessageField(TextField):
    INNER_ELEMENT_NAME = 'Message'

    def from_xml(self, elem, account):
        reply = elem.find(self.response_tag())
        if reply is None:
            return None
        message = reply.find('{%s}%s' % (TNS, self.INNER_ELEMENT_NAME))
        if message is None:
            return None
        return message.text

    def to_xml(self, value, version):
        field_elem = create_element(self.request_tag())
        message = create_element('t:%s' % self.INNER_ELEMENT_NAME)
        message.text = value
        return set_xml_value(field_elem, message, version=version)


class CharField(TextField):
    """A field that stores a string value with a limited length"""
    is_complex = False

    def __init__(self, *args, **kwargs):
        self.max_length = kwargs.pop('max_length', 255)
        if not 1 <= self.max_length <= 255:
            # A field supporting messages longer than 255 chars should be TextField
            raise ValueError("'max_length' must be in the range 1-255")
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        value = super().clean(value, version=version)
        if value is not None:
            if self.is_list:
                for v in value:
                    if len(v) > self.max_length:
                        raise ValueError("'%s' value '%s' exceeds length %s" % (self.name, v, self.max_length))
            else:
                if len(value) > self.max_length:
                    raise ValueError("'%s' value '%s' exceeds length %s" % (self.name, value, self.max_length))
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


class CharListField(CharField):
    is_list = True

    def list_elem_tag(self):
        return '{%s}String' % self.namespace

    def from_xml(self, elem, account):
        iter_elem = elem.find(self.response_tag())
        if iter_elem is not None:
            return get_xml_attrs(iter_elem, self.list_elem_tag())
        return self.default


class URIField(TextField):
    """Helper to mark strings that must conform to xsd:anyURI
    If we want an URI validator, see http://stackoverflow.com/questions/14466585/is-this-regex-correct-for-xsdanyuri

    """
    pass


class EmailAddressField(CharField):
    """A helper class used for email address string that we can use for email validation"""
    pass


class CultureField(CharField):
    """Helper to mark strings that are # RFC 1766 culture values."""
    pass


class Choice:
    """Implements versioned choices for the ChoiceField field"""

    def __init__(self, value, supported_from=None):
        self.value = value
        self.supported_from = supported_from

    def supports_version(self, version):
        # 'version' is a Version instance, for convenience by callers
        if not isinstance(version, Version):
            raise ValueError("'version' %r must be a Version instance" % version)
        if not self.supported_from:
            return True
        return version.build >= self.supported_from


class ChoiceField(CharField):
    def __init__(self, *args, **kwargs):
        self.choices = kwargs.pop('choices')
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        value = super().clean(value, version=version)
        if value is None:
            return None
        valid_choices = list(c.value for c in self.choices)
        if version:
            valid_choices_for_version = self.supported_choices(version=version)
            if value in valid_choices_for_version:
                return value
            if value in valid_choices:
                raise ErrorInvalidServerVersion("Choice '%s' only supports EWS builds from %s to %s (server has %s)" % (
                    self.name, self.supported_from or '*', self.deprecated_from or '*', version))
        else:
            if value in valid_choices:
                return value
        raise ValueError("Invalid choice '%s' for field '%s'. Valid choices are: %s" % (
            value, self.name, ', '.join(valid_choices)
        ))

    def supported_choices(self, version):
        return list(c.value for c in self.choices if c.supports_version(version))


FREE_BUSY_CHOICES = [Choice('Free'), Choice('Tentative'), Choice('Busy'), Choice('OOF'), Choice('NoData'),
                     Choice('WorkingElsewhere', supported_from=EXCHANGE_2013)]


class FreeBusyStatusField(ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs['choices'] = set(FREE_BUSY_CHOICES)
        super().__init__(*args, **kwargs)


class BodyField(TextField):
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
            body_type = field_elem.get('BodyType')
            return {
                Body.body_type: Body,
                HTMLBody.body_type: HTMLBody,
            }[body_type](val)
        return self.default

    def to_xml(self, value, version):
        from .properties import Body, HTMLBody
        field_elem = create_element(self.request_tag())
        body_type = {
            Body: Body.body_type,
            HTMLBody: HTMLBody.body_type,
        }[type(value)]
        field_elem.set('BodyType', body_type)
        return set_xml_value(field_elem, value, version=version)


class EWSElementField(FieldURIField):
    def __init__(self, *args, **kwargs):
        self._value_cls = kwargs.pop('value_cls')
        if 'namespace' not in kwargs:
            kwargs['namespace'] = self.value_cls.NAMESPACE
        super().__init__(*args, **kwargs)

    @property
    def value_cls(self):
        if isinstance(self._value_cls, str):
            # Support 'value_cls' as string to allow self-referencing classes. The class must be importable from the
            # top-level module.
            self._value_cls = getattr(import_module(self.__module__.split('.')[0]), self._value_cls)
        return self._value_cls

    def from_xml(self, elem, account):
        if self.is_list:
            iter_elem = elem.find(self.response_tag())
            if iter_elem is not None:
                return [self.value_cls.from_xml(elem=e, account=account)
                        for e in iter_elem.findall(self.value_cls.response_tag())]
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
    is_list = True
    is_complex = True


class AssociatedCalendarItemIdField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .properties import AssociatedCalendarItemId
        kwargs['value_cls'] = AssociatedCalendarItemId
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return value.to_xml(version=version)


class RecurrenceField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .recurrence import Recurrence
        kwargs['value_cls'] = Recurrence
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return value.to_xml(version=version)


class TaskRecurrenceField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .recurrence import TaskRecurrence
        kwargs['value_cls'] = TaskRecurrence
        super().__init__(*args, **kwargs)

    def to_xml(self, value, version):
        return value.to_xml(version=version)


class ReferenceItemIdField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .properties import ReferenceItemId
        kwargs['value_cls'] = ReferenceItemId
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
        kwargs['value_cls'] = MessageHeader
        super().__init__(*args, **kwargs)


class BaseEmailField(EWSElementField):
    """A base class for EWSElement classes that have an 'email_address' field that we want to provide helpers for"""

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
                        'Expected XML element %r missing on field %r' % (self.value_cls.response_tag(), self.name)
                    )
                return self.value_cls.from_xml(elem=nested_elem, account=account)
            return self.value_cls.from_xml(elem=sub_elem, account=account)
        return self.default


class EmailField(BaseEmailField):
    def __init__(self, *args, **kwargs):
        from .properties import Email
        kwargs['value_cls'] = Email
        super().__init__(*args, **kwargs)


class RecipientAddressField(BaseEmailField):
    def __init__(self, *args, **kwargs):
        from .properties import RecipientAddress
        kwargs['value_cls'] = RecipientAddress
        super().__init__(*args, **kwargs)


class MailboxField(BaseEmailField):
    def __init__(self, *args, **kwargs):
        from .properties import Mailbox
        kwargs['value_cls'] = Mailbox
        super().__init__(*args, **kwargs)


class MailboxListField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import Mailbox
        kwargs['value_cls'] = Mailbox
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if value is not None:
            value = [self.value_cls(email_address=s) if isinstance(s, str) else s for s in value]
        return super().clean(value, version=version)


class MemberListField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import Member
        kwargs['value_cls'] = Member
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if value is not None:
            from .properties import Mailbox
            value = [
                self.value_cls(mailbox=Mailbox(email_address=s)) if isinstance(s, str) else s for s in value
            ]
        return super().clean(value, version=version)


class AttendeesField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .properties import Attendee
        kwargs['value_cls'] = Attendee
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        from .properties import Mailbox
        if value is not None:
            value = [self.value_cls(mailbox=Mailbox(email_address=s), response_type='Accept')
                     if isinstance(s, str) else s for s in value]
        return super().clean(value, version=version)


class AttachmentField(EWSElementListField):
    def __init__(self, *args, **kwargs):
        from .attachments import Attachment
        kwargs['value_cls'] = Attachment
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
    """A field to hold the label on an IndexedElement"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_attribute = True

    def from_xml(self, elem, account):
        return elem.get(self.field_uri)


class SubField(Field):
    namespace = TNS

    # A field to hold the value on an SingleFieldIndexedElement
    value_cls = str

    def from_xml(self, elem, account):
        return elem.text

    def to_xml(self, value, version):
        return value

    @staticmethod
    def field_uri_xml(field_uri, label):
        from .properties import IndexedFieldURI
        return IndexedFieldURI(field_uri=field_uri, field_index=label).to_xml(version=None)

    def __hash__(self):
        return hash(self.name)


class EmailSubField(SubField):
    """A field to hold the value on an SingleFieldIndexedElement"""
    value_cls = str

    def from_xml(self, elem, account):
        return elem.text or elem.get('Name')  # Sometimes elem.text is empty. Exchange saves the same in 'Name' attr


class NamedSubField(SubField):
    """A field to hold the value on an MultiFieldIndexedElement"""
    value_cls = str

    def __init__(self, *args, **kwargs):
        self.field_uri = kwargs.pop('field_uri')
        if ':' in self.field_uri:
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
        return IndexedFieldURI(field_uri='%s:%s' % (field_uri, self.field_uri), field_index=label).to_xml(version=None)

    def request_tag(self):
        return 't:%s' % self.field_uri

    def response_tag(self):
        return '{%s}%s' % (self.namespace, self.field_uri)


class IndexedField(EWSElementField):
    PARENT_ELEMENT_NAME = None

    def to_xml(self, value, version):
        return set_xml_value(create_element('t:%s' % self.PARENT_ELEMENT_NAME), value, version)

    def field_uri_xml(self):
        # Callers must call field_uri_xml() on the subfield
        raise NotImplementedError()

    def response_tag(self):
        return '{%s}%s' % (self.namespace, self.PARENT_ELEMENT_NAME)

    def __hash__(self):
        return hash(self.field_uri)


class EmailAddressesField(IndexedField):
    is_list = True

    PARENT_ELEMENT_NAME = 'EmailAddresses'

    def __init__(self, *args, **kwargs):
        from .indexed_properties import EmailAddress
        kwargs['value_cls'] = EmailAddress
        super().__init__(*args, **kwargs)

    def field_uri_xml(self):
        raise NotImplementedError()

    def clean(self, value, version=None):
        if value is not None:
            default_labels = self.value_cls.LABEL_CHOICES
            if len(value) > len(default_labels):
                raise ValueError('This field can handle at most %s values (value: %r)' % (len(default_labels), value))
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

    PARENT_ELEMENT_NAME = 'PhoneNumbers'

    def __init__(self, *args, **kwargs):
        from .indexed_properties import PhoneNumber
        kwargs['value_cls'] = PhoneNumber
        super().__init__(*args, **kwargs)

    def field_uri_xml(self):
        raise NotImplementedError()


class PhysicalAddressField(IndexedField):
    is_list = True

    PARENT_ELEMENT_NAME = 'PhysicalAddresses'

    def __init__(self, *args, **kwargs):
        from .indexed_properties import PhysicalAddress
        kwargs['value_cls'] = PhysicalAddress
        super().__init__(*args, **kwargs)

    def field_uri_xml(self):
        raise NotImplementedError()


class ExtendedPropertyField(Field):
    def __init__(self, *args, **kwargs):
        self.value_cls = kwargs.pop('value_cls')
        super().__init__(*args, **kwargs)

    def clean(self, value, version=None):
        if value is None:
            if self.is_required:
                raise ValueError("'%s' is a required field" % self.name)
            return self.default
        elif not isinstance(value, self.value_cls):
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
            set_xml_value(extended_property, value, version=version)
        else:
            # Allow keeping ExtendedProperty field values as their simple Python type
            set_xml_value(extended_property, self.value_cls(value), version=version)
        return extended_property

    def __hash__(self):
        return hash(self.name)


class ItemField(FieldURIField):
    @property
    def value_cls(self):
        # This is a workaround for circular imports. Item
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
        return '{%s}UnknownEntry' % self.namespace


class PermissionSetField(EWSElementField):
    is_complex = True

    def __init__(self, *args, **kwargs):
        from .properties import PermissionSet
        kwargs['value_cls'] = PermissionSet
        super().__init__(*args, **kwargs)


class EffectiveRightsField(EWSElementField):
    def __init__(self, *args, **kwargs):
        from .properties import EffectiveRights
        kwargs['value_cls'] = EffectiveRights
        super().__init__(*args, **kwargs)


class BuildField(CharField):
    def __init__(self, *args, **kwargs):
        from .version import Build
        super().__init__(*args, **kwargs)
        self.value_cls = Build

    def from_xml(self, elem, account):
        val = super().from_xml(elem=elem, account=account)
        if val:
            try:
                return self.value_cls.from_hex_string(val)
            except (TypeError, ValueError):
                log.warning('Invalid server version string: %r', val)
        return val


class ProtocolListField(EWSElementListField):
    # There is not containing element for this field. Just multiple 'Protocol' elements on the 'Account' element.
    def __init__(self, *args, **kwargs):
        from .autodiscover.properties import Protocol
        kwargs['value_cls'] = Protocol
        super().__init__(*args, **kwargs)

    def from_xml(self, elem, account):
        return [self.value_cls.from_xml(elem=e, account=account) for e in elem.findall(self.value_cls.response_tag())]


class RoutingTypeField(ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs['choices'] = {Choice('SMTP'), Choice('EX')}
        kwargs['default'] = 'SMTP'
        super().__init__(*args, **kwargs)


class IdElementField(EWSElementField):
    def __init__(self, *args, **kwargs):
        kwargs['is_searchable'] = False
        kwargs['is_read_only'] = True
        super().__init__(*args, **kwargs)
