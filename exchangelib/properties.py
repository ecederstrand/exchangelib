from __future__ import unicode_literals

import abc
import binascii
import codecs
import datetime
from inspect import getmro
import logging
import struct
from threading import Lock

from future.utils import PY2
from six import text_type, string_types

from .fields import SubField, TextField, EmailAddressField, ChoiceField, DateTimeField, EWSElementField, MailboxField, \
    Choice, BooleanField, IdField, ExtendedPropertyField, IntegerField, TimeField, EnumField, CharField, EmailField, \
    EWSElementListField, EnumListField, FreeBusyStatusField, UnknownEntriesField, MessageField, RecipientAddressField, \
    WEEKDAY_NAMES, FieldPath, Field
from .util import get_xml_attr, create_element, set_xml_value, value_to_xml_text, MNS, TNS
from .version import EXCHANGE_2013

log = logging.getLogger(__name__)


class InvalidField(ValueError):
    pass


class InvalidFieldForVersion(ValueError):
    pass


class Body(text_type):
    # Helper to mark the 'body' field as a complex attribute.
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/body
    body_type = 'Text'

    def __add__(self, other):
        # Make sure Body('') + 'foo' returns a Body type
        return self.__class__(super(Body, self).__add__(other))

    def __mod__(self, other):
        # Make sure Body('%s') % 'foo' returns a Body type
        return self.__class__(super(Body, self).__mod__(other))

    def format(self, *args, **kwargs):
        # Make sure Body('{}').format('foo') returns a Body type
        return self.__class__(super(Body, self).format(*args, **kwargs))


class HTMLBody(Body):
    # Helper to mark the 'body' field as a complex attribute.
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/body
    body_type = 'HTML'


class UID(bytes):
    """Helper class to encode Calendar UIDs. See issue #453. Example:

    class GlobalObjectId(ExtendedProperty):
        distinguished_property_set_id = 'Meeting'
        property_id = 3
        property_type = 'Binary'

    CalendarItem.register('global_object_id', GlobalObjectId)
    account.calendar.filter(global_object_id=GlobalObjectId(UID('261cbc18-1f65-5a0a-bd11-23b1e224cc2f')))
    """
    _HEADER = binascii.hexlify(bytearray((
        0x04, 0x00, 0x00, 0x00,
        0x82, 0x00, 0xE0, 0x00,
        0x74, 0xC5, 0xB7, 0x10,
        0x1A, 0x82, 0xE0, 0x08)))

    _EXCEPTION_REPLACEMENT_TIME = binascii.hexlify(bytearray((
        0, 0, 0, 0)))

    _CREATION_TIME = binascii.hexlify(bytearray((
        0, 0, 0, 0,
        0, 0, 0, 0)))

    _RESERVED = binascii.hexlify(bytearray((
        0, 0, 0, 0,
        0, 0, 0, 0)))

    # https://docs.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-oxocal/1d3aac05-a7b9-45cc-a213-47f0a0a2c5c1
    # https://docs.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-asemail/e7424ddc-dd10-431e-a0b7-5c794863370e
    # https://stackoverflow.com/questions/42259122
    # https://stackoverflow.com/questions/33757805

    def __new__(cls, uid):
        payload = binascii.hexlify(bytearray('vCal-Uid\x01\x00\x00\x00{}\x00'.format(uid).encode('ascii')))
        length = binascii.hexlify(bytearray(struct.pack('<I', int(len(payload)/2))))
        encoding = b''.join([
            cls._HEADER, cls._EXCEPTION_REPLACEMENT_TIME, cls._CREATION_TIME, cls._RESERVED, length, payload
        ])
        return super(UID, cls).__new__(cls, codecs.decode(encoding, 'hex'))


class EWSElement(object):
    __metaclass__ = abc.ABCMeta

    ELEMENT_NAME = None  # The name of the XML tag
    FIELDS = []  # A list of attributes supported by this item class, ordered the same way as in EWS documentation
    NAMESPACE = TNS  # The XML tag namespace. Either TNS or MNS

    _fields_lock = Lock()

    __slots__ = tuple()
    __slots_keys = None

    def __init__(self, **kwargs):
        for f in self.FIELDS:
            setattr(self, f.name, kwargs.pop(f.name, None))
        if kwargs:
            raise AttributeError("%s are invalid kwargs for this class" % ', '.join("'%s'" % k for k in kwargs))

    @classmethod
    def _slots_keys(cls):
        # Find __slots__ entries for this and all parent classes. Keep order, with parent slots first.
        if cls.__slots_keys is None:
            seen = set()
            keys = []
            for c in reversed(getmro(cls)):
                if not hasattr(c, '__slots__'):
                    continue
                for k in c.__slots__:
                    if k in seen:
                        # We allow duplicate keys because we don't want to require subclasses of e.g.
                        # ExtendedProperty to define an empty __slots__ class attribute.
                        continue
                    keys.append(k)
                    seen.add(k)
            cls.__slots_keys = tuple(keys)
        return cls.__slots_keys

    def clean(self, version=None):
        # Validate attribute values using the field validator
        for f in self.FIELDS:
            if not f.supports_version(version):
                continue
            if isinstance(f, ExtendedPropertyField) and not hasattr(self, f.name):
                # The extended field may have been registered after this item was created. Set default values.
                setattr(self, f.name, f.clean(None, version=version))
                continue
            val = getattr(self, f.name)
            setattr(self, f.name, f.clean(val, version=version))

    @staticmethod
    def _clear(elem):
        # Clears an XML element to reduce memory consumption
        elem.clear()
        # Don't attempt to clean up previous siblings. We may not have parsed them yet.
        elem.getparent().remove(elem)

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS}
        cls._clear(elem)
        return cls(**kwargs)

    def to_xml(self, version):
        self.clean(version=version)
        # WARNING: The order of addition of XML elements is VERY important. Exchange expects XML elements in a
        # specific, non-documented order and will fail with meaningless errors if the order is wrong.

        # Call create_element() without args, to not fill up the cache with unique attribute values.
        elem = create_element(self.request_tag())

        # Add attributes
        for f in self.attribute_fields():
            if f.is_read_only:
                continue
            value = getattr(self, f.name)
            if value is None or (f.is_list and not value):
                continue
            elem.set(f.field_uri, value_to_xml_text(getattr(self, f.name)))

        # Add elements and values
        for f in self.supported_fields(version=version):
            if f.is_read_only:
                continue
            value = getattr(self, f.name)
            if value is None or (f.is_list and not value):
                continue
            set_xml_value(elem, f.to_xml(value, version=version), version)
        return elem

    @classmethod
    def request_tag(cls):
        if not cls.ELEMENT_NAME:
            raise ValueError('Class %s is missing the ELEMENT_NAME attribute' % cls)
        return {
            TNS: 't:%s' % cls.ELEMENT_NAME,
            MNS: 'm:%s' % cls.ELEMENT_NAME,
        }[cls.NAMESPACE]

    @classmethod
    def response_tag(cls):
        if not cls.NAMESPACE:
            raise ValueError('Class %s is missing the NAMESPACE attribute' % cls)
        if not cls.ELEMENT_NAME:
            raise ValueError('Class %s is missing the ELEMENT_NAME attribute' % cls)
        return '{%s}%s' % (cls.NAMESPACE, cls.ELEMENT_NAME)

    @classmethod
    def attribute_fields(cls):
        return tuple(f for f in cls.FIELDS if f.is_attribute)

    @classmethod
    def supported_fields(cls, version=None):
        # Return non-ID field names. If version is specified, only return the fields supported by this version
        return tuple(f for f in cls.FIELDS if not f.is_attribute and f.supports_version(version))

    @classmethod
    def get_field_by_fieldname(cls, fieldname):
        for f in cls.FIELDS:
            if f.name == fieldname:
                return f
        raise InvalidField("'%s' is not a valid field name on '%s'" % (fieldname, cls.__name__))

    @classmethod
    def validate_field(cls, field, version):
        # Takes a list of fieldnames, Field or FieldPath objects pointing to item fields, and checks that they are valid
        # for the given version.
        # Allow both Field and FieldPath instances and string field paths as input
        if isinstance(field, string_types):
            field = cls.get_field_by_fieldname(fieldname=field)
        elif isinstance(field, FieldPath):
            field = field.field
        if not isinstance(field, Field):
            raise ValueError("Field %r must be a string, Field or FieldPath instance" % field)
        cls.get_field_by_fieldname(fieldname=field.name)  # Will raise if field name is invalid
        if not field.supports_version(version):
            # The field exists but is not valid for this version
            raise InvalidFieldForVersion(
                "Field '%s' is not supported on server version %s (supported from: %s, deprecated from: %s)"
                % (field.name, version, field.supported_from, field.deprecated_from))

    @classmethod
    def add_field(cls, field, insert_after):
        # Insert a new field at the preferred place in the tuple and invalidate the fieldname cache
        with cls._fields_lock:
            idx = tuple(f.name for f in cls.FIELDS).index(insert_after) + 1
            cls.FIELDS.insert(idx, field)

    @classmethod
    def remove_field(cls, field):
        # Remove the given field and invalidate the fieldname cache
        with cls._fields_lock:
            cls.FIELDS.remove(field)

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash(
            tuple(tuple(getattr(self, f.name) or ()) if f.is_list else getattr(self, f.name) for f in self.FIELDS)
        )

    if PY2:
        def __getstate__(self):
            try:
                state = self.__dict__.copy()
            except AttributeError:
                # This is a class where only __slots__ is defined
                state = {}
            state.update({k: getattr(self, k) for k in self._slots_keys()})
            return state

        def __setstate__(self, state):
            try:
                for k in self.__dict__.keys():
                    setattr(self, k, state.get(k))
            except AttributeError:
                # This is a class where only __slots__ is defined
                pass
            for k in self._slots_keys():
                setattr(self, k, state.get(k))

    def _field_vals(self):
        field_vals = []  # Keep sorting
        for f in self.FIELDS:
            val = getattr(self, f.name)
            if isinstance(f, EnumField) and isinstance(val, int):
                val = f.as_string(val)
            field_vals.append((f.name, val))
        return field_vals

    def __str__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%r' % (name, val) for name, val in self._field_vals() if val is not None
        )

    def __repr__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%r' % (name, val) for name, val in self._field_vals()
        )


class MessageHeader(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/internetmessageheader
    ELEMENT_NAME = 'InternetMessageHeader'

    FIELDS = [
        TextField('name', field_uri='HeaderName', is_attribute=True),
        SubField('value'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class ItemId(EWSElement):
    # 'id' and 'changekey' are UUIDs generated by Exchange
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/itemid
    ELEMENT_NAME = 'ItemId'

    ID_ATTR = 'Id'
    CHANGEKEY_ATTR = 'ChangeKey'
    FIELDS = [
        IdField('id', field_uri=ID_ATTR, is_required=True),
        IdField('changekey', field_uri=CHANGEKEY_ATTR, is_required=False),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def __init__(self, *args, **kwargs):
        if not kwargs:
            # Allow to set attributes without keyword
            kwargs = dict(zip(self._slots_keys(), args))
        super(ItemId, self).__init__(**kwargs)


class ParentItemId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/parentitemid
    ELEMENT_NAME = 'ParentItemId'
    NAMESPACE = MNS

    __slots__ = tuple()


class RootItemId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/rootitemid
    ELEMENT_NAME = 'RootItemId'
    NAMESPACE = MNS

    ID_ATTR = 'RootItemId'
    CHANGEKEY_ATTR = 'RootItemChangeKey'
    FIELDS = [
        IdField('id', field_uri=ID_ATTR, is_required=True),
        IdField('changekey', field_uri=CHANGEKEY_ATTR, is_required=True),
    ]

    __slots__ = tuple()


class AssociatedCalendarItemId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/associatedcalendaritemid
    ELEMENT_NAME = 'AssociatedCalendarItemId'

    __slots__ = tuple()


class ConversationId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/conversationid
    ELEMENT_NAME = 'ConversationId'

    FIELDS = [
        IdField('id', field_uri=ItemId.ID_ATTR, is_required=True),
        # Sometimes required, see MSDN link
        IdField('changekey', field_uri=ItemId.CHANGEKEY_ATTR),
    ]

    __slots__ = tuple()


class ParentFolderId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/parentfolderid
    ELEMENT_NAME = 'ParentFolderId'

    __slots__ = tuple()


class ReferenceItemId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/referenceitemid
    ELEMENT_NAME = 'ReferenceItemId'

    __slots__ = tuple()


class PersonaId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/personaid
    ELEMENT_NAME = 'PersonaId'
    NAMESPACE = MNS

    @classmethod
    def response_tag(cls):
        # For some reason, EWS wants this in the MNS namespace in a request, but TNS namespace in a response...
        return '{%s}%s' % (TNS, cls.ELEMENT_NAME)

    __slots__ = tuple()


class FolderId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/folderid
    ELEMENT_NAME = 'FolderId'

    __slots__ = tuple()


class Mailbox(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailbox
    ELEMENT_NAME = 'Mailbox'

    FIELDS = [
        TextField('name', field_uri='Name'),
        EmailAddressField('email_address', field_uri='EmailAddress'),
        ChoiceField('routing_type', field_uri='RoutingType', choices={Choice('SMTP')}, default='SMTP'),
        ChoiceField('mailbox_type', field_uri='MailboxType', choices={
            Choice('Mailbox'), Choice('PublicDL'), Choice('PrivateDL'), Choice('Contact'), Choice('PublicFolder'),
            Choice('Unknown'), Choice('OneOff'), Choice('GroupMailbox', supported_from=EXCHANGE_2013)
        }, default='Mailbox'),
        EWSElementField('item_id', value_cls=ItemId, is_read_only=True),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def clean(self, version=None):
        super(Mailbox, self).clean(version=version)
        if not self.email_address and not self.item_id:
            # See "Remarks" section of
            # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailbox
            raise ValueError("Mailbox must have either 'email_address' or 'item_id' set")

    def __hash__(self):
        # Exchange may add 'mailbox_type' and 'name' on insert. We're satisfied if the item_id or email address matches.
        if self.item_id:
            return hash(self.item_id)
        return hash(self.email_address.lower())


class DLMailbox(Mailbox):
    # Like Mailbox, but creates elements in the 'messages' namespace when sending requests
    NAMESPACE = MNS
    __slots__ = tuple()


class SendingAs(Mailbox):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/sendingas
    # Like Mailbox, but creates elements in the 'messages' namespace when sending requests
    ELEMENT_NAME = 'SendingAs'
    NAMESPACE = MNS
    __slots__ = tuple()


class RecipientAddress(Mailbox):
    # Like Mailbox, but with a different tag name
    #
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/recipientaddress
    ELEMENT_NAME = 'RecipientAddress'

    __slots__ = tuple()


class AvailabilityMailbox(EWSElement):
    # Like Mailbox, but with slightly different attributes
    #
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailbox-availability
    ELEMENT_NAME = 'Mailbox'
    FIELDS = [
        TextField('name', field_uri='Name'),
        EmailAddressField('email_address', field_uri='Address', is_required=True),
        ChoiceField('routing_type', field_uri='RoutingType', choices={Choice('SMTP')}, default='SMTP'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def __hash__(self):
        # Exchange may add 'name' on insert. We're satisfied if the email address matches.
        return hash(self.email_address.lower())

    @classmethod
    def from_mailbox(cls, mailbox):
        if not isinstance(mailbox, Mailbox):
            raise ValueError("'mailbox' %r must be a Mailbox instance" % mailbox)
        return cls(name=mailbox.name, email_address=mailbox.email_address, routing_type=mailbox.routing_type)


class Email(AvailabilityMailbox):
    # Like AvailabilityMailbox, but with a different tag name
    #
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/email-emailaddresstype
    ELEMENT_NAME = 'Email'

    __slots__ = tuple()


class MailboxData(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailboxdata
    ELEMENT_NAME = 'MailboxData'
    ATTENDEE_TYPES = {'Optional', 'Organizer', 'Required', 'Resource', 'Room'}

    FIELDS = [
        EmailField('email'),
        ChoiceField('attendee_type', field_uri='AttendeeType', choices={Choice(c) for c in ATTENDEE_TYPES}),
        BooleanField('exclude_conflicts', field_uri='ExcludeConflicts'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def __hash__(self):
        # Exchange may add 'name' on insert. We're satisfied if the email address matches.
        return hash((self.email.email_address.lower(), self.attendee_type, self.exclude_conflicts))


class DistinguishedFolderId(ItemId):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/distinguishedfolderid
    ELEMENT_NAME = 'DistinguishedFolderId'

    FIELDS = [
        IdField('id', field_uri=ItemId.ID_ATTR, is_required=True),
        IdField('changekey', field_uri=ItemId.CHANGEKEY_ATTR),
        MailboxField('mailbox'),
    ]

    __slots__ = ('mailbox',)

    def clean(self, version=None):
        from .folders import PublicFoldersRoot
        super(DistinguishedFolderId, self).clean(version=version)
        if self.id == PublicFoldersRoot.DISTINGUISHED_FOLDER_ID:
            # Avoid "ErrorInvalidOperation: It is not valid to specify a mailbox with the public folder root" from EWS
            self.mailbox = None


class TimeWindow(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/timewindow
    ELEMENT_NAME = 'TimeWindow'
    FIELDS = [
        DateTimeField('start', field_uri='StartTime', is_required=True),
        DateTimeField('end', field_uri='EndTime', is_required=True),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class FreeBusyViewOptions(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/freebusyviewoptions
    ELEMENT_NAME = 'FreeBusyViewOptions'
    REQUESTED_VIEWS = {'MergedOnly', 'FreeBusy', 'FreeBusyMerged', 'Detailed', 'DetailedMerged'}
    FIELDS = [
        EWSElementField('time_window', value_cls=TimeWindow, is_required=True),
        # Interval value is in minutes
        IntegerField('merged_free_busy_interval', field_uri='MergedFreeBusyIntervalInMinutes', min=6, max=1440,
                     default=30, is_required=True),
        ChoiceField('requested_view', field_uri='RequestedView', choices={Choice(c) for c in REQUESTED_VIEWS},
                    is_required=True),  # Choice('None') is also valid, but only for responses
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class Attendee(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/attendee
    ELEMENT_NAME = 'Attendee'

    RESPONSE_TYPES = {'Unknown', 'Organizer', 'Tentative', 'Accept', 'Decline', 'NoResponseReceived'}

    FIELDS = [
        MailboxField('mailbox', is_required=True),
        ChoiceField('response_type', field_uri='ResponseType', choices={Choice(c) for c in RESPONSE_TYPES},
                    default='Unknown'),
        DateTimeField('last_response_time', field_uri='LastResponseTime'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def __hash__(self):
        # TODO: maybe take 'response_type' and 'last_response_time' into account?
        return hash(self.mailbox)


class TimeZoneTransition(EWSElement):
    # Base class for StandardTime and DaylightTime classes
    FIELDS = [
        IntegerField('bias', field_uri='Bias', is_required=True),  # Offset from the default bias, in minutes
        TimeField('time', field_uri='Time', is_required=True),
        IntegerField('occurrence', field_uri='DayOrder', is_required=True),  # n'th occurrence of weekday in iso_month
        IntegerField('iso_month', field_uri='Month', is_required=True),
        EnumField('weekday', field_uri='DayOfWeek', enum=WEEKDAY_NAMES, is_required=True),
        # 'Year' is not implemented yet
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    @classmethod
    def from_xml(cls, elem, account):
        res = super(TimeZoneTransition, cls).from_xml(elem, account)
        # Some parts of EWS use '5' to mean 'last occurrence in month', others use '-1'. Let's settle on '5' because
        # only '5' is accepted in requests.
        if res.occurrence == -1:
            res.occurrence = 5
        return res

    def clean(self, version=None):
        # pylint: disable=access-member-before-definition
        super(TimeZoneTransition, self).clean(version=version)
        if self.occurrence == -1:
            # See from_xml()
            self.occurrence = 5


class StandardTime(TimeZoneTransition):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/standardtime
    ELEMENT_NAME = 'StandardTime'
    __slots__ = tuple()


class DaylightTime(TimeZoneTransition):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/daylighttime
    ELEMENT_NAME = 'DaylightTime'
    __slots__ = tuple()


class TimeZone(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/timezone-availability
    ELEMENT_NAME = 'TimeZone'

    FIELDS = [
        IntegerField('bias', field_uri='Bias', is_required=True),  # Standard (non-DST) offset from UTC, in minutes
        EWSElementField('standard_time', value_cls=StandardTime),
        EWSElementField('daylight_time', value_cls=DaylightTime),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def to_server_timezone(self, timezones, for_year):
        """Returns the Microsoft timezone ID corresponding to this timezone. There may not be a match at all, and there
        may be multiple matches. If so, we return a random timezone ID.

        :param timezones: A list of server timezones, as returned by
            list(account.protocol.get_timezones(return_full_timezone_data=True))
        :param for_year:
        :return: A Microsoft timezone ID, as a string
        """
        candidates = set()
        for tz_id, tz_name, tz_periods, tz_transitions, tz_transitions_groups in timezones:
            candidate = self.from_server_timezone(tz_periods, tz_transitions, tz_transitions_groups, for_year)
            if candidate == self:
                log.debug('Found exact candidate: %s (%s)', tz_id, tz_name)
                # We prefer this timezone over anything else. Return immediately.
                return tz_id
            # Reduce list based on base bias and standard / daylight bias values
            if candidate.bias != self.bias:
                continue
            if candidate.standard_time is None:
                if self.standard_time is not None:
                    continue
            else:
                if self.standard_time is None:
                    continue
                if candidate.standard_time.bias != self.standard_time.bias:
                    continue
            if candidate.daylight_time is None:
                if self.daylight_time is not None:
                    continue
            else:
                if self.daylight_time is None:
                    continue
                if candidate.daylight_time.bias != self.daylight_time.bias:
                    continue
            log.debug('Found candidate with matching biases: %s (%s)', tz_id, tz_name)
            candidates.add(tz_id)
        if not candidates:
            raise ValueError('No server timezones match this timezone definition')
        if len(candidates) == 1:
            log.info('Could not find an exact timezone match for %s. Selecting the best candidate', self)
        else:
            log.warning('Could not find an exact timezone match for %s. Selecting a random candidate', self)
        return candidates.pop()

    @classmethod
    def from_server_timezone(cls, periods, transitions, transitionsgroups, for_year):
        # Creates a TimeZone object from the result of a GetServerTimeZones call with full timezone data

        # Get the default bias
        bias = cls._get_bias(periods=periods, for_year=for_year)

        # Get a relevant transition ID
        valid_tg_id = cls._get_valid_transition_id(transitions=transitions, for_year=for_year)
        transitiongroup = transitionsgroups[valid_tg_id]
        if not 0 <= len(transitiongroup) <= 2:
            raise ValueError('Expected 0-2 transitions in transitionsgroup %s' % transitiongroup)

        standard_time, daylight_time = cls._get_std_and_dst(transitiongroup=transitiongroup, periods=periods, bias=bias)
        return cls(bias=bias, standard_time=standard_time, daylight_time=daylight_time)

    @staticmethod
    def _get_bias(periods, for_year):
        # Set a default bias
        valid_period = None
        for (year, period_type), period in sorted(periods.items()):
            if period_type != 'Standard':
                continue
            if year > for_year:
                break
            valid_period = period
        if valid_period is None:
            raise ValueError('No standard bias found in periods %s' % periods)
        return int(valid_period['bias'].total_seconds()) // 60  # Convert to minutes

    @staticmethod
    def _get_valid_transition_id(transitions, for_year):
        # Look through the transitions, and pick the relevant one according to the 'for_year' value
        valid_tg_id = None
        for tg_id, from_date in sorted(transitions.items()):
            if from_date and from_date.year > for_year:
                break
            valid_tg_id = tg_id
        if valid_tg_id is None:
            raise ValueError('No valid transition for year %s: %s' % (for_year, transitions))
        return valid_tg_id

    @staticmethod
    def _get_std_and_dst(transitiongroup, periods, bias):
        # Return 'standard_time' and 'daylight_time' objects. We do unnecessary work here, but it keeps code simple.
        standard_time, daylight_time = None, None
        for transition in transitiongroup:
            period = periods[transition['to']]
            if len(transition.keys()) == 1:
                # This is a simple transition representing a timezone with no DST. Some servers don't accept TimeZone
                # elements without a STD and DST element (see issue #488). Return StandardTime and DaylightTime objects
                # with dummy values and 0 bias - this satisfies the broken servers and hopefully doesn't break the
                # well-behaving servers.
                standard_time = StandardTime(bias=0, time=datetime.time(0), occurrence=1, iso_month=1, weekday=1)
                daylight_time = DaylightTime(bias=0, time=datetime.time(0), occurrence=5, iso_month=12, weekday=7)
                continue
            # 'offset' is the time of day to transition, as timedelta since midnight. Must be a reasonable value
            if not datetime.timedelta(0) <= transition['offset'] < datetime.timedelta(days=1):
                raise ValueError("'offset' value %s must be be between 0 and 24 hours" % transition['offset'])
            transition_kwargs = dict(
                time=(datetime.datetime(2000, 1, 1) + transition['offset']).time(),
                occurrence=transition['occurrence'],
                iso_month=transition['iso_month'],
                weekday=transition['iso_weekday'],
            )
            if period['name'] == 'Standard':
                transition_kwargs['bias'] = 0
                standard_time = StandardTime(**transition_kwargs)
                continue
            if period['name'] == 'Daylight':
                dst_bias = int(period['bias'].total_seconds()) // 60  # Convert to minutes
                transition_kwargs['bias'] = dst_bias - bias
                daylight_time = DaylightTime(**transition_kwargs)
                continue
            raise ValueError('Unknown transition: %s' % transition)
        return standard_time, daylight_time


class CalendarView(EWSElement):
    """
    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendarview
    """
    ELEMENT_NAME = 'CalendarView'
    NAMESPACE = MNS

    FIELDS = [
        DateTimeField('start', field_uri='StartDate', is_required=True, is_attribute=True),
        DateTimeField('end', field_uri='EndDate', is_required=True, is_attribute=True),
        IntegerField('max_items', field_uri='MaxEntriesReturned', min=1, is_attribute=True),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def clean(self, version=None):
        super(CalendarView, self).clean(version=version)
        if self.end < self.start:
            raise ValueError("'start' must be before 'end'")


class CalendarEventDetails(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendareventdetails
    ELEMENT_NAME = 'CalendarEventDetails'
    FIELDS = [
        CharField('id', field_uri='ID'),
        CharField('subject', field_uri='Subject'),
        CharField('location', field_uri='Location'),
        BooleanField('is_meeting', field_uri='IsMeeting'),
        BooleanField('is_recurring', field_uri='IsRecurring'),
        BooleanField('is_exception', field_uri='IsException'),
        BooleanField('is_reminder_set', field_uri='IsReminderSet'),
        BooleanField('is_private', field_uri='IsPrivate'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class CalendarEvent(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendarevent
    ELEMENT_NAME = 'CalendarEvent'
    FIELDS = [
        DateTimeField('start', field_uri='StartTime'),
        DateTimeField('end', field_uri='EndTime'),
        FreeBusyStatusField('busy_type', field_uri='BusyType', is_required=True, default='Busy'),
        EWSElementField('details', field_uri='CalendarEventDetails', value_cls=CalendarEventDetails),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class WorkingPeriod(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/workingperiod
    ELEMENT_NAME = 'WorkingPeriod'
    FIELDS = [
        EnumListField('weekdays', field_uri='DayOfWeek', enum=WEEKDAY_NAMES, is_required=True),
        TimeField('start', field_uri='StartTimeInMinutes', is_required=True),
        TimeField('end', field_uri='EndTimeInMinutes', is_required=True),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class FreeBusyView(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/freebusyview
    ELEMENT_NAME = 'FreeBusyView'
    NAMESPACE = MNS
    FIELDS = [
        ChoiceField('view_type', field_uri='FreeBusyViewType', choices={
            Choice('None'), Choice('MergedOnly'), Choice('FreeBusy'), Choice('FreeBusyMerged'), Choice('Detailed'),
            Choice('DetailedMerged'),
        }, is_required=True),
        # A string of digits. Each digit points to a position in .fields.FREE_BUSY_CHOICES
        CharField('merged', field_uri='MergedFreeBusy'),
        EWSElementListField('calendar_events', field_uri='CalendarEventArray', value_cls=CalendarEvent),
        # WorkingPeriod is located inside the WorkingPeriodArray element which is inside the WorkingHours element
        EWSElementListField('working_hours', field_uri='WorkingPeriodArray', value_cls=WorkingPeriod),
        # TimeZone is also inside the WorkingHours element. It contains information about the timezone which the
        # account is located in.
        EWSElementField('working_hours_timezone', field_uri='TimeZone', value_cls=TimeZone),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {}
        working_hours_elem = elem.find('{%s}WorkingHours' % TNS)
        for f in cls.FIELDS:
            if f.name in ['working_hours', 'working_hours_timezone']:
                if working_hours_elem is None:
                    continue
                kwargs[f.name] = f.from_xml(elem=working_hours_elem, account=account)
                continue
            kwargs[f.name] = f.from_xml(elem=elem, account=account)
        cls._clear(elem)
        return cls(**kwargs)


class RoomList(Mailbox):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/roomlist
    ELEMENT_NAME = 'RoomList'
    NAMESPACE = MNS

    __slots__ = tuple()

    @classmethod
    def response_tag(cls):
        # In a GetRoomLists response, room lists are delivered as Address elements. See
        # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/address-emailaddresstype
        return '{%s}Address' % TNS


class Room(Mailbox):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/room
    ELEMENT_NAME = 'Room'

    __slots__ = tuple()

    @classmethod
    def from_xml(cls, elem, account):
        id_elem = elem.find('{%s}Id' % TNS)
        item_id_elem = id_elem.find(ItemId.response_tag())
        kwargs = dict(
            name=get_xml_attr(id_elem, '{%s}Name' % TNS),
            email_address=get_xml_attr(id_elem, '{%s}EmailAddress' % TNS),
            mailbox_type=get_xml_attr(id_elem, '{%s}MailboxType' % TNS),
            item_id=ItemId.from_xml(elem=item_id_elem, account=account) if item_id_elem else None,
        )
        cls._clear(elem)
        return cls(**kwargs)


class Member(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/member-ex15websvcsotherref
    ELEMENT_NAME = 'Member'

    FIELDS = [
        MailboxField('mailbox', is_required=True),
        ChoiceField('status', field_uri='Status', choices={
            Choice('Unrecognized'), Choice('Normal'), Choice('Demoted')
        }, default='Normal'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def __hash__(self):
        # TODO: maybe take 'status' into account?
        return hash(self.mailbox)


class UserId(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/userid
    ELEMENT_NAME = 'UserId'

    FIELDS = [
        CharField('sid', field_uri='SID'),
        EmailAddressField('primary_smtp_address', field_uri='PrimarySmtpAddress'),
        CharField('display_name', field_uri='DisplayName'),
        ChoiceField('distinguished_user', field_uri='DistinguishedUser', choices={
            Choice('Default'), Choice('Anonymous')
        }),
        CharField('external_user_identity', field_uri='ExternalUserIdentity'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class Permission(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/permission
    ELEMENT_NAME = 'Permission'

    PERMISSION_ENUM = {Choice('None'), Choice('Owned'), Choice('All')}
    FIELDS = [
        ChoiceField('permission_level', field_uri='PermissionLevel', choices={
            Choice('None'), Choice('Owner'), Choice('PublishingEditor'), Choice('Editor'), Choice('PublishingAuthor'),
            Choice('Author'), Choice('NoneditingAuthor'), Choice('Reviewer'), Choice('Contributor'), Choice('Custom')
        }, default='None'),
        BooleanField('can_create_items', field_uri='CanCreateItems', default=False),
        BooleanField('can_create_subfolders', field_uri='CanCreateSubfolders', default=False),
        BooleanField('is_folder_owner', field_uri='IsFolderOwner', default=False),
        BooleanField('is_folder_visible', field_uri='IsFolderVisible', default=False),
        BooleanField('is_folder_contact', field_uri='IsFolderContact', default=False),
        ChoiceField('edit_items', field_uri='EditItems', choices=PERMISSION_ENUM, default='None'),
        ChoiceField('delete_items', field_uri='DeleteItems', choices=PERMISSION_ENUM, default='None'),
        ChoiceField('read_items', field_uri='ReadItems', choices={
            Choice('None'), Choice('FullDetails')
        }, default='None'),
        EWSElementField('user_id', field_uri='UserId', value_cls=UserId, is_required=True)
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class CalendarPermission(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendarpermission
    ELEMENT_NAME = 'Permission'

    PERMISSION_ENUM = {Choice('None'), Choice('Owned'), Choice('All')}
    FIELDS = [
        ChoiceField('calendar_permission_level', field_uri='CalendarPermissionLevel', choices={
            Choice('None'), Choice('Owner'), Choice('PublishingEditor'), Choice('Editor'), Choice('PublishingAuthor'),
            Choice('Author'), Choice('NoneditingAuthor'), Choice('Reviewer'), Choice('Contributor'),
            Choice('FreeBusyTimeOnly'), Choice('FreeBusyTimeAndSubjectAndLocation'), Choice('Custom')
        }, default='None'),
    ] + Permission.FIELDS[1:]

    __slots__ = tuple(f.name for f in FIELDS)


class PermissionSet(EWSElement):
    # MSDN:
    # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/permissionset-permissionsettype
    # and
    # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/permissionset-calendarpermissionsettype

    # For simplicity, we implement the two distinct but equally names elements as one class.
    ELEMENT_NAME = 'PermissionSet'

    FIELDS = [
        EWSElementListField('permissions', field_uri='Permissions', value_cls=Permission),
        EWSElementListField('calendar_permissions', field_uri='CalendarPermissions', value_cls=CalendarPermission),
        UnknownEntriesField('unknown_entries', field_uri='UnknownEntries'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class EffectiveRights(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/effectiverights
    ELEMENT_NAME = 'EffectiveRights'

    FIELDS = [
        BooleanField('create_associated', field_uri='CreateAssociated', default=False),
        BooleanField('create_contents', field_uri='CreateContents', default=False),
        BooleanField('create_hierarchy', field_uri='CreateHierarchy', default=False),
        BooleanField('delete', field_uri='Delete', default=False),
        BooleanField('modify', field_uri='Modify', default=False),
        BooleanField('read', field_uri='Read', default=False),
        BooleanField('view_private_items', field_uri='ViewPrivateItems', default=False),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def __contains__(self, item):
        return getattr(self, item, False)


class DelegatePermissions(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/delegatepermissions
    PERMISSION_LEVEL_CHOICES = {
            Choice('None'), Choice('Editor'), Choice('Reviewer'), Choice('Author'), Choice('Custom'),
        }
    FIELDS = [
        ChoiceField('calendar_folder_permission_level', field_uri='CalendarFolderPermissionLevel',
                    choices=PERMISSION_LEVEL_CHOICES, default='None'),
        ChoiceField('tasks_folder_permission_level', field_uri='TasksFolderPermissionLevel',
                    choices=PERMISSION_LEVEL_CHOICES, default='None'),
        ChoiceField('inbox_folder_permission_level', field_uri='InboxFolderPermissionLevel',
                    choices=PERMISSION_LEVEL_CHOICES, default='None'),
        ChoiceField('contacts_folder_permission_level', field_uri='ContactsFolderPermissionLevel',
                    choices=PERMISSION_LEVEL_CHOICES, default='None'),
        ChoiceField('notes_folder_permission_level', field_uri='NotesFolderPermissionLevel',
                    choices=PERMISSION_LEVEL_CHOICES, default='None'),
        ChoiceField('journal_folder_permission_level', field_uri='JournalFolderPermissionLevel',
                    choices=PERMISSION_LEVEL_CHOICES, default='None'),
    ]


class DelegateUser(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/delegateuser
    ELEMENT_NAME = 'DelegateUser'
    NAMESPACE = MNS

    FIELDS = [
        EWSElementField('user_id', field_uri='UserId', value_cls=UserId),
        EWSElementField('delegate_permissions', field_uri='DelegatePermissions', value_cls=DelegatePermissions),
        BooleanField('receive_copies_of_meeting_messages', field_uri='ReceiveCopiesOfMeetingMessages', default=False),
        BooleanField('view_private_items', field_uri='ViewPrivateItems', default=False),
    ]


class SearchableMailbox(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/searchablemailbox
    ELEMENT_NAME = 'SearchableMailbox'

    FIELDS = [
        CharField('guid', field_uri='Guid'),
        EmailAddressField('primary_smtp_address', field_uri='PrimarySmtpAddress'),
        BooleanField('is_external', field_uri='IsExternalMailbox'),
        EmailAddressField('external_email', field_uri='ExternalEmailAddress'),
        CharField('display_name', field_uri='DisplayName'),
        BooleanField('is_membership_group', field_uri='IsMembershipGroup'),
        CharField('reference_id', field_uri='ReferenceId'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class FailedMailbox(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/failedmailbox
    FIELDS = [
        CharField('mailbox', field_uri='Mailbox'),
        IntegerField('error_code', field_uri='ErrorCode'),
        CharField('error_message', field_uri='ErrorMessage'),
        BooleanField('is_archive', field_uri='IsArchive'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


# MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailtipsrequested
MAIL_TIPS_TYPES = (
    'All',
    'OutOfOfficeMessage',
    'MailboxFullStatus',
    'CustomMailTip',
    'ExternalMemberCount',
    'TotalMemberCount',
    'MaxMessageSize',
    'DeliveryRestriction',
    'ModerationStatus',
    'InvalidRecipient',
)


class OutOfOffice(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/outofoffice
    ELEMENT_NAME = 'OutOfOffice'

    FIELDS = [
        MessageField('reply_body', field_uri='ReplyBody'),
        DateTimeField('start', field_uri='StartTime', is_required=False),
        DateTimeField('end', field_uri='EndTime', is_required=False),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    @classmethod
    def duration_to_start_end(cls, elem, account):
        kwargs = {}
        duration = elem.find('{%s}Duration' % TNS)
        if duration is not None:
            for attr in ('start', 'end'):
                f = cls.get_field_by_fieldname(attr)
                kwargs[attr] = f.from_xml(elem=duration, account=account)
        return kwargs

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {}
        for attr in ('reply_body',):
            f = cls.get_field_by_fieldname(attr)
            kwargs[attr] = f.from_xml(elem=elem, account=account)
        kwargs.update(cls.duration_to_start_end(elem=elem, account=account))
        cls._clear(elem)
        return cls(**kwargs)


class MailTips(EWSElement):
    # MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailtips
    ELEMENT_NAME = 'MailTips'
    NAMESPACE = MNS

    FIELDS = [
        RecipientAddressField('recipient_address'),
        ChoiceField('pending_mail_tips', field_uri='PendingMailTips', choices={Choice(c) for c in MAIL_TIPS_TYPES}),
        EWSElementField('out_of_office', field_uri='OutOfOffice', value_cls=OutOfOffice),
        BooleanField('mailbox_full', field_uri='MailboxFull'),
        TextField('custom_mail_tip', field_uri='CustomMailTip'),
        IntegerField('total_member_count', field_uri='TotalMemberCount'),
        IntegerField('external_member_count', field_uri='ExternalMemberCount'),
        IntegerField('max_message_size', field_uri='MaxMessageSize'),
        BooleanField('delivery_restricted', field_uri='DeliveryRestricted'),
        BooleanField('is_moderated', field_uri='IsModerated'),
        BooleanField('invalid_recipient', field_uri='InvalidRecipient'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class IdChangeKeyMixIn(EWSElement):
    # A class that has 'id' and 'changekey' fields which are actually attributes on ID element
    ID_ELEMENT_CLS = ItemId

    FIELDS = [
        IdField('id', field_uri=ID_ELEMENT_CLS.ID_ATTR, is_read_only=True),
        IdField('changekey', field_uri=ID_ELEMENT_CLS.CHANGEKEY_ATTR, is_read_only=True),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    @classmethod
    def id_from_xml(cls, elem):
        id_elem = elem.find(cls.ID_ELEMENT_CLS.response_tag())
        if id_elem is None:
            return None, None
        return id_elem.get(cls.ID_ELEMENT_CLS.ID_ATTR), id_elem.get(cls.ID_ELEMENT_CLS.CHANGEKEY_ATTR)

    @classmethod
    def from_xml(cls, elem, account):
        item_id, changekey = cls.id_from_xml(elem)
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.supported_fields()}
        cls._clear(elem)
        return cls(id=item_id, changekey=changekey, **kwargs)

    def __eq__(self, other):
        if isinstance(other, tuple):
            return hash((self.id, self.changekey)) == hash(other)
        return super(IdChangeKeyMixIn, self).__eq__(other)

    def __hash__(self):
        # If we have an ID and changekey, use that as key. Else return a hash of all attributes
        if self.id:
            return hash((self.id, self.changekey))
        return super(IdChangeKeyMixIn, self).__hash__()
