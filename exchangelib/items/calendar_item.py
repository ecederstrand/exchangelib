import datetime
import logging

from .base import BaseItem, BaseReplyItem, SEND_AND_SAVE_COPY, SEND_TO_NONE
from .item import Item
from .message import Message
from ..ewsdatetime import EWSDate, EWSDateTime
from ..fields import BooleanField, IntegerField, TextField, ChoiceField, URIField, BodyField, DateTimeField, \
    MessageHeaderField, AttachmentField, RecurrenceField, MailboxField, AttendeesField, Choice, OccurrenceField, \
    OccurrenceListField, TimeZoneField, CharField, EnumAsIntField, FreeBusyStatusField, ReferenceItemIdField, \
    AssociatedCalendarItemIdField, DateOrDateTimeField, EWSElementListField, AppointmentStateField
from ..properties import Attendee, ReferenceItemId, OccurrenceItemId, RecurringMasterItemId, EWSMeta
from ..recurrence import FirstOccurrence, LastOccurrence, Occurrence, DeletedOccurrence
from ..services import CreateItem
from ..util import set_xml_value, require_account
from ..version import EXCHANGE_2010, EXCHANGE_2013

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
    """A mixin for items that can be declined or accepted."""

    def accept(self, message_disposition=None, **kwargs):
        return AcceptItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            **kwargs
        ).send(message_disposition)

    def decline(self, message_disposition=None, **kwargs):
        return DeclineItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            **kwargs
        ).send(message_disposition)

    def tentatively_accept(self, message_disposition=None, **kwargs):
        return TentativelyAcceptItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            **kwargs
        ).send(message_disposition)


class CalendarItem(Item, AcceptDeclineMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendaritem"""

    ELEMENT_NAME = 'CalendarItem'

    uid = TextField(field_uri='calendar:UID', is_required_after_save=True, is_searchable=False)
    start = DateOrDateTimeField(field_uri='calendar:Start', is_required=True)
    end = DateOrDateTimeField(field_uri='calendar:End', is_required=True)
    original_start = DateTimeField(field_uri='calendar:OriginalStart', is_read_only=True)
    is_all_day = BooleanField(field_uri='calendar:IsAllDayEvent', is_required=True, default=False)
    legacy_free_busy_status = FreeBusyStatusField(field_uri='calendar:LegacyFreeBusyStatus', is_required=True,
                                                  default='Busy')
    location = TextField(field_uri='calendar:Location')
    when = TextField(field_uri='calendar:When')
    is_meeting = BooleanField(field_uri='calendar:IsMeeting', is_read_only=True)
    is_cancelled = BooleanField(field_uri='calendar:IsCancelled', is_read_only=True)
    is_recurring = BooleanField(field_uri='calendar:IsRecurring', is_read_only=True)
    meeting_request_was_sent = BooleanField(field_uri='calendar:MeetingRequestWasSent', is_read_only=True)
    is_response_requested = BooleanField(field_uri='calendar:IsResponseRequested', default=None,
                                         is_required_after_save=True, is_searchable=False)
    type = ChoiceField(field_uri='calendar:CalendarItemType', choices={Choice(c) for c in CALENDAR_ITEM_CHOICES},
                       is_read_only=True)
    my_response_type = ChoiceField(field_uri='calendar:MyResponseType', choices={
            Choice(c) for c in Attendee.RESPONSE_TYPES
    }, is_read_only=True)
    organizer = MailboxField(field_uri='calendar:Organizer', is_read_only=True)
    required_attendees = AttendeesField(field_uri='calendar:RequiredAttendees', is_searchable=False)
    optional_attendees = AttendeesField(field_uri='calendar:OptionalAttendees', is_searchable=False)
    resources = AttendeesField(field_uri='calendar:Resources', is_searchable=False)
    conflicting_meeting_count = IntegerField(field_uri='calendar:ConflictingMeetingCount', is_read_only=True)
    adjacent_meeting_count = IntegerField(field_uri='calendar:AdjacentMeetingCount', is_read_only=True)
    conflicting_meetings = EWSElementListField(field_uri='calendar:ConflictingMeetings', value_cls='CalendarItem',
                                               namespace=Item.NAMESPACE, is_read_only=True)
    adjacent_meetings = EWSElementListField(field_uri='calendar:AdjacentMeetings', value_cls='CalendarItem',
                                            namespace=Item.NAMESPACE, is_read_only=True)
    duration = CharField(field_uri='calendar:Duration', is_read_only=True)
    appointment_reply_time = DateTimeField(field_uri='calendar:AppointmentReplyTime', is_read_only=True)
    appointment_sequence_number = IntegerField(field_uri='calendar:AppointmentSequenceNumber', is_read_only=True)
    appointment_state = AppointmentStateField(field_uri='calendar:AppointmentState', is_read_only=True)
    recurrence = RecurrenceField(field_uri='calendar:Recurrence', is_searchable=False)
    first_occurrence = OccurrenceField(field_uri='calendar:FirstOccurrence', value_cls=FirstOccurrence,
                                       is_read_only=True)
    last_occurrence = OccurrenceField(field_uri='calendar:LastOccurrence', value_cls=LastOccurrence,
                                      is_read_only=True)
    modified_occurrences = OccurrenceListField(field_uri='calendar:ModifiedOccurrences', value_cls=Occurrence,
                                               is_read_only=True)
    deleted_occurrences = OccurrenceListField(field_uri='calendar:DeletedOccurrences', value_cls=DeletedOccurrence,
                                              is_read_only=True)
    _meeting_timezone = TimeZoneField(field_uri='calendar:MeetingTimeZone', deprecated_from=EXCHANGE_2010,
                                      is_searchable=False)
    _start_timezone = TimeZoneField(field_uri='calendar:StartTimeZone', supported_from=EXCHANGE_2010,
                                    is_searchable=False)
    _end_timezone = TimeZoneField(field_uri='calendar:EndTimeZone', supported_from=EXCHANGE_2010,
                                  is_searchable=False)
    conference_type = EnumAsIntField(field_uri='calendar:ConferenceType', enum=CONFERENCE_TYPES, min=0,
                                     default=None, is_required_after_save=True)
    allow_new_time_proposal = BooleanField(field_uri='calendar:AllowNewTimeProposal', default=None,
                                           is_required_after_save=True, is_searchable=False)
    is_online_meeting = BooleanField(field_uri='calendar:IsOnlineMeeting', default=None,
                                     is_read_only=True)
    meeting_workspace_url = URIField(field_uri='calendar:MeetingWorkspaceUrl')
    net_show_url = URIField(field_uri='calendar:NetShowUrl')

    def occurrence(self, index):
        """Get an occurrence of a recurring master by index. No query is sent to the server to actually fetch the item.
        Call refresh() on the item do do so.

        Only call this method on a recurring master.

        :param index: The index, which is 1-based

        :return The occurrence
        """
        return self.__class__(
            account=self.account,
            folder=self.folder,
            _id=OccurrenceItemId(id=self.id, changekey=self.changekey, instance_index=index),
        )

    def recurring_master(self):
        """Get the recurring master of an occurrence. No query is sent to the server to actually fetch the item.
        Call refresh() on the item do do so.

        Only call this method on an occurrence of a recurring master.

        :return: The master occurrence
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
        # Sets proper values on the timezone fields if they are not already set
        if self.start is None:
            start_tz = None
        elif type(self.start) in (EWSDate, datetime.date):
            start_tz = self.account.default_timezone
        else:
            start_tz = self.start.tzinfo
        if self.end is None:
            end_tz = None
        elif type(self.end) in (EWSDate, datetime.date):
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
        if field_name == 'end':
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
            if type(value) in (EWSDate, datetime.date):
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

    associated_calendar_item_id = AssociatedCalendarItemIdField(field_uri='meeting:AssociatedCalendarItemId')
    is_delegated = BooleanField(field_uri='meeting:IsDelegated', is_read_only=True, default=False)
    is_out_of_date = BooleanField(field_uri='meeting:IsOutOfDate', is_read_only=True, default=False)
    has_been_processed = BooleanField(field_uri='meeting:HasBeenProcessed', is_read_only=True, default=False)
    response_type = ChoiceField(field_uri='meeting:ResponseType', choices={
        Choice('Unknown'), Choice('Organizer'), Choice('Tentative'), Choice('Accept'), Choice('Decline'),
        Choice('NoResponseReceived')
    }, is_required=True, default='Unknown')

    reply_to_idx = Message.FIELDS.index_by_name('reply_to')
    FIELDS = Message.FIELDS[:reply_to_idx + 1]


class MeetingRequest(BaseMeetingItem, AcceptDeclineMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/meetingrequest"""

    ELEMENT_NAME = 'MeetingRequest'

    meeting_request_type = ChoiceField(field_uri='meetingRequest:MeetingRequestType', choices={
        Choice('FullUpdate'), Choice('InformationalUpdate'), Choice('NewMeetingRequest'), Choice('None'),
        Choice('Outdated'), Choice('PrincipalWantsCopy'), Choice('SilentUpdate')
    }, default='None')
    intended_free_busy_status = ChoiceField(field_uri='meetingRequest:IntendedFreeBusyStatus', choices={
            Choice('Free'), Choice('Tentative'), Choice('Busy'), Choice('OOF'), Choice('NoData')
    }, is_required=True, default='Busy')

    # FIELDS on this element are shuffled compared to other elements
    culture_idx = Item.FIELDS.index_by_name('culture')
    assoc_idx = BaseMeetingItem.FIELDS.index_by_name('associated_calendar_item_id')
    FIELDS = Item.FIELDS[:culture_idx + 1] + BaseMeetingItem.FIELDS[assoc_idx:] + Item.FIELDS[culture_idx + 1:]


class MeetingMessage(BaseMeetingItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/meetingmessage"""

    ELEMENT_NAME = 'MeetingMessage'

    # FIELDS on this element are shuffled compared to other elements
    culture_idx = Item.FIELDS.index_by_name('culture')
    assoc_idx = BaseMeetingItem.FIELDS.index_by_name('associated_calendar_item_id')
    FIELDS = Item.FIELDS[:culture_idx + 1] + BaseMeetingItem.FIELDS[assoc_idx:] + Item.FIELDS[culture_idx + 1:]


class MeetingResponse(BaseMeetingItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/meetingresponse"""

    ELEMENT_NAME = 'MeetingResponse'

    received_by = MailboxField(field_uri='message:ReceivedBy', is_read_only=True)
    received_representing = MailboxField(field_uri='message:ReceivedRepresenting', is_read_only=True)
    proposed_start = DateTimeField(field_uri='meeting:ProposedStart', supported_from=EXCHANGE_2013)
    proposed_end = DateTimeField(field_uri='meeting:ProposedEnd', supported_from=EXCHANGE_2013)

    # FIELDS on this element are shuffled compared to other elements
    culture_idx = Item.FIELDS.index_by_name('culture')
    effective_rights_idx = culture_idx + 1
    assoc_idx = BaseMeetingItem.FIELDS.index_by_name('associated_calendar_item_id')
    FIELDS = Item.FIELDS[:culture_idx + 1] + BaseMeetingItem.FIELDS[assoc_idx:] \
        + Item.FIELDS[effective_rights_idx:effective_rights_idx + 1]


class MeetingCancellation(BaseMeetingItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/meetingcancellation"""

    ELEMENT_NAME = 'MeetingCancellation'


class BaseMeetingReplyItem(BaseItem, metaclass=EWSMeta):
    """Base class for meeting request reply items that share the same fields (Accept, TentativelyAccept, Decline)."""

    item_class = CharField(field_uri='item:ItemClass', is_read_only=True)
    sensitivity = ChoiceField(field_uri='item:Sensitivity', choices={
        Choice('Normal'), Choice('Personal'), Choice('Private'), Choice('Confidential')
    }, is_required=True, default='Normal')
    body = BodyField(field_uri='item:Body')  # Accepts and returns Body or HTMLBody instances
    attachments = AttachmentField(field_uri='item:Attachments')  # ItemAttachment or FileAttachment
    headers = MessageHeaderField(field_uri='item:InternetMessageHeaders', is_read_only=True)

    sender = Message.FIELDS['sender']
    to_recipients = Message.FIELDS['to_recipients']
    cc_recipients = Message.FIELDS['cc_recipients']
    bcc_recipients = Message.FIELDS['bcc_recipients']
    is_read_receipt_requested = Message.FIELDS['is_read_receipt_requested']
    is_delivery_receipt_requested = Message.FIELDS['is_delivery_receipt_requested']

    reference_item_id = ReferenceItemIdField(field_uri='item:ReferenceItemId')
    received_by = MailboxField(field_uri='message:ReceivedBy', is_read_only=True)
    received_representing = MailboxField(field_uri='message:ReceivedRepresenting', is_read_only=True)
    proposed_start = DateTimeField(field_uri='meeting:ProposedStart', supported_from=EXCHANGE_2013)
    proposed_end = DateTimeField(field_uri='meeting:ProposedEnd', supported_from=EXCHANGE_2013)

    @require_account
    def send(self, message_disposition=SEND_AND_SAVE_COPY):
        return CreateItem(account=self.account).get(
            items=[self],
            folder=self.folder,
            message_disposition=message_disposition,
            send_meeting_invitations=SEND_TO_NONE,
        )


class AcceptItem(BaseMeetingReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/acceptitem"""

    ELEMENT_NAME = 'AcceptItem'


class TentativelyAcceptItem(BaseMeetingReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/tentativelyacceptitem"""

    ELEMENT_NAME = 'TentativelyAcceptItem'


class DeclineItem(BaseMeetingReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/declineitem"""

    ELEMENT_NAME = 'DeclineItem'


class CancelCalendarItem(BaseReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/cancelcalendaritem"""

    ELEMENT_NAME = 'CancelCalendarItem'
    author_idx = BaseReplyItem.FIELDS.index_by_name('author')
    FIELDS = BaseReplyItem.FIELDS[:author_idx] + BaseReplyItem.FIELDS[author_idx + 1:]
