# coding=utf-8
"""
Implements a selection of the folders and folder items found in an Exchange account.

Exchange is very picky about things like the order of XML elements in SOAP requests, so we need to generate XML
automatically instead of taking advantage of Python SOAP libraries and the WSDL file.
"""

from __future__ import unicode_literals

import base64
import mimetypes
import warnings
from decimal import Decimal
from logging import getLogger

from future.utils import python_2_unicode_compatible
from six import text_type, string_types

from .ewsdatetime import EWSDateTime, UTC, UTC_NOW
from .queryset import QuerySet
from .restriction import Restriction, Q
from .services import TNS, IdOnly, SHALLOW, DEEP, FindFolder, GetFolder, FindItem, GetAttachment, CreateAttachment, \
    DeleteAttachment, MNS, ITEM_TRAVERSAL_CHOICES, FOLDER_TRAVERSAL_CHOICES, SHAPE_CHOICES
from .util import create_element, add_xml_child, get_xml_attrs, get_xml_attr, set_xml_value, value_to_xml_text, \
    xml_text_to_value, isanysubclass
from .version import EXCHANGE_2010

string_type = string_types[0]
log = getLogger(__name__)

# MessageDisposition values. See https://msdn.microsoft.com/en-us/library/office/aa565209(v=exchg.150).aspx
SAVE_ONLY = 'SaveOnly'
SEND_ONLY = 'SendOnly'
SEND_AND_SAVE_COPY = 'SendAndSaveCopy'
MESSAGE_DISPOSITION_CHOICES = (SAVE_ONLY, SEND_ONLY, SEND_AND_SAVE_COPY)

# SendMeetingInvitations values: see https://msdn.microsoft.com/en-us/library/office/aa565209(v=exchg.150).aspx
# SendMeetingInvitationsOrCancellations: see https://msdn.microsoft.com/en-us/library/office/aa580254(v=exchg.150).aspx
# SendMeetingCancellations values: see https://msdn.microsoft.com/en-us/library/office/aa562961(v=exchg.150).aspx
SEND_TO_NONE = 'SendToNone'
SEND_ONLY_TO_ALL = 'SendOnlyToAll'
SEND_ONLY_TO_CHANGED = 'SendOnlyToChanged'
SEND_TO_ALL_AND_SAVE_COPY = 'SendToAllAndSaveCopy'
SEND_TO_CHANGED_AND_SAVE_COPY = 'SendToChangedAndSaveCopy'
SEND_MEETING_INVITATIONS_CHOICES = (SEND_TO_NONE, SEND_ONLY_TO_ALL, SEND_TO_ALL_AND_SAVE_COPY)
SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES = (SEND_TO_NONE, SEND_ONLY_TO_ALL, SEND_ONLY_TO_CHANGED,
                                                      SEND_TO_ALL_AND_SAVE_COPY, SEND_TO_CHANGED_AND_SAVE_COPY)
SEND_MEETING_CANCELLATIONS_CHOICES = (SEND_TO_NONE, SEND_ONLY_TO_ALL, SEND_TO_ALL_AND_SAVE_COPY)

# AffectedTaskOccurrences values. See https://msdn.microsoft.com/en-us/library/office/aa562961(v=exchg.150).aspx
ALL_OCCURRENCIES = 'AllOccurrences'
SPECIFIED_OCCURRENCE_ONLY = 'SpecifiedOccurrenceOnly'
AFFECTED_TASK_OCCURRENCES_CHOICES = (ALL_OCCURRENCIES, SPECIFIED_OCCURRENCE_ONLY)

# ConflictResolution values. See https://msdn.microsoft.com/en-us/library/office/aa580254(v=exchg.150).aspx
NEVER_OVERWRITE = 'NeverOverwrite'
AUTO_RESOLVE = 'AutoResolve'
ALWAYS_OVERWRITE = 'AlwaysOverwrite'
CONFLICT_RESOLUTION_CHOICES = (NEVER_OVERWRITE, AUTO_RESOLVE, ALWAYS_OVERWRITE)

# DeleteType values. See https://msdn.microsoft.com/en-us/library/office/aa562961(v=exchg.150).aspx
HARD_DELETE = 'HardDelete'
SOFT_DELETE = 'SoftDelete'
MOVE_TO_DELETED_ITEMS = 'MoveToDeletedItems'
DELETE_TYPE_CHOICES = (HARD_DELETE, SOFT_DELETE, MOVE_TO_DELETED_ITEMS)


class Choice(text_type):
    # A helper class used for string enums
    pass


class Email(text_type):
    # A helper class used for email address string
    pass


class AnyURI(text_type):
    # Helper to mark strings that must conform to xsd:anyURI
    # If we want an URI validator, see http://stackoverflow.com/questions/14466585/is-this-regex-correct-for-xsdanyuri
    pass


class Body(text_type):
    # Helper to mark the 'body' field as a complex attribute.
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj219983(v=exchg.150).aspx
    body_type = 'Text'


class HTMLBody(Body):
    # Helper to mark the 'body' field as a complex attribute.
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj219983(v=exchg.150).aspx
    body_type = 'HTML'


class MimeContent(text_type):
    # Helper to work with the base64 encoded MimeContent Message field
    def b64encode(self):
        return base64.b64encode(self).decode('ascii')

    def b64decode(self):
        return base64.b64decode(self)


class EWSElement(object):
    ELEMENT_NAME = None

    __slots__ = tuple()

    @classmethod
    def set_field_xml(cls, field_elem, items, version):
        # Builds the XML for a SetItemField element
        for item in items:
            field_elem.append(item.to_xml(version=version))
        return field_elem

    def clean(self):
        # Perform any attribute validation here
        pass

    def to_xml(self, version):
        raise NotImplementedError()

    @classmethod
    def from_xml(cls, elem):
        raise NotImplementedError()

    @classmethod
    def request_tag(cls):
        return 't:%s' % cls.ELEMENT_NAME

    @classmethod
    def response_tag(cls):
        return '{%s}%s' % (TNS, cls.ELEMENT_NAME)

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash(tuple(getattr(self, f) for f in self.__slots__))

    def __repr__(self):
        return self.__class__.__name__ + repr(tuple(getattr(self, f) for f in self.__slots__))


class MessageHeader(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565307(v=exchg.150).aspx
    ELEMENT_NAME = 'InternetMessageHeader'
    NAME_ATTR = 'HeaderName'

    __slots__ = ('name', 'value')

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def to_xml(self, version):
        self.clean()
        elem = create_element(self.request_tag())
        # Use .set() to not fill up the create_element() cache with unique values
        elem.set(self.NAME_ATTR, self.name)
        set_xml_value(elem, self.value, version)
        return elem

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        res = cls(name=elem.get(cls.NAME_ATTR), value=elem.text)
        elem.clear()
        return res


class ItemId(EWSElement):
    # 'id' and 'changekey' are UUIDs generated by Exchange
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580234(v=exchg.150).aspx
    ELEMENT_NAME = 'ItemId'

    ID_ATTR = 'Id'
    CHANGEKEY_ATTR = 'ChangeKey'

    __slots__ = ('id', 'changekey')

    def __init__(self, id, changekey):
        if not isinstance(id, string_types) or not id:
            raise ValueError("id '%s' must be a non-empty string" % id)
        if not isinstance(changekey, string_types) or not changekey:
            raise ValueError("changekey '%s' must be a non-empty string" % changekey)
        self.id = id
        self.changekey = changekey

    def to_xml(self, version):
        self.clean()
        elem = create_element(self.request_tag())
        # Use .set() to not fill up the create_element() cache with unique values
        elem.set(self.ID_ATTR, self.id)
        elem.set(self.CHANGEKEY_ATTR, self.changekey)
        return elem

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        res = cls(id=elem.get(cls.ID_ATTR), changekey=elem.get(cls.CHANGEKEY_ATTR))
        elem.clear()
        return res

    def __eq__(self, other):
        # A more efficient version of super().__eq__
        if other is None:
            return False
        return self.id == other.id and self.changekey == other.changekey


class FolderId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa579461(v=exchg.150).aspx
    ELEMENT_NAME = 'FolderId'

    __slots__ = ('id', 'changekey')


class ParentItemId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa563720(v=exchg.150).aspx
    ELEMENT_NAME = 'ParentItemId'

    __slots__ = ('id', 'changekey')

    @classmethod
    def request_tag(cls):
        return 'm:%s' % cls.ELEMENT_NAME


class RootItemId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/bb204277(v=exchg.150).aspx
    ELEMENT_NAME = 'RootItemId'
    ID_ATTR = 'RootItemId'
    CHANGEKEY_ATTR = 'RootItemChangeKey'

    __slots__ = ('id', 'changekey')

    @classmethod
    def request_tag(cls):
        return 'm:%s' % cls.ELEMENT_NAME

    @classmethod
    def response_tag(cls):
        return '{%s}%s' % (MNS, cls.ELEMENT_NAME)


class AttachmentId(EWSElement):
    # 'id' and 'changekey' are UUIDs generated by Exchange
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580987(v=exchg.150).aspx
    ELEMENT_NAME = 'AttachmentId'

    ID_ATTR = 'Id'
    ROOT_ID_ATTR = 'RootItemId'
    ROOT_CHANGEKEY_ATTR = 'RootItemChangeKey'

    __slots__ = ('id', 'root_id', 'root_changekey')

    def __init__(self, id, root_id=None, root_changekey=None):
        if not isinstance(id, string_types) or not id:
            raise ValueError("id '%s' must be a non-empty string" % id)
        if root_id is not None or root_changekey is not None:
            if root_id is not None and (not isinstance(root_id, string_types) or not root_id):
                raise ValueError("root_id '%s' must be a non-empty string" % root_id)
            if root_changekey is not None and (not isinstance(root_changekey, string_types) or not root_changekey):
                raise ValueError("root_changekey '%s' must be a non-empty string" % root_changekey)
        self.id = id
        self.root_id = root_id
        self.root_changekey = root_changekey

    def to_xml(self, version):
        self.clean()
        elem = create_element(self.request_tag())
        # Use .set() to not fill up the create_element() cache with unique values
        elem.set(self.ID_ATTR, self.id)
        if self.root_id:
            elem.set(self.ROOT_ID_ATTR, self.root_id)
        if self.root_changekey:
            elem.set(self.ROOT_CHANGEKEY_ATTR, self.root_changekey)
        return elem

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        res = cls(
            id=elem.get(cls.ID_ATTR),
            root_id=elem.get(cls.ROOT_ID_ATTR),
            root_changekey=elem.get(cls.ROOT_CHANGEKEY_ATTR)
        )
        elem.clear()
        return res


class Attachment(EWSElement):
    """
    Parent class for FileAttachment and ItemAttachment
    """
    ATTACHMENT_FIELDS = {
        'name': ('Name', string_type),
        'content_type': ('ContentType', string_type),
        'attachment_id': (AttachmentId, AttachmentId),
        'content_id': ('ContentId', string_type),
        'content_location': ('ContentLocation', AnyURI),
        'size': ('Size', int),
        'last_modified_time': ('LastModifiedTime', EWSDateTime),
        'is_inline': ('IsInline', bool),
    }
    ORDERED_FIELDS = (
        'attachment_id', 'name', 'content_type', 'content_id', 'content_location', 'size', 'last_modified_time',
        'is_inline',
    )

    __slots__ = ('parent_item',) + ORDERED_FIELDS

    def __init__(self, parent_item=None, attachment_id=None, name=None, content_type=None, content_id=None,
                 content_location=None, size=None, last_modified_time=None, is_inline=None):
        if content_type is None and name is not None:
            content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        self.parent_item = parent_item
        self.name = name
        self.content_type = content_type
        self.attachment_id = attachment_id
        self.content_id = content_id
        self.content_location = content_location
        self.size = size  # Size is attachment size in bytes
        self.last_modified_time = last_modified_time
        self.is_inline = is_inline

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        for field_name in self.ORDERED_FIELDS:
            if field_name == 'size':
                # 'Size' is read-only
                continue
            val = getattr(self, field_name)
            if field_name == 'content':
                # EWS wants file content base64-encoded
                if val is None:
                    raise ValueError("File attachment must contain data")
                val = base64.b64encode(val).decode('ascii')
            if val is None:
                continue
            field_uri = self.ATTACHMENT_FIELDS[field_name][0]
            if isinstance(field_uri, string_types):
                add_xml_child(entry, 't:%s' % field_uri, val)
            elif issubclass(field_uri, EWSElement):
                set_xml_value(entry, val, version)
            else:
                assert False, 'field_uri %s not supported' % field_uri
        return entry

    @classmethod
    def from_xml(cls, elem, parent_item=None):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        kwargs = {}
        for field_name, (field_uri, field_type) in cls.ATTACHMENT_FIELDS.items():
            if field_name == 'item':
                kwargs[field_name] = None
                for item_cls in ITEM_CLASSES:
                    item_elem = elem.find(item_cls.response_tag())
                    if item_elem is not None:
                        account = parent_item.account if parent_item else None
                        kwargs[field_name] = item_cls.from_xml(elem=item_elem, account=account)
                        break
                continue
            if issubclass(field_type, EWSElement):
                kwargs[field_name] = field_type.from_xml(elem=elem.find(field_type.response_tag()))
                continue
            response_tag = '{%s}%s' % (TNS, field_uri)
            val = get_xml_attr(elem, response_tag)
            if field_name == 'content':
                kwargs[field_name] = None if val is None else base64.b64decode(val)
                continue
            if field_name == 'last_modified_time' and val is not None and not val.endswith('Z'):
                # Sometimes, EWS will send timestamps without the 'Z' for UTC. It seems like the values are still
                # UTC, so mark them as such so EWSDateTime can still interpret the timestamps.
                val += 'Z'
            kwargs[field_name] = xml_text_to_value(value=val, field_type=field_type)
        elem.clear()
        return cls(parent_item=parent_item, **kwargs)

    def attach(self):
        # Adds this attachment to an item and updates the item_id and updated changekey on the parent item
        if self.attachment_id:
            raise ValueError('This attachment has already been created')
        if not self.parent_item.account:
            raise ValueError('Parent item %s must have an account' % self.parent_item)
        items = list(
            self.from_xml(elem=i)
            for i in CreateAttachment(account=self.parent_item.account).call(parent_item=self.parent_item, items=[self])
        )
        assert len(items) == 1
        attachment_id = items[0].attachment_id
        assert attachment_id.root_id == self.parent_item.item_id
        assert attachment_id.root_changekey != self.parent_item.changekey
        self.parent_item.changekey = attachment_id.root_changekey
        # EWS does not like receiving root_id and root_changekey on subsequent requests
        attachment_id.root_id = None
        attachment_id.root_changekey = None
        self.attachment_id = attachment_id

    def detach(self):
        # Deletes an attachment remotely and returns the item_id and updated changekey of the parent item
        if not self.attachment_id:
            raise ValueError('This attachment has not been created')
        if not self.parent_item:
            raise ValueError('This attachment is not attached to an item')
        items = list(
            RootItemId.from_xml(elem=i)
            for i in DeleteAttachment(account=self.parent_item.account).call(items=[self.attachment_id])
        )
        assert len(items) == 1
        root_item_id = items[0]
        assert root_item_id.id == self.parent_item.item_id
        assert root_item_id.changekey != self.parent_item.changekey
        self.parent_item.changekey = root_item_id.changekey
        self.parent_item = None
        self.attachment_id = None

    def __hash__(self):
        if self.attachment_id is None:
            return hash(tuple(getattr(self, f) for f in self.__slots__[1:]))
        return hash(self.attachment_id)

    def __repr__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%s' % (k, repr(getattr(self, k))) for k in self.ORDERED_FIELDS if k not in ('item', 'content')
        )


class IndexedField(EWSElement):
    PARENT_ELEMENT_NAME = None
    ELEMENT_NAME = None
    LABELS = ()
    FIELD_URI = None
    SUB_FIELD_ELEMENT_NAMES = {}

    @classmethod
    def field_uri_xml(cls, label, subfield=None):
        if cls.SUB_FIELD_ELEMENT_NAMES:
            if subfield:
                return create_element(
                    't:IndexedFieldURI',
                    FieldURI='%s:%s' % (cls.FIELD_URI, cls.SUB_FIELD_ELEMENT_NAMES[subfield]),
                    FieldIndex=label,
                )
            return [create_element(
                't:IndexedFieldURI',
                FieldURI='%s:%s' % (cls.FIELD_URI, field),
                FieldIndex=label,
            ) for field in cls.SUB_FIELD_ELEMENT_NAMES.values()]
        return create_element(
            't:IndexedFieldURI',
            FieldURI=cls.FIELD_URI,
            FieldIndex=label,
        )


class EmailAddress(IndexedField):
    # MSDN:  https://msdn.microsoft.com/en-us/library/office/aa564757(v=exchg.150).aspx
    PARENT_ELEMENT_NAME = 'EmailAddresses'
    ELEMENT_NAME = 'Entry'
    LABELS = {'EmailAddress1', 'EmailAddress2', 'EmailAddress3'}
    FIELD_URI = 'contacts:EmailAddress'

    __slots__ = ('label', 'email')

    def __init__(self, email, label='EmailAddress1'):
        assert label in self.LABELS, label
        assert isinstance(email, string_types), email
        self.label = label
        self.email = email

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag(), Key=self.label)
        set_xml_value(entry, self.email, version)
        return entry

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        res = cls(
            label=elem.get('Key'),
            email=elem.text or elem.get('Name'),  # Sometimes elem.text is empty. Exchange saves the same in 'Name' attr
        )
        elem.clear()
        return res


class PhoneNumber(IndexedField):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565941(v=exchg.150).aspx
    PARENT_ELEMENT_NAME = 'PhoneNumbers'
    ELEMENT_NAME = 'Entry'
    LABELS = {
        'AssistantPhone', 'BusinessFax', 'BusinessPhone', 'BusinessPhone2', 'Callback', 'CarPhone', 'CompanyMainPhone',
        'HomeFax', 'HomePhone', 'HomePhone2', 'Isdn', 'MobilePhone', 'OtherFax', 'OtherTelephone', 'Pager',
        'PrimaryPhone', 'RadioPhone', 'Telex', 'TtyTddPhone',
    }
    FIELD_URI = 'contacts:PhoneNumber'

    __slots__ = ('label', 'phone_number')

    def __init__(self, phone_number, label='PrimaryPhone'):
        assert label in self.LABELS, label
        assert isinstance(phone_number, (int, string_type)), phone_number
        self.label = label
        self.phone_number = phone_number

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag(), Key=self.label)
        set_xml_value(entry, text_type(self.phone_number), version)
        return entry

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        res = cls(
            label=elem.get('Key'),
            phone_number=elem.text,
        )
        elem.clear()
        return res


class PhysicalAddress(IndexedField):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564323(v=exchg.150).aspx
    PARENT_ELEMENT_NAME = 'PhysicalAddresses'
    ELEMENT_NAME = 'Entry'
    LABELS = {'Business', 'Home', 'Other'}
    FIELD_URI = 'contacts:PhysicalAddress'

    SUB_FIELD_ELEMENT_NAMES = {
        'street': 'Street',
        'city': 'City',
        'state': 'State',
        'country': 'CountryOrRegion',
        'zipcode': 'PostalCode',
    }

    __slots__ = ('label', 'street', 'city', 'state', 'country', 'zipcode')

    def __init__(self, street=None, city=None, state=None, country=None, zipcode=None, label='Business'):
        assert label in self.LABELS, label
        if street is not None:
            assert isinstance(street, string_types), street
        if city is not None:
            assert isinstance(city, string_types), city
        if state is not None:
            assert isinstance(state, string_types), state
        if country is not None:
            assert isinstance(country, string_types), country
        if zipcode is not None:
            assert isinstance(zipcode, (string_type, int)), zipcode
        self.label = label
        self.street = street  # Street *and* house number (and similar info)
        self.city = city
        self.state = state
        self.country = country
        self.zipcode = zipcode

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag(), Key=self.label)
        for attr in self.__slots__:
            if attr == 'label':
                continue
            val = getattr(self, attr)
            if val is not None:
                add_xml_child(entry, 't:%s' % self.SUB_FIELD_ELEMENT_NAMES[attr], val)
        return entry

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        kwargs = dict(label=elem.get('Key'))
        for k, v in cls.SUB_FIELD_ELEMENT_NAMES.items():
            kwargs[k] = get_xml_attr(elem, '{%s}%s' % (TNS, v))
        elem.clear()
        return cls(**kwargs)


class Mailbox(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565036(v=exchg.150).aspx
    ELEMENT_NAME = 'Mailbox'
    MAILBOX_TYPES = {'Mailbox', 'PublicDL', 'PrivateDL', 'Contact', 'PublicFolder', 'Unknown', 'OneOff'}

    __slots__ = ('name', 'email_address', 'mailbox_type', 'item_id')

    def __init__(self, name=None, email_address=None, mailbox_type=None, item_id=None):
        # There's also the 'RoutingType' element, but it's optional and must have value "SMTP"
        if name is not None:
            assert isinstance(name, string_types)
        if email_address is not None:
            assert isinstance(email_address, string_types)
        if mailbox_type is not None:
            assert mailbox_type in self.MAILBOX_TYPES
        if item_id is not None:
            assert isinstance(item_id, ItemId)
        self.name = name
        self.email_address = email_address
        self.mailbox_type = mailbox_type
        self.item_id = item_id

    def to_xml(self, version):
        self.clean()
        if not self.email_address and not self.item_id:
            # See "Remarks" section of https://msdn.microsoft.com/en-us/library/office/aa565036(v=exchg.150).aspx
            raise AttributeError('Mailbox must have either email_address or item_id')
        mailbox = create_element(self.request_tag())
        if self.name:
            add_xml_child(mailbox, 't:Name', self.name)
        if self.email_address:
            add_xml_child(mailbox, 't:EmailAddress', self.email_address)
        if self.mailbox_type:
            add_xml_child(mailbox, 't:MailboxType', self.mailbox_type)
        if self.item_id:
            set_xml_value(mailbox, self.item_id, version)
        return mailbox

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (elem.tag, cls.response_tag())
        res = cls(
            name=get_xml_attr(elem, '{%s}Name' % TNS),
            email_address=get_xml_attr(elem, '{%s}EmailAddress' % TNS),
            mailbox_type=get_xml_attr(elem, '{%s}MailboxType' % TNS),
            item_id=ItemId.from_xml(elem=elem.find(ItemId.response_tag())),
        )
        elem.clear()
        return res

    def __hash__(self):
        # Exchange may add 'mailbox_type' and 'name' on insert. We're satisfied if the item_id or email address matches.
        if self.item_id:
            return hash(self.item_id)
        return hash(self.email_address.lower())


class RoomList(Mailbox):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899514(v=exchg.150).aspx
    ELEMENT_NAME = 'RoomList'
    # In a GetRoomLists response, room lists are delivered as Address elements
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899404(v=exchg.150).aspx
    RESPONSE_ELEMENT_NAME = 'Address'

    @classmethod
    def request_tag(cls):
        return 'm:%s' % cls.ELEMENT_NAME

    @classmethod
    def response_tag(cls):
        return '{%s}%s' % (TNS, cls.RESPONSE_ELEMENT_NAME)


class Room(Mailbox):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899479(v=exchg.150).aspx
    ELEMENT_NAME = 'Room'

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (elem.tag, cls.response_tag())
        id_elem = elem.find('{%s}Id' % TNS)
        res = cls(
            name=get_xml_attr(id_elem, '{%s}Name' % TNS),
            email_address=get_xml_attr(id_elem, '{%s}EmailAddress' % TNS),
            mailbox_type=get_xml_attr(id_elem, '{%s}MailboxType' % TNS),
            item_id=ItemId.from_xml(elem=id_elem.find(ItemId.response_tag())),
        )
        elem.clear()
        return res


class ExtendedProperty(EWSElement):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa566405(v=exchg.150).aspx

    Property_* values: https://msdn.microsoft.com/en-us/library/office/aa564843(v=exchg.150).aspx
    """
    # TODO: Property sets, tags and distinguished set ID are not implemented yet
    ELEMENT_NAME = 'ExtendedProperty'

    DISTINGUISHED_SETS = {
        'Meeting',
        'Appointment',
        'Common',
        'PublicStrings',
        'Address',
        'InternetHeaders',
        'CalendarAssistant',
        'UnifiedMessaging',
    }
    PROPERTY_TYPES = {
        'ApplicationTime',
        'Binary',
        'BinaryArray',
        'Boolean',
        'CLSID',
        'CLSIDArray',
        'Currency',
        'CurrencyArray',
        'Double',
        'DoubleArray',
        # 'Error',
        'Float',
        'FloatArray',
        'Integer',
        'IntegerArray',
        'Long',
        'LongArray',
        # 'Null',
        # 'Object',
        # 'ObjectArray',
        'Short',
        'ShortArray',
        # 'SystemTime',  # Not implemented yet
        # 'SystemTimeArray',  # Not implemented yet
        'String',
        'StringArray',
    }  # The commented-out types cannot be used for setting or getting (see docs) and are thus not very useful here

    property_id = None
    property_name = None
    property_type = None

    __slots__ = ('value',)

    def __init__(self, value):
        python_type = self.python_type()
        if self.is_array_type():
            for v in value:
                assert isinstance(v, python_type)
        else:
            assert isinstance(value, python_type)
        self.value = value

    @classmethod
    def is_array_type(cls):
        return cls.property_type.endswith('Array')

    @classmethod
    def python_type(cls):
        # Return the best equivalent for a Python type for the property type of this class
        base_type = cls.property_type[:-5] if cls.is_array_type() else cls.property_type
        return {
            'ApplicationTime': Decimal,
            'Binary': bytes,
            'Boolean': bool,
            'CLSID': string_type,
            'Currency': int,
            'Double': Decimal,
            'Float': Decimal,
            'Integer': int,
            'Long': int,
            'Short': int,
            # 'SystemTime': int,
            'String': string_type,
        }[base_type]

    @classmethod
    def field_uri_xml(cls):
        assert cls.property_type in cls.PROPERTY_TYPES
        return create_element(
            't:ExtendedFieldURI',
            PropertySetId=cls.property_id,
            PropertyName=cls.property_name,
            PropertyType=cls.property_type
        )

    def to_xml(self, version):
        self.clean()
        extended_property = create_element(self.request_tag())
        set_xml_value(extended_property, self.field_uri_xml(), version)
        if self.is_array_type():
            values = create_element('t:Values')
            for v in self.value:
                add_xml_child(values, 't:Value', v)
            extended_property.append(values)
        else:
            add_xml_child(extended_property, 't:Value', self.value)
        return extended_property

    @classmethod
    def get_value(cls, elem):
        # Gets value of this specific ExtendedProperty from a list of 'ExtendedProperty' XML elements
        python_type = cls.python_type()
        extended_field_value = None
        for e in elem:
            extended_field_uri = e.find('{%s}ExtendedFieldURI' % TNS)
            match = True

            for k, v in (
                    ('PropertySetId', cls.property_id),
                    ('PropertyName', cls.property_name),
                    ('PropertyType', cls.property_type),
            ):
                if extended_field_uri.get(k) != v:
                    match = False
                    break
            if match:
                if cls.is_array_type():
                    extended_field_value = [
                        xml_text_to_value(value=val, field_type=python_type)
                        for val in get_xml_attrs(e, '{%s}Value' % TNS)
                    ]
                else:
                    extended_field_value = xml_text_to_value(
                        value=get_xml_attr(e, '{%s}Value' % TNS), field_type=python_type)
                    if python_type == string_type and not extended_field_value:
                        # For string types, we want to return the empty string instead of None if the element was
                        # actually found, but there was no XML value. For other types, it would be more problematic
                        # to make that distinction, e.g. return False for bool, 0 for int, etc.
                        extended_field_value = ''
                break
        return extended_field_value


class ExternId(ExtendedProperty):
    property_id = 'c11ff724-aa03-4555-9952-8fa248a11c3e'  # This is arbirtary. We just want a unique UUID.
    property_name = 'External ID'
    property_type = 'String'

    __slots__ = ExtendedProperty.__slots__


class Attendee(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580339(v=exchg.150).aspx
    ELEMENT_NAME = 'Attendee'
    RESPONSE_TYPES = {'Unknown', 'Organizer', 'Tentative', 'Accept', 'Decline', 'NoResponseReceived'}

    __slots__ = ('mailbox', 'response_type', 'last_response_time')

    def __init__(self, mailbox, response_type, last_response_time=None):
        if isinstance(mailbox, string_types):
            mailbox = Mailbox(email_address=mailbox)
        assert isinstance(mailbox, Mailbox)
        assert response_type in self.RESPONSE_TYPES
        if last_response_time is not None:
            assert isinstance(last_response_time, EWSDateTime)
        self.mailbox = mailbox
        self.response_type = response_type
        self.last_response_time = last_response_time

    def to_xml(self, version):
        self.clean()
        attendee = create_element(self.request_tag())
        set_xml_value(attendee, self.mailbox, version)
        add_xml_child(attendee, 't:ResponseType', self.response_type)
        if self.last_response_time:
            add_xml_child(attendee, 't:LastResponseTime', self.last_response_time)
        return attendee

    @classmethod
    def from_xml(cls, elem):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        last_response_time = get_xml_attr(elem, '{%s}LastResponseTime' % TNS)
        res = cls(
            mailbox=Mailbox.from_xml(elem=elem.find(Mailbox.response_tag())),
            response_type=get_xml_attr(elem, '{%s}ResponseType' % TNS) or 'Unknown',
            last_response_time=EWSDateTime.from_string(last_response_time) if last_response_time else None,
        )
        elem.clear()
        return res

    @classmethod
    def set_field_xml(cls, field_elem, items, version):
        # Builds the XML for a SetItemField element
        for item in items:
            attendee = create_element(cls.request_tag())
            set_xml_value(attendee, item.mailbox, version)
            field_elem.append(attendee)
        return field_elem

    def __hash__(self):
        # TODO: maybe take 'response_type' and 'last_response_time' into account?
        return hash(self.mailbox)


class Item(EWSElement):
    ELEMENT_NAME = 'Item'
    # The prefix part of the FieldURI for items of this type. See
    # https://msdn.microsoft.com/en-us/library/office/aa494315(v=exchg.150).aspx
    FIELDURI_PREFIX = 'item'

    SUBJECT_MAXLENGTH = 255

    # ITEM_FIELDS is a mapping from Python attribute name to a 2-tuple containing XML element name and value type.
    # Not all attributes are supported. See full list at
    # https://msdn.microsoft.com/en-us/library/office/aa580790(v=exchg.150).aspx

    # 'extern_id' is not a native EWS Item field. We use it for identification when item originates in an external
    # system. The field is implemented as an extended property on the Item.
    ITEM_FIELDS = {
        'item_id': ('ItemId', string_type),
        'changekey': ('ChangeKey', string_type),
        'mime_content': ('MimeContent', MimeContent),
        'sensitivity': ('Sensitivity', Choice),
        'importance': ('Importance', Choice),
        'is_draft': ('IsDraft', bool),
        'subject': ('Subject', string_type),
        'headers': ('InternetMessageHeaders', [MessageHeader]),
        'body': ('Body', Body),  # Or HTMLBody, which is a subclass of Body
        'attachments': ('Attachments', [Attachment]),  # ItemAttachment or FileAttachment
        'reminder_is_set': ('ReminderIsSet', bool),
        'categories': ('Categories', [string_type]),
        'extern_id': (ExternId, ExternId),
        'datetime_created': ('DateTimeCreated', EWSDateTime),
        'datetime_sent': ('DateTimeSent', EWSDateTime),
        'datetime_received': ('DateTimeReceived', EWSDateTime),
        'last_modified_name': ('LastModifiedName', string_type),
        'last_modified_time': ('LastModifiedTime', EWSDateTime),
    }
    # Possible values for string enums
    CHOICES = {
        'sensitivity': {'Normal', 'Personal', 'Private', 'Confidential'},
        'importance': {'Low', 'Normal', 'High'},
    }
    # Container for extended properties registered by the user
    EXTENDED_PROPERTIES = []
    # The order in which fields must be added to the XML output. It seems the same ordering is needed as the order in
    # which fields are listed at e.g. https://msdn.microsoft.com/en-us/library/office/aa580790(v=exchg.150).aspx
    ORDERED_FIELDS = ()
    # Item fields that are necessary to create an item
    REQUIRED_FIELDS = {'sensitivity', 'importance', 'reminder_is_set'}
    # Fields that are read-only in Exchange. Put mime_content and headers here until they are properly supported
    READONLY_FIELDS = {'is_draft', 'datetime_created', 'datetime_sent', 'datetime_received', 'last_modified_name',
                       'last_modified_time', 'mime_content', 'headers'}
    # Fields that are readonly when an item is no longer a draft. Updating these would result in
    # ErrorInvalidPropertyUpdateSentMessage
    READONLY_AFTER_SEND_FIELDS = set()

    # 'account' is optional but allows calling 'send()'
    # 'folder' is optional but allows calling 'save()' and 'delete()'
    __slots__ = ('account', 'folder') + tuple(ITEM_FIELDS)

    def __init__(self, **kwargs):
        for k in Item.__slots__:
            default = False if k == 'reminder_is_set' else [] if k == 'attachments' else None
            v = kwargs.pop(k, default)
            if v is not None:
                # Test if arguments have the correct type. Some types, e.g. ExtendedProperty and Body, are special
                # because we want to allow setting the attribute as a simple Python type for simplicity and ease of use,
                # while allowing the actual class instances.
                # 'field_type' may be a list with a single type. In that case we want to check all list members.
                if k == 'account':
                    from .account import Account
                    field_type = Account
                elif k == 'folder':
                    field_type = Folder
                else:
                    field_type = self.type_for_field(k)
                if isinstance(field_type, list):
                    elem_type = field_type[0]
                    assert isinstance(v, list)
                    for item in v:
                        if not isinstance(item, elem_type):
                            raise TypeError('Field %s value "%s" must be of type %s' % (k, v, field_type))
                else:
                    if isanysubclass(field_type, ExtendedProperty):
                        valid_field_types = (field_type, field_type.python_type())
                    elif field_type in (Body, HTMLBody, Choice, MimeContent):
                        valid_field_types = (field_type, string_type)
                    else:
                        valid_field_types = (field_type,)
                    if not isinstance(v, valid_field_types):
                        raise TypeError('Field %s value "%s" must be of type %s' % (k, v, field_type))
            setattr(self, k, v)
        for k, v in kwargs.items():
            raise TypeError("'%s' is an invalid keyword argument for this function" % k)
        for a in self.attachments:
            if a.parent_item:
                assert a.parent_item is self  # An attachment cannot refer to 'self' in __init__
            else:
                a.parent_item = self
            self.attach(self.attachments)

    def clean(self):
        if self.subject and len(self.subject) > self.SUBJECT_MAXLENGTH:
            raise ValueError("'subject' length exceeds %s" % self.SUBJECT_MAXLENGTH)

    def save(self, conflict_resolution=AUTO_RESOLVE, send_meeting_invitations=SEND_TO_NONE):
        item = self._save(message_disposition=SAVE_ONLY, conflict_resolution=conflict_resolution,
                          send_meeting_invitations=send_meeting_invitations)
        if self.item_id:
            # _save() returns tuple()
            item_id, changekey = item
            assert self.item_id == item_id
            assert self.changekey != changekey
            self.changekey = changekey
        else:
            # _save() returns Item
            self.item_id, self.changekey = item.item_id, item.changekey
            for old_att, new_att in zip(self.attachments, item.attachments):
                assert old_att.attachment_id is None
                assert new_att.attachment_id is not None
                old_att.attachment_id = new_att.attachment_id
        return self

    def _save(self, message_disposition, conflict_resolution, send_meeting_invitations):
        if not self.account:
            raise ValueError('Item must have an account')
        if self.item_id:
            assert self.changekey
            update_fields = []
            for f in self.fieldnames():
                if f == 'attachments':
                    # Attachments are handled separately after item creation
                    continue
                if f in self.readonly_fields():
                    # These cannot be changed
                    continue
                if not self.is_draft and f in self.readonly_after_send_fields():
                    # These cannot be changed when the item is no longer a draft
                    continue
                if f in self.required_fields() and getattr(self, f) is None:
                    continue
                update_fields.append(f)
            # bulk_update() returns a tuple
            res = self.account.bulk_update(
                items=[(self, update_fields)], message_disposition=message_disposition,
                conflict_resolution=conflict_resolution,
                send_meeting_invitations_or_cancellations=send_meeting_invitations)
            if message_disposition == SEND_AND_SAVE_COPY:
                assert len(res) == 0
                return None
            else:
                if not res:
                    raise ValueError('Item disappeared')
                assert len(res) == 1, res
                return res[0]
        else:
            # bulk_create() returns an Item because we want to return item_id on both main item *and* attachments
            res = self.account.bulk_create(
                items=[self], folder=self.folder, message_disposition=message_disposition,
                send_meeting_invitations=send_meeting_invitations)
            if message_disposition in (SEND_ONLY, SEND_AND_SAVE_COPY):
                assert len(res) == 0
                return None
            else:
                assert len(res) == 1, res
                return res[0]

    def refresh(self):
        # Updates the item based on fresh data from EWS
        if not self.account:
            raise ValueError('Item must have an account')
        res = list(self.account.fetch(ids=[self]))
        if not res:
            raise ValueError('Item disappeared')
        assert len(res) == 1, res
        fresh_item = res[0]
        for k in self.__slots__:
            setattr(self, k, getattr(fresh_item, k))

    def move(self, to_folder):
        if not self.account:
            raise ValueError('Item must have an account')
        res = self.account.bulk_move(ids=[self], to_folder=to_folder)
        if not res:
            raise ValueError('Item disappeared')
        assert len(res) == 1, res
        self.item_id, self.changekey = res[0]
        self.folder = to_folder

    def move_to_trash(self, send_meeting_cancellations=SEND_TO_NONE,
                      affected_task_occurrences=SPECIFIED_OCCURRENCE_ONLY, suppress_read_receipts=True):
        # Delete and move to the trash folder.
        self._delete(delete_type=MOVE_TO_DELETED_ITEMS, send_meeting_cancellations=send_meeting_cancellations,
                     affected_task_occurrences=affected_task_occurrences, suppress_read_receipts=suppress_read_receipts)
        self.item_id, self.changekey = None, None
        self.folder = self.folder.account.trash

    def soft_delete(self, send_meeting_cancellations=SEND_TO_NONE, affected_task_occurrences=SPECIFIED_OCCURRENCE_ONLY,
                    suppress_read_receipts=True):
        # Delete and move to the dumpster, if it is enabled.
        self._delete(delete_type=SOFT_DELETE, send_meeting_cancellations=send_meeting_cancellations,
                     affected_task_occurrences=affected_task_occurrences, suppress_read_receipts=suppress_read_receipts)
        self.item_id, self.changekey = None, None
        self.folder = self.folder.account.recoverable_deleted_items

    def delete(self, send_meeting_cancellations=SEND_TO_NONE, affected_task_occurrences=SPECIFIED_OCCURRENCE_ONLY,
               suppress_read_receipts=True):
        # Remove the item permanently. No copies are stored anywhere.
        self._delete(delete_type=HARD_DELETE, send_meeting_cancellations=send_meeting_cancellations,
                     affected_task_occurrences=affected_task_occurrences, suppress_read_receipts=suppress_read_receipts)
        self.item_id, self.changekey, self.folder = None, None, None

    def _delete(self, delete_type, send_meeting_cancellations, affected_task_occurrences, suppress_read_receipts):
        if not self.account:
            raise ValueError('Item must have an account')
        res = self.account.bulk_delete(
            ids=[self], delete_type=delete_type, send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences, suppress_read_receipts=suppress_read_receipts)
        if not res:
            raise ValueError('Item disappeared')
        assert len(res) == 1, res
        if not res[0][0]:
            raise ValueError('Error deleting message: %s', res[0][1])

    def attach(self, attachments):
        """Add an attachment, or a list of attachments, to this item. If the item has already been saved, the
        attachments will be created on the server immediately. If the item has not yet been saved, the attachments will
        be created on the server the item is saved.

        Adding attachments to an existing item will update the changekey of the item.
        """
        if isinstance(attachments, Attachment):
            attachments = [attachments]
        for a in attachments:
            assert isinstance(a, Attachment)
            if not a.parent_item:
                a.parent_item = self
            if self.item_id and not a.attachment_id:
                # Already saved object. Attach the attachment server-side now
                a.attach()
            if a not in self.attachments:
                self.attachments.append(a)

    def detach(self, attachments):
        """Remove an attachment, or a list of attachments, from this item. If the item has already been saved, the
        attachments will be deleted on the server immediately. If the item has not yet been saved, the attachments will
        simply not be created on the server the item is saved.

        Removing attachments from an existing item will update the changekey of the item.
        """
        if isinstance(attachments, Attachment):
            attachments = [attachments]
        for a in attachments:
            assert isinstance(a, Attachment)
            assert a.parent_item is self
            if self.item_id:
                # Item is already created. Detach  the attachment server-side now
                a.detach()
            if a in self.attachments:
                self.attachments.remove(a)

    @classmethod
    def fieldnames(cls):
        # Return non-ID field names
        return tuple(f for f in cls.ITEM_FIELDS if f not in ('item_id', 'changekey'))

    @classmethod
    def ordered_fieldnames(cls):
        res = []
        for f in cls.ORDERED_FIELDS:
            if isinstance(f, list):
                # This is the EXTENDED_PROPERTIES element which can be modified by register(). Expand the list
                res.extend(f)
            else:
                res.append(f)
        return res

    @classmethod
    def uri_for_field(cls, fieldname):
        return cls.ITEM_FIELDS[fieldname][0]

    @classmethod
    def fielduri_for_field(cls, fieldname):
        # See all valid FieldURI values at https://msdn.microsoft.com/en-us/library/office/aa494315(v=exchg.150).aspx
        try:
            uri = cls.uri_for_field(fieldname)
        except KeyError:
            raise ValueError("No fielduri defined for fieldname '%s'" % fieldname)
        if isinstance(uri, string_types):
            return '%s:%s' % (cls.FIELDURI_PREFIX, uri)
        return uri

    @classmethod
    def elem_for_field(cls, fieldname):
        assert isinstance(fieldname, string_types)
        try:
            uri = cls.uri_for_field(fieldname)
        except KeyError:
            raise ValueError("No fielduri defined for fieldname '%s'" % fieldname)
        assert isinstance(uri, string_types)
        return create_element('t:%s' % uri)

    @classmethod
    def response_xml_elem_for_field(cls, fieldname):
        try:
            uri = cls.uri_for_field(fieldname)
        except KeyError:
            raise ValueError("No fielduri defined for fieldname '%s'" % fieldname)
        if isinstance(uri, string_types):
            return '{%s}%s' % (TNS, uri)
        if issubclass(uri, IndexedField):
            return '{%s}%s' % (TNS, uri.PARENT_ELEMENT_NAME)
        assert False, 'Unknown uri for fieldname %s: %s' % (fieldname, uri)

    @classmethod
    def required_fields(cls):
        return Item.REQUIRED_FIELDS

    @classmethod
    def readonly_fields(cls):
        return Item.READONLY_FIELDS

    @classmethod
    def readonly_after_send_fields(cls):
        return Item.READONLY_AFTER_SEND_FIELDS

    @classmethod
    def complex_fields(cls):
        # Return fields that are complex EWS types. Quoting the EWS FindItem docs:
        #
        #   The FindItem operation returns only the first 512 bytes of any streamable property. For Unicode, it returns
        #   the first 255 characters by using a null-terminated Unicode string. It does not return any of the message
        #   body formats or the recipient lists.
        #
        complex_types = (Body, HTMLBody, Attachment, [Attachment])
        return tuple(f for f in cls.fieldnames() if cls.type_for_field(f) in complex_types)

    @classmethod
    def type_for_field(cls, fieldname):
        try:
            return cls.ITEM_FIELDS[fieldname][1]
        except KeyError:
            raise ValueError("No type defined for fieldname '%s'" % fieldname)

    @classmethod
    def additional_property_elems(cls, fieldname):
        elems = []
        field_uri = cls.fielduri_for_field(fieldname)
        if isinstance(field_uri, string_types):
            elems.append(create_element('t:FieldURI', FieldURI=field_uri))
        elif issubclass(field_uri, IndexedField):
            for l in field_uri.LABELS:
                field_uri_xml = field_uri.field_uri_xml(label=l)
                if hasattr(field_uri_xml, '__iter__'):
                    elems.extend(field_uri_xml)
                else:
                    elems.append(field_uri_xml)
        else:
            assert issubclass(field_uri, ExtendedProperty)
            elems.append(field_uri.field_uri_xml())
        return elems

    @classmethod
    def id_from_xml(cls, elem):
        id_elem = elem.find(ItemId.response_tag())
        if id_elem is None:
            return None, None
        return id_elem.get(ItemId.ID_ATTR), id_elem.get(ItemId.CHANGEKEY_ATTR)

    @classmethod
    def from_xml(cls, elem, account=None, folder=None):
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        item_id, changekey = cls.id_from_xml(elem)
        kwargs = {}
        extended_properties = elem.findall(ExtendedProperty.response_tag())
        for fieldname in cls.fieldnames():
            field_type = cls.type_for_field(fieldname)
            if field_type in (EWSDateTime, bool, int, Decimal, string_type, Choice, Email, AnyURI, Body, HTMLBody, MimeContent):
                field_elem = elem.find(cls.response_xml_elem_for_field(fieldname))
                val = None if field_elem is None else field_elem.text or None
                if val is not None:
                    try:
                        val = xml_text_to_value(value=val, field_type=field_type)
                    except ValueError:
                        pass
                    except KeyError:
                        assert False, 'Field %s type %s not supported' % (fieldname, field_type)
                    if fieldname == 'body':
                        body_type = field_elem.get('BodyType')
                        try:
                            val = {
                                Body.body_type: lambda v: Body(v),
                                HTMLBody.body_type: lambda v: HTMLBody(v),
                            }[body_type](val)
                        except KeyError:
                            assert False, "Unknown BodyType '%s'" % body_type
                    kwargs[fieldname] = val
            elif isinstance(field_type, list):
                list_type = field_type[0]
                if list_type == string_type:
                    iter_elem = elem.find(cls.response_xml_elem_for_field(fieldname))
                    if iter_elem is not None:
                        kwargs[fieldname] = get_xml_attrs(iter_elem, '{%s}String' % TNS)
                elif list_type == Attachment:
                    # Look for both FileAttachment and ItemAttachment
                    iter_elem = elem.find(cls.response_xml_elem_for_field(fieldname))
                    if iter_elem is not None:
                        attachments = []
                        for att_type in (FileAttachment, ItemAttachment):
                            attachments.extend(
                                [att_type.from_xml(e) for e in iter_elem.findall(att_type.response_tag())]
                            )
                        kwargs[fieldname] = attachments
                elif issubclass(list_type, EWSElement):
                    iter_elem = elem.find(cls.response_xml_elem_for_field(fieldname))
                    if iter_elem is not None:
                        kwargs[fieldname] = [list_type.from_xml(e) for e in iter_elem.findall(list_type.response_tag())]
                else:
                    assert False, 'Field %s type %s not supported' % (fieldname, field_type)
            elif issubclass(field_type, ExtendedProperty):
                kwargs[fieldname] = field_type.get_value(extended_properties)
            elif issubclass(field_type, EWSElement):
                sub_elem = elem.find(cls.response_xml_elem_for_field(fieldname))
                if sub_elem is not None:
                    if field_type == Mailbox:
                        # We want the nested Mailbox, not the wrapper element
                        kwargs[fieldname] = field_type.from_xml(sub_elem.find(Mailbox.response_tag()))
                    else:
                        kwargs[fieldname] = field_type.from_xml(sub_elem)
            else:
                assert False, 'Field %s type %s not supported' % (fieldname, field_type)
        elem.clear()
        return cls(item_id=item_id, changekey=changekey, account=account, folder=folder, **kwargs)

    def __eq__(self, other):
        if isinstance(other, tuple):
            item_id, changekey = other
            return self.item_id == item_id and self.changekey == changekey
        return self.item_id == other.item_id and self.changekey == other.changekey

    def __hash__(self):
        # If we have an item_id and changekey, use that as key. Else return a hash of all attributes
        if self.item_id:
            return hash((self.item_id, self.changekey))
        return hash(tuple(
            tuple(attr) if isinstance(attr, list) else attr for attr in (getattr(self, f) for f in self.__slots__)
        ))

    def __str__(self):
        return '\n'.join('%s: %s' % (f, getattr(self, f))
                         for f in ('item_id', 'changekey') + tuple(self.ordered_fieldnames()))

    def __repr__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%s' % (k, repr(getattr(self, k))) for k in self.fieldnames()
        )


class ItemMixIn(Item):
    def to_xml(self, version):
        self.clean()
        # WARNING: The order of addition of XML elements is VERY important. Exchange expects XML elements in a
        # specific, non-documented order and will fail with meaningless errors if the order is wrong.
        i = create_element(self.request_tag())
        for f in self.ordered_fieldnames():
            assert f not in self.readonly_fields(), (f, self.readonly_fields())
            field_uri = self.fielduri_for_field(f)
            v = getattr(self, f)
            if v is None:
                continue
            if isinstance(v, (tuple, list)) and not v:
                continue

            # Allow setting attendee and mailbox types as plain strings
            field_type = self.type_for_field(f)
            if field_type == Mailbox and isinstance(v, string_types):
                v = Mailbox(email_address=v)
            elif field_type == [Mailbox] and v is not None:
                v = [Mailbox(email_address=s) if isinstance(s, string_types) else s for s in v]
            elif field_type == Attendee and isinstance(v, string_types):
                v = Attendee(mailbox=Mailbox(email_address=v), response_type='Accept')
            elif field_type == [Attendee] and v is not None:
                v = [Attendee(mailbox=Mailbox(email_address=s), response_type='Accept')
                     if isinstance(s, string_types) else s for s in v]

            if isinstance(field_uri, string_types):
                field_elem = self.elem_for_field(f)
                if f == 'body':
                    body_type = HTMLBody.body_type if isinstance(v, HTMLBody) else Body.body_type
                    field_elem.set('BodyType', body_type)
                i.append(set_xml_value(field_elem, v, version))
            elif issubclass(field_uri, IndexedField):
                i.append(set_xml_value(create_element('t:%s' % field_uri.PARENT_ELEMENT_NAME), v, version))
            elif issubclass(field_uri, ExtendedProperty):
                set_xml_value(i, field_uri(getattr(self, f)), version)
            else:
                assert False, 'Unknown field_uri type: %s' % field_uri
        return i

    @classmethod
    def register(cls, attr_name, attr_cls):
        """
        Register a custom extended property in this item class so they can be accessed just like any other attribute
        """
        if attr_name in cls.fieldnames():
            raise AttributeError("%s' is already registered" % attr_name)
        if not issubclass(attr_cls, ExtendedProperty):
            raise ValueError("'%s' must be a subclass of ExtendedProperty" % attr_cls)
        assert attr_name not in cls.EXTENDED_PROPERTIES
        cls.ITEM_FIELDS[attr_name] = (attr_cls, attr_cls)
        cls.EXTENDED_PROPERTIES.append(attr_name)

    @classmethod
    def deregister(cls, attr_name):
        """
        De-register an extended property that has been registered with register()
        """
        if attr_name not in cls.fieldnames():
            raise AttributeError("%s' is not registered" % attr_name)
        attr_cls = cls.type_for_field(attr_name)
        if not issubclass(attr_cls, ExtendedProperty):
            raise AttributeError("'%s' is not registered as an ExtendedProperty")
        assert attr_name in cls.EXTENDED_PROPERTIES
        cls.EXTENDED_PROPERTIES.remove(attr_name)
        del cls.ITEM_FIELDS[attr_name]

    @classmethod
    def fieldnames(cls):
        return tuple(cls.ITEM_FIELDS) + Item.fieldnames()

    @classmethod
    def fielduri_for_field(cls, fieldname):
        try:
            field_uri = cls.ITEM_FIELDS[fieldname][0]
        except KeyError:
            return Item.fielduri_for_field(fieldname)
        if isinstance(field_uri, string_types):
            return '%s:%s' % (cls.FIELDURI_PREFIX, field_uri)
        return field_uri

    @classmethod
    def elem_for_field(cls, fieldname):
        try:
            uri = cls.uri_for_field(fieldname)
        except KeyError:
            return Item.elem_for_field(fieldname)
        assert isinstance(uri, string_types)
        return create_element('t:%s' % uri)

    @classmethod
    def response_xml_elem_for_field(cls, fieldname):
        try:
            uri = cls.uri_for_field(fieldname)
        except KeyError:
            return Item.response_xml_elem_for_field(fieldname)
        if isinstance(uri, string_types):
            return '{%s}%s' % (TNS, uri)
        if issubclass(uri, IndexedField):
            return '{%s}%s' % (TNS, uri.PARENT_ELEMENT_NAME)
        assert False, 'Unknown uri for fieldname %s: %s' % (fieldname, uri)

    @classmethod
    def required_fields(cls):
        return cls.REQUIRED_FIELDS | Item.required_fields()

    @classmethod
    def readonly_fields(cls):
        return cls.READONLY_FIELDS | Item.readonly_fields()

    @classmethod
    def readonly_after_send_fields(cls):
        return cls.READONLY_AFTER_SEND_FIELDS | Item.readonly_after_send_fields()

    @classmethod
    def choices_for_field(cls, fieldname):
        try:
            return cls.CHOICES[fieldname]
        except KeyError:
            return Item.CHOICES[fieldname]

    @classmethod
    def type_for_field(cls, fieldname):
        try:
            return cls.ITEM_FIELDS[fieldname][1]
        except KeyError:
            return Item.type_for_field(fieldname)


@python_2_unicode_compatible
class CalendarItem(ItemMixIn):
    """
    Models a calendar item. Not all attributes are supported. See full list at
    https://msdn.microsoft.com/en-us/library/office/aa564765(v=exchg.150).aspx
    """
    ELEMENT_NAME = 'CalendarItem'
    LOCATION_MAXLENGTH = 255
    FIELDURI_PREFIX = 'calendar'
    CHOICES = {
        # TODO: The 'WorkingElsewhere' status was added in Exchange2015 but we don't support versioned choices yet
        'legacy_free_busy_status': {'Free', 'Tentative', 'Busy', 'OOF', 'NoData'},
    }
    ITEM_FIELDS = {
        'start': ('Start', EWSDateTime),
        'end': ('End', EWSDateTime),
        'location': ('Location', string_type),
        'organizer': ('Organizer', Mailbox),
        'legacy_free_busy_status': ('LegacyFreeBusyStatus', Choice),
        'required_attendees': ('RequiredAttendees', [Attendee]),
        'optional_attendees': ('OptionalAttendees', [Attendee]),
        'resources': ('Resources', [Attendee]),
        'is_all_day': ('IsAllDayEvent', bool),
    }
    EXTENDED_PROPERTIES = ['extern_id']
    ORDERED_FIELDS = (
        'subject', 'sensitivity', 'body', 'attachments', 'categories', 'importance', 'reminder_is_set',
        EXTENDED_PROPERTIES, 'start', 'end', 'is_all_day', 'legacy_free_busy_status', 'location', 'required_attendees',
        'optional_attendees', 'resources'
    )
    REQUIRED_FIELDS = {'subject', 'start', 'end', 'legacy_free_busy_status', 'is_all_day'}
    READONLY_FIELDS = {'organizer'}

    __slots__ = tuple(ITEM_FIELDS) + tuple(Item.ITEM_FIELDS)

    def __init__(self, **kwargs):
        for k in self.ITEM_FIELDS:
            field_type = self.ITEM_FIELDS[k][1]
            default = 'Busy' if k == 'legacy_free_busy_status' \
                else False if (k in self.required_fields() and field_type == bool) else None
            v = kwargs.pop(k, default)
            if k in ('start', 'end') and v and not getattr(v, 'tzinfo'):
                raise ValueError("'%s' must be timezone aware" % k)
            if field_type == Choice:
                assert v is None or v in self.choices_for_field(k), (v, self.choices_for_field(k))
            setattr(self, k, v)
        super(CalendarItem, self).__init__(**kwargs)

    def clean(self):
        super(CalendarItem, self).clean()
        if self.location and len(self.location) > self.LOCATION_MAXLENGTH:
            raise ValueError("'location' length exceeds %s" % self.LOCATION_MAXLENGTH)

    def to_xml(self, version):
        self.clean()
        # WARNING: The order of addition of XML elements is VERY important. Exchange expects XML elements in a
        # specific, non-documented order and will fail with meaningless errors if the order is wrong.
        i = super(CalendarItem, self).to_xml(version=version)
        if version.build < EXCHANGE_2010:
            i.append(create_element('t:MeetingTimeZone', TimeZoneName=self.start.tzinfo.ms_id))
        else:
            i.append(create_element('t:StartTimeZone', Id=self.start.tzinfo.ms_id, Name=self.start.tzinfo.ms_name))
            i.append(create_element('t:EndTimeZone', Id=self.end.tzinfo.ms_id, Name=self.end.tzinfo.ms_name))
        return i


class Message(ItemMixIn):
    # Supported attrs: see https://msdn.microsoft.com/en-us/library/office/aa494306(v=exchg.150).aspx
    ELEMENT_NAME = 'Message'
    FIELDURI_PREFIX = 'message'
    # TODO: This list is incomplete
    ITEM_FIELDS = {
        'is_read': ('IsRead', bool),
        'is_delivery_receipt_requested': ('IsDeliveryReceiptRequested', bool),
        'is_read_receipt_requested': ('IsReadReceiptRequested', bool),
        'is_response_requested': ('IsResponseRequested', bool),
        'author': ('From', Mailbox),  # We can't use fieldname 'from' since it's a Python keyword
        'sender': ('Sender', Mailbox),
        'reply_to': ('ReplyTo', [Mailbox]),
        'to_recipients': ('ToRecipients', [Mailbox]),
        'cc_recipients': ('CcRecipients', [Mailbox]),
        'bcc_recipients': ('BccRecipients', [Mailbox]),
        'message_id': ('InternetMessageId', string_type),
    }
    EXTENDED_PROPERTIES = ['extern_id']
    ORDERED_FIELDS = (
        'subject', 'sensitivity', 'body', 'attachments', 'categories', 'importance', 'reminder_is_set',
        EXTENDED_PROPERTIES,
        'to_recipients', 'cc_recipients', 'bcc_recipients',
        'is_read_receipt_requested', 'is_delivery_receipt_requested',
        'author', 'is_read', 'is_response_requested', 'reply_to',
    )
    REQUIRED_FIELDS = {'subject', 'is_read', 'is_delivery_receipt_requested', 'is_read_receipt_requested',
                       'is_response_requested'}
    READONLY_FIELDS = {'sender', 'message_id'}
    READONLY_AFTER_SEND_FIELDS = {'is_read_receipt_requested', 'is_delivery_receipt_requested', 'author', 'sender',
                                  'reply_to', 'to_recipients', 'cc_recipients', 'bcc_recipients', 'message_id'}

    __slots__ = tuple(ITEM_FIELDS) + tuple(Item.ITEM_FIELDS)

    def __init__(self, **kwargs):
        for k in self.ITEM_FIELDS:
            field_type = self.ITEM_FIELDS[k][1]
            default = False if (k in self.required_fields() and field_type == bool) else None
            v = kwargs.pop(k, default)
            if field_type == Choice:
                assert v is None or v in self.choices_for_field(k), (v, self.choices_for_field(k))
            setattr(self, k, v)
        super(Message, self).__init__(**kwargs)

    def send(self, save_copy=True, copy_to_folder=None, conflict_resolution=AUTO_RESOLVE,
             send_meeting_invitations=SEND_TO_NONE):
        # Only sends a message. The message can either be an existing draft stored in EWS or a new message that does
        # not yet exist in EWS.
        if not self.account:
            raise ValueError('Item must have an account')
        if self.item_id:
            res = self.account.bulk_send(ids=[self], save_copy=save_copy, copy_to_folder=copy_to_folder)
            if not res:
                raise ValueError('Item disappeared')
            assert len(res) == 1, res
            if not res[0][0]:
                raise ValueError('Error sending message: %s', res[0][1])
            # The item will be deleted from the original folder
            self.item_id, self.changekey = None, None
            self.folder = copy_to_folder
        else:
            # New message
            if copy_to_folder:
                if not save_copy:
                    raise AttributeError("'save_copy' must be True when 'copy_to_folder' is set")
                # This would better be done via send_and_save() but lets just support it here
                self.folder = copy_to_folder
                return self.send_and_save(conflict_resolution=conflict_resolution,
                                          send_meeting_invitations=send_meeting_invitations)
            assert copy_to_folder is None
            res = self._save(message_disposition=SEND_ONLY, conflict_resolution=conflict_resolution,
                             send_meeting_invitations=send_meeting_invitations)
            assert res is None

    def send_and_save(self, conflict_resolution=AUTO_RESOLVE, send_meeting_invitations=SEND_TO_NONE):
        # Sends Message and saves a copy in the parent folder. Does not return an ItemId.
        res = self._save(message_disposition=SEND_AND_SAVE_COPY, conflict_resolution=conflict_resolution,
                         send_meeting_invitations=send_meeting_invitations)
        assert res is None


class Task(ItemMixIn):
    # Supported attrs: see https://msdn.microsoft.com/en-us/library/office/aa563930(v=exchg.150).aspx
    ELEMENT_NAME = 'Task'
    FIELDURI_PREFIX = 'task'
    NOT_STARTED = 'NotStarted'
    COMPLETED = 'Completed'
    CHOICES = {
        'status': {NOT_STARTED, 'InProgress', COMPLETED, 'WaitingOnOthers', 'Deferred'},
        'delegation_state': {'NoMatch', 'OwnNew', 'Owned', 'Accepted', 'Declined', 'Max'},
    }
    # TODO: This list is incomplete
    ITEM_FIELDS = {
        'actual_work': ('ActualWork', int),
        'assigned_time': ('AssignedTime', EWSDateTime),
        'billing_information': ('BillingInformation', string_type),
        'change_count': ('ChangeCount', int),
        'companies': ('Companies', [string_type]),
        'contacts': ('Contacts', [string_type]),
        'complete_date': ('CompleteDate', EWSDateTime),
        'is_complete': ('IsComplete', bool),
        'due_date': ('DueDate', EWSDateTime),
        'delegator': ('Delegator', string_type),
        'delegation_state': ('DelegationState', Choice),
        'is_recurring': ('IsRecurring', bool),
        'is_team_task': ('IsTeamTask', bool),
        'mileage': ('Mileage', string_type),
        'owner': ('Owner', string_type),
        'percent_complete': ('PercentComplete', Decimal),
        'start_date': ('StartDate', EWSDateTime),
        'status': ('Status', Choice),
        'status_description': ('StatusDescription', string_type),
        'total_work': ('TotalWork', int),
    }
    REQUIRED_FIELDS = {'subject', 'status'}
    EXTENDED_PROPERTIES = ['extern_id']
    ORDERED_FIELDS = (
        'subject', 'sensitivity', 'body', 'attachments', 'categories', 'importance', 'reminder_is_set',
        EXTENDED_PROPERTIES,
        'actual_work',  # 'assigned_time',
        'billing_information',  # 'change_count',
        'companies',  # 'complete_date',
        'contacts',  # 'delegation_state', 'delegator',
        'due_date',  # 'is_complete', 'is_team_task',
        'mileage',  # 'owner',
        'percent_complete', 'start_date', 'status',  # 'status_description',
        'total_work',
    )
    # 'complete_date' can be set, but is ignored by the server, which sets it to now()
    READONLY_FIELDS = {'is_recurring', 'is_complete', 'is_team_task', 'assigned_time', 'change_count',
                       'delegation_state', 'delegator', 'owner', 'status_description', 'complete_date'}

    __slots__ = tuple(ITEM_FIELDS) + tuple(Item.ITEM_FIELDS)

    def __init__(self, **kwargs):
        for k in self.ITEM_FIELDS:
            field_type = self.ITEM_FIELDS[k][1]
            default = False if (k in self.required_fields() and field_type == bool) else None
            v = kwargs.pop(k, default)
            if field_type == Choice:
                assert v is None or v in self.choices_for_field(k), (v, self.choices_for_field(k))
            setattr(self, k, v)
        if self.due_date and self.start_date and self.due_date < self.start_date:
            log.warning("'due_date' must be greater than 'start_date' (%s vs %s). Resetting 'due_date'",
                        self.due_date, self.start_date)
            self.due_date = self.start_date
        if self.complete_date:
            if self.status != self.COMPLETED:
                log.warning("'status' must be '%s' when 'complete_date' is set (%s). Resetting",
                            self.COMPLETED, self.status)
                self.status = self.COMPLETED
            now = UTC_NOW()
            if (self.complete_date - now).total_seconds() > 120:
                # 'complete_date' can be set automatically by the server. Allow some grace between local and server time
                log.warning("'complete_date' must be in the past (%s vs %s). Resetting", self.complete_date, now)
                self.complete_date = now
            if self.start_date and self.complete_date < self.start_date:
                log.warning("'complete_date' must be greater than 'start_date' (%s vs %s). Resetting",
                            self.complete_date, self.start_date)
                self.complete_date = self.start_date
        if self.percent_complete is not None:
            assert isinstance(self.percent_complete, Decimal)
            assert Decimal(0) <= self.percent_complete <= Decimal(100), self.percent_complete
            if self.status == self.COMPLETED and self.percent_complete != Decimal(100):
                # percent_complete must be 100% if task is complete
                log.warning("'percent_complete' must be 100 when 'status' is '%s' (%s). Resetting",
                            self.COMPLETED, self.percent_complete)
                self.percent_complete = Decimal(100)
            elif self.status == self.NOT_STARTED and self.percent_complete != Decimal(0):
                # percent_complete must be 0% if task is not started
                log.warning("'percent_complete' must be 0 when 'status' is '%s' (%s). Resetting",
                            self.NOT_STARTED, self.percent_complete)
                self.percent_complete = Decimal(0)
        super(Task, self).__init__(**kwargs)


class Contact(ItemMixIn):
    # Supported attrs: see https://msdn.microsoft.com/en-us/library/office/aa581315(v=exchg.150).aspx
    ELEMENT_NAME = 'Contact'
    FIELDURI_PREFIX = 'contacts'
    CHOICES = {
        'file_as_mapping': {
            'None', 'LastCommaFirst', 'FirstSpaceLast', 'Company', 'LastCommaFirstCompany', 'CompanyLastFirst',
            'LastFirst', 'LastFirstCompany', 'CompanyLastCommaFirst', 'LastFirstSuffix', 'LastSpaceFirstCompany',
            'CompanyLastSpaceFirst', 'LastSpaceFirst', 'DisplayName', 'FirstName', 'LastFirstMiddleSuffix', 'LastName',
            'Empty',
        }
    }
    # TODO: This list is incomplete
    ITEM_FIELDS = {
        'file_as': ('FileAs', string_type),
        'file_as_mapping': ('FileAsMapping', Choice),
        'display_name': ('DisplayName', string_type),
        'given_name': ('GivenName', string_type),
        'initials': ('Initials', string_type),
        'middle_name': ('MiddleName', string_type),
        'nickname': ('Nickname', string_type),
        'company_name': ('CompanyName', string_type),
        'email_addresses': (EmailAddress, [EmailAddress]),
        'physical_addresses': (PhysicalAddress, [PhysicalAddress]),
        'phone_numbers': (PhoneNumber, [PhoneNumber]),
        'assistant_name': ('AssistantName', string_type),
        'birthday': ('Birthday', EWSDateTime),
        'business_homepage': ('BusinessHomePage', AnyURI),
        'companies': ('Companies', [string_type]),
        'department': ('Department', string_type),
        'generation': ('Generation', string_type),
        # 'im_addresses': ('ImAddresses', [ImAddress]),
        'job_title': ('JobTitle', string_type),
        'manager': ('Manager', string_type),
        'mileage': ('Mileage', string_type),
        'office': ('OfficeLocation', string_type),
        'profession': ('Profession', string_type),
        'surname': ('Surname', string_type),
        # 'email_alias': ('Alias', Email),
        # 'notes': ('Notes', string_type),  # Only available from Exchange 2010 SP2
    }
    REQUIRED_FIELDS = {'display_name'}
    EXTENDED_PROPERTIES = ['extern_id']
    ORDERED_FIELDS = (
        'subject', 'sensitivity', 'body', 'attachments', 'categories', 'importance', 'reminder_is_set',
        EXTENDED_PROPERTIES,
        'file_as', 'file_as_mapping',
        'display_name', 'given_name', 'initials', 'middle_name', 'nickname', 'company_name',
        'email_addresses', 'physical_addresses',
        'phone_numbers',
        'assistant_name', 'birthday', 'business_homepage', 'companies', 'department',
        'generation', 'job_title', 'manager', 'mileage', 'office', 'profession', 'surname',  # 'email_alias', 'notes',
    )

    __slots__ = tuple(ITEM_FIELDS) + tuple(Item.ITEM_FIELDS)

    def __init__(self, **kwargs):
        for k in self.ITEM_FIELDS:
            field_type = self.ITEM_FIELDS[k][1]
            default = False if (k in self.required_fields() and field_type == bool) else None
            v = kwargs.pop(k, default)
            if field_type == Choice:
                assert v is None or v in self.choices_for_field(k), (v, self.choices_for_field(k))
            setattr(self, k, v)
        super(Contact, self).__init__(**kwargs)


class MeetingRequest(ItemMixIn):
    # Supported attrs: https://msdn.microsoft.com/en-us/library/office/aa565229(v=exchg.150).aspx
    # TODO: Untested and unfinished. Only the bare minimum supported to allow reading a folder that contains meeting
    # requests.
    ELEMENT_NAME = 'MeetingRequest'
    FIELDURI_PREFIX = 'meetingRequest'
    ITEM_FIELDS = {
    }
    EXTENDED_PROPERTIES = []
    ORDERED_FIELDS = (
        'subject', EXTENDED_PROPERTIES, 'author', 'is_read', 'start', 'end'
    )
    REQUIRED_FIELDS = {'subject'}
    READONLY_FIELDS = {'author'}

    __slots__ = tuple(ITEM_FIELDS) + tuple(Item.ITEM_FIELDS)

    def __init__(self, **kwargs):
        for k in self.ITEM_FIELDS:
            field_type = self.ITEM_FIELDS[k][1]
            default = False if (k in self.required_fields() and field_type == bool) else None
            v = kwargs.pop(k, default)
            setattr(self, k, v)
        super(MeetingRequest, self).__init__(**kwargs)


class MeetingResponse(ItemMixIn):
    # Supported attrs: https://msdn.microsoft.com/en-us/library/office/aa564337(v=exchg.150).aspx
    # TODO: Untested and unfinished. Only the bare minimum supported to allow reading a folder that contains meeting
    # responses.
    ELEMENT_NAME = 'MeetingResponse'
    FIELDURI_PREFIX = 'meetingRequest'
    ITEM_FIELDS = {
    }
    EXTENDED_PROPERTIES = []
    ORDERED_FIELDS = (
        'subject', EXTENDED_PROPERTIES, 'author', 'is_read', 'start', 'end'
    )
    REQUIRED_FIELDS = {'subject'}
    READONLY_FIELDS = {'author'}

    __slots__ = tuple(ITEM_FIELDS) + tuple(Item.ITEM_FIELDS)

    def __init__(self, **kwargs):
        for k in self.ITEM_FIELDS:
            field_type = self.ITEM_FIELDS[k][1]
            default = False if (k in self.required_fields() and field_type == bool) else None
            v = kwargs.pop(k, default)
            setattr(self, k, v)
        super(MeetingResponse, self).__init__(**kwargs)


class MeetingCancellation(ItemMixIn):
    # Supported attrs: https://msdn.microsoft.com/en-us/library/office/aa564685(v=exchg.150).aspx
    # TODO: Untested and unfinished. Only the bare minimum supported to allow reading a folder that contains meeting
    # cancellations.
    ELEMENT_NAME = 'MeetingCancellation'
    FIELDURI_PREFIX = 'meetingRequest'
    ITEM_FIELDS = {
    }
    EXTENDED_PROPERTIES = []
    ORDERED_FIELDS = (
        'subject', EXTENDED_PROPERTIES, 'author', 'is_read', 'start', 'end'
    )
    REQUIRED_FIELDS = {'subject'}
    READONLY_FIELDS = {'author'}

    __slots__ = tuple(ITEM_FIELDS) + tuple(Item.ITEM_FIELDS)

    def __init__(self, **kwargs):
        for k in self.ITEM_FIELDS:
            field_type = self.ITEM_FIELDS[k][1]
            default = False if (k in self.required_fields() and field_type == bool) else None
            v = kwargs.pop(k, default)
            setattr(self, k, v)
        super(MeetingCancellation, self).__init__(**kwargs)


class FileAttachment(Attachment):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa580492(v=exchg.150).aspx
    """
    # TODO: This class is most likely inefficient for large data. Investigate methods to reduce copying
    ELEMENT_NAME = 'FileAttachment'
    ATTACHMENT_FIELDS = {
        'content': ('Content', bytes),
        'is_contact_photo': ('IsContactPhoto', bool),
    }
    ATTACHMENT_FIELDS.update(Attachment.ATTACHMENT_FIELDS)
    ORDERED_FIELDS = (
        'attachment_id', 'name', 'content_type', 'content_id', 'content_location', 'size', 'last_modified_time',
        'is_inline', 'is_contact_photo', 'content',
    )

    __slots__ = ('parent_item',) + tuple(ORDERED_FIELDS[:-1]) + ('_content',)

    def __init__(self, *args, **kwargs):
        self._content = kwargs.pop('content', None)
        self.is_contact_photo = kwargs.pop('is_contact_photo', None)
        super(FileAttachment, self).__init__(*args, **kwargs)
        for field_name, (_, field_type) in self.ATTACHMENT_FIELDS.items():
            if field_name == 'content':
                field_name = '_content'
            val = getattr(self, field_name)
            if val is not None and not isinstance(val, field_type):
                raise ValueError("Field '%s' must be of type '%s'" % (field_name, field_type))

    @property
    def content(self):
        if self.attachment_id is None:
            return self._content
        if self._content is not None:
            return self._content
        # We have an ID to the data but still haven't called GetAttachment to get the actual data. Do that now.
        if not self.parent_item.account:
            raise ValueError('%s must have an account' % self.__class__.__name__)
        elems = list(GetAttachment(account=self.parent_item.account).call(
            items=[self.attachment_id], include_mime_content=False))
        assert len(elems) == 1
        elem = elems[0]
        assert not isinstance(elem, tuple), elem
        # Don't use get_xml_attr() here because we want to handle empty file content as '', not None
        val = elem.find('{%s}%s' % (TNS, self.ATTACHMENT_FIELDS['content'][0]))
        if val is None:
            self._content = None
        else:
            self._content = base64.b64decode(val.text)
            elem.clear()
        return self._content

    @content.setter
    def content(self, value):
        assert isinstance(value, bytes)
        self._content = value


class ItemAttachment(Attachment):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa562997(v=exchg.150).aspx
    """
    ELEMENT_NAME = 'ItemAttachment'
    ATTACHMENT_FIELDS = {
        'item': (Item, Item),
    }
    ATTACHMENT_FIELDS.update(Attachment.ATTACHMENT_FIELDS)
    ORDERED_FIELDS = (
        'attachment_id', 'name', 'content_type', 'content_id', 'content_location', 'size', 'last_modified_time',
        'is_inline', 'item',
    )

    __slots__ = ('parent_item',) + tuple(ORDERED_FIELDS[:-1]) + ('_item',)

    def __init__(self, *args, **kwargs):
        self._item = kwargs.pop('item', None)
        super(ItemAttachment, self).__init__(*args, **kwargs)
        for field_name, (_, field_type) in self.ATTACHMENT_FIELDS.items():
            if field_name == 'item':
                field_name = '_item'
            val = getattr(self, field_name)
            if val is not None and not isinstance(val, field_type):
                raise ValueError("Field '%s' must be of type '%s'" % (field_name, field_type))

    @property
    def item(self):
        if self.attachment_id is None:
            return self._item
        if self._item is not None:
            return self._item
        # We have an ID to the data but still haven't called GetAttachment to get the actual data. Do that now.
        if not self.parent_item.account:
            raise ValueError('%s must have an account' % self.__class__.__name__)
        items = list(
            self.__class__.from_xml(elem=i)
            for i in GetAttachment(account=self.parent_item.account).call(
                items=[self.attachment_id], include_mime_content=True)
        )
        assert len(items) == 1
        self._item = items[0]._item
        return self._item

    @item.setter
    def item(self, value):
        assert isinstance(value, Item)
        self._item = value


ITEM_CLASSES = (CalendarItem, Contact, Message, Task, MeetingRequest, MeetingResponse, MeetingCancellation)


@python_2_unicode_compatible
class Folder(EWSElement):
    DISTINGUISHED_FOLDER_ID = None  # See https://msdn.microsoft.com/en-us/library/office/aa580808(v=exchg.150).aspx
    # Default item type for this folder. See http://msdn.microsoft.com/en-us/library/hh354773(v=exchg.80).aspx
    CONTAINER_CLASS = None
    supported_item_models = ITEM_CLASSES  # The Item types that this folder can contain. Default is all
    LOCALIZED_NAMES = dict()  # A map of (str)locale: (tuple)localized_folder_names
    ITEM_MODEL_MAP = {cls.response_tag(): cls for cls in ITEM_CLASSES}

    def __init__(self, account, name=None, folder_class=None, folder_id=None, changekey=None):
        self.account = account
        self.name = name or self.DISTINGUISHED_FOLDER_ID
        self.folder_class = folder_class
        self.folder_id = folder_id
        self.changekey = changekey
        if not self.is_distinguished:
            assert self.folder_id
        if self.folder_id:
            assert self.changekey
        log.debug('%s created for %s', self, account)

    @property
    def is_distinguished(self):
        if not self.name or not self.DISTINGUISHED_FOLDER_ID:
            return False
        return self.name.lower() == self.DISTINGUISHED_FOLDER_ID.lower()

    @staticmethod
    def folder_cls_from_container_class(container_class):
        """Returns a reasonable folder class given a container class, e.g. 'IPF.Note'
        """
        return {cls.CONTAINER_CLASS: cls for cls in (Calendar, Contacts, Messages, Tasks)}.get(container_class, Folder)

    @staticmethod
    def folder_cls_from_folder_name(folder_name, locale):
        """Returns the folder class that matches a localized folder name.

        locale is a string, e.g. 'da_DK'
        """
        folder_classes = set(WELLKNOWN_FOLDERS.values())
        for folder_cls in folder_classes:
            for localized_name in folder_cls.LOCALIZED_NAMES.get(locale, []):
                if folder_name.lower() == localized_name.lower():
                    return folder_cls
        raise KeyError()

    @classmethod
    def item_model_from_tag(cls, tag):
        return cls.ITEM_MODEL_MAP[tag]

    @classmethod
    def allowed_field_names(cls):
        field_names = set()
        for item_model in cls.supported_item_models:
            field_names.update(item_model.fieldnames())
        return field_names

    @classmethod
    def complex_field_names(cls):
        field_names = set()
        for item_model in cls.supported_item_models:
            field_names.update(item_model.complex_fields())
        return field_names

    @classmethod
    def additional_property_elems(cls, fieldnames):
        # Some field names have more than one FieldURI. For example, 'mileage' field is present on both Contact and
        # Task, as contacts:Mileage and tasks:Mileage.
        elem_attrs = set()
        unique_elems = []
        for f in fieldnames:
            is_valid = False
            for item_model in cls.supported_item_models:
                try:
                    # Make sure to remove duplicate FieldURI elements
                    for elem in item_model.additional_property_elems(fieldname=f):
                        attrs = tuple(elem.items())
                        if attrs in elem_attrs:
                            continue
                        elem_attrs.add(attrs)
                        unique_elems.append(elem)
                    is_valid = True
                except ValueError:
                    pass
            if not is_valid:
                raise ValueError("No fielduri defined for fieldname '%s'" % f)
        return unique_elems

    @classmethod
    def fielduri_for_field(cls, fieldname):
        for item_model in cls.supported_item_models:
            try:
                return item_model.fielduri_for_field(fieldname=fieldname)
            except ValueError:
                pass
        raise ValueError("No fielduri defined for fieldname '%s'" % fieldname)

    @classmethod
    def field_type_for_field(cls, fieldname):
        for item_model in cls.supported_item_models:
            try:
                return item_model.type_for_field(fieldname=fieldname)
            except ValueError:
                pass
        raise ValueError("No fielduri defined for fieldname '%s'" % fieldname)

    def all(self):
        return QuerySet(self).all()

    def none(self):
        return QuerySet(self).none()

    def filter(self, *args, **kwargs):
        return QuerySet(self).filter(*args, **kwargs)

    def exclude(self, *args, **kwargs):
        return QuerySet(self).exclude(*args, **kwargs)

    def get(self, *args, **kwargs):
        return QuerySet(self).get(*args, **kwargs)

    def find_items(self, *args, **kwargs):
        """
        Finds items in the folder.

        'shape' controls the exact fields returned are governed by. Be aware that complex elements can only be fetched
        with fetch().

        'depth' controls the whether to return soft-deleted items or not.

        Non-keyword args may be a search expression as supported by Restriction.from_source(), or a list of Q instances.

        Optional extra keyword arguments follow a Django-like QuerySet filter syntax (see
           https://docs.djangoproject.com/en/1.10/ref/models/querysets/#field-lookups).

        We don't support '__year' and other date-related lookups. We also don't support '__endswith' or '__iendswith'.

        We support the additional '__not' lookup in place of Django's exclude() for simple cases. For more complicated
        cases you need to create a Q object and use ~Q().

        Examples:

            my_account.inbox.filter(datetime_received__gt=EWSDateTime(2016, 1, 1))
            my_account.calendar.filter(start__range=(EWSDateTime(2016, 1, 1), EWSDateTime(2017, 1, 1)))
            my_account.tasks.filter(subject='Hi mom')
            my_account.tasks.filter(subject__not='Hi mom')
            my_account.tasks.filter(subject__contains='Foo')
            my_account.tasks.filter(subject__icontains='foo')

        """
        # 'endswith' and 'iendswith' could be implemented by searching with 'contains' or 'icontains' and then
        # post-processing items. Fetch the field in question with additional_fields and remove items where the search
        # string is not a postfix.

        shape = kwargs.pop('shape', IdOnly)
        depth = kwargs.pop('depth', SHALLOW)
        assert shape in SHAPE_CHOICES
        assert depth in ITEM_TRAVERSAL_CHOICES

        # Define the extra properties we want on the return objects
        additional_fields = kwargs.pop('additional_fields', tuple())
        if additional_fields:
            allowed_field_names = self.allowed_field_names()
            complex_field_names = self.complex_field_names()
            for f in additional_fields:
                if f not in allowed_field_names:
                    raise ValueError("'%s' is not a field on %s" % (f, self.supported_item_models))
                if f in complex_field_names:
                    raise ValueError("find_items() does not support field '%s'. Use fetch() instead" % f)

        # Get the SortOrder field, if any
        order = kwargs.pop('order', None)

        # Get the CalendarView, if any
        calendar_view = kwargs.pop('calendar_view', None)

        # Get the requested number of items per page. Set a sane default and disallow None
        page_size = kwargs.pop('page_size', None) or FindItem.CHUNKSIZE

        # Build up any restrictions
        q = Q.from_filter_args(self.__class__, *args, **kwargs)
        if q and not q.is_empty():
            restriction = Restriction(q.translate_fields(folder_class=self.__class__))
        else:
            restriction = None
        log.debug(
            'Finding %s items for %s (shape: %s, depth: %s, additional_fields: %s, restriction: %s)',
            self.DISTINGUISHED_FOLDER_ID,
            self.account,
            shape,
            depth,
            additional_fields,
            restriction.q if restriction else None,
        )
        items = FindItem(folder=self).call(
            additional_fields=additional_fields,
            restriction=restriction,
            order=order,
            shape=shape,
            depth=depth,
            calendar_view=calendar_view,
            page_size=page_size,
        )
        if shape == IdOnly and additional_fields is None:
            for i in items:
                yield Item.id_from_xml(i)
        else:
            for i in items:
                yield self.item_model_from_tag(i.tag).from_xml(elem=i, account=self.account, folder=self)

    def add_items(self, *args, **kwargs):
        warnings.warn('add_items() is deprecated. Use bulk_create() instead', PendingDeprecationWarning)
        return self.bulk_create(*args, **kwargs)

    def bulk_create(self, items, *args, **kwargs):
        return self.account.bulk_create(folder=self, items=items, *args, **kwargs)

    def delete_items(self, ids, *args, **kwargs):
        warnings.warn('delete_items() is deprecated. Use bulk_delete() instead', PendingDeprecationWarning)
        return self.bulk_delete(ids, *args, **kwargs)

    def bulk_delete(self, ids, *args, **kwargs):
        warnings.warn('Folder.bulk_delete() is deprecated. Use Account.bulk_delete() instead', PendingDeprecationWarning)
        return self.account.bulk_delete(ids, *args, **kwargs)

    def update_items(self, items, *args, **kwargs):
        warnings.warn('update_items() is deprecated. Use bulk_update() instead', PendingDeprecationWarning)
        return self.bulk_update(items, *args, **kwargs)

    def bulk_update(self, items, *args, **kwargs):
        warnings.warn('Folder.bulk_update() is deprecated. Use Account.bulk_update() instead', PendingDeprecationWarning)
        return self.account.bulk_update(items, *args, **kwargs)

    def get_items(self, *args, **kwargs):
        warnings.warn('get_items() is deprecated. Use fetch() instead', PendingDeprecationWarning)
        return self.fetch(*args, **kwargs)

    def fetch(self, *args, **kwargs):
        if hasattr(self, 'with_extra_fields'):
            raise DeprecationWarning(
                "'%(cls)s.with_extra_fields' is deprecated. Use 'fetch(ids, only_fields=[...])' instead"
                % dict(cls=self.__class__.__name__))
        return self.account.fetch(folder=self, *args, **kwargs)

    def test_access(self):
        """
        Does a simple FindItem to test (read) access to the folder. Maybe the account doesn't exist, maybe the
        service user doesn't have access to the calendar. This will throw the most common errors.
        """
        list(self.filter(subject='DUMMY'))
        return True

    @classmethod
    def from_xml(cls, elem, account=None):
        assert account
        # fld_type = re.sub('{.*}', '', elem.tag)
        fld_id_elem = elem.find(FolderId.response_tag())
        fld_id = fld_id_elem.get(FolderId.ID_ATTR)
        changekey = fld_id_elem.get(FolderId.CHANGEKEY_ATTR)
        display_name = get_xml_attr(elem, '{%s}DisplayName' % TNS)
        folder_class = get_xml_attr(elem, '{%s}FolderClass' % TNS)
        elem.clear()
        return cls(account=account, name=display_name, folder_class=folder_class, folder_id=fld_id, changekey=changekey)

    def to_xml(self, version):
        self.clean()
        return FolderId(id=self.folder_id, changekey=self.changekey).to_xml(version=version)

    def get_folders(self, shape=IdOnly, depth=DEEP):
        # 'depth' controls whether to return direct children or recurse into sub-folders
        assert shape in SHAPE_CHOICES
        assert depth in FOLDER_TRAVERSAL_CHOICES
        folders = []
        for elem in FindFolder(folder=self).call(
                additional_fields=('folder:DisplayName', 'folder:FolderClass'),
                shape=shape,
                depth=depth,
                page_size=100,
        ):
            # The "FolderClass" element value is the only indication we have in the FindFolder response of which
            # folder class we should create the folder with.
            #
            # We should be able to just use the name, but apparently default folder names can be renamed to a set of
            # localized names using a PowerShell command:
            #     https://technet.microsoft.com/da-dk/library/dd351103(v=exchg.160).aspx
            #
            # Instead, search for a folder class using the localized name. If none are found, fall back to getting the
            # folder class by the "FolderClass" value.
            #
            # TODO: fld_class.LOCALIZED_NAMES is most definitely neither complete nor authoritative
            dummy_fld = Folder.from_xml(elem=elem, account=self.account)  # We use from_xml() only to parse elem
            try:
                folder_cls = self.folder_cls_from_folder_name(folder_name=dummy_fld.name, locale=self.account.locale)
                log.debug('Folder class %s matches localized folder name %s', folder_cls, dummy_fld.name)
            except KeyError:
                folder_cls = self.folder_cls_from_container_class(dummy_fld.folder_class)
                log.debug('Folder class %s matches container class %s (%s)', folder_cls, dummy_fld.folder_class, dummy_fld.name)
            folders.append(folder_cls(**dummy_fld.__dict__))
        return folders

    def get_folder_by_name(self, name):
        """Takes a case-sensitive folder name and returns an instance of that folder, if a folder with that name exists
        as a direct or indirect subfolder of this folder.
        """
        assert isinstance(name, string_types)
        matching_folders = []
        for f in self.get_folders(depth=DEEP):
            if f.name == name:
                matching_folders.append(f)
        if not matching_folders:
            raise ValueError('No subfolders found with name %s' % name)
        if len(matching_folders) > 1:
            raise ValueError('Multiple subfolders found with name %s' % name)
        return matching_folders[0]

    @classmethod
    def get_distinguished(cls, account, shape=IdOnly):
        assert shape in SHAPE_CHOICES
        folders = []
        for elem in GetFolder(account=account).call(
                distinguished_folder_id=cls.DISTINGUISHED_FOLDER_ID,
                additional_fields=('folder:DisplayName', 'folder:FolderClass'),
                shape=shape
        ):
            folders.append(cls.from_xml(elem=elem, account=account))
        assert len(folders) == 1
        return folders[0]

    def __repr__(self):
        return self.__class__.__name__ + \
               repr((self.account, self.name, self.folder_class, self.folder_id, self.changekey))

    def __str__(self):
        return '%s (%s)' % (self.__class__.__name__, self.name)


class Root(Folder):
    DISTINGUISHED_FOLDER_ID = 'root'


class CalendarView(EWSElement):
    """
    MSDN: https://msdn.microsoft.com/en-US/library/office/aa564515%28v=exchg.150%29.aspx
    """
    ELEMENT_NAME = 'CalendarView'

    __slots__ = ('start', 'end', 'max_items')

    def __init__(self, start, end, max_items=None):
        if not isinstance(start, EWSDateTime):
            raise ValueError("'start' must be an EWSDateTime")
        if not isinstance(end, EWSDateTime):
            raise ValueError("'end' must be an EWSDateTime")
        if not getattr(start, 'tzinfo'):
            raise ValueError("'start' must be timezone aware")
        if not getattr(end, 'tzinfo'):
            raise ValueError("'end' must be timezone aware")
        if end < start:
            raise AttributeError("'start' must be before 'end'")
        if max_items is not None:
            if not isinstance(max_items, int):
                raise ValueError("'max_items' must be an int")
            if max_items < 1:
                raise ValueError("'max_items' must be a positive integer")
        self.start = start
        self.end = end
        self.max_items = max_items

    def request_tag(cls):
        return 'm:%s' % cls.ELEMENT_NAME

    def to_xml(self, version):
        self.clean()
        elem = create_element(self.request_tag())
        # Use .set() to not fill up the create_element() cache with unique values
        elem.set('StartDate', value_to_xml_text(self.start.astimezone(UTC)))
        elem.set('EndDate', value_to_xml_text(self.end.astimezone(UTC)))
        if self.max_items is not None:
            elem.set('MaxEntriesReturned', value_to_xml_text(self.max_items))
        return elem


class Calendar(Folder):
    """
    An interface for the Exchange calendar
    """
    DISTINGUISHED_FOLDER_ID = 'calendar'
    CONTAINER_CLASS = 'IPF.Appointment'
    supported_item_models = (CalendarItem,)

    LOCALIZED_NAMES = {
        'da_DK': ('Kalender',),
        'de_DE': ('Kalender',),
        'en_US': ('Calendar',),
        'es_ES': ('Calendario',),
        'fr_CA': ('Calendrier',),
        'nl_NL': ('Agenda',),
        'ru_RU': ('Календарь',),
        'sv_SE': ('Kalender',),
    }

    def view(self, start, end, max_items=None, *args, **kwargs):
        """ Implements the CalendarView option to FindItem. The difference between filter() and view() is that filter()
        only returns the master CalendarItem for recurring items, while view() unfolds recurring items and returns all
        CalendarItem occurrences as one would normally expect when presenting a calendar.

        Supports the same semantics as filter, except for 'start' and 'end' keyword attributes which are both required
        and behave differently than filter. Here, they denote the start and end of the timespan of the view. All items
        the overlap the timespan are returned (items that end exactly on 'start' are also returned, for some reason).

        EWS does not allow combining CalendarView with search restrictions (filter and exclude).

        'max_items' defines the maximum number of items returned in this view. Optional.
        """
        qs = QuerySet(self).filter(*args, **kwargs)
        qs.calendar_view = CalendarView(start=start, end=end, max_items=max_items)
        return qs


class DeletedItems(Folder):
    DISTINGUISHED_FOLDER_ID = 'deleteditems'
    CONTAINER_CLASS = 'IPF.Note'
    supported_item_models = ITEM_CLASSES

    LOCALIZED_NAMES = {
        'da_DK': ('Slettet post',),
        'de_DE': ('Gelöschte Elemente',),
        'en_US': ('Deleted Items',),
        'es_ES': ('Elementos eliminados',),
        'fr_CA': ('Éléments supprimés',),
        'nl_NL': ('Verwijderde items',),
        'ru_RU': ('Удаленные',),
        'sv_SE': ('Borttaget',),
    }


class Messages(Folder):
    CONTAINER_CLASS = 'IPF.Note'
    supported_item_models = (Message, MeetingRequest, MeetingResponse, MeetingCancellation)


class Drafts(Messages):
    DISTINGUISHED_FOLDER_ID = 'drafts'

    LOCALIZED_NAMES = {
        'da_DK': ('Kladder',),
        'de_DE': ('Entwürfe',),
        'en_US': ('Drafts',),
        'es_ES': ('Borradores',),
        'fr_CA': ('Brouillons',),
        'nl_NL': ('Concepten',),
        'ru_RU': ('Черновики',),
        'sv_SE': ('Utkast',),
    }


class Inbox(Messages):
    DISTINGUISHED_FOLDER_ID = 'inbox'

    LOCALIZED_NAMES = {
        'da_DK': ('Indbakke',),
        'de_DE': ('Posteingang',),
        'en_US': ('Inbox',),
        'es_ES': ('Bandeja de entrada',),
        'fr_CA': ('Boîte de réception',),
        'nl_NL': ('Postvak IN',),
        'ru_RU': ('Входящие',),
        'sv_SE': ('Inkorgen',),
    }


class Outbox(Messages):
    DISTINGUISHED_FOLDER_ID = 'outbox'

    LOCALIZED_NAMES = {
        'da_DK': ('Udbakke',),
        'de_DE': ('Kalender',),
        'en_US': ('Outbox',),
        'es_ES': ('Bandeja de salida',),
        'fr_CA': ("Boîte d'envoi",),
        'nl_NL': ('Postvak UIT',),
        'ru_RU': ('Исходящие',),
        'sv_SE': ('Utkorgen',),
    }


class SentItems(Messages):
    DISTINGUISHED_FOLDER_ID = 'sentitems'

    LOCALIZED_NAMES = {
        'da_DK': ('Sendt post',),
        'de_DE': ('Gesendete Elemente',),
        'en_US': ('Sent Items',),
        'es_ES': ('Elementos enviados',),
        'fr_CA': ('Éléments envoyés',),
        'nl_NL': ('Verzonden items',),
        'ru_RU': ('Отправленные',),
        'sv_SE': ('Skickat',),
    }


class JunkEmail(Messages):
    DISTINGUISHED_FOLDER_ID = 'junkemail'

    LOCALIZED_NAMES = {
        'da_DK': ('Uønsket e-mail',),
        'de_DE': ('Junk-E-Mail',),
        'en_US': ('Junk E-mail',),
        'es_ES': ('Correo no deseado',),
        'fr_CA': ('Courrier indésirables',),
        'nl_NL': ('Ongewenste e-mail',),
        'ru_RU': ('Нежелательная почта',),
        'sv_SE': ('Skräppost',),
    }


class RecoverableItemsDeletions(Folder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsdeletions'
    supported_item_models = ITEM_CLASSES

    LOCALIZED_NAMES = {
    }


class RecoverableItemsRoot(Folder):
    DISTINGUISHED_FOLDER_ID = 'recoverableitemsroot'
    supported_item_models = ITEM_CLASSES

    LOCALIZED_NAMES = {
    }


class Tasks(Folder):
    DISTINGUISHED_FOLDER_ID = 'tasks'
    CONTAINER_CLASS = 'IPF.Task'
    supported_item_models = (Task,)

    LOCALIZED_NAMES = {
        'da_DK': ('Opgaver',),
        'de_DE': ('Aufgaben',),
        'en_US': ('Tasks',),
        'es_ES': ('Tareas',),
        'fr_CA': ('Tâches',),
        'nl_NL': ('Taken',),
        'ru_RU': ('Задачи',),
        'sv_SE': ('Uppgifter',),
    }


class Contacts(Folder):
    DISTINGUISHED_FOLDER_ID = 'contacts'
    CONTAINER_CLASS = 'IPF.Contact'
    supported_item_models = (Contact,)

    LOCALIZED_NAMES = {
        'da_DK': ('Kontaktpersoner',),
        'de_DE': ('Kontakte',),
        'en_US': ('Contacts',),
        'es_ES': ('Contactos',),
        'fr_CA': ('Contacts',),
        'nl_NL': ('Contactpersonen',),
        'ru_RU': ('Контакты',),
        'sv_SE': ('Kontakter',),
    }


class GenericFolder(Folder):
    pass


class WellknownFolder(Folder):
    # Use this class until we have specific folder implementations
    pass


# See http://msdn.microsoft.com/en-us/library/microsoft.exchange.webservices.data.wellknownfoldername(v=exchg.80).aspx
WELLKNOWN_FOLDERS = dict([
    ('Calendar', Calendar),
    ('Contacts', Contacts),
    ('DeletedItems', DeletedItems),
    ('Drafts', Drafts),
    ('Inbox', Inbox),
    ('Journal', WellknownFolder),
    ('Notes', WellknownFolder),
    ('Outbox', Outbox),
    ('SentItems', SentItems),
    ('Tasks', Tasks),
    ('MsgFolderRoot', WellknownFolder),
    ('PublicFoldersRoot', WellknownFolder),
    ('Root', Root),
    ('JunkEmail', JunkEmail),
    ('Search', WellknownFolder),
    ('VoiceMail', WellknownFolder),
    ('RecoverableItemsRoot', RecoverableItemsRoot),
    ('RecoverableItemsDeletions', RecoverableItemsDeletions),
    ('RecoverableItemsVersions', WellknownFolder),
    ('RecoverableItemsPurges', WellknownFolder),
    ('ArchiveRoot', WellknownFolder),
    ('ArchiveMsgFolderRoot', WellknownFolder),
    ('ArchiveDeletedItems', WellknownFolder),
    ('ArchiveRecoverableItemsRoot', Folder),
    ('ArchiveRecoverableItemsDeletions', WellknownFolder),
    ('ArchiveRecoverableItemsVersions', WellknownFolder),
    ('ArchiveRecoverableItemsPurges', WellknownFolder),
    ('SyncIssues', WellknownFolder),
    ('Conflicts', WellknownFolder),
    ('LocalFailures', WellknownFolder),
    ('ServerFailures', WellknownFolder),
    ('RecipientCache', WellknownFolder),
    ('QuickContacts', WellknownFolder),
    ('ConversationHistory', WellknownFolder),
    ('ToDoSearch', WellknownFolder),
    ('', GenericFolder),
])
