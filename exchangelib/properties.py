from __future__ import unicode_literals

import abc
import datetime
import logging

from six import text_type, string_types

from .fields import SubField, TextField, EmailAddressField, ChoiceField, DateTimeField, EWSElementField, MailboxField, \
    Choice, BooleanField, IdField, ExtendedPropertyField, IntegerField, TimeField, EnumField, CharField, EmailField, \
    EWSElementListField, EnumListField, FreeBusyStatusField, WEEKDAY_NAMES
from .services import MNS, TNS
from .util import get_xml_attr, create_element, set_xml_value, value_to_xml_text
from .version import EXCHANGE_2013

string_type = string_types[0]
log = logging.getLogger(__name__)


class Body(text_type):
    # Helper to mark the 'body' field as a complex attribute.
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj219983(v=exchg.150).aspx
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
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj219983(v=exchg.150).aspx
    body_type = 'HTML'


class EWSElement(object):
    __metaclass__ = abc.ABCMeta

    ELEMENT_NAME = None
    FIELDS = []
    NAMESPACE = TNS  # Either TNS or MNS

    __slots__ = tuple()

    def __init__(self, **kwargs):
        for f in self.FIELDS:
            setattr(self, f.name, kwargs.pop(f.name, None))
        if kwargs:
            raise AttributeError("%s are invalid kwargs for this class" % ', '.join("'%s'" % k for k in kwargs))

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

    @classmethod
    def from_xml(cls, elem, account):
        if elem is None:
            return None
        if elem.tag != cls.response_tag():
            raise ValueError('Unexpected element tag in class %s: %s vs %s' % (cls, elem.tag, cls.response_tag()))
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS}
        elem.clear()
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
        if not hasattr(cls, '_fields_map'):
            cls._fields_map = {f.name: f for f in cls.FIELDS}
        try:
            return cls._fields_map[fieldname]
        except KeyError:
            raise ValueError("'%s' is not a valid field on '%s'" % (fieldname, cls.__name__))

    @classmethod
    def add_field(cls, field, idx):
        # Insert a new field at the preferred place in the tuple and invalidate the fieldname cache
        cls.FIELDS.insert(idx, field)
        try:
            delattr(cls, '_fields_map')
        except AttributeError:
            pass

    @classmethod
    def remove_field(cls, field):
        # Remove the given field and invalidate the fieldname cache
        cls.FIELDS.remove(field)
        try:
            delattr(cls, '_fields_map')
        except AttributeError:
            pass

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash(
            tuple(tuple(getattr(self, f.name) or ()) if f.is_list else getattr(self, f.name) for f in self.FIELDS)
        )

    def __str__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%s' % (f.name, repr(getattr(self, f.name))) for f in self.FIELDS if getattr(self, f.name) is not None
        )

    def __repr__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%s' % (f.name, repr(getattr(self, f.name))) for f in self.FIELDS
        )


class MessageHeader(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565307(v=exchg.150).aspx
    ELEMENT_NAME = 'InternetMessageHeader'

    FIELDS = [
        TextField('name', field_uri='HeaderName', is_attribute=True),
        SubField('value'),
    ]

    __slots__ = ('name', 'value')


class ItemId(EWSElement):
    # 'id' and 'changekey' are UUIDs generated by Exchange
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580234(v=exchg.150).aspx
    ELEMENT_NAME = 'ItemId'

    ID_ATTR = 'Id'
    CHANGEKEY_ATTR = 'ChangeKey'
    FIELDS = [
        IdField('id', field_uri=ID_ATTR, is_required=True),
        IdField('changekey', field_uri=CHANGEKEY_ATTR, is_required=False),
    ]

    __slots__ = ('id', 'changekey')

    def __init__(self, *args, **kwargs):
        if not kwargs:
            # Allow to set attributes without keyword
            kwargs = dict(zip(self.__slots__, args))
        super(ItemId, self).__init__(**kwargs)


class ParentItemId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa563720(v=exchg.150).aspx
    ELEMENT_NAME = 'ParentItemId'
    NAMESPACE = MNS

    __slots__ = ItemId.__slots__


class RootItemId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/bb204277(v=exchg.150).aspx
    ELEMENT_NAME = 'RootItemId'
    NAMESPACE = MNS

    ID_ATTR = 'RootItemId'
    CHANGEKEY_ATTR = 'RootItemChangeKey'
    FIELDS = [
        IdField('id', field_uri=ID_ATTR, is_required=True),
        IdField('changekey', field_uri=CHANGEKEY_ATTR, is_required=True),
    ]

    __slots__ = ItemId.__slots__


class AssociatedCalendarItemId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa581060(v=exchg.150).aspx
    ELEMENT_NAME = 'AssociatedCalendarItemId'

    __slots__ = ItemId.__slots__


class ConversationId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899527(v=exchg.150).aspx
    ELEMENT_NAME = 'ConversationId'

    FIELDS = [
        IdField('id', field_uri=ItemId.ID_ATTR, is_required=True),
        # Sometimes required, see MSDN link
        IdField('changekey', field_uri=ItemId.CHANGEKEY_ATTR),
    ]

    __slots__ = ItemId.__slots__


class ParentFolderId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa494327(v=exchg.150).aspx
    ELEMENT_NAME = 'ParentFolderId'

    __slots__ = ItemId.__slots__


class ReferenceItemId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564031(v=exchg.150).aspx
    ELEMENT_NAME = 'ReferenceItemId'

    __slots__ = ItemId.__slots__


class PersonaId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj191430(v=exchg.150).aspx
    ELEMENT_NAME = 'PersonaId'
    NAMESPACE = MNS

    @classmethod
    def response_tag(cls):
        # For some reason, EWS wants this in the MNS namespace in a request, but TNS namespace in a response...
        return '{%s}%s' % (TNS, cls.ELEMENT_NAME)

    __slots__ = ItemId.__slots__


class Mailbox(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565036(v=exchg.150).aspx
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

    __slots__ = ('name', 'email_address', 'routing_type', 'mailbox_type', 'item_id')

    def clean(self, version=None):
        super(Mailbox, self).clean(version=version)
        if not self.email_address and not self.item_id:
            # See "Remarks" section of https://msdn.microsoft.com/en-us/library/office/aa565036(v=exchg.150).aspx
            raise ValueError("Mailbox must have either 'email_address' or 'item_id' set")

    def __hash__(self):
        # Exchange may add 'mailbox_type' and 'name' on insert. We're satisfied if the item_id or email address matches.
        if self.item_id:
            return hash(self.item_id)
        return hash(self.email_address.lower())


class AvailabilityMailbox(EWSElement):
    # Like Mailbox, but with slightly different attributes
    #
    # MSDN: https://msdn.microsoft.com/en-us/library/aa564754(v=exchg.140).aspx
    ELEMENT_NAME = 'Mailbox'
    FIELDS = [
        TextField('name', field_uri='Name'),
        EmailAddressField('email_address', field_uri='Address', is_required=True),
        ChoiceField('routing_type', field_uri='RoutingType', choices={Choice('SMTP')}, default='SMTP'),
    ]

    __slots__ = ('name', 'email_address', 'routing_type')

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
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565868(v=exchg.150).aspx
    ELEMENT_NAME = 'Email'

    __slots__ = ('name', 'email_address', 'routing_type')

    def __hash__(self):
        # Exchange may add 'name' on insert. We're satisfied if the email address matches.
        return hash(self.email_address.lower())


class MailboxData(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa566036(v=exchg.150).aspx
    ELEMENT_NAME = 'MailboxData'
    FIELDS = [
        EmailField('email'),
        ChoiceField('attendee_type', field_uri='AttendeeType', choices={
            Choice('Optional'), Choice('Organizer'), Choice('Required'), Choice('Resource'), Choice('Room')
        }),
        BooleanField('exclude_conflicts', field_uri='ExcludeConflicts'),
    ]

    __slots__ = ('email', 'attendee_type', 'exclude_conflicts')

    def __hash__(self):
        # Exchange may add 'name' on insert. We're satisfied if the email address matches.
        return hash((self.email.email_address.lower(), self.attendee_type, self.exclude_conflicts))


class TimeWindow(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580740(v=exchg.150).aspx
    ELEMENT_NAME = 'TimeWindow'
    FIELDS = [
        DateTimeField('start', field_uri='StartTime', is_required=True),
        DateTimeField('end', field_uri='EndTime', is_required=True),
    ]

    __slots__ = ('start', 'end')


class FreeBusyViewOptions(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565063(v=exchg.150).aspx
    ELEMENT_NAME = 'FreeBusyViewOptions'
    FIELDS = [
        EWSElementField('time_window', value_cls=TimeWindow, is_required=True),
        # Interval value is in minutes
        IntegerField('merged_free_busy_interval', field_uri='MergedFreeBusyIntervalInMinutes', min=6, max=1440,
                     default=30, is_required=True),
        ChoiceField('requested_view', field_uri='RequestedView', choices={
            Choice('MergedOnly'), Choice('FreeBusy'), Choice('FreeBusyMerged'), Choice('Detailed'),
            Choice('DetailedMerged'),
        }, is_required=True),  # Choice('None') is also valid, but only for responses
    ]

    __slots__ = ('time_window', 'merged_free_busy_interval', 'requested_view')


class Attendee(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580339(v=exchg.150).aspx
    ELEMENT_NAME = 'Attendee'

    RESPONSE_TYPES = {'Unknown', 'Organizer', 'Tentative', 'Accept', 'Decline', 'NoResponseReceived'}

    FIELDS = [
        MailboxField('mailbox', is_required=True),
        ChoiceField('response_type', field_uri='ResponseType', choices={Choice(c) for c in RESPONSE_TYPES},
                    default='Unknown'),
        DateTimeField('last_response_time', field_uri='LastResponseTime'),
    ]

    __slots__ = ('mailbox', 'response_type', 'last_response_time')

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

    __slots__ = ('bias', 'time', 'occurrence', 'iso_month', 'weekday')


class StandardTime(TimeZoneTransition):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa563445(v=exchg.150).aspx
    ELEMENT_NAME = 'StandardTime'
    __slots__ = TimeZoneTransition.__slots__


class DaylightTime(TimeZoneTransition):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564336(v=exchg.150).aspx
    ELEMENT_NAME = 'DaylightTime'
    __slots__ = TimeZoneTransition.__slots__


class TimeZone(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565658(v=exchg.150).aspx
    ELEMENT_NAME = 'TimeZone'

    FIELDS = [
        IntegerField('bias', field_uri='Bias', is_required=True),  # Standard (non-DST) offset from UTC, in minutes
        EWSElementField('standard_time', value_cls=StandardTime),
        EWSElementField('daylight_time', value_cls=DaylightTime),
    ]

    __slots__ = ('bias', 'standard_time', 'daylight_time')

    @classmethod
    def from_server_timezone(cls, periods, transitions, transitionsgroups, for_year):
        # Creates a TimeZone object from the result of a GetServerTimeZones call with full timezone data
        kwargs = {}

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
        kwargs['bias'] = int(valid_period['bias'].total_seconds()) // 60  # Convert to minutes

        # Look through the transitions, and pick the relevant one according to the 'for_year' value
        valid_tg_id = None
        for tg_id, from_date in sorted(transitions.items()):
            if from_date and from_date.year > for_year:
                break
            valid_tg_id = tg_id
        if valid_tg_id is None:
            raise ValueError('No valid transition for year %s: %s' % (for_year, transitions))

        # Set or reset the 'standard_time' and 'daylight_time' kwargs. We do unnecessary work here, but it keeps
        # code simple
        if not 0 <= len(transitionsgroups[valid_tg_id]) <= 2:
            raise ValueError('Expected 0-2 transitions in transitionsgroup %s' % transitionsgroups[valid_tg_id])
        for transition in transitionsgroups[valid_tg_id]:
            period = periods[transition['to']]
            if len(transition.keys()) == 1:
                # This is a simple transition to STD time. That cannot be represented by this class
                continue
            # 'offset' is the time of day to transition, as timedelta since midnight. Must be a reasonable value
            if not datetime.timedelta(0) <= transition['offset'] < datetime.timedelta(days=1):
                raise ValueError("'offset' value %s must be be between 0 and 24 hours" % transition['offset'])
            transition_kwargs = dict(
                time=(datetime.datetime(2000, 1, 1) + transition['offset']).time(),
                occurrence=transition['occurrence'] if transition['occurrence'] >= 1 else 1,  # Value can be -1
                iso_month=transition['iso_month'],
                weekday=transition['iso_weekday'],
            )
            if period['name'] == 'Standard':
                transition_kwargs['bias'] = 0
                kwargs['standard_time'] = StandardTime(**transition_kwargs)
                continue
            if period['name'] == 'Daylight':
                std_bias = kwargs['bias']
                dst_bias = int(period['bias'].total_seconds()) // 60  # Convert to minutes
                transition_kwargs['bias'] = dst_bias - std_bias
                kwargs['daylight_time'] = DaylightTime(**transition_kwargs)
                continue
            raise ValueError('Unknown transition: %s' % transition)

        return cls(**kwargs)


class CalendarEvent(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/aa564053(v=exchg.80).aspx
    ELEMENT_NAME = 'CalendarEvent'
    FIELDS = [
        DateTimeField('start', field_uri='StartTime'),
        DateTimeField('end', field_uri='EndTime'),
        FreeBusyStatusField('busy_type', field_uri='BusyType', is_required=True, default='Busy'),
        # CalendarEventDetails
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class WorkingPeriod(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580377(v=exchg.150).aspx
    ELEMENT_NAME = 'WorkingPeriod'
    FIELDS = [
        EnumListField('weekdays', field_uri='DayOfWeek', enum=WEEKDAY_NAMES, is_required=True),
        TimeField('start', field_uri='StartTimeInMinutes', is_required=True),
        TimeField('end', field_uri='EndTimeInMinutes', is_required=True),
    ]

    __slots__ = tuple(f.name for f in FIELDS)


class FreeBusyView(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/aa565398(v=exchg.80).aspx
    ELEMENT_NAME = 'FreeBusyView'
    NAMESPACE = MNS
    FIELDS = [
        ChoiceField('view_type', field_uri='FreeBusyViewType', choices={
            Choice('None'), Choice('MergedOnly'), Choice('FreeBusy'), Choice('FreeBusyMerged'), Choice('Detailed'),
            Choice('DetailedMerged'),
        }, is_required=True),
        # A string of digits. Each digit points to a position in FREE_BUSY_CHOICES
        CharField('merged', field_uri='MergedFreeBusy'),
        EWSElementListField('calendar_events', field_uri='CalendarEventArray', value_cls=CalendarEvent),
        # WorkingPeriod is located inside WorkingHours element. WorkingHours also has timezone info that we
        # hopefully don't care about.
        EWSElementListField('working_hours', field_uri='WorkingPeriodArray', value_cls=WorkingPeriod),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    @classmethod
    def from_xml(cls, elem, account):
        if elem is None:
            return None
        if elem.tag != cls.response_tag():
            raise ValueError('Unexpected element tag in class %s: %s vs %s' % (cls, elem.tag, cls.response_tag()))
        kwargs = {}
        for f in cls.FIELDS:
            if f.name == 'working_hours':
                kwargs[f.name] = f.from_xml(elem=elem.find('{%s}WorkingHours' % TNS), account=account)
                continue
            kwargs[f.name] = f.from_xml(elem=elem, account=account)
        elem.clear()
        return cls(**kwargs)


class RoomList(Mailbox):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899514(v=exchg.150).aspx
    ELEMENT_NAME = 'RoomList'
    NAMESPACE = MNS

    __slots__ = Mailbox.__slots__

    @classmethod
    def response_tag(cls):
        # In a GetRoomLists response, room lists are delivered as Address elements
        # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899404(v=exchg.150).aspx
        return '{%s}Address' % TNS


class Room(Mailbox):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899479(v=exchg.150).aspx
    ELEMENT_NAME = 'Room'

    __slots__ = Mailbox.__slots__

    @classmethod
    def from_xml(cls, elem, account):
        if elem is None:
            return None
        if elem.tag != cls.response_tag():
            raise ValueError('Unexpected element tag in class %s: %s vs %s' % (cls, elem.tag, cls.response_tag()))
        id_elem = elem.find('{%s}Id' % TNS)
        res = cls(
            name=get_xml_attr(id_elem, '{%s}Name' % TNS),
            email_address=get_xml_attr(id_elem, '{%s}EmailAddress' % TNS),
            mailbox_type=get_xml_attr(id_elem, '{%s}MailboxType' % TNS),
            item_id=ItemId.from_xml(elem=id_elem.find(ItemId.response_tag()), account=account),
        )
        elem.clear()
        return res


class Member(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899487(v=exchg.150).aspx
    ELEMENT_NAME = 'Member'

    FIELDS = [
        MailboxField('mailbox', is_required=True),
        ChoiceField('status', field_uri='Status', choices={
            Choice('Unrecognized'), Choice('Normal'), Choice('Demoted')
        }, default='Normal'),
    ]

    __slots__ = ('mailbox', 'status')

    def __hash__(self):
        # TODO: maybe take 'status' into account?
        return hash(self.mailbox)


class EffectiveRights(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/bb891883(v=exchg.150).aspx
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


class SearchableMailbox(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj191013(v=exchg.150).aspx
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
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj191027(v=exchg.150).aspx
    FIELDS = [
        CharField('mailbox', field_uri='Mailbox'),
        IntegerField('error_code', field_uri='ErrorCode'),
        CharField('error_message', field_uri='ErrorMessage'),
        BooleanField('is_archive', field_uri='IsArchive'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)
