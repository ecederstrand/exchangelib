from ..ewsdatetime import EWSDate as EWSDate, EWSDateTime as EWSDateTime
from ..fields import AppointmentStateField as AppointmentStateField, AssociatedCalendarItemIdField as AssociatedCalendarItemIdField, AttachmentField as AttachmentField, AttendeesField as AttendeesField, BodyField as BodyField, BooleanField as BooleanField, CharField as CharField, Choice as Choice, ChoiceField as ChoiceField, DateOrDateTimeField as DateOrDateTimeField, DateTimeField as DateTimeField, EWSElementListField as EWSElementListField, EnumAsIntField as EnumAsIntField, FreeBusyStatusField as FreeBusyStatusField, IntegerField as IntegerField, MailboxField as MailboxField, MessageHeaderField as MessageHeaderField, OccurrenceField as OccurrenceField, OccurrenceListField as OccurrenceListField, RecurrenceField as RecurrenceField, ReferenceItemIdField as ReferenceItemIdField, TextField as TextField, TimeZoneField as TimeZoneField, URIField as URIField
from ..properties import Attendee as Attendee, EWSMeta as EWSMeta, OccurrenceItemId as OccurrenceItemId, RecurringMasterItemId as RecurringMasterItemId, ReferenceItemId as ReferenceItemId
from ..recurrence import DeletedOccurrence as DeletedOccurrence, FirstOccurrence as FirstOccurrence, LastOccurrence as LastOccurrence, Occurrence as Occurrence
from ..util import require_account as require_account, set_xml_value as set_xml_value
from ..version import EXCHANGE_2010 as EXCHANGE_2010, EXCHANGE_2013 as EXCHANGE_2013
from .base import BaseItem as BaseItem, BaseReplyItem as BaseReplyItem, SEND_AND_SAVE_COPY as SEND_AND_SAVE_COPY, SEND_TO_NONE as SEND_TO_NONE
from .item import Item as Item
from .message import Message as Message
from _typeshed import Incomplete

log: Incomplete
CONFERENCE_TYPES: Incomplete
SINGLE: str
OCCURRENCE: str
EXCEPTION: str
RECURRING_MASTER: str
CALENDAR_ITEM_CHOICES: Incomplete

class AcceptDeclineMixIn:
    def accept(self, message_disposition=..., **kwargs): ...
    def decline(self, message_disposition=..., **kwargs): ...
    def tentatively_accept(self, message_disposition=..., **kwargs): ...

class CalendarItem(Item, AcceptDeclineMixIn):
    ELEMENT_NAME: str
    uid: Incomplete
    recurrence_id: Incomplete
    start: Incomplete
    end: Incomplete
    original_start: Incomplete
    is_all_day: Incomplete
    legacy_free_busy_status: Incomplete
    location: Incomplete
    when: Incomplete
    is_meeting: Incomplete
    is_cancelled: Incomplete
    is_recurring: Incomplete
    meeting_request_was_sent: Incomplete
    is_response_requested: Incomplete
    type: Incomplete
    my_response_type: Incomplete
    organizer: Incomplete
    required_attendees: Incomplete
    optional_attendees: Incomplete
    resources: Incomplete
    conflicting_meeting_count: Incomplete
    adjacent_meeting_count: Incomplete
    conflicting_meetings: Incomplete
    adjacent_meetings: Incomplete
    duration: Incomplete
    appointment_reply_time: Incomplete
    appointment_sequence_number: Incomplete
    appointment_state: Incomplete
    recurrence: Incomplete
    first_occurrence: Incomplete
    last_occurrence: Incomplete
    modified_occurrences: Incomplete
    deleted_occurrences: Incomplete
    conference_type: Incomplete
    allow_new_time_proposal: Incomplete
    is_online_meeting: Incomplete
    meeting_workspace_url: Incomplete
    net_show_url: Incomplete
    def occurrence(self, index): ...
    def recurring_master(self): ...
    @classmethod
    def timezone_fields(cls): ...
    def clean_timezone_fields(self, version) -> None: ...
    def clean(self, version: Incomplete | None = None) -> None: ...
    def cancel(self, **kwargs): ...
    @classmethod
    def from_xml(cls, elem, account): ...
    def tz_field_for_field_name(self, field_name): ...
    def date_to_datetime(self, field_name): ...
    def to_xml(self, version): ...

class BaseMeetingItem(Item, metaclass=EWSMeta):
    associated_calendar_item_id: Incomplete
    is_delegated: Incomplete
    is_out_of_date: Incomplete
    has_been_processed: Incomplete
    response_type: Incomplete
    effective_rights_idx: Incomplete
    sender_idx: Incomplete
    received_representing_idx: Incomplete
    FIELDS: Incomplete

class MeetingRequest(BaseMeetingItem, AcceptDeclineMixIn):
    ELEMENT_NAME: str
    meeting_request_type: Incomplete
    intended_free_busy_status: Incomplete
    start_idx: Incomplete
    is_response_requested_idx: Incomplete
    FIELDS: Incomplete

class MeetingMessage(BaseMeetingItem):
    ELEMENT_NAME: str

class MeetingResponse(BaseMeetingItem):
    ELEMENT_NAME: str
    proposed_start: Incomplete
    proposed_end: Incomplete

class MeetingCancellation(BaseMeetingItem):
    ELEMENT_NAME: str

class BaseMeetingReplyItem(BaseItem, metaclass=EWSMeta):
    item_class: Incomplete
    sensitivity: Incomplete
    body: Incomplete
    attachments: Incomplete
    headers: Incomplete
    sender: Incomplete
    to_recipients: Incomplete
    cc_recipients: Incomplete
    bcc_recipients: Incomplete
    is_read_receipt_requested: Incomplete
    is_delivery_receipt_requested: Incomplete
    reference_item_id: Incomplete
    received_by: Incomplete
    received_representing: Incomplete
    proposed_start: Incomplete
    proposed_end: Incomplete
    def send(self, message_disposition=...): ...

class AcceptItem(BaseMeetingReplyItem):
    ELEMENT_NAME: str

class TentativelyAcceptItem(BaseMeetingReplyItem):
    ELEMENT_NAME: str

class DeclineItem(BaseMeetingReplyItem):
    ELEMENT_NAME: str

class CancelCalendarItem(BaseReplyItem):
    ELEMENT_NAME: str
    author_idx: Incomplete
    FIELDS: Incomplete

class _Booking(Item):
    ELEMENT_NAME: str
