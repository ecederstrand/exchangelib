import abc
from .errors import AutoDiscoverFailed as AutoDiscoverFailed, ErrorInternalServerError as ErrorInternalServerError, ErrorNonExistentMailbox as ErrorNonExistentMailbox, ErrorOrganizationNotFederated as ErrorOrganizationNotFederated, ErrorServerBusy as ErrorServerBusy, InvalidTypeError as InvalidTypeError
from .fields import AddressListField as AddressListField, AssociatedCalendarItemIdField as AssociatedCalendarItemIdField, Base64Field as Base64Field, BooleanField as BooleanField, CharField as CharField, CharListField as CharListField, Choice as Choice, ChoiceField as ChoiceField, DateTimeBackedDateField as DateTimeBackedDateField, DateTimeField as DateTimeField, DictionaryField as DictionaryField, EWSElementField as EWSElementField, EWSElementListField as EWSElementListField, EmailAddressField as EmailAddressField, EmailField as EmailField, EnumField as EnumField, EnumListField as EnumListField, ExtendedPropertyField as ExtendedPropertyField, Field as Field, FieldPath as FieldPath, FlaggedForActionField as FlaggedForActionField, FolderActionField as FolderActionField, FreeBusyStatusField as FreeBusyStatusField, GenericEventListField as GenericEventListField, IdElementField as IdElementField, IdField as IdField, ImportanceField as ImportanceField, IntegerField as IntegerField, InvalidField as InvalidField, InvalidFieldForVersion as InvalidFieldForVersion, MailboxField as MailboxField, MessageField as MessageField, RecipientAddressField as RecipientAddressField, ReferenceItemIdField as ReferenceItemIdField, RoutingTypeField as RoutingTypeField, SensitivityField as SensitivityField, SubField as SubField, TextField as TextField, TimeDeltaField as TimeDeltaField, TimeField as TimeField, TransitionListField as TransitionListField, TypeValueField as TypeValueField, UnknownEntriesField as UnknownEntriesField, WEEKDAY_NAMES as WEEKDAY_NAMES
from .util import ANS as ANS, MNS as MNS, TNS as TNS, create_element as create_element, get_xml_attr as get_xml_attr, set_xml_value as set_xml_value, value_to_xml_text as value_to_xml_text
from .version import Build as Build, EXCHANGE_2013 as EXCHANGE_2013, Version as Version
from _typeshed import Incomplete

log: Incomplete

class Fields(list):
    def __init__(self, *fields) -> None: ...
    def __getitem__(self, idx_or_slice): ...
    def __add__(self, other): ...
    def __iadd__(self, other): ...
    def __contains__(self, item) -> bool: ...
    def copy(self): ...
    def index_by_name(self, field_name): ...
    def insert(self, index, field) -> None: ...
    def remove(self, field) -> None: ...
    def append(self, field) -> None: ...

class Body(str):
    body_type: str
    def __add__(self, other): ...
    def __mod__(self, other): ...
    def format(self, *args, **kwargs): ...

class HTMLBody(Body):
    body_type: str

class UID(bytes):
    def __new__(cls, uid): ...
    @classmethod
    def to_global_object_id(cls, uid): ...

class EWSMeta(type, metaclass=abc.ABCMeta):
    def __new__(mcs, name, bases, kwargs): ...
    def __getattribute__(cls, k): ...

class EWSElement(metaclass=EWSMeta):
    ELEMENT_NAME: Incomplete
    FIELDS: Incomplete
    NAMESPACE = TNS
    def __init__(self, **kwargs) -> None: ...
    def __setattr__(self, key, value): ...
    def clean(self, version: Incomplete | None = None) -> None: ...
    @classmethod
    def from_xml(cls, elem, account): ...
    def to_xml(self, version): ...
    @classmethod
    def request_tag(cls): ...
    @classmethod
    def response_tag(cls): ...
    @classmethod
    def attribute_fields(cls): ...
    @classmethod
    def supported_fields(cls, version): ...
    @classmethod
    def get_field_by_fieldname(cls, fieldname): ...
    @classmethod
    def validate_field(cls, field, version) -> None: ...
    @classmethod
    def add_field(cls, field, insert_after) -> None: ...
    @classmethod
    def remove_field(cls, field) -> None: ...
    def __eq__(self, other): ...
    def __hash__(self): ...

class MessageHeader(EWSElement):
    ELEMENT_NAME: str
    name: Incomplete
    value: Incomplete

class BaseItemId(EWSElement, metaclass=EWSMeta):
    ID_ATTR: Incomplete
    CHANGEKEY_ATTR: Incomplete
    def __init__(self, *args, **kwargs) -> None: ...

class ItemId(BaseItemId):
    ELEMENT_NAME: str
    ID_ATTR: str
    CHANGEKEY_ATTR: str
    id: Incomplete
    changekey: Incomplete

class ParentItemId(ItemId):
    ELEMENT_NAME: str
    NAMESPACE = MNS

class RootItemId(BaseItemId):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    ID_ATTR: str
    CHANGEKEY_ATTR: str
    id: Incomplete
    changekey: Incomplete

class AssociatedCalendarItemId(ItemId):
    ELEMENT_NAME: str

class ConversationId(ItemId):
    ELEMENT_NAME: str

class ParentFolderId(ItemId):
    ELEMENT_NAME: str

class ReferenceItemId(ItemId):
    ELEMENT_NAME: str

class PersonaId(ItemId):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    @classmethod
    def response_tag(cls): ...

class SourceId(ItemId):
    ELEMENT_NAME: str

class FolderId(ItemId):
    ELEMENT_NAME: str

class RecurringMasterItemId(BaseItemId):
    ELEMENT_NAME: str
    ID_ATTR: str
    CHANGEKEY_ATTR: str
    id: Incomplete
    changekey: Incomplete

class OccurrenceItemId(BaseItemId):
    ELEMENT_NAME: str
    ID_ATTR: str
    CHANGEKEY_ATTR: str
    id: Incomplete
    changekey: Incomplete
    instance_index: Incomplete

class MovedItemId(ItemId):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    @classmethod
    def id_from_xml(cls, elem): ...

class OldItemId(ItemId):
    ELEMENT_NAME: str

class OldFolderId(FolderId):
    ELEMENT_NAME: str

class OldParentFolderId(ParentFolderId):
    ELEMENT_NAME: str

class Mailbox(EWSElement):
    ELEMENT_NAME: str
    MAILBOX: str
    ONE_OFF: str
    MAILBOX_TYPE_CHOICES: Incomplete
    name: Incomplete
    email_address: Incomplete
    routing_type: Incomplete
    mailbox_type: Incomplete
    item_id: Incomplete
    def clean(self, version: Incomplete | None = None) -> None: ...
    def __hash__(self): ...

class DLMailbox(Mailbox):
    NAMESPACE = MNS

class SendingAs(Mailbox):
    ELEMENT_NAME: str
    NAMESPACE = MNS

class RecipientAddress(Mailbox):
    ELEMENT_NAME: str

class EmailAddress(Mailbox):
    ELEMENT_NAME: str

class Address(Mailbox):
    ELEMENT_NAME: str

class AvailabilityMailbox(EWSElement):
    ELEMENT_NAME: str
    name: Incomplete
    email_address: Incomplete
    routing_type: Incomplete
    def __hash__(self): ...
    @classmethod
    def from_mailbox(cls, mailbox): ...

class Email(AvailabilityMailbox):
    ELEMENT_NAME: str

class MailboxData(EWSElement):
    ELEMENT_NAME: str
    ATTENDEE_TYPES: Incomplete
    email: Incomplete
    attendee_type: Incomplete
    exclude_conflicts: Incomplete

class DistinguishedFolderId(FolderId):
    ELEMENT_NAME: str
    mailbox: Incomplete
    @classmethod
    def from_xml(cls, elem, account): ...
    def clean(self, version: Incomplete | None = None) -> None: ...

class TimeWindow(EWSElement):
    ELEMENT_NAME: str
    start: Incomplete
    end: Incomplete
    def clean(self, version: Incomplete | None = None) -> None: ...

class FreeBusyViewOptions(EWSElement):
    ELEMENT_NAME: str
    REQUESTED_VIEWS: Incomplete
    time_window: Incomplete
    merged_free_busy_interval: Incomplete
    requested_view: Incomplete

class Attendee(EWSElement):
    ELEMENT_NAME: str
    RESPONSE_TYPES: Incomplete
    mailbox: Incomplete
    response_type: Incomplete
    last_response_time: Incomplete
    proposed_start: Incomplete
    proposed_end: Incomplete
    def __hash__(self): ...

class TimeZoneTransition(EWSElement, metaclass=EWSMeta):
    bias: Incomplete
    time: Incomplete
    occurrence: Incomplete
    iso_month: Incomplete
    weekday: Incomplete
    @classmethod
    def from_xml(cls, elem, account): ...
    def clean(self, version: Incomplete | None = None) -> None: ...

class StandardTime(TimeZoneTransition):
    ELEMENT_NAME: str

class DaylightTime(TimeZoneTransition):
    ELEMENT_NAME: str

class TimeZone(EWSElement):
    ELEMENT_NAME: str
    bias: Incomplete
    standard_time: Incomplete
    daylight_time: Incomplete
    def to_server_timezone(self, timezones, for_year): ...
    @classmethod
    def from_server_timezone(cls, tz_definition, for_year): ...

class CalendarView(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    start: Incomplete
    end: Incomplete
    max_items: Incomplete
    def clean(self, version: Incomplete | None = None) -> None: ...

class CalendarEventDetails(EWSElement):
    ELEMENT_NAME: str
    id: Incomplete
    subject: Incomplete
    location: Incomplete
    is_meeting: Incomplete
    is_recurring: Incomplete
    is_exception: Incomplete
    is_reminder_set: Incomplete
    is_private: Incomplete

class CalendarEvent(EWSElement):
    ELEMENT_NAME: str
    start: Incomplete
    end: Incomplete
    busy_type: Incomplete
    details: Incomplete

class WorkingPeriod(EWSElement):
    ELEMENT_NAME: str
    weekdays: Incomplete
    start: Incomplete
    end: Incomplete

class FreeBusyView(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    view_type: Incomplete
    merged: Incomplete
    calendar_events: Incomplete
    working_hours: Incomplete
    working_hours_timezone: Incomplete
    @classmethod
    def from_xml(cls, elem, account): ...

class RoomList(Mailbox):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    @classmethod
    def response_tag(cls): ...

class Room(Mailbox):
    ELEMENT_NAME: str
    @classmethod
    def from_xml(cls, elem, account): ...

class Member(EWSElement):
    ELEMENT_NAME: str
    mailbox: Incomplete
    status: Incomplete
    def __hash__(self): ...

class UserId(EWSElement):
    ELEMENT_NAME: str
    sid: Incomplete
    primary_smtp_address: Incomplete
    display_name: Incomplete
    distinguished_user: Incomplete
    external_user_identity: Incomplete

class BasePermission(EWSElement, metaclass=EWSMeta):
    PERMISSION_ENUM: Incomplete
    can_create_items: Incomplete
    can_create_subfolders: Incomplete
    is_folder_owner: Incomplete
    is_folder_visible: Incomplete
    is_folder_contact: Incomplete
    edit_items: Incomplete
    delete_items: Incomplete
    read_items: Incomplete
    user_id: Incomplete

class Permission(BasePermission):
    ELEMENT_NAME: str
    LEVEL_CHOICES: Incomplete
    permission_level: Incomplete

class CalendarPermission(BasePermission):
    ELEMENT_NAME: str
    LEVEL_CHOICES: Incomplete
    calendar_permission_level: Incomplete

class PermissionSet(EWSElement):
    ELEMENT_NAME: str
    permissions: Incomplete
    calendar_permissions: Incomplete
    unknown_entries: Incomplete

class EffectiveRights(EWSElement):
    ELEMENT_NAME: str
    create_associated: Incomplete
    create_contents: Incomplete
    create_hierarchy: Incomplete
    delete: Incomplete
    modify: Incomplete
    read: Incomplete
    view_private_items: Incomplete
    def __contains__(self, item) -> bool: ...

class DelegatePermissions(EWSElement):
    ELEMENT_NAME: str
    PERMISSION_LEVEL_CHOICES: Incomplete
    calendar_folder_permission_level: Incomplete
    tasks_folder_permission_level: Incomplete
    inbox_folder_permission_level: Incomplete
    contacts_folder_permission_level: Incomplete
    notes_folder_permission_level: Incomplete
    journal_folder_permission_level: Incomplete

class DelegateUser(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    user_id: Incomplete
    delegate_permissions: Incomplete
    receive_copies_of_meeting_messages: Incomplete
    view_private_items: Incomplete

class SearchableMailbox(EWSElement):
    ELEMENT_NAME: str
    guid: Incomplete
    primary_smtp_address: Incomplete
    is_external: Incomplete
    external_email: Incomplete
    display_name: Incomplete
    is_membership_group: Incomplete
    reference_id: Incomplete

class FailedMailbox(EWSElement):
    ELEMENT_NAME: str
    mailbox: Incomplete
    error_code: Incomplete
    error_message: Incomplete
    is_archive: Incomplete

MAIL_TIPS_TYPES: Incomplete

class OutOfOffice(EWSElement):
    ELEMENT_NAME: str
    reply_body: Incomplete
    start: Incomplete
    end: Incomplete
    @classmethod
    def duration_to_start_end(cls, elem, account): ...
    @classmethod
    def from_xml(cls, elem, account): ...

class MailTips(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    recipient_address: Incomplete
    pending_mail_tips: Incomplete
    out_of_office: Incomplete
    mailbox_full: Incomplete
    custom_mail_tip: Incomplete
    total_member_count: Incomplete
    external_member_count: Incomplete
    max_message_size: Incomplete
    delivery_restricted: Incomplete
    is_moderated: Incomplete
    invalid_recipient: Incomplete

ENTRY_ID: str
EWS_ID: str
EWS_LEGACY_ID: str
HEX_ENTRY_ID: str
OWA_ID: str
STORE_ID: str
ID_FORMATS: Incomplete

class AlternateId(EWSElement):
    ELEMENT_NAME: str
    id: Incomplete
    format: Incomplete
    mailbox: Incomplete
    is_archive: Incomplete
    @classmethod
    def response_tag(cls): ...

class AlternatePublicFolderId(EWSElement):
    ELEMENT_NAME: str
    folder_id: Incomplete
    format: Incomplete

class AlternatePublicFolderItemId(EWSElement):
    ELEMENT_NAME: str
    folder_id: Incomplete
    format: Incomplete
    item_id: Incomplete

class FieldURI(EWSElement):
    ELEMENT_NAME: str
    field_uri: Incomplete

class IndexedFieldURI(EWSElement):
    ELEMENT_NAME: str
    field_uri: Incomplete
    field_index: Incomplete

class ExtendedFieldURI(EWSElement):
    ELEMENT_NAME: str
    distinguished_property_set_id: Incomplete
    property_set_id: Incomplete
    property_tag: Incomplete
    property_name: Incomplete
    property_id: Incomplete
    property_type: Incomplete

class ExceptionFieldURI(EWSElement):
    ELEMENT_NAME: str
    field_uri: Incomplete

class CompleteName(EWSElement):
    ELEMENT_NAME: str
    title: Incomplete
    first_name: Incomplete
    middle_name: Incomplete
    last_name: Incomplete
    suffix: Incomplete
    initials: Incomplete
    full_name: Incomplete
    nickname: Incomplete
    yomi_first_name: Incomplete
    yomi_last_name: Incomplete

class ReminderMessageData(EWSElement):
    ELEMENT_NAME: str
    reminder_text: Incomplete
    location: Incomplete
    start_time: Incomplete
    end_time: Incomplete
    associated_calendar_item_id: Incomplete

class AcceptSharingInvitation(EWSElement):
    ELEMENT_NAME: str
    reference_item_id: Incomplete

class SuppressReadReceipt(EWSElement):
    ELEMENT_NAME: str
    reference_item_id: Incomplete

class RemoveItem(EWSElement):
    ELEMENT_NAME: str
    reference_item_id: Incomplete

class ResponseObjects(EWSElement):
    ELEMENT_NAME: str
    accept_item: Incomplete
    tentatively_accept_item: Incomplete
    decline_item: Incomplete
    reply_to_item: Incomplete
    forward_item: Incomplete
    reply_all_to_item: Incomplete
    cancel_calendar_item: Incomplete
    remove_item: Incomplete
    post_reply_item: Incomplete
    success_read_receipt: Incomplete
    accept_sharing_invitation: Incomplete

class PhoneNumber(EWSElement):
    ELEMENT_NAME: str
    number: Incomplete
    type: Incomplete

class IdChangeKeyMixIn(EWSElement, metaclass=EWSMeta):
    ID_ELEMENT_CLS: Incomplete
    def __init__(self, **kwargs) -> None: ...
    @classmethod
    def get_field_by_fieldname(cls, fieldname): ...
    @property
    def id(self): ...
    @id.setter
    def id(self, value) -> None: ...
    @property
    def changekey(self): ...
    @changekey.setter
    def changekey(self, value) -> None: ...
    @classmethod
    def id_from_xml(cls, elem): ...
    def to_id(self): ...
    def __eq__(self, other): ...
    def __hash__(self): ...

class DictionaryEntry(EWSElement):
    ELEMENT_NAME: str
    key: Incomplete
    value: Incomplete

class UserConfigurationName(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = TNS
    name: Incomplete
    folder: Incomplete
    def clean(self, version: Incomplete | None = None) -> None: ...
    @classmethod
    def from_xml(cls, elem, account): ...

class UserConfigurationNameMNS(UserConfigurationName):
    NAMESPACE = MNS

class UserConfiguration(IdChangeKeyMixIn):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    ID_ELEMENT_CLS = ItemId
    user_configuration_name: Incomplete
    dictionary: Incomplete
    xml_data: Incomplete
    binary_data: Incomplete

class Attribution(IdChangeKeyMixIn):
    ELEMENT_NAME: str
    ID_ELEMENT_CLS = SourceId
    ID: Incomplete
    display_name: Incomplete
    is_writable: Incomplete
    is_quick_contact: Incomplete
    is_hidden: Incomplete
    folder_id: Incomplete

class BodyContentValue(EWSElement):
    ELEMENT_NAME: str
    value: Incomplete
    body_type: Incomplete

class BodyContentAttributedValue(EWSElement):
    ELEMENT_NAME: str
    value: Incomplete
    attributions: Incomplete

class StringAttributedValue(EWSElement):
    ELEMENT_NAME: str
    value: Incomplete
    attributions: Incomplete

class PersonaPhoneNumberTypeValue(EWSElement):
    ELEMENT_NAME: str
    number: Incomplete
    type: Incomplete

class PhoneNumberAttributedValue(EWSElement):
    ELEMENT_NAME: str
    value: Incomplete
    attributions: Incomplete

class EmailAddressTypeValue(Mailbox):
    ELEMENT_NAME: str
    original_display_name: Incomplete

class EmailAddressAttributedValue(EWSElement):
    ELEMENT_NAME: str
    value: Incomplete
    attributions: Incomplete

class PersonaPostalAddressTypeValue(Mailbox):
    ELEMENT_NAME: str
    street: Incomplete
    city: Incomplete
    state: Incomplete
    country: Incomplete
    postal_code: Incomplete
    post_office_box: Incomplete
    type: Incomplete
    latitude: Incomplete
    longitude: Incomplete
    accuracy: Incomplete
    altitude: Incomplete
    altitude_accuracy: Incomplete
    formatted_address: Incomplete
    location_uri: Incomplete
    location_source: Incomplete

class PostalAddressAttributedValue(EWSElement):
    ELEMENT_NAME: str
    value: Incomplete
    attributions: Incomplete

class Event(EWSElement, metaclass=EWSMeta):
    watermark: Incomplete

class TimestampEvent(Event, metaclass=EWSMeta):
    FOLDER: str
    ITEM: str
    timestamp: Incomplete
    item_id: Incomplete
    folder_id: Incomplete
    parent_folder_id: Incomplete
    @property
    def event_type(self): ...

class OldTimestampEvent(TimestampEvent, metaclass=EWSMeta):
    old_item_id: Incomplete
    old_folder_id: Incomplete
    old_parent_folder_id: Incomplete

class CopiedEvent(OldTimestampEvent):
    ELEMENT_NAME: str

class CreatedEvent(TimestampEvent):
    ELEMENT_NAME: str

class DeletedEvent(TimestampEvent):
    ELEMENT_NAME: str

class ModifiedEvent(TimestampEvent):
    ELEMENT_NAME: str
    unread_count: Incomplete

class MovedEvent(OldTimestampEvent):
    ELEMENT_NAME: str

class NewMailEvent(TimestampEvent):
    ELEMENT_NAME: str

class StatusEvent(Event):
    ELEMENT_NAME: str

class FreeBusyChangedEvent(TimestampEvent):
    ELEMENT_NAME: str

class Notification(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    subscription_id: Incomplete
    previous_watermark: Incomplete
    more_events: Incomplete
    events: Incomplete

class BaseTransition(EWSElement, metaclass=EWSMeta):
    to: Incomplete
    kind: Incomplete
    @staticmethod
    def transition_model_from_tag(tag): ...
    @classmethod
    def from_xml(cls, elem, account): ...

class Transition(BaseTransition):
    ELEMENT_NAME: str

class AbsoluteDateTransition(BaseTransition):
    ELEMENT_NAME: str
    date: Incomplete

class RecurringDayTransition(BaseTransition):
    ELEMENT_NAME: str
    offset: Incomplete
    month: Incomplete
    day_of_week: Incomplete
    occurrence: Incomplete
    @classmethod
    def from_xml(cls, elem, account): ...

class RecurringDateTransition(BaseTransition):
    ELEMENT_NAME: str
    offset: Incomplete
    month: Incomplete
    day: Incomplete

class Period(EWSElement):
    ELEMENT_NAME: str
    id: Incomplete
    name: Incomplete
    bias: Incomplete
    @property
    def bias_in_minutes(self): ...

class TransitionsGroup(EWSElement):
    ELEMENT_NAME: str
    id: Incomplete
    transitions: Incomplete

class TimeZoneDefinition(EWSElement):
    ELEMENT_NAME: str
    id: Incomplete
    name: Incomplete
    periods: Incomplete
    transitions_groups: Incomplete
    transitions: Incomplete
    def get_std_and_dst(self, for_year): ...

class UserResponse(EWSElement):
    ELEMENT_NAME: str
    SETTINGS_MAP: Incomplete
    REVERSE_SETTINGS_MAP: Incomplete
    error_code: Incomplete
    error_message: Incomplete
    redirect_address: Incomplete
    redirect_url: Incomplete
    user_settings_errors: Incomplete
    user_settings: Incomplete
    @property
    def autodiscover_smtp_address(self): ...
    @property
    def ews_url(self): ...
    @property
    def version(self): ...
    def raise_errors(self) -> None: ...
    @classmethod
    def parse_elem(cls, elem): ...
    @classmethod
    def from_xml(cls, elem, account): ...

class WithinDateRange(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    start_date_time: Incomplete
    end_date_time: Incomplete

class WithinSizeRange(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    minimum_size: Incomplete
    maximum_size: Incomplete

class Conditions(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = TNS
    categories: Incomplete
    contains_body_strings: Incomplete
    contains_header_strings: Incomplete
    contains_recipient_strings: Incomplete
    contains_sender_strings: Incomplete
    contains_subject_or_body_strings: Incomplete
    contains_subject_strings: Incomplete
    flagged_for_action: Incomplete
    from_addresses: Incomplete
    from_connected_accounts: Incomplete
    has_attachments: Incomplete
    importance: Incomplete
    is_approval_request: Incomplete
    is_automatic_forward: Incomplete
    is_automatic_reply: Incomplete
    is_encrypted: Incomplete
    is_meeting_request: Incomplete
    is_meeting_response: Incomplete
    is_ndr: Incomplete
    is_permission_controlled: Incomplete
    is_read_receipt: Incomplete
    is_signed: Incomplete
    is_voicemail: Incomplete
    item_classes: Incomplete
    message_classifications: Incomplete
    not_sent_to_me: Incomplete
    sent_cc_me: Incomplete
    sent_only_to_me: Incomplete
    sent_to_addresses: Incomplete
    sent_to_me: Incomplete
    sent_to_or_cc_me: Incomplete
    sensitivity: Incomplete
    within_date_range: Incomplete
    within_size_range: Incomplete

class Exceptions(Conditions):
    ELEMENT_NAME: str
    NAMESPACE = TNS

class CopyToFolder(EWSElement):
    ELEMENT_NAME: str
    folder_id: Incomplete
    distinguished_folder_id: Incomplete

class MoveToFolder(CopyToFolder):
    ELEMENT_NAME: str

class Actions(EWSElement):
    ELEMENT_NAME: str
    assign_categories: Incomplete
    copy_to_folder: Incomplete
    delete: Incomplete
    forward_as_attachment_to_recipients: Incomplete
    forward_to_recipients: Incomplete
    mark_importance: Incomplete
    mark_as_read: Incomplete
    move_to_folder: Incomplete
    permanent_delete: Incomplete
    redirect_to_recipients: Incomplete
    send_sms_alert_to_recipients: Incomplete
    server_reply_with_message: Incomplete
    stop_processing_rules: Incomplete

class Rule(EWSElement):
    account: Incomplete
    def __init__(self, **kwargs) -> None: ...
    ELEMENT_NAME: str
    id: Incomplete
    display_name: Incomplete
    priority: Incomplete
    is_enabled: Incomplete
    is_not_supported: Incomplete
    is_in_error: Incomplete
    conditions: Incomplete
    exceptions: Incomplete
    actions: Incomplete
    @classmethod
    def from_xml(cls, elem, account): ...
    def save(self): ...
    def delete(self) -> None: ...

class InboxRules(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    rule: Incomplete

class CreateRuleOperation(EWSElement):
    ELEMENT_NAME: str
    rule: Incomplete

class SetRuleOperation(EWSElement):
    ELEMENT_NAME: str
    rule: Incomplete

class DeleteRuleOperation(EWSElement):
    ELEMENT_NAME: str
    id: Incomplete

class Operations(EWSElement):
    ELEMENT_NAME: str
    NAMESPACE = MNS
    create_rule_operation: Incomplete
    set_rule_operation: Incomplete
    delete_rule_operation: Incomplete
