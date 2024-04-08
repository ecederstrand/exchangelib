import abc
import binascii
import codecs
import datetime
import logging
import struct
from inspect import getmro
from threading import Lock

from .errors import (
    AutoDiscoverFailed,
    ErrorInternalServerError,
    ErrorNonExistentMailbox,
    ErrorOrganizationNotFederated,
    ErrorServerBusy,
    InvalidTypeError,
)
from .fields import (
    WEEKDAY_NAMES,
    AddressListField,
    AssociatedCalendarItemIdField,
    Base64Field,
    BooleanField,
    CharField,
    CharListField,
    Choice,
    ChoiceField,
    DateTimeBackedDateField,
    DateTimeField,
    DictionaryField,
    EmailAddressField,
    EmailField,
    EnumField,
    EnumListField,
    EWSElementField,
    EWSElementListField,
    ExtendedPropertyField,
    Field,
    FieldPath,
    FlaggedForActionField,
    FolderActionField,
    FreeBusyStatusField,
    GenericEventListField,
    IdElementField,
    IdField,
    ImportanceField,
    IntegerField,
    InvalidField,
    InvalidFieldForVersion,
    MailboxField,
    MessageField,
    RecipientAddressField,
    ReferenceItemIdField,
    RoutingTypeField,
    SensitivityField,
    SubField,
    TextField,
    TimeDeltaField,
    TimeField,
    TransitionListField,
    TypeValueField,
    UnknownEntriesField,
)
from .util import ANS, MNS, TNS, create_element, get_xml_attr, set_xml_value, value_to_xml_text
from .version import EXCHANGE_2013, Build, Version

log = logging.getLogger(__name__)


class Fields(list):
    """A collection type for the FIELDS class attribute. Works like a list but supports fast lookup by name."""

    def __init__(self, *fields):
        super().__init__(fields)
        self._dict = {}
        for f in fields:
            # Check for duplicate field names
            if f.name in self._dict:
                raise ValueError(f"Field {f!r} is a duplicate")
            self._dict[f.name] = f

    def __getitem__(self, idx_or_slice):
        # Support fast lookup by name. Make sure slicing returns an instance of this class
        if isinstance(idx_or_slice, str):
            return self._dict[idx_or_slice]
        if isinstance(idx_or_slice, int):
            return super().__getitem__(idx_or_slice)
        res = super().__getitem__(idx_or_slice)
        return self.__class__(*res)

    def __add__(self, other):
        # Make sure addition returns an instance of this class
        res = super().__add__(other)
        return self.__class__(*res)

    def __iadd__(self, other):
        for f in other:
            self.append(f)
        return self

    def __contains__(self, item):
        return item in self._dict

    def copy(self):
        return self.__class__(*self)

    def index_by_name(self, field_name):
        for i, f in enumerate(self):
            if f.name == field_name:
                return i
        raise ValueError(f"Unknown field name {field_name!r}")

    def insert(self, index, field):
        if field.name in self._dict:
            raise ValueError(f"Field {field!r} is a duplicate")
        super().insert(index, field)
        self._dict[field.name] = field

    def remove(self, field):
        super().remove(field)
        del self._dict[field.name]

    def append(self, field):
        super().append(field)
        self._dict[field.name] = field


class Body(str):
    """Helper to mark the 'body' field as a complex attribute.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/body
    """

    body_type = "Text"

    def __add__(self, other):
        # Make sure Body('') + 'foo' returns a Body type
        return self.__class__(super().__add__(other))

    def __mod__(self, other):
        # Make sure Body('%s') % 'foo' returns a Body type
        return self.__class__(super().__mod__(other))

    def format(self, *args, **kwargs):
        # Make sure Body('{}').format('foo') returns a Body type
        return self.__class__(super().format(*args, **kwargs))


class HTMLBody(Body):
    """Helper to mark the 'body' field as a complex attribute.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/body
    """

    body_type = "HTML"


class UID(bytes):
    """Helper class to encode Calendar UIDs. See issue #453. Example:

    class GlobalObjectId(ExtendedProperty):
        distinguished_property_set_id = 'Meeting'
        property_id = 3
        property_type = 'Binary'

    CalendarItem.register('global_object_id', GlobalObjectId)
    account.calendar.filter(global_object_id=UID('261cbc18-1f65-5a0a-bd11-23b1e224cc2f'))
    """

    _HEADER = binascii.hexlify(
        bytearray((0x04, 0x00, 0x00, 0x00, 0x82, 0x00, 0xE0, 0x00, 0x74, 0xC5, 0xB7, 0x10, 0x1A, 0x82, 0xE0, 0x08))
    )

    _EXCEPTION_REPLACEMENT_TIME = binascii.hexlify(bytearray((0, 0, 0, 0)))

    _CREATION_TIME = binascii.hexlify(bytearray((0, 0, 0, 0, 0, 0, 0, 0)))

    _RESERVED = binascii.hexlify(bytearray((0, 0, 0, 0, 0, 0, 0, 0)))

    # https://docs.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-oxocal/1d3aac05-a7b9-45cc-a213-47f0a0a2c5c1
    # https://docs.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-asemail/e7424ddc-dd10-431e-a0b7-5c794863370e
    # https://stackoverflow.com/questions/42259122
    # https://stackoverflow.com/questions/33757805

    def __new__(cls, uid):
        payload = binascii.hexlify(bytearray(f"vCal-Uid\x01\x00\x00\x00{uid}\x00".encode("ascii")))
        length = binascii.hexlify(bytearray(struct.pack("<I", int(len(payload) / 2))))
        encoding = b"".join(
            [cls._HEADER, cls._EXCEPTION_REPLACEMENT_TIME, cls._CREATION_TIME, cls._RESERVED, length, payload]
        )
        return super().__new__(cls, codecs.decode(encoding, "hex"))

    @classmethod
    def to_global_object_id(cls, uid):
        """Converts a UID as returned by EWS to GlobalObjectId format"""
        return binascii.unhexlify(uid)


def _mangle(field_name):
    return f"__{field_name}"


class EWSMeta(type, metaclass=abc.ABCMeta):
    def __new__(mcs, name, bases, kwargs):
        # Collect fields defined directly on the class
        local_fields = Fields()
        for k in tuple(kwargs.keys()):
            v = kwargs[k]
            if isinstance(v, Field):
                v.name = k
                local_fields.append(v)
                del kwargs[k]

        # Build a list of fields defined on this and all base classes
        base_fields = Fields()
        for base in bases:
            if hasattr(base, "FIELDS"):
                base_fields += base.FIELDS

        # FIELDS defined on a model overrides the base class fields
        fields = kwargs.get("FIELDS", base_fields) + local_fields

        # Include all fields as class attributes, so we can use them as instance attributes
        kwargs.update({_mangle(f.name): f for f in fields})

        # Calculate __slots__ so we don't have to hard-code it on the model
        kwargs["__slots__"] = tuple(f.name for f in fields if f.name not in base_fields) + kwargs.get("__slots__", ())

        # FIELDS is mentioned in docs and expected by internal code. Add it here, but only if the class has its own
        # fields. Otherwise, we want the implicit FIELDS from the base class (used for injecting custom fields on the
        # Folder class, making the custom field available for subclasses).
        if local_fields:
            kwargs["FIELDS"] = fields
        klass = super().__new__(mcs, name, bases, kwargs)
        klass._slots_keys = mcs._get_slots_keys(klass)
        return klass

    @staticmethod
    def _get_slots_keys(klass):
        seen = set()
        keys = []
        for c in reversed(getmro(klass)):
            if not hasattr(c, "__slots__"):
                continue
            for k in c.__slots__:
                if k in seen:
                    # We allow duplicate keys because we don't want to require subclasses of e.g.
                    # ExtendedProperty to define an empty __slots__ class attribute.
                    continue
                keys.append(k)
                seen.add(k)
        return keys

    def __getattribute__(cls, k):
        """Return Field instances via their mangled class attribute"""
        try:
            return super().__getattribute__("__dict__")[_mangle(k)]
        except KeyError:
            return super().__getattribute__(k)


class EWSElement(metaclass=EWSMeta):
    """Base class for all XML element implementations."""

    ELEMENT_NAME = None  # The name of the XML tag
    FIELDS = Fields()  # A list of attributes supported by this item class, ordered the same way as in EWS documentation
    NAMESPACE = TNS  # The XML tag namespace. Either TNS or MNS

    _fields_lock = Lock()

    def __init__(self, **kwargs):
        for f in self.FIELDS:
            setattr(self, f.name, kwargs.pop(f.name, None))
        if kwargs:
            raise AttributeError(f"{sorted(kwargs.keys())!r} are invalid kwargs for this class")

    def __setattr__(self, key, value):
        # Avoid silently accepting spelling errors to field names that are not set via __init__. We need to be able to
        # set values for predefined and registered fields, whatever non-field attributes this class defines, and
        # property setters.
        if key in self.FIELDS:
            return super().__setattr__(key, value)
        if key in self._slots_keys:
            return super().__setattr__(key, value)
        if hasattr(self, key):
            # Property setters
            return super().__setattr__(key, value)
        raise AttributeError(
            f"{key!r} is not a valid attribute. See {self.__class__.__name__}.FIELDS for valid field names"
        )

    def clean(self, version=None):
        # Validate attribute values using the field validator
        for f in self.FIELDS:
            if version and not f.supports_version(version):
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
        parent = elem.getparent()
        if parent is None:
            return
        parent.remove(elem)

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS}
        cls._clear(elem)
        return cls(**kwargs)

    def to_xml(self, version):
        self.clean(version=version)
        # WARNING: The order of addition of XML elements is VERY important. Exchange expects XML elements in a
        # specific, non-documented order and will fail with meaningless errors if the order is wrong.

        # Collect attributes
        attrs = {}
        for f in self.attribute_fields():
            if f.is_read_only:
                continue
            value = getattr(self, f.name)
            if value is None or (f.is_list and not value):
                continue
            attrs[f.field_uri] = value_to_xml_text(getattr(self, f.name))

        # Create element with attributes
        elem = create_element(self.request_tag(), attrs=attrs)

        # Add elements and values
        for f in self.supported_fields(version=version):
            if f.is_read_only:
                continue
            value = getattr(self, f.name)
            if value is None or (f.is_list and not value):
                continue
            set_xml_value(elem, f.to_xml(value, version=version))
        return elem

    @classmethod
    def request_tag(cls):
        if not cls.ELEMENT_NAME:
            raise ValueError(f"Class {cls} is missing the ELEMENT_NAME attribute")
        return {
            TNS: f"t:{cls.ELEMENT_NAME}",
            MNS: f"m:{cls.ELEMENT_NAME}",
        }[cls.NAMESPACE]

    @classmethod
    def response_tag(cls):
        if not cls.NAMESPACE:
            raise ValueError(f"Class {cls} is missing the NAMESPACE attribute")
        if not cls.ELEMENT_NAME:
            raise ValueError(f"Class {cls} is missing the ELEMENT_NAME attribute")
        return f"{{{cls.NAMESPACE}}}{cls.ELEMENT_NAME}"

    @classmethod
    def attribute_fields(cls):
        return tuple(f for f in cls.FIELDS if f.is_attribute)

    @classmethod
    def supported_fields(cls, version):
        """Return the fields supported by the given server version."""

        return tuple(f for f in cls.FIELDS if not f.is_attribute and f.supports_version(version))

    @classmethod
    def get_field_by_fieldname(cls, fieldname):
        try:
            return cls.FIELDS[fieldname]
        except KeyError:
            raise InvalidField(f"{fieldname!r} is not a valid field name on {cls.__name__}")

    @classmethod
    def validate_field(cls, field, version):
        """Take a list of fieldnames, Field or FieldPath objects pointing to item fields, and check that they are
        valid for the given version.

        :param field:
        :param version:
        """
        # Allow both Field and FieldPath instances and string field paths as input
        if isinstance(field, str):
            field = cls.get_field_by_fieldname(fieldname=field)
        elif isinstance(field, FieldPath):
            field = field.field
        cls.get_field_by_fieldname(fieldname=field.name)  # Will raise if field name is invalid
        if not field.supports_version(version):
            # The field exists but is not valid for this version
            raise InvalidFieldForVersion(
                f"Field {field.name!r} only supports server versions from {field.supported_from or '*'} to "
                f"{field.deprecated_from or '*'} (server has {version})"
            )

    @classmethod
    def add_field(cls, field, insert_after):
        """Insert a new field at the preferred place in the tuple and update the slots cache.

        :param field:
        :param insert_after:
        """
        with cls._fields_lock:
            idx = cls.FIELDS.index_by_name(insert_after) + 1
            # This class may not have its own FIELDS attribute. Make sure not to edit an attribute belonging to a parent
            # class.
            cls.FIELDS.insert(idx, field)
            setattr(cls, _mangle(field.name), field)

    @classmethod
    def remove_field(cls, field):
        """Remove the given field and update the slots cache.

        :param field:
        """
        with cls._fields_lock:
            # This class may not have its own FIELDS attribute. Make sure not to edit an attribute belonging to a parent
            # class.
            cls.FIELDS.remove(field)
            delattr(cls, _mangle(field.name))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash(
            tuple(tuple(getattr(self, f.name) or ()) if f.is_list else getattr(self, f.name) for f in self.FIELDS)
        )

    def _field_vals(self):
        field_vals = []  # Keep sorting
        for f in self.FIELDS:
            val = getattr(self, f.name)
            if isinstance(f, EnumField) and isinstance(val, int):
                val = f.as_string(val)
            field_vals.append((f.name, val))
        return field_vals

    def __str__(self):
        args_str = ", ".join(f"{name}={val!r}" for name, val in self._field_vals() if val is not None)
        return f"{self.__class__.__name__}({args_str})"

    def __repr__(self):
        args_str = ", ".join(f"{name}={val!r}" for name, val in self._field_vals())
        return f"{self.__class__.__name__}({args_str})"


class MessageHeader(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/internetmessageheader"""

    ELEMENT_NAME = "InternetMessageHeader"

    name = TextField(field_uri="HeaderName", is_attribute=True)
    value = SubField()


class BaseItemId(EWSElement, metaclass=EWSMeta):
    """Base class for ItemId elements."""

    ID_ATTR = None
    CHANGEKEY_ATTR = None

    def __init__(self, *args, **kwargs):
        if not kwargs:
            # Allow to set attributes without keyword
            kwargs = dict(zip(self._slots_keys, args))
        super().__init__(**kwargs)


class ItemId(BaseItemId):
    """'id' and 'changekey' are UUIDs generated by Exchange.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/itemid
    """

    ELEMENT_NAME = "ItemId"
    ID_ATTR = "Id"
    CHANGEKEY_ATTR = "ChangeKey"

    id = IdField(field_uri=ID_ATTR, is_required=True)
    changekey = IdField(field_uri=CHANGEKEY_ATTR, is_required=False)


class ParentItemId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/parentitemid"""

    ELEMENT_NAME = "ParentItemId"
    NAMESPACE = MNS


class RootItemId(BaseItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/rootitemid"""

    ELEMENT_NAME = "RootItemId"
    NAMESPACE = MNS
    ID_ATTR = "RootItemId"
    CHANGEKEY_ATTR = "RootItemChangeKey"

    id = IdField(field_uri=ID_ATTR, is_required=True)
    changekey = IdField(field_uri=CHANGEKEY_ATTR, is_required=True)


class AssociatedCalendarItemId(ItemId):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/associatedcalendaritemid
    """

    ELEMENT_NAME = "AssociatedCalendarItemId"


class ConversationId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/conversationid"""

    ELEMENT_NAME = "ConversationId"

    # ChangeKey attribute is sometimes required, see MSDN link


class ParentFolderId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/parentfolderid"""

    ELEMENT_NAME = "ParentFolderId"


class ReferenceItemId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/referenceitemid"""

    ELEMENT_NAME = "ReferenceItemId"


class PersonaId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/personaid"""

    ELEMENT_NAME = "PersonaId"
    NAMESPACE = MNS

    @classmethod
    def response_tag(cls):
        # This element is in MNS in the request and TNS in the response...
        return f"{{{TNS}}}{cls.ELEMENT_NAME}"


class SourceId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/sourceid"""

    ELEMENT_NAME = "SourceId"


class FolderId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/folderid"""

    ELEMENT_NAME = "FolderId"


class RecurringMasterItemId(BaseItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/recurringmasteritemid"""

    ELEMENT_NAME = "RecurringMasterItemId"
    ID_ATTR = "OccurrenceId"
    CHANGEKEY_ATTR = "ChangeKey"

    id = IdField(field_uri=ID_ATTR, is_required=True)
    changekey = IdField(field_uri=CHANGEKEY_ATTR, is_required=False)


class OccurrenceItemId(BaseItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/occurrenceitemid"""

    ELEMENT_NAME = "OccurrenceItemId"
    ID_ATTR = "RecurringMasterId"
    CHANGEKEY_ATTR = "ChangeKey"

    id = IdField(field_uri=ID_ATTR, is_required=True)
    changekey = IdField(field_uri=CHANGEKEY_ATTR, is_required=False)
    instance_index = IntegerField(field_uri="InstanceIndex", is_attribute=True, is_required=True, min=1)


class MovedItemId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/moveditemid"""

    ELEMENT_NAME = "MovedItemId"
    NAMESPACE = MNS

    @classmethod
    def id_from_xml(cls, elem):
        item = cls.from_xml(elem=elem, account=None)
        return item.id, item.changekey


class OldItemId(ItemId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/oldfolderid"""

    ELEMENT_NAME = "OldItemId"


class OldFolderId(FolderId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/olditemid"""

    ELEMENT_NAME = "OldFolderId"


class OldParentFolderId(ParentFolderId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/oldparentfolderid"""

    ELEMENT_NAME = "OldParentFolderId"


class Mailbox(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailbox"""

    ELEMENT_NAME = "Mailbox"
    MAILBOX = "Mailbox"
    ONE_OFF = "OneOff"
    MAILBOX_TYPE_CHOICES = {
        Choice(MAILBOX),
        Choice("PublicDL"),
        Choice("PrivateDL"),
        Choice("Contact"),
        Choice("PublicFolder"),
        Choice("Unknown"),
        Choice(ONE_OFF),
        Choice("GroupMailbox", supported_from=EXCHANGE_2013),
    }

    name = TextField(field_uri="Name")
    email_address = EmailAddressField(field_uri="EmailAddress")
    # RoutingType values are not restricted:
    # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/routingtype-emailaddresstype
    routing_type = TextField(field_uri="RoutingType", default="SMTP")
    mailbox_type = ChoiceField(field_uri="MailboxType", choices=MAILBOX_TYPE_CHOICES, default=MAILBOX)
    item_id = EWSElementField(value_cls=ItemId, is_read_only=True)

    def clean(self, version=None):
        super().clean(version=version)

        if self.mailbox_type != self.ONE_OFF and not self.email_address and not self.item_id:
            # A OneOff Mailbox (a one-off member of a personal distribution list) may lack these fields, but other
            # Mailboxes require at least one. See also "Remarks" section of
            # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailbox
            raise ValueError(f"Mailbox type {self.mailbox_type!r} must have either 'email_address' or 'item_id' set")

    def __hash__(self):
        # Exchange may add 'mailbox_type' and 'name' on insert. We're satisfied if the item_id or email address matches.
        if self.item_id:
            return hash(self.item_id)
        if self.email_address:
            return hash(self.email_address.lower())
        return super().__hash__()


class DLMailbox(Mailbox):
    """Like Mailbox, but creates elements in the 'messages' namespace when sending requests."""

    NAMESPACE = MNS


class SendingAs(Mailbox):
    """Like Mailbox, but creates elements in the 'messages' namespace when sending requests.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/sendingas
    """

    ELEMENT_NAME = "SendingAs"
    NAMESPACE = MNS


class RecipientAddress(Mailbox):
    """Like Mailbox, but with a different tag name.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/recipientaddress
    """

    ELEMENT_NAME = "RecipientAddress"


class EmailAddress(Mailbox):
    """Like Mailbox, but with a different tag name.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/emailaddress-emailaddresstype
    """

    ELEMENT_NAME = "EmailAddress"


class Address(Mailbox):
    """Like Mailbox, but with a different tag name.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/address-emailaddresstype
    """

    ELEMENT_NAME = "Address"


class AvailabilityMailbox(EWSElement):
    """Like Mailbox, but with slightly different attributes.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailbox-availability
    """

    ELEMENT_NAME = "Mailbox"

    name = TextField(field_uri="Name")
    email_address = EmailAddressField(field_uri="Address", is_required=True)
    # RoutingType values restricted to EX and SMTP:
    # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/routingtype-emailaddress
    routing_type = RoutingTypeField(field_uri="RoutingType")

    def __hash__(self):
        # Exchange may add 'name' on insert. We're satisfied if the email address matches.
        if self.email_address:
            return hash(self.email_address.lower())
        return super().__hash__()

    @classmethod
    def from_mailbox(cls, mailbox):
        if not isinstance(mailbox, Mailbox):
            raise InvalidTypeError("mailbox", mailbox, Mailbox)
        return cls(name=mailbox.name, email_address=mailbox.email_address, routing_type=mailbox.routing_type)


class Email(AvailabilityMailbox):
    """Like AvailabilityMailbox, but with a different tag name.
    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/email-emailaddresstype
    """

    ELEMENT_NAME = "Email"


class MailboxData(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailboxdata"""

    ELEMENT_NAME = "MailboxData"
    ATTENDEE_TYPES = {"Optional", "Organizer", "Required", "Resource", "Room"}

    email = EmailField()
    attendee_type = ChoiceField(field_uri="AttendeeType", choices={Choice(c) for c in ATTENDEE_TYPES})
    exclude_conflicts = BooleanField(field_uri="ExcludeConflicts")


class DistinguishedFolderId(FolderId):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/distinguishedfolderid"""

    ELEMENT_NAME = "DistinguishedFolderId"

    mailbox = MailboxField()

    @classmethod
    def from_xml(cls, elem, account):
        return cls(id=elem.text or None)

    def clean(self, version=None):
        from .folders import PublicFoldersRoot

        super().clean(version=version)
        if self.id == PublicFoldersRoot.DISTINGUISHED_FOLDER_ID:
            # Avoid "ErrorInvalidOperation: It is not valid to specify a mailbox with the public folder root" from EWS
            self.mailbox = None


class TimeWindow(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/timewindow"""

    ELEMENT_NAME = "TimeWindow"

    start = DateTimeField(field_uri="StartTime", is_required=True)
    end = DateTimeField(field_uri="EndTime", is_required=True)

    def clean(self, version=None):
        if self.start >= self.end:
            raise ValueError(f"'start' must be less than 'end' ({self.start} -> {self.end})")
        super().clean(version=version)


class FreeBusyViewOptions(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/freebusyviewoptions"""

    ELEMENT_NAME = "FreeBusyViewOptions"
    REQUESTED_VIEWS = {"MergedOnly", "FreeBusy", "FreeBusyMerged", "Detailed", "DetailedMerged"}

    time_window = EWSElementField(value_cls=TimeWindow, is_required=True)
    # Interval value is in minutes
    merged_free_busy_interval = IntegerField(
        field_uri="MergedFreeBusyIntervalInMinutes", min=5, max=1440, default=30, is_required=True
    )
    requested_view = ChoiceField(
        field_uri="RequestedView", choices={Choice(c) for c in REQUESTED_VIEWS}, is_required=True
    )  # Choice('None') is also valid, but only for responses


class Attendee(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/attendee"""

    ELEMENT_NAME = "Attendee"
    RESPONSE_TYPES = {"Unknown", "Organizer", "Tentative", "Accept", "Decline", "NoResponseReceived"}

    mailbox = MailboxField(is_required=True)
    response_type = ChoiceField(
        field_uri="ResponseType", choices={Choice(c) for c in RESPONSE_TYPES}, default="Unknown"
    )
    last_response_time = DateTimeField(field_uri="LastResponseTime")
    proposed_start = DateTimeField(field_uri="ProposedStart")
    proposed_end = DateTimeField(field_uri="ProposedEnd")

    def __hash__(self):
        return hash(self.mailbox)


class TimeZoneTransition(EWSElement, metaclass=EWSMeta):
    """Base class for StandardTime and DaylightTime classes."""

    bias = IntegerField(field_uri="Bias", is_required=True)  # Offset from the default bias, in minutes
    time = TimeField(field_uri="Time", is_required=True)
    occurrence = IntegerField(field_uri="DayOrder", is_required=True)  # n'th occurrence of weekday in iso_month
    iso_month = IntegerField(field_uri="Month", is_required=True)
    weekday = EnumField(field_uri="DayOfWeek", enum=WEEKDAY_NAMES, is_required=True)
    # 'Year' is not implemented yet

    @classmethod
    def from_xml(cls, elem, account):
        res = super().from_xml(elem=elem, account=account)
        # Some parts of EWS use '5' to mean 'last occurrence in month', others use '-1'. Let's settle on '5' because
        # only '5' is accepted in requests.
        if res.occurrence == -1:
            res.occurrence = 5
        return res

    def clean(self, version=None):
        super().clean(version=version)
        if self.occurrence == -1:
            # See from_xml()
            self.occurrence = 5


class StandardTime(TimeZoneTransition):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/standardtime"""

    ELEMENT_NAME = "StandardTime"


class DaylightTime(TimeZoneTransition):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/daylighttime"""

    ELEMENT_NAME = "DaylightTime"


class TimeZone(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/timezone-availability"""

    ELEMENT_NAME = "TimeZone"

    bias = IntegerField(field_uri="Bias", is_required=True)  # Standard (non-DST) offset from UTC, in minutes
    standard_time = EWSElementField(value_cls=StandardTime)
    daylight_time = EWSElementField(value_cls=DaylightTime)

    def to_server_timezone(self, timezones, for_year):
        """Return the Microsoft timezone ID corresponding to this timezone. There may not be a match at all, and there
        may be multiple matches. If so, return a random timezone ID.

        :param timezones: A list of server timezones, as returned by
          Protocol.get_timezones(return_full_timezone_data=True)
        :param for_year: return: A Microsoft timezone ID, as a string

        :return: A Microsoft timezone ID, as a string
        """
        candidates = set()
        for tz_definition in timezones:
            candidate = self.from_server_timezone(
                tz_definition=tz_definition,
                for_year=for_year,
            )
            if candidate == self:
                log.debug("Found exact candidate: %s (%s)", tz_definition.id, tz_definition.name)
                # We prefer this timezone over anything else. Return immediately.
                return tz_definition.id
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
            log.debug("Found candidate with matching biases: %s (%s)", tz_definition.id, tz_definition.name)
            candidates.add(tz_definition.id)
        if not candidates:
            raise ValueError("No server timezones match this timezone definition")
        if len(candidates) == 1:
            log.info("Could not find an exact timezone match for %s. Selecting the best candidate", self)
        else:
            log.warning("Could not find an exact timezone match for %s. Selecting a random candidate", self)
        return candidates.pop()

    @classmethod
    def from_server_timezone(cls, tz_definition, for_year):
        # Creates a TimeZone object from the result of a GetServerTimeZones call with full timezone data
        std_time, daylight_time, period = tz_definition.get_std_and_dst(for_year=for_year)
        return cls(bias=period.bias_in_minutes, standard_time=std_time, daylight_time=daylight_time)


class CalendarView(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendarview"""

    ELEMENT_NAME = "CalendarView"
    NAMESPACE = MNS

    start = DateTimeField(field_uri="StartDate", is_required=True, is_attribute=True)
    end = DateTimeField(field_uri="EndDate", is_required=True, is_attribute=True)
    max_items = IntegerField(field_uri="MaxEntriesReturned", min=1, is_attribute=True)

    def clean(self, version=None):
        super().clean(version=version)
        if self.end < self.start:
            raise ValueError("'start' must be before 'end'")


class CalendarEventDetails(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendareventdetails"""

    ELEMENT_NAME = "CalendarEventDetails"

    id = CharField(field_uri="ID")
    subject = CharField(field_uri="Subject")
    location = CharField(field_uri="Location")
    is_meeting = BooleanField(field_uri="IsMeeting")
    is_recurring = BooleanField(field_uri="IsRecurring")
    is_exception = BooleanField(field_uri="IsException")
    is_reminder_set = BooleanField(field_uri="IsReminderSet")
    is_private = BooleanField(field_uri="IsPrivate")


class CalendarEvent(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendarevent"""

    ELEMENT_NAME = "CalendarEvent"

    start = DateTimeField(field_uri="StartTime")
    end = DateTimeField(field_uri="EndTime")
    busy_type = FreeBusyStatusField(field_uri="BusyType", is_required=True, default="Busy")
    details = EWSElementField(value_cls=CalendarEventDetails)


class WorkingPeriod(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/workingperiod"""

    ELEMENT_NAME = "WorkingPeriod"

    weekdays = EnumListField(field_uri="DayOfWeek", enum=WEEKDAY_NAMES, is_required=True)
    start = TimeField(field_uri="StartTimeInMinutes", is_required=True)
    end = TimeField(field_uri="EndTimeInMinutes", is_required=True)


class FreeBusyView(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/freebusyview"""

    ELEMENT_NAME = "FreeBusyView"
    NAMESPACE = MNS
    view_type = ChoiceField(
        field_uri="FreeBusyViewType",
        choices={
            Choice("None"),
            Choice("MergedOnly"),
            Choice("FreeBusy"),
            Choice("FreeBusyMerged"),
            Choice("Detailed"),
            Choice("DetailedMerged"),
        },
        is_required=True,
    )
    # A string of digits. Each digit points to a position in .fields.FREE_BUSY_CHOICES
    merged = CharField(field_uri="MergedFreeBusy")
    calendar_events = EWSElementListField(field_uri="CalendarEventArray", value_cls=CalendarEvent)
    # WorkingPeriod is located inside the WorkingPeriodArray element which is inside the WorkingHours element
    working_hours = EWSElementListField(field_uri="WorkingPeriodArray", value_cls=WorkingPeriod)
    # TimeZone is also inside the WorkingHours element. It contains information about the timezone which the
    # account is located in.
    working_hours_timezone = EWSElementField(value_cls=TimeZone)

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {}
        working_hours_elem = elem.find(f"{{{TNS}}}WorkingHours")
        for f in cls.FIELDS:
            if f.name in ("working_hours", "working_hours_timezone"):
                if working_hours_elem is None:
                    continue
                kwargs[f.name] = f.from_xml(elem=working_hours_elem, account=account)
                continue
            kwargs[f.name] = f.from_xml(elem=elem, account=account)
        cls._clear(elem)
        return cls(**kwargs)


class RoomList(Mailbox):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/roomlist"""

    ELEMENT_NAME = "RoomList"
    NAMESPACE = MNS

    @classmethod
    def response_tag(cls):
        # In a GetRoomLists response, room lists are delivered as Address elements. See
        # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/address-emailaddresstype
        return f"{{{TNS}}}Address"


class Room(Mailbox):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/room"""

    ELEMENT_NAME = "Room"

    @classmethod
    def from_xml(cls, elem, account):
        id_elem = elem.find(f"{{{TNS}}}Id")
        item_id_elem = id_elem.find(ItemId.response_tag())
        kwargs = dict(
            name=get_xml_attr(id_elem, f"{{{TNS}}}Name"),
            email_address=get_xml_attr(id_elem, f"{{{TNS}}}EmailAddress"),
            mailbox_type=get_xml_attr(id_elem, f"{{{TNS}}}MailboxType"),
            item_id=ItemId.from_xml(elem=item_id_elem, account=account) if item_id_elem else None,
        )
        cls._clear(elem)
        return cls(**kwargs)


class Member(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/member-ex15websvcsotherref
    """

    ELEMENT_NAME = "Member"

    mailbox = MailboxField(is_required=True)
    status = ChoiceField(
        field_uri="Status", choices={Choice("Unrecognized"), Choice("Normal"), Choice("Demoted")}, default="Normal"
    )

    def __hash__(self):
        return hash(self.mailbox)


class UserId(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/userid"""

    ELEMENT_NAME = "UserId"

    sid = CharField(field_uri="SID")
    primary_smtp_address = EmailAddressField(field_uri="PrimarySmtpAddress")
    display_name = CharField(field_uri="DisplayName")
    distinguished_user = ChoiceField(field_uri="DistinguishedUser", choices={Choice("Default"), Choice("Anonymous")})
    external_user_identity = CharField(field_uri="ExternalUserIdentity")


class BasePermission(EWSElement, metaclass=EWSMeta):
    """Base class for the Permission and CalendarPermission classes"""

    PERMISSION_ENUM = {Choice("None"), Choice("Owned"), Choice("All")}

    can_create_items = BooleanField(field_uri="CanCreateItems", default=False)
    can_create_subfolders = BooleanField(field_uri="CanCreateSubfolders", default=False)
    is_folder_owner = BooleanField(field_uri="IsFolderOwner", default=False)
    is_folder_visible = BooleanField(field_uri="IsFolderVisible", default=False)
    is_folder_contact = BooleanField(field_uri="IsFolderContact", default=False)
    edit_items = ChoiceField(field_uri="EditItems", choices=PERMISSION_ENUM, default="None")
    delete_items = ChoiceField(field_uri="DeleteItems", choices=PERMISSION_ENUM, default="None")
    read_items = ChoiceField(field_uri="ReadItems", choices={Choice("None"), Choice("FullDetails")}, default="None")
    user_id = EWSElementField(value_cls=UserId, is_required=True)


class Permission(BasePermission):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/permission"""

    ELEMENT_NAME = "Permission"
    LEVEL_CHOICES = (
        "None",
        "Owner",
        "PublishingEditor",
        "Editor",
        "PublishingAuthor",
        "Author",
        "NoneditingAuthor",
        "Reviewer",
        "Contributor",
        "Custom",
    )

    permission_level = ChoiceField(
        field_uri="CalendarPermissionLevel", choices={Choice(c) for c in LEVEL_CHOICES}, default=LEVEL_CHOICES[0]
    )


class CalendarPermission(BasePermission):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/calendarpermission"""

    ELEMENT_NAME = "CalendarPermission"
    LEVEL_CHOICES = (
        "None",
        "Owner",
        "PublishingEditor",
        "Editor",
        "PublishingAuthor",
        "Author",
        "NoneditingAuthor",
        "Reviewer",
        "Contributor",
        "FreeBusyTimeOnly",
        "FreeBusyTimeAndSubjectAndLocation",
        "Custom",
    )

    calendar_permission_level = ChoiceField(
        field_uri="CalendarPermissionLevel", choices={Choice(c) for c in LEVEL_CHOICES}, default=LEVEL_CHOICES[0]
    )


class PermissionSet(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/permissionset-permissionsettype
    and
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/permissionset-calendarpermissionsettype
    """

    # For simplicity, we implement the two distinct but equally names elements as one class.
    ELEMENT_NAME = "PermissionSet"

    permissions = EWSElementListField(field_uri="Permissions", value_cls=Permission)
    calendar_permissions = EWSElementListField(field_uri="CalendarPermissions", value_cls=CalendarPermission)
    unknown_entries = UnknownEntriesField(field_uri="UnknownEntries")


class EffectiveRights(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/effectiverights"""

    ELEMENT_NAME = "EffectiveRights"

    create_associated = BooleanField(field_uri="CreateAssociated", default=False)
    create_contents = BooleanField(field_uri="CreateContents", default=False)
    create_hierarchy = BooleanField(field_uri="CreateHierarchy", default=False)
    delete = BooleanField(field_uri="Delete", default=False)
    modify = BooleanField(field_uri="Modify", default=False)
    read = BooleanField(field_uri="Read", default=False)
    view_private_items = BooleanField(field_uri="ViewPrivateItems", default=False)

    def __contains__(self, item):
        return getattr(self, item, False)


class DelegatePermissions(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/delegatepermissions"""

    ELEMENT_NAME = "DelegatePermissions"
    PERMISSION_LEVEL_CHOICES = {
        Choice("None"),
        Choice("Editor"),
        Choice("Reviewer"),
        Choice("Author"),
        Choice("Custom"),
    }

    calendar_folder_permission_level = ChoiceField(
        field_uri="CalendarFolderPermissionLevel", choices=PERMISSION_LEVEL_CHOICES, default="None"
    )
    tasks_folder_permission_level = ChoiceField(
        field_uri="TasksFolderPermissionLevel", choices=PERMISSION_LEVEL_CHOICES, default="None"
    )
    inbox_folder_permission_level = ChoiceField(
        field_uri="InboxFolderPermissionLevel", choices=PERMISSION_LEVEL_CHOICES, default="None"
    )
    contacts_folder_permission_level = ChoiceField(
        field_uri="ContactsFolderPermissionLevel", choices=PERMISSION_LEVEL_CHOICES, default="None"
    )
    notes_folder_permission_level = ChoiceField(
        field_uri="NotesFolderPermissionLevel", choices=PERMISSION_LEVEL_CHOICES, default="None"
    )
    journal_folder_permission_level = ChoiceField(
        field_uri="JournalFolderPermissionLevel", choices=PERMISSION_LEVEL_CHOICES, default="None"
    )


class DelegateUser(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/delegateuser"""

    ELEMENT_NAME = "DelegateUser"
    NAMESPACE = MNS

    user_id = EWSElementField(value_cls=UserId)
    delegate_permissions = EWSElementField(value_cls=DelegatePermissions)
    receive_copies_of_meeting_messages = BooleanField(field_uri="ReceiveCopiesOfMeetingMessages", default=False)
    view_private_items = BooleanField(field_uri="ViewPrivateItems", default=False)


class SearchableMailbox(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/searchablemailbox"""

    ELEMENT_NAME = "SearchableMailbox"

    guid = CharField(field_uri="Guid")
    primary_smtp_address = EmailAddressField(field_uri="PrimarySmtpAddress")
    is_external = BooleanField(field_uri="IsExternalMailbox")
    external_email = EmailAddressField(field_uri="ExternalEmailAddress")
    display_name = CharField(field_uri="DisplayName")
    is_membership_group = BooleanField(field_uri="IsMembershipGroup")
    reference_id = CharField(field_uri="ReferenceId")


class FailedMailbox(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/failedmailbox"""

    ELEMENT_NAME = "FailedMailbox"

    mailbox = CharField(field_uri="Mailbox")
    error_code = IntegerField(field_uri="ErrorCode")
    error_message = CharField(field_uri="ErrorMessage")
    is_archive = BooleanField(field_uri="IsArchive")


# MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailtipsrequested
MAIL_TIPS_TYPES = (
    "All",
    "OutOfOfficeMessage",
    "MailboxFullStatus",
    "CustomMailTip",
    "ExternalMemberCount",
    "TotalMemberCount",
    "MaxMessageSize",
    "DeliveryRestriction",
    "ModerationStatus",
    "InvalidRecipient",
)


class OutOfOffice(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/outofoffice"""

    ELEMENT_NAME = "OutOfOffice"

    reply_body = MessageField(field_uri="ReplyBody")
    start = DateTimeField(field_uri="StartTime", is_required=False)
    end = DateTimeField(field_uri="EndTime", is_required=False)

    @classmethod
    def duration_to_start_end(cls, elem, account):
        kwargs = {}
        duration = elem.find(f"{{{TNS}}}Duration")
        if duration is not None:
            for attr in ("start", "end"):
                f = cls.get_field_by_fieldname(attr)
                kwargs[attr] = f.from_xml(elem=duration, account=account)
        return kwargs

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {}
        for attr in ("reply_body",):
            f = cls.get_field_by_fieldname(attr)
            kwargs[attr] = f.from_xml(elem=elem, account=account)
        kwargs.update(cls.duration_to_start_end(elem=elem, account=account))
        cls._clear(elem)
        return cls(**kwargs)


class MailTips(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/mailtips"""

    ELEMENT_NAME = "MailTips"
    NAMESPACE = MNS

    recipient_address = RecipientAddressField()
    pending_mail_tips = ChoiceField(field_uri="PendingMailTips", choices={Choice(c) for c in MAIL_TIPS_TYPES})
    out_of_office = EWSElementField(value_cls=OutOfOffice)
    mailbox_full = BooleanField(field_uri="MailboxFull")
    custom_mail_tip = TextField(field_uri="CustomMailTip")
    total_member_count = IntegerField(field_uri="TotalMemberCount")
    external_member_count = IntegerField(field_uri="ExternalMemberCount")
    max_message_size = IntegerField(field_uri="MaxMessageSize")
    delivery_restricted = BooleanField(field_uri="DeliveryRestricted")
    is_moderated = BooleanField(field_uri="IsModerated")
    invalid_recipient = BooleanField(field_uri="InvalidRecipient")


ENTRY_ID = "EntryId"  # The base64-encoded PR_ENTRYID property
EWS_ID = "EwsId"  # The EWS format used in Exchange 2007 SP1 and later
EWS_LEGACY_ID = "EwsLegacyId"  # The EWS format used in Exchange 2007 before SP1
HEX_ENTRY_ID = "HexEntryId"  # The hexadecimal representation of the PR_ENTRYID property
OWA_ID = "OwaId"  # The OWA format for Exchange 2007 and 2010
STORE_ID = "StoreId"  # The Exchange Store format
# IdFormat enum
ID_FORMATS = (ENTRY_ID, EWS_ID, EWS_LEGACY_ID, HEX_ENTRY_ID, OWA_ID, STORE_ID)


class AlternateId(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/alternateid"""

    ELEMENT_NAME = "AlternateId"

    id = CharField(field_uri="Id", is_required=True, is_attribute=True)
    format = ChoiceField(
        field_uri="Format", is_required=True, is_attribute=True, choices={Choice(c) for c in ID_FORMATS}
    )
    mailbox = EmailAddressField(field_uri="Mailbox", is_required=True, is_attribute=True)
    is_archive = BooleanField(field_uri="IsArchive", is_required=False, is_attribute=True)

    @classmethod
    def response_tag(cls):
        # This element is in TNS in the request and MNS in the response...
        return f"{{{MNS}}}{cls.ELEMENT_NAME}"


class AlternatePublicFolderId(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/alternatepublicfolderid"""

    ELEMENT_NAME = "AlternatePublicFolderId"

    folder_id = CharField(field_uri="FolderId", is_required=True, is_attribute=True)
    format = ChoiceField(
        field_uri="Format", is_required=True, is_attribute=True, choices={Choice(c) for c in ID_FORMATS}
    )


class AlternatePublicFolderItemId(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/alternatepublicfolderitemid
    """

    ELEMENT_NAME = "AlternatePublicFolderItemId"

    folder_id = CharField(field_uri="FolderId", is_required=True, is_attribute=True)
    format = ChoiceField(
        field_uri="Format", is_required=True, is_attribute=True, choices={Choice(c) for c in ID_FORMATS}
    )
    item_id = CharField(field_uri="ItemId", is_required=True, is_attribute=True)


class FieldURI(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/fielduri"""

    ELEMENT_NAME = "FieldURI"

    field_uri = CharField(field_uri="FieldURI", is_attribute=True, is_required=True)


class IndexedFieldURI(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/indexedfielduri"""

    ELEMENT_NAME = "IndexedFieldURI"

    field_uri = CharField(field_uri="FieldURI", is_attribute=True, is_required=True)
    field_index = CharField(field_uri="FieldIndex", is_attribute=True, is_required=True)


class ExtendedFieldURI(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/extendedfielduri"""

    ELEMENT_NAME = "ExtendedFieldURI"

    distinguished_property_set_id = CharField(field_uri="DistinguishedPropertySetId", is_attribute=True)
    property_set_id = CharField(field_uri="PropertySetId", is_attribute=True)
    property_tag = CharField(field_uri="PropertyTag", is_attribute=True)
    property_name = CharField(field_uri="PropertyName", is_attribute=True)
    property_id = CharField(field_uri="PropertyId", is_attribute=True)
    property_type = CharField(field_uri="PropertyType", is_attribute=True)


class ExceptionFieldURI(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/exceptionfielduri"""

    ELEMENT_NAME = "ExceptionFieldURI"

    field_uri = CharField(field_uri="FieldURI", is_attribute=True, is_required=True)


class CompleteName(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/completename"""

    ELEMENT_NAME = "CompleteName"

    title = CharField(field_uri="Title")
    first_name = CharField(field_uri="FirstName")
    middle_name = CharField(field_uri="MiddleName")
    last_name = CharField(field_uri="LastName")
    suffix = CharField(field_uri="Suffix")
    initials = CharField(field_uri="Initials")
    full_name = CharField(field_uri="FullName")
    nickname = CharField(field_uri="Nickname")
    yomi_first_name = CharField(field_uri="YomiFirstName")
    yomi_last_name = CharField(field_uri="YomiLastName")


class ReminderMessageData(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/remindermessagedata"""

    ELEMENT_NAME = "ReminderMessageData"

    reminder_text = CharField(field_uri="ReminderText")
    location = CharField(field_uri="Location")
    start_time = TimeField(field_uri="StartTime")
    end_time = TimeField(field_uri="EndTime")
    associated_calendar_item_id = AssociatedCalendarItemIdField(
        field_uri="AssociatedCalendarItemId", supported_from=Build(15, 0, 913, 9)
    )


class AcceptSharingInvitation(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/acceptsharinginvitation"""

    ELEMENT_NAME = "AcceptSharingInvitation"

    reference_item_id = ReferenceItemIdField(field_uri="item:ReferenceItemId")


class SuppressReadReceipt(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/suppressreadreceipt"""

    ELEMENT_NAME = "SuppressReadReceipt"

    reference_item_id = ReferenceItemIdField(field_uri="item:ReferenceItemId")


class RemoveItem(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/removeitem"""

    ELEMENT_NAME = "RemoveItem"

    reference_item_id = ReferenceItemIdField(field_uri="item:ReferenceItemId")


class ResponseObjects(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/responseobjects"""

    ELEMENT_NAME = "ResponseObjects"

    accept_item = EWSElementField(field_uri="AcceptItem", value_cls="AcceptItem", namespace=TNS)
    tentatively_accept_item = EWSElementField(
        field_uri="TentativelyAcceptItem", value_cls="TentativelyAcceptItem", namespace=TNS
    )
    decline_item = EWSElementField(field_uri="DeclineItem", value_cls="DeclineItem", namespace=TNS)
    reply_to_item = EWSElementField(field_uri="ReplyToItem", value_cls="ReplyToItem", namespace=TNS)
    forward_item = EWSElementField(field_uri="ForwardItem", value_cls="ForwardItem", namespace=TNS)
    reply_all_to_item = EWSElementField(field_uri="ReplyAllToItem", value_cls="ReplyAllToItem", namespace=TNS)
    cancel_calendar_item = EWSElementField(
        field_uri="CancelCalendarItem", value_cls="CancelCalendarItem", namespace=TNS
    )
    remove_item = EWSElementField(field_uri="RemoveItem", value_cls=RemoveItem)
    post_reply_item = EWSElementField(field_uri="PostReplyItem", value_cls="PostReplyItem", namespace=TNS)
    success_read_receipt = EWSElementField(field_uri="SuppressReadReceipt", value_cls=SuppressReadReceipt)
    accept_sharing_invitation = EWSElementField(field_uri="AcceptSharingInvitation", value_cls=AcceptSharingInvitation)


class PhoneNumber(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/phonenumber"""

    ELEMENT_NAME = "PhoneNumber"

    number = CharField(field_uri="Number")
    type = CharField(field_uri="Type")


class IdChangeKeyMixIn(EWSElement, metaclass=EWSMeta):
    """Base class for classes that have a concept of 'id' and 'changekey' values. The values are actually stored on
    a separate element, but we add convenience methods to hide that fact.
    """

    ID_ELEMENT_CLS = None

    def __init__(self, **kwargs):
        _id, _changekey = kwargs.pop("id", None), kwargs.pop("changekey", None)
        if _id or _changekey:
            kwargs["_id"] = self.ID_ELEMENT_CLS(_id, _changekey)
        super().__init__(**kwargs)

    @classmethod
    def get_field_by_fieldname(cls, fieldname):
        if fieldname in ("id", "changekey"):
            return cls.ID_ELEMENT_CLS.get_field_by_fieldname(fieldname=fieldname)
        return super().get_field_by_fieldname(fieldname=fieldname)

    @property
    def id(self):
        if self._id is None:
            return None
        return self._id.id

    @id.setter
    def id(self, value):
        if self._id is None:
            self._id = self.ID_ELEMENT_CLS()
        self._id.id = value

    @property
    def changekey(self):
        if self._id is None:
            return None
        return self._id.changekey

    @changekey.setter
    def changekey(self, value):
        if self._id is None:
            self._id = self.ID_ELEMENT_CLS()
        self._id.changekey = value

    @classmethod
    def id_from_xml(cls, elem):
        # This method must be reasonably fast
        id_elem = elem.find(cls.ID_ELEMENT_CLS.response_tag())
        if id_elem is None:
            return None, None
        return id_elem.get(cls.ID_ELEMENT_CLS.ID_ATTR), id_elem.get(cls.ID_ELEMENT_CLS.CHANGEKEY_ATTR)

    def to_id(self):
        if self._id is None:
            raise ValueError("Must have an ID")
        return self._id

    def __eq__(self, other):
        if isinstance(other, tuple):
            return hash((self.id, self.changekey)) == hash(other)
        return super().__eq__(other)

    def __hash__(self):
        # If we have an ID and changekey, use that as key. Else return a hash of all attributes
        if self.id:
            return hash((self.id, self.changekey))
        return super().__hash__()


class DictionaryEntry(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/dictionaryentry"""

    ELEMENT_NAME = "DictionaryEntry"

    key = TypeValueField(field_uri="DictionaryKey")
    value = TypeValueField(field_uri="DictionaryValue")


class UserConfigurationName(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/userconfigurationname"""

    ELEMENT_NAME = "UserConfigurationName"
    NAMESPACE = TNS

    name = CharField(field_uri="Name", is_attribute=True)
    folder = EWSElementField(value_cls=FolderId)

    def clean(self, version=None):
        from .folders import BaseFolder

        if isinstance(self.folder, BaseFolder):
            self.folder = self.folder.to_id()
        super().clean(version=version)

    @classmethod
    def from_xml(cls, elem, account):
        # We also accept distinguished folders
        f = EWSElementField(value_cls=DistinguishedFolderId)
        distinguished_folder_id = f.from_xml(elem=elem, account=account)
        res = super().from_xml(elem=elem, account=account)
        if distinguished_folder_id:
            res.folder = distinguished_folder_id
        return res


class UserConfigurationNameMNS(UserConfigurationName):
    """Like UserConfigurationName, but in the MNS namespace.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/userconfigurationname
    """

    NAMESPACE = MNS


class UserConfiguration(IdChangeKeyMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/userconfiguration"""

    ELEMENT_NAME = "UserConfiguration"
    NAMESPACE = MNS
    ID_ELEMENT_CLS = ItemId

    _id = IdElementField(field_uri="ItemId", value_cls=ID_ELEMENT_CLS)
    user_configuration_name = EWSElementField(value_cls=UserConfigurationName)
    dictionary = DictionaryField(field_uri="Dictionary")
    xml_data = Base64Field(field_uri="XmlData")
    binary_data = Base64Field(field_uri="BinaryData")


class Attribution(IdChangeKeyMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/phonenumber"""

    ELEMENT_NAME = "Attribution"
    ID_ELEMENT_CLS = SourceId

    ID = CharField(field_uri="Id")
    _id = IdElementField(field_uri="SourceId", value_cls=ID_ELEMENT_CLS)
    display_name = CharField(field_uri="DisplayName")
    is_writable = BooleanField(field_uri="IsWritable")
    is_quick_contact = BooleanField(field_uri="IsQuickContact")
    is_hidden = BooleanField(field_uri="IsHidden")
    folder_id = EWSElementField(value_cls=FolderId)


class BodyContentValue(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/value-bodycontenttype
    """

    ELEMENT_NAME = "Value"

    value = CharField(field_uri="Value")
    body_type = CharField(field_uri="BodyType")


class BodyContentAttributedValue(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/bodycontentattributedvalue
    """

    ELEMENT_NAME = "BodyContentAttributedValue"

    value = EWSElementField(value_cls=BodyContentValue)
    attributions = EWSElementListField(field_uri="Attributions", value_cls=Attribution)


class StringAttributedValue(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/stringattributedvalue
    """

    ELEMENT_NAME = "StringAttributedValue"

    value = CharField(field_uri="Value")
    attributions = CharListField(field_uri="Attributions", list_elem_name="Attribution")


class PersonaPhoneNumberTypeValue(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/value-personaphonenumbertype
    """

    ELEMENT_NAME = "Value"

    number = CharField(field_uri="Number")
    type = CharField(field_uri="Type")


class PhoneNumberAttributedValue(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/phonenumberattributedvalue
    """

    ELEMENT_NAME = "PhoneNumberAttributedValue"

    value = EWSElementField(value_cls=PersonaPhoneNumberTypeValue)
    attributions = CharListField(field_uri="Attributions", list_elem_name="Attribution")


class EmailAddressTypeValue(Mailbox):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/value-emailaddresstype
    """

    ELEMENT_NAME = "Value"

    original_display_name = TextField(field_uri="OriginalDisplayName")


class EmailAddressAttributedValue(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/emailaddressattributedvalue
    """

    ELEMENT_NAME = "EmailAddressAttributedValue"

    value = EWSElementField(value_cls=EmailAddressTypeValue)
    attributions = EWSElementListField(field_uri="Attributions", value_cls=Attribution)


class PersonaPostalAddressTypeValue(Mailbox):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/value-personapostaladdresstype
    """

    ELEMENT_NAME = "Value"

    street = TextField(field_uri="Street")
    city = TextField(field_uri="City")
    state = TextField(field_uri="State")
    country = TextField(field_uri="Country")
    postal_code = TextField(field_uri="PostalCode")
    post_office_box = TextField(field_uri="PostOfficeBox")
    type = TextField(field_uri="Type")
    latitude = TextField(field_uri="Latitude")
    longitude = TextField(field_uri="Longitude")
    accuracy = TextField(field_uri="Accuracy")
    altitude = TextField(field_uri="Altitude")
    altitude_accuracy = TextField(field_uri="AltitudeAccuracy")
    formatted_address = TextField(field_uri="FormattedAddress")
    location_uri = TextField(field_uri="LocationUri")
    location_source = TextField(field_uri="LocationSource")


class PostalAddressAttributedValue(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/postaladdressattributedvalue
    """

    ELEMENT_NAME = "PostalAddressAttributedValue"

    value = EWSElementField(value_cls=PersonaPostalAddressTypeValue)
    attributions = EWSElementListField(field_uri="Attributions", value_cls=Attribution)


class Event(EWSElement, metaclass=EWSMeta):
    """Base class for all event types."""

    watermark = CharField(field_uri="Watermark")


class TimestampEvent(Event, metaclass=EWSMeta):
    """Base class for both item and folder events with a timestamp."""

    FOLDER = "folder"
    ITEM = "item"

    timestamp = DateTimeField(field_uri="TimeStamp")
    item_id = EWSElementField(value_cls=ItemId)
    folder_id = EWSElementField(value_cls=FolderId)
    parent_folder_id = EWSElementField(value_cls=ParentFolderId)

    @property
    def event_type(self):
        if self.item_id is not None:
            return self.ITEM
        if self.folder_id is not None:
            return self.FOLDER
        return None  # Empty object


class OldTimestampEvent(TimestampEvent, metaclass=EWSMeta):
    """Base class for both item and folder copy/move events."""

    old_item_id = EWSElementField(value_cls=OldItemId)
    old_folder_id = EWSElementField(value_cls=OldFolderId)
    old_parent_folder_id = EWSElementField(value_cls=OldParentFolderId)


class CopiedEvent(OldTimestampEvent):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/copiedevent"""

    ELEMENT_NAME = "CopiedEvent"


class CreatedEvent(TimestampEvent):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/createdevent"""

    ELEMENT_NAME = "CreatedEvent"


class DeletedEvent(TimestampEvent):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/deletedevent"""

    ELEMENT_NAME = "DeletedEvent"


class ModifiedEvent(TimestampEvent):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/modifiedevent"""

    ELEMENT_NAME = "ModifiedEvent"

    unread_count = IntegerField(field_uri="UnreadCount")


class MovedEvent(OldTimestampEvent):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/movedevent"""

    ELEMENT_NAME = "MovedEvent"


class NewMailEvent(TimestampEvent):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/newmailevent"""

    ELEMENT_NAME = "NewMailEvent"


class StatusEvent(Event):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/statusevent"""

    ELEMENT_NAME = "StatusEvent"


class FreeBusyChangedEvent(TimestampEvent):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/freebusychangedevent"""

    ELEMENT_NAME = "FreeBusyChangedEvent"


class Notification(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/notification-ex15websvcsotherref
    """

    ELEMENT_NAME = "Notification"
    NAMESPACE = MNS

    subscription_id = CharField(field_uri="SubscriptionId")
    previous_watermark = CharField(field_uri="PreviousWatermark")
    more_events = BooleanField(field_uri="MoreEvents")
    events = GenericEventListField("")


class BaseTransition(EWSElement, metaclass=EWSMeta):
    """Base class for all other transition classes"""

    to = CharField(field_uri="To")
    kind = CharField(field_uri="Kind", is_attribute=True)  # An attribute on the 'To' element

    @staticmethod
    def transition_model_from_tag(tag):
        return {
            cls.response_tag(): cls
            for cls in (Transition, AbsoluteDateTransition, RecurringDateTransition, RecurringDayTransition)
        }[tag]

    @classmethod
    def from_xml(cls, elem, account):
        kind = elem.find(cls.get_field_by_fieldname("to").response_tag()).get("Kind")
        res = super().from_xml(elem=elem, account=account)
        res.kind = kind
        return res


class Transition(BaseTransition):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/transition"""

    ELEMENT_NAME = "Transition"


class AbsoluteDateTransition(BaseTransition):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/absolutedatetransition"""

    ELEMENT_NAME = "AbsoluteDateTransition"

    date = DateTimeBackedDateField(field_uri="DateTime")


class RecurringDayTransition(BaseTransition):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/recurringdaytransition"""

    ELEMENT_NAME = "RecurringDayTransition"

    offset = TimeDeltaField(field_uri="TimeOffset")
    month = IntegerField(field_uri="Month")
    # Valid ISO 8601 weekday, as a number in range 1 -> 7 (1 being Monday)
    day_of_week = EnumField(field_uri="DayOfWeek", enum=WEEKDAY_NAMES)
    occurrence = IntegerField(field_uri="Occurrence")

    @classmethod
    def from_xml(cls, elem, account):
        res = super().from_xml(elem=elem, account=account)
        # See TimeZoneTransition.from_xml()
        if res.occurrence == -1:
            res.occurrence = 5
        return res


class RecurringDateTransition(BaseTransition):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/recurringdatetransition"""

    ELEMENT_NAME = "RecurringDateTransition"

    offset = TimeDeltaField(field_uri="TimeOffset")
    month = IntegerField(field_uri="Month")
    day = IntegerField(field_uri="Day")  # Day of month


class Period(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/period"""

    ELEMENT_NAME = "Period"

    id = CharField(field_uri="Id", is_attribute=True)
    name = CharField(field_uri="Name", is_attribute=True)
    bias = TimeDeltaField(field_uri="Bias", is_attribute=True)

    @property
    def bias_in_minutes(self):
        return int(self.bias.total_seconds()) // 60  # Convert to minutes


class TransitionsGroup(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/transitionsgroup"""

    ELEMENT_NAME = "TransitionsGroup"

    id = CharField(field_uri="Id", is_attribute=True)
    transitions = TransitionListField(value_cls=BaseTransition)


class TimeZoneDefinition(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/timezonedefinition"""

    ELEMENT_NAME = "TimeZoneDefinition"

    id = CharField(field_uri="Id", is_attribute=True)
    name = CharField(field_uri="Name", is_attribute=True)

    periods = EWSElementListField(field_uri="Periods", value_cls=Period)
    transitions_groups = EWSElementListField(field_uri="TransitionsGroups", value_cls=TransitionsGroup)
    transitions = TransitionListField(field_uri="Transitions", value_cls=BaseTransition)

    def _get_standard_period(self, transitions_group):
        # Find the first standard period referenced from transitions_group
        standard_periods_map = {p.id: p for p in self.periods if p.name == "Standard"}
        for transition in transitions_group.transitions:
            try:
                return standard_periods_map[transition.to]
            except KeyError:
                continue
        raise ValueError(f"No standard period matching any transition in {transitions_group}")

    def _get_transitions_group(self, for_year):
        # Look through the transitions, and pick the relevant transition group according to the 'for_year' value
        transitions_group = None
        transitions_groups_map = {tg.id: tg for tg in self.transitions_groups}
        for transition in sorted(self.transitions, key=lambda t: t.to):
            if transition.kind != "Group":
                continue
            if isinstance(transition, AbsoluteDateTransition) and transition.date.year > for_year:
                break
            transitions_group = transitions_groups_map[transition.to]
        if transitions_group is None:
            raise ValueError(f"No valid transition group for year {for_year}: {self.transitions}")
        return transitions_group

    def get_std_and_dst(self, for_year):
        # Return 'standard_time' and 'daylight_time' objects. We do unnecessary work here, but it keeps code simple.
        transitions_group = self._get_transitions_group(for_year)
        if not 0 <= len(transitions_group.transitions) <= 2:
            raise ValueError(f"Expected 0-2 transitions in transitions group {transitions_group}")

        standard_period = self._get_standard_period(transitions_group)
        periods_map = {p.id: p for p in self.periods}
        standard_time, daylight_time = None, None
        if len(transitions_group.transitions) == 1:
            # This is a simple transition group representing a timezone with no DST. Some servers don't accept
            # TimeZone elements without an STD and DST element (see issue #488). Return StandardTime and DaylightTime
            # objects with dummy values and 0 bias - this satisfies the broken servers and hopefully doesn't break
            # the well-behaving servers.
            standard_time = StandardTime(bias=0, time=datetime.time(0), occurrence=1, iso_month=1, weekday=1)
            daylight_time = DaylightTime(bias=0, time=datetime.time(0), occurrence=5, iso_month=12, weekday=7)
            return standard_time, daylight_time, standard_period
        for transition in transitions_group.transitions:
            # 'offset' is the time of day to transition, as timedelta since midnight. Check that it's a reasonable value
            transition.clean(version=None)
            transition_kwargs = dict(
                time=(datetime.datetime(2000, 1, 1) + transition.offset).time(),
                occurrence=transition.occurrence,
                iso_month=transition.month,
                weekday=transition.day_of_week,
            )
            period = periods_map[transition.to]
            if period.name == "Standard":
                transition_kwargs["bias"] = 0
                standard_time = StandardTime(**transition_kwargs)
                continue
            if period.name == "Daylight":
                transition_kwargs["bias"] = period.bias_in_minutes - standard_period.bias_in_minutes
                daylight_time = DaylightTime(**transition_kwargs)
                continue
            raise ValueError(f"Unknown transition: {transition}")
        return standard_time, daylight_time, standard_period


class UserResponse(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/userresponse-soap"""

    ELEMENT_NAME = "UserResponse"

    # See https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/setting-soap
    SETTINGS_MAP = {
        "user_display_name": "UserDisplayName",
        "user_dn": "UserDN",
        "user_deployment_id": "UserDeploymentId",
        "internal_mailbox_server": "InternalMailboxServer",
        "internal_rpc_client_server": "InternalRpcClientServer",
        "internal_mailbox_server_dn": "InternalMailboxServerDN",
        "internal_ecp_url": "InternalEcpUrl",
        "internal_ecp_voicemail_url": "InternalEcpVoicemailUrl",
        "internal_ecp_email_subscriptions_url": "InternalEcpEmailSubscriptionsUrl",
        "internal_ecp_text_messaging_url": "InternalEcpTextMessagingUrl",
        "internal_ecp_delivery_report_url": "InternalEcpDeliveryReportUrl",
        "internal_ecp_retention_policy_tags_url": "InternalEcpRetentionPolicyTagsUrl",
        "internal_ecp_publishing_url": "InternalEcpPublishingUrl",
        "internal_ews_url": "InternalEwsUrl",
        "internal_oab_url": "InternalOABUrl",
        "internal_um_url": "InternalUMUrl",
        "internal_web_client_urls": "InternalWebClientUrls",
        "mailbox_dn": "MailboxDN",
        "public_folder_server": "PublicFolderServer",
        "active_directory_server": "ActiveDirectoryServer",
        "external_mailbox_server": "ExternalMailboxServer",
        "external_mailbox_server_requires_ssl": "ExternalMailboxServerRequiresSSL",
        "external_mailbox_server_authentication_methods": "ExternalMailboxServerAuthenticationMethods",
        "ecp_voicemail_url_fragment,": "EcpVoicemailUrlFragment,",
        "ecp_email_subscriptions_url_fragment": "EcpEmailSubscriptionsUrlFragment",
        "ecp_text_messaging_url_fragment": "EcpTextMessagingUrlFragment",
        "ecp_delivery_report_url_fragment": "EcpDeliveryReportUrlFragment",
        "ecp_retention_policy_tags_url_fragment": "EcpRetentionPolicyTagsUrlFragment",
        "ecp_publishing_url_fragment": "EcpPublishingUrlFragment",
        "external_ecp_url": "ExternalEcpUrl",
        "external_ecp_voicemail_url": "ExternalEcpVoicemailUrl",
        "external_ecp_email_subscriptions_url": "ExternalEcpEmailSubscriptionsUrl",
        "external_ecp_text_messaging_url": "ExternalEcpTextMessagingUrl",
        "external_ecp_delivery_report_url": "ExternalEcpDeliveryReportUrl",
        "external_ecp_retention_policy_tags_url": "ExternalEcpRetentionPolicyTagsUrl",
        "external_ecp_publishing_url": "ExternalEcpPublishingUrl",
        "external_ews_url": "ExternalEwsUrl",
        "external_oab_url": "ExternalOABUrl",
        "external_um_url": "ExternalUMUrl",
        "external_web_client_urls": "ExternalWebClientUrls",
        "cross_organization_sharing_enabled": "CrossOrganizationSharingEnabled",
        "alternate_mailboxes": "AlternateMailboxes",
        "cas_version": "CasVersion",
        "ews_supported_schemas": "EwsSupportedSchemas",
        "internal_pop3_connections": "InternalPop3Connections",
        "external_pop3_connections": "ExternalPop3Connections",
        "internal_imap4_connections": "InternalImap4Connections",
        "external_imap4_connections": "ExternalImap4Connections",
        "internal_smtp_connections": "InternalSmtpConnections",
        "external_smtp_connections": "ExternalSmtpConnections",
        "internal_server_exclusive_connect": "InternalServerExclusiveConnect",
        "external_server_exclusive_connect": "ExternalServerExclusiveConnect",
        "exchange_rpc_url": "ExchangeRpcUrl",
        "show_gal_as_default_view": "ShowGalAsDefaultView",
        "auto_discover_smtp_address": "AutoDiscoverSMTPAddress",
        "interop_external_ews_url": "InteropExternalEwsUrl",
        "external_ews_version": "ExternalEwsVersion",
        "interop_external_ews_version": "InteropExternalEwsVersion",
        "mobile_mailbox_policy_interop": "MobileMailboxPolicyInterop",
        "grouping_information": "GroupingInformation",
        "user_ms_online": "UserMSOnline",
        "mapi_http_enabled": "MapiHttpEnabled",
    }
    REVERSE_SETTINGS_MAP = {v: k for k, v in SETTINGS_MAP.items()}

    error_code = CharField()
    error_message = CharField()
    redirect_address = CharField()
    redirect_url = CharField()
    user_settings_errors = DictionaryField()
    user_settings = DictionaryField()

    @property
    def autodiscover_smtp_address(self):
        return self.user_settings.get("auto_discover_smtp_address")

    @property
    def ews_url(self):
        return self.user_settings.get("external_ews_url")

    @property
    def version(self):
        if not self.user_settings.get("ews_supported_schemas"):
            return None
        supported_schemas = [s.strip() for s in self.user_settings.get("ews_supported_schemas").split(",")]
        newest_supported_schema = sorted(supported_schemas, reverse=True)[0]

        for version in Version.all_versions():
            if newest_supported_schema == version.api_version:
                return version
        raise ValueError(f"Unknown supported schemas: {supported_schemas}")

    def raise_errors(self):
        if self.error_code == "InvalidUser":
            raise ErrorNonExistentMailbox(self.error_message)
        if self.error_code in (
            "InvalidRequest",
            "InvalidSetting",
            "SettingIsNotAvailable",
            "InvalidDomain",
            "NotFederated",
        ):
            raise AutoDiscoverFailed(f"{self.error_code}: {self.error_message}")
        if self.user_settings_errors:
            raise AutoDiscoverFailed(f"User settings errors: {self.user_settings_errors}")

    @classmethod
    def parse_elem(cls, elem):
        # Possible ErrorCode values:
        #   https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/errorcode-soap
        error_code = get_xml_attr(elem, f"{{{ANS}}}ErrorCode")
        error_message = get_xml_attr(elem, f"{{{ANS}}}ErrorMessage")
        if error_code == "InternalServerError":
            return ErrorInternalServerError(error_message)
        if error_code == "ServerBusy":
            return ErrorServerBusy(error_message)
        if error_code == "NotFederated":
            return ErrorOrganizationNotFederated(error_message)
        return cls(error_code=error_code, error_message=error_message)

    @classmethod
    def from_xml(cls, elem, account):
        res = cls.parse_elem(elem)
        if isinstance(res, Exception):
            raise res
        if res.error_code not in ("NoError", "RedirectAddress", "RedirectUrl"):
            return cls(error_code=res.error_code, error_message=res.error_message)

        redirect_target = get_xml_attr(elem, f"{{{ANS}}}RedirectTarget")
        redirect_address = redirect_target if res.error_code == "RedirectAddress" else None
        redirect_url = redirect_target if res.error_code == "RedirectUrl" else None
        user_settings_errors = {}
        settings_errors_elem = elem.find(f"{{{ANS}}}UserSettingErrors")
        if settings_errors_elem is not None:
            for setting_error in settings_errors_elem:
                error_code = get_xml_attr(setting_error, f"{{{ANS}}}ErrorCode")
                error_message = get_xml_attr(setting_error, f"{{{ANS}}}ErrorMessage")
                name = get_xml_attr(setting_error, f"{{{ANS}}}SettingName")
                user_settings_errors[cls.REVERSE_SETTINGS_MAP[name]] = (error_code, error_message)
        user_settings = {}
        settings_elem = elem.find(f"{{{ANS}}}UserSettings")
        if settings_elem is not None:
            for setting in settings_elem:
                name = get_xml_attr(setting, f"{{{ANS}}}Name")
                value = get_xml_attr(setting, f"{{{ANS}}}Value")
                user_settings[cls.REVERSE_SETTINGS_MAP[name]] = value
        return cls(
            redirect_address=redirect_address,
            redirect_url=redirect_url,
            user_settings_errors=user_settings_errors,
            user_settings=user_settings,
        )


class WithinDateRange(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/withindaterange
    """

    ELEMENT_NAME = "DateRange"
    NAMESPACE = MNS

    start_date_time = DateTimeField(field_uri="StartDateTime", is_required=True)
    end_date_time = DateTimeField(field_uri="EndDateTime", is_required=True)


class WithinSizeRange(EWSElement):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/withinsizerange
    """

    ELEMENT_NAME = "SizeRange"
    NAMESPACE = MNS

    minimum_size = IntegerField(field_uri="MinimumSize", is_required=True)
    maximum_size = IntegerField(field_uri="MaximumSize", is_required=True)


class Conditions(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/conditions"""

    ELEMENT_NAME = "Conditions"
    NAMESPACE = TNS

    categories = CharListField(field_uri="Categories")
    contains_body_strings = CharListField(field_uri="ContainsBodyStrings")
    contains_header_strings = CharListField(field_uri="ContainsHeaderStrings")
    contains_recipient_strings = CharListField(field_uri="ContainsRecipientStrings")
    contains_sender_strings = CharListField(field_uri="ContainsSenderStrings")
    contains_subject_or_body_strings = CharListField(field_uri="ContainsSubjectOrBodyStrings")
    contains_subject_strings = CharListField(field_uri="ContainsSubjectStrings")
    flagged_for_action = FlaggedForActionField(field_uri="FlaggedForAction")
    from_addresses = EWSElementField(value_cls=Mailbox, field_uri="FromAddresses")
    from_connected_accounts = CharListField(field_uri="FromConnectedAccounts")
    has_attachments = BooleanField(field_uri="HasAttachments")
    importance = ImportanceField(field_uri="Importance")
    is_approval_request = BooleanField(field_uri="IsApprovalRequest")
    is_automatic_forward = BooleanField(field_uri="IsAutomaticForward")
    is_automatic_reply = BooleanField(field_uri="IsAutomaticReply")
    is_encrypted = BooleanField(field_uri="IsEncrypted")
    is_meeting_request = BooleanField(field_uri="IsMeetingRequest")
    is_meeting_response = BooleanField(field_uri="IsMeetingResponse")
    is_ndr = BooleanField(field_uri="IsNDR")
    is_permission_controlled = BooleanField(field_uri="IsPermissionControlled")
    is_read_receipt = BooleanField(field_uri="IsReadReceipt")
    is_signed = BooleanField(field_uri="IsSigned")
    is_voicemail = BooleanField(field_uri="IsVoicemail")
    item_classes = CharListField(field_uri="ItemClasses")
    message_classifications = CharListField(field_uri="MessageClassifications")
    not_sent_to_me = BooleanField(field_uri="NotSentToMe")
    sent_cc_me = BooleanField(field_uri="SentCcMe")
    sent_only_to_me = BooleanField(field_uri="SentOnlyToMe")
    sent_to_addresses = EWSElementField(value_cls=Mailbox, field_uri="SentToAddresses")
    sent_to_me = BooleanField(field_uri="SentToMe")
    sent_to_or_cc_me = BooleanField(field_uri="SentToOrCcMe")
    sensitivity = SensitivityField(field_uri="Sensitivity")
    within_date_range = EWSElementField(value_cls=WithinDateRange, field_uri="WithinDateRange")
    within_size_range = EWSElementField(value_cls=WithinSizeRange, field_uri="WithinSizeRange")


class Exceptions(Conditions):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/exceptions"""

    ELEMENT_NAME = "Exceptions"
    NAMESPACE = TNS


class CopyToFolder(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/copytofolder"""

    ELEMENT_NAME = "CopyToFolder"

    folder_id = EWSElementField(value_cls=FolderId)
    distinguished_folder_id = EWSElementField(value_cls=DistinguishedFolderId)


class MoveToFolder(CopyToFolder):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/movetofolder"""

    ELEMENT_NAME = "MoveToFolder"


class Actions(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/actions"""

    ELEMENT_NAME = "Actions"

    assign_categories = CharListField(field_uri="AssignCategories")
    copy_to_folder = FolderActionField(value_cls=CopyToFolder)
    delete = BooleanField(field_uri="Delete")
    forward_as_attachment_to_recipients = AddressListField(field_uri="ForwardAsAttachmentToRecipients")
    forward_to_recipients = AddressListField(field_uri="ForwardToRecipients")
    mark_importance = ImportanceField(field_uri="MarkImportance")
    mark_as_read = BooleanField(field_uri="MarkAsRead")
    move_to_folder = FolderActionField(value_cls=MoveToFolder)
    permanent_delete = BooleanField(field_uri="PermanentDelete")
    redirect_to_recipients = AddressListField(field_uri="RedirectToRecipients")
    send_sms_alert_to_recipients = AddressListField(field_uri="SendSMSAlertToRecipients")
    server_reply_with_message = EWSElementField(value_cls=ItemId, field_uri="ServerReplyWithMessage")
    stop_processing_rules = BooleanField(field_uri="StopProcessingRules")


class Rule(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/rule-ruletype"""

    def __init__(self, **kwargs):
        """Pick out optional 'account' kwarg, and pass the rest to the parent class.

        :param kwargs:
            'account' is optional but allows calling 'send()' and 'delete()'
        """
        from .account import Account

        self.account = kwargs.pop("account", None)
        if self.account is not None and not isinstance(self.account, Account):
            raise InvalidTypeError("account", self.account, Account)
        super().__init__(**kwargs)

    __slots__ = ("account",)

    ELEMENT_NAME = "Rule"

    id = CharField(field_uri="RuleId")
    display_name = CharField(field_uri="DisplayName", is_required=True)
    priority = IntegerField(field_uri="Priority", is_required=True)
    is_enabled = BooleanField(field_uri="IsEnabled")
    is_not_supported = BooleanField(field_uri="IsNotSupported")
    is_in_error = BooleanField(field_uri="IsInError")
    conditions = EWSElementField(value_cls=Conditions)
    exceptions = EWSElementField(value_cls=Exceptions)
    actions = EWSElementField(value_cls=Actions, is_required=True)

    @classmethod
    def from_xml(cls, elem, account):
        res = super().from_xml(elem=elem, account=account)
        res.account = account
        return res

    def save(self):
        if self.id is None:
            self.account.create_rule(self)
        else:
            self.account.set_rule(self)
        return self

    def delete(self):
        if self.is_enabled is False:
            # Cannot delete a disabled rule - server throws 'ErrorItemNotFound'
            self.is_enabled = True
            self.save()
        self.account.delete_rule(self)


class InboxRules(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/inboxrules"""

    ELEMENT_NAME = "InboxRules"
    NAMESPACE = MNS

    rule = EWSElementListField(value_cls=Rule)


class CreateRuleOperation(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/createruleoperation"""

    ELEMENT_NAME = "CreateRuleOperation"

    rule = EWSElementField(value_cls=Rule)


class SetRuleOperation(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/setruleoperation"""

    ELEMENT_NAME = "SetRuleOperation"

    rule = EWSElementField(value_cls=Rule)


class DeleteRuleOperation(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/deleteruleoperation"""

    ELEMENT_NAME = "DeleteRuleOperation"

    id = CharField(field_uri="RuleId")


class Operations(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/operations"""

    ELEMENT_NAME = "Operations"
    NAMESPACE = MNS

    create_rule_operation = EWSElementField(value_cls=CreateRuleOperation)
    set_rule_operation = EWSElementField(value_cls=SetRuleOperation)
    delete_rule_operation = EWSElementField(value_cls=DeleteRuleOperation)
