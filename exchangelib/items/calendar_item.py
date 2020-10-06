import datetime
import logging

from ..ewsdatetime import EWSDate, EWSDateTime
from ..fields import BooleanField, IntegerField, TextField, ChoiceField, URIField, BodyField, DateTimeField, \
    MessageHeaderField, AttachmentField, RecurrenceField, MailboxField, AttendeesField, Choice, OccurrenceField, \
    OccurrenceListField, TimeZoneField, CharField, EnumAsIntField, FreeBusyStatusField, ReferenceItemIdField, \
    AssociatedCalendarItemIdField, DateOrDateTimeField, EWSElementListField, AppointmentStateField
from ..properties import Attendee, ReferenceItemId, AssociatedCalendarItemId, OccurrenceItemId, RecurringMasterItemId, \
    Fields
from ..recurrence import FirstOccurrence, LastOccurrence, Occurrence, DeletedOccurrence
from ..services import CreateItem
from ..util import set_xml_value, require_account
from ..version import EXCHANGE_2010, EXCHANGE_2013
from .base import BaseItem, BaseReplyItem, BulkCreateResult, SEND_ONLY, SEND_AND_SAVE_COPY, SEND_TO_NONE
from .item import Item
from .message import Message

log = logging.getLogger(__name__)

# Conference Type values. See
# https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/conferencetype
CONFERENCE_TYPES = ('NetMeeting', 'NetShow', 'Chat')

# CalendarItemType enums
SINGLE = 'Single'
OCCURRENCE = 'Occurrence'
EXCEPTION = 'Exception'
RECURRING_MASTER = 'RecurringMaster'
CALENDAR_ITEM_CHOICES = (SINGLE, OCCURRENCE, EXCEPTION, RECURRING_MASTER)


class AcceptDeclineMixIn:
    def accept(self, **kwargs):
        return AcceptItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            **kwargs
        ).send()

    def decline(self, **kwargs):
        return DeclineItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            **kwargs
        ).send()

    def tentatively_accept(self, **kwargs):
        return TentativelyAcceptItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            **kwargs
        ).send()


class CalendarItem(Item, AcceptDeclineMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendaritem"""
    ELEMENT_NAME = 'CalendarItem'
    LOCAL_FIELDS = Fields(
        TextField('uid', field_uri='calendar:UID', is_required_after_save=True, is_searchable=False),
        DateOrDateTimeField('start', field_uri='calendar:Start', is_required=True),
        DateOrDateTimeField('end', field_uri='calendar:End', is_required=True),
        DateTimeField('original_start', field_uri='calendar:OriginalStart', is_read_only=True),
        BooleanField('is_all_day', field_uri='calendar:IsAllDayEvent', is_required=True, default=False),
        FreeBusyStatusField('legacy_free_busy_status', field_uri='calendar:LegacyFreeBusyStatus', is_required=True,
                            default='Busy'),
        TextField('location', field_uri='calendar:Location'),
        TextField('when', field_uri='calendar:When'),
        BooleanField('is_meeting', field_uri='calendar:IsMeeting', is_read_only=True),
        BooleanField('is_cancelled', field_uri='calendar:IsCancelled', is_read_only=True),
        BooleanField('is_recurring', field_uri='calendar:IsRecurring', is_read_only=True),
        BooleanField('meeting_request_was_sent', field_uri='calendar:MeetingRequestWasSent', is_read_only=True),
        BooleanField('is_response_requested', field_uri='calendar:IsResponseRequested', default=None,
                     is_required_after_save=True, is_searchable=False),
        ChoiceField('type', field_uri='calendar:CalendarItemType', choices={Choice(c) for c in CALENDAR_ITEM_CHOICES},
                    is_read_only=True),
        ChoiceField('my_response_type', field_uri='calendar:MyResponseType', choices={
            Choice(c) for c in Attendee.RESPONSE_TYPES
        }, is_read_only=True),
        MailboxField('organizer', field_uri='calendar:Organizer', is_read_only=True),
        AttendeesField('required_attendees', field_uri='calendar:RequiredAttendees', is_searchable=False),
        AttendeesField('optional_attendees', field_uri='calendar:OptionalAttendees', is_searchable=False),
        AttendeesField('resources', field_uri='calendar:Resources', is_searchable=False),
        IntegerField('conflicting_meeting_count', field_uri='calendar:ConflictingMeetingCount', is_read_only=True),
        IntegerField('adjacent_meeting_count', field_uri='calendar:AdjacentMeetingCount', is_read_only=True),
        EWSElementListField('conflicting_meetings', field_uri='calendar:ConflictingMeetings', value_cls='CalendarItem',
                            namespace=Item.NAMESPACE, is_read_only=True),
        EWSElementListField('adjacent_meetings', field_uri='calendar:AdjacentMeetings', value_cls='CalendarItem',
                            namespace=Item.NAMESPACE, is_read_only=True),
        CharField('duration', field_uri='calendar:Duration', is_read_only=True),
        DateTimeField('appointment_reply_time', field_uri='calendar:AppointmentReplyTime', is_read_only=True),
        IntegerField('appointment_sequence_number', field_uri='calendar:AppointmentSequenceNumber', is_read_only=True),
        AppointmentStateField('appointment_state', field_uri='calendar:AppointmentState', is_read_only=True),
        RecurrenceField('recurrence', field_uri='calendar:Recurrence', is_searchable=False),
        OccurrenceField('first_occurrence', field_uri='calendar:FirstOccurrence', value_cls=FirstOccurrence,
                        is_read_only=True),
        OccurrenceField('last_occurrence', field_uri='calendar:LastOccurrence', value_cls=LastOccurrence,
                        is_read_only=True),
        OccurrenceListField('modified_occurrences', field_uri='calendar:ModifiedOccurrences', value_cls=Occurrence,
                            is_read_only=True),
        OccurrenceListField('deleted_occurrences', field_uri='calendar:DeletedOccurrences', value_cls=DeletedOccurrence,
                            is_read_only=True),
        TimeZoneField('_meeting_timezone', field_uri='calendar:MeetingTimeZone', deprecated_from=EXCHANGE_2010,
                      is_searchable=False),
        TimeZoneField('_start_timezone', field_uri='calendar:StartTimeZone', supported_from=EXCHANGE_2010,
                      is_searchable=False),
        TimeZoneField('_end_timezone', field_uri='calendar:EndTimeZone', supported_from=EXCHANGE_2010,
                      is_searchable=False),
        EnumAsIntField('conference_type', field_uri='calendar:ConferenceType', enum=CONFERENCE_TYPES, min=0,
                       default=None, is_required_after_save=True),
        BooleanField('allow_new_time_proposal', field_uri='calendar:AllowNewTimeProposal', default=None,
                     is_required_after_save=True, is_searchable=False),
        BooleanField('is_online_meeting', field_uri='calendar:IsOnlineMeeting', default=None,
                     is_read_only=True),
        URIField('meeting_workspace_url', field_uri='calendar:MeetingWorkspaceUrl'),
        URIField('net_show_url', field_uri='calendar:NetShowUrl'),
    )
    FIELDS = Item.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)

    def occurrence(self, index):
        """

        Args:
          index:

        Returns:
          is 1-based. No other field values are fetched from the server.

          Only call this method on a recurring master.

        """
        return self.__class__(
            account=self.account,
            folder=self.folder,
            _id=OccurrenceItemId(id=self.id, changekey=self.changekey, instance_index=index),
        )

    def recurring_master(self):
        """

        Returns:
          other field values are fetched from the server.

          Only call this method on an occurrence of a recurring master.

        """
        return self.__class__(
            account=self.account,
            folder=self.folder,
            _id=RecurringMasterItemId(id=self.id, changekey=self.changekey),
        )

    @classmethod
    def timezone_fields(cls):
        return [f for f in cls.FIELDS if isinstance(f, TimeZoneField)]

    def clean_timezone_fields(self, version):
        # pylint: disable=access-member-before-definition
        # Sets proper values on the timezone fields if they are not already set
        if self.start is None:
            start_tz = None
        elif type(self.start) == EWSDate:
            start_tz = self.account.default_timezone
        else:
            start_tz = self.start.tzinfo
        if self.end is None:
            end_tz = None
        elif type(self.end) == EWSDate:
            end_tz = self.account.default_timezone
        else:
            end_tz = self.end.tzinfo
        if version.build < EXCHANGE_2010:
            if self._meeting_timezone is None:
                self._meeting_timezone = start_tz
            self._start_timezone = None
            self._end_timezone = None
        else:
            self._meeting_timezone = None
            if self._start_timezone is None:
                self._start_timezone = start_tz
            if self._end_timezone is None:
                self._end_timezone = end_tz

    def clean(self, version=None):
        # pylint: disable=access-member-before-definition
        super().clean(version=version)
        if self.start and self.end and self.end < self.start:
            raise ValueError("'end' must be greater than 'start' (%s -> %s)" % (self.start, self.end))
        if version:
            self.clean_timezone_fields(version=version)

    def cancel(self, **kwargs):
        return CancelCalendarItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            **kwargs
        ).send()

    def _update_fieldnames(self):
        update_fields = super()._update_fieldnames()
        if self.type == OCCURRENCE:
            # Some CalendarItem fields cannot be updated when the item is an occurrence. The values are empty when we
            # receive them so would have been updated because they are set to None.
            update_fields.remove('recurrence')
            update_fields.remove('uid')
        return update_fields

    @classmethod
    def from_xml(cls, elem, account):
        item = super().from_xml(elem=elem, account=account)
        # EWS returns the start and end values as a datetime regardless of the is_all_day status. Convert to date if
        # applicable.
        if not item.is_all_day:
            return item
        for field_name in ('start', 'end'):
            val = getattr(item, field_name)
            if val is None:
                continue
            # Return just the date part of the value. Subtract 1 day from the date if this is the end field. This is
            # the inverse of what we do in .to_xml(). Convert to the local timezone before getting the date.
            if field_name == 'end':
                val -= datetime.timedelta(days=1)
            tz = getattr(item, '_%s_timezone' % field_name)
            setattr(item, field_name, val.astimezone(tz).date())
        return item

    def tz_field_for_field_name(self, field_name):
        meeting_tz_field, start_tz_field, end_tz_field = CalendarItem.timezone_fields()
        if self.account.version.build < EXCHANGE_2010:
            return meeting_tz_field
        if field_name == 'start':
            return start_tz_field
        elif field_name == 'end':
            return end_tz_field
        raise ValueError('Unsupported field_name')

    def date_to_datetime(self, field_name):
        # EWS always expects a datetime. If we have a date value, then convert it to datetime in the local
        # timezone. Additionally, if this the end field, add 1 day to the date. We could add 12 hours to both
        # start and end values and let EWS apply its logic, but that seems hacky.
        value = getattr(self, field_name)
        tz = getattr(self, self.tz_field_for_field_name(field_name).name)
        value = EWSDateTime.combine(value, datetime.time(0, 0)).replace(tzinfo=tz)
        if field_name == 'end':
            value += datetime.timedelta(days=1)
        return value

    def to_xml(self, version):
        # EWS has some special logic related to all-day start and end values. Non-midnight start values are pushed to
        # the previous midnight. Non-midnight end values are pushed to the following midnight. Midnight in this context
        # refers to midnight in the local timezone. See
        #
        # https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/how-to-create-all-day-events-by-using-ews-in-exchange
        #
        elem = super().to_xml(version=version)
        if not self.is_all_day:
            return elem
        for field_name in ('start', 'end'):
            value = getattr(self, field_name)
            if value is None:
                continue
            if type(value) == EWSDate:
                # EWS always expects a datetime
                value = self.date_to_datetime(field_name=field_name)
                # We already generated an XML element for this field, but it contains a plain date at this point, which
                # is invalid. Replace the value.
                field = self.get_field_by_fieldname(field_name)
                set_xml_value(elem=elem.find(field.response_tag()), value=value, version=version)
        return elem


class BaseMeetingItem(Item):
    """A base class for meeting requests that share the same fields (Message, Request, Response, Cancellation)

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/responsecode
        Certain types are created as a side effect of doing something else. Meeting messages, for example, are created
        when you send a calendar item to attendees; they are not explicitly created.

    Therefore BaseMeetingItem inherits from  EWSElement has no save() or send() method

    """
    LOCAL_FIELDS = Message.LOCAL_FIELDS[:14] + Fields(
        AssociatedCalendarItemIdField('associated_calendar_item_id', field_uri='meeting:AssociatedCalendarItemId',
                                      value_cls=AssociatedCalendarItemId),
        BooleanField('is_delegated', field_uri='meeting:IsDelegated', is_read_only=True, default=False),
        BooleanField('is_out_of_date', field_uri='meeting:IsOutOfDate', is_read_only=True, default=False),
        BooleanField('has_been_processed', field_uri='meeting:HasBeenProcessed', is_read_only=True, default=False),
        ChoiceField('response_type', field_uri='meeting:ResponseType',
                    choices={Choice('Unknown'), Choice('Organizer'), Choice('Tentative'),
                             Choice('Accept'), Choice('Decline'), Choice('NoResponseReceived')},
                    is_required=True, default='Unknown'),
    )
    FIELDS = Item.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)


class MeetingRequest(BaseMeetingItem, AcceptDeclineMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/meetingrequest"""
    ELEMENT_NAME = 'MeetingRequest'
    LOCAL_FIELDS = Fields(
        ChoiceField('meeting_request_type', field_uri='meetingRequest:MeetingRequestType',
                    choices={Choice('FullUpdate'), Choice('InformationalUpdate'), Choice('NewMeetingRequest'),
                             Choice('None'), Choice('Outdated'), Choice('PrincipalWantsCopy'),
                             Choice('SilentUpdate')},
                    default='None'),
        ChoiceField('intended_free_busy_status', field_uri='meetingRequest:IntendedFreeBusyStatus', choices={
                    Choice('Free'), Choice('Tentative'), Choice('Busy'), Choice('OOF'), Choice('NoData')},
                    is_required=True, default='Busy'),
    ) + Fields(*(f for f in CalendarItem.LOCAL_FIELDS[1:] if f.name != 'is_response_requested'))

    # FIELDS on this element are shuffled compared to other elements
    culture_idx = None
    for i, field in enumerate(Item.FIELDS):
        if field.name == 'culture':
            culture_idx = i
            break
    FIELDS = Item.FIELDS[:culture_idx + 1] + BaseMeetingItem.LOCAL_FIELDS + LOCAL_FIELDS + Item.FIELDS[culture_idx + 1:]

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)


class MeetingMessage(BaseMeetingItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/meetingmessage"""
    # TODO: Untested - not sure if this is ever used
    ELEMENT_NAME = 'MeetingMessage'

    # FIELDS on this element are shuffled compared to other elements
    culture_idx = None
    for i, field in enumerate(Item.FIELDS):
        if field.name == 'culture':
            culture_idx = i
            break
    FIELDS = Item.FIELDS[:culture_idx + 1] + BaseMeetingItem.LOCAL_FIELDS + Item.FIELDS[culture_idx + 1:]

    __slots__ = tuple()


class MeetingResponse(BaseMeetingItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/meetingresponse"""
    ELEMENT_NAME = 'MeetingResponse'
    LOCAL_FIELDS = Fields(
        MailboxField('received_by', field_uri='message:ReceivedBy', is_read_only=True),
        MailboxField('received_representing', field_uri='message:ReceivedRepresenting', is_read_only=True),
        DateTimeField('proposed_start', field_uri='meeting:ProposedStart', supported_from=EXCHANGE_2013),
        DateTimeField('proposed_end', field_uri='meeting:ProposedEnd', supported_from=EXCHANGE_2013),
    )
    # FIELDS on this element are shuffled compared to other elements
    culture_idx = None
    for i, field in enumerate(Item.FIELDS):
        if field.name == 'culture':
            culture_idx = i
    effective_rights_idx = culture_idx + 1
    FIELDS = Item.FIELDS[:culture_idx + 1] \
        + BaseMeetingItem.LOCAL_FIELDS \
        + Item.FIELDS[effective_rights_idx:effective_rights_idx + 1] \
        + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)


class MeetingCancellation(BaseMeetingItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/meetingcancellation"""
    ELEMENT_NAME = 'MeetingCancellation'

    __slots__ = tuple()


class BaseMeetingReplyItem(BaseItem):
    """Base class for meeting request reply items that share the same fields (Accept, TentativelyAccept, Decline)"""
    FIELDS = Fields(
        CharField('item_class', field_uri='item:ItemClass', is_read_only=True),
        ChoiceField('sensitivity', field_uri='item:Sensitivity', choices={
            Choice('Normal'), Choice('Personal'), Choice('Private'), Choice('Confidential')
        }, is_required=True, default='Normal'),
        BodyField('body', field_uri='item:Body'),  # Accepts and returns Body or HTMLBody instances
        AttachmentField('attachments', field_uri='item:Attachments'),  # ItemAttachment or FileAttachment
        MessageHeaderField('headers', field_uri='item:InternetMessageHeaders', is_read_only=True),
    ) + Message.LOCAL_FIELDS[:6] + Fields(
        ReferenceItemIdField('reference_item_id', field_uri='item:ReferenceItemId'),
        MailboxField('received_by', field_uri='message:ReceivedBy', is_read_only=True),
        MailboxField('received_representing', field_uri='message:ReceivedRepresenting', is_read_only=True),
        DateTimeField('proposed_start', field_uri='meeting:ProposedStart', supported_from=EXCHANGE_2013),
        DateTimeField('proposed_end', field_uri='meeting:ProposedEnd', supported_from=EXCHANGE_2013),
    )

    __slots__ = tuple(f.name for f in FIELDS)

    @require_account
    def send(self, message_disposition=SEND_AND_SAVE_COPY):
        res = CreateItem(account=self.account).get(
            items=[self],
            folder=self.folder,
            message_disposition=message_disposition,
            send_meeting_invitations=SEND_TO_NONE,
            expect_result=message_disposition not in (SEND_ONLY, SEND_AND_SAVE_COPY),
        )
        return BulkCreateResult.from_xml(elem=res, account=self)


class AcceptItem(BaseMeetingReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/acceptitem"""
    ELEMENT_NAME = 'AcceptItem'

    __slots__ = tuple()


class TentativelyAcceptItem(BaseMeetingReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/tentativelyacceptitem"""
    ELEMENT_NAME = 'TentativelyAcceptItem'

    __slots__ = tuple()


class DeclineItem(BaseMeetingReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/declineitem"""
    ELEMENT_NAME = 'DeclineItem'

    __slots__ = tuple()


class CancelCalendarItem(BaseReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/cancelcalendaritem"""
    ELEMENT_NAME = 'CancelCalendarItem'
    FIELDS = Fields(*(f for f in BaseReplyItem.FIELDS if f.name != 'author'))
    __slots__ = tuple()
