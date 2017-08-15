from __future__ import unicode_literals

import abc
import logging

from six import text_type, string_types

from .fields import SubField, TextField, EmailField, ChoiceField, DateTimeField, EWSElementField, MailboxField, Choice, \
    BooleanField
from .services import MNS, TNS
from .util import get_xml_attr, create_element

string_type = string_types[0]
log = logging.getLogger(__name__)


class Body(text_type):
    # Helper to mark the 'body' field as a complex attribute.
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj219983(v=exchg.150).aspx
    body_type = 'Text'


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
            raise AttributeError("%s are invalid kwargs for this class" % ', '.join("'%s'" % k for k in kwargs.keys()))

    def clean(self, version=None):
        # Validate attribute values using the field validator
        for f in self.FIELDS:
            if not f.supports_version(version):
                continue
            val = getattr(self, f.name)
            setattr(self, f.name, f.clean(val, version=version))

    @classmethod
    def from_xml(cls, elem, account):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS}
        elem.clear()
        return cls(**kwargs)

    def to_xml(self, version):
        self.clean(version=version)
        # WARNING: The order of addition of XML elements is VERY important. Exchange expects XML elements in a
        # specific, non-documented order and will fail with meaningless errors if the order is wrong.
        i = create_element(self.request_tag())
        for f in self.supported_fields(version=version):
            if f.is_read_only:
                continue
            value = getattr(self, f.name)
            if value is None or (f.is_list and not value):
                continue
            i.append(f.to_xml(value, version=version))
        return i

    @classmethod
    def request_tag(cls):
        assert cls.ELEMENT_NAME
        return {
            TNS: 't:%s' % cls.ELEMENT_NAME,
            MNS: 'm:%s' % cls.ELEMENT_NAME,
        }[cls.NAMESPACE]

    @classmethod
    def response_tag(cls):
        assert cls.NAMESPACE and cls.ELEMENT_NAME
        return '{%s}%s' % (cls.NAMESPACE, cls.ELEMENT_NAME)

    @classmethod
    def supported_fields(cls, version=None):
        # Return non-ID field names. If version is specified, only return the fields supported by this version
        return tuple(f for f in cls.FIELDS if f.name not in ('item_id', 'changekey') and f.supports_version(version))

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
        return hash(tuple(getattr(self, f) for f in self.__slots__))

    def __repr__(self):
        return self.__class__.__name__ + repr(tuple(getattr(self, f) for f in self.__slots__))


class MessageHeader(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565307(v=exchg.150).aspx
    ELEMENT_NAME = 'InternetMessageHeader'
    NAME_ATTR = 'HeaderName'

    FIELDS = [
        TextField('name', field_uri='HeaderName'),
        SubField('value'),
    ]

    __slots__ = ('name', 'value')

    @classmethod
    def from_xml(cls, elem, account):
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
    FIELDS = [
        TextField('id', field_uri=ID_ATTR, is_required=True),
        TextField('changekey', field_uri=CHANGEKEY_ATTR, is_required=True),
    ]

    __slots__ = ('id', 'changekey')

    def __init__(self, *args, **kwargs):
        if not kwargs:
            # Allow to set attributes without keyword
            kwargs = dict(zip(self.__slots__, args))
        super(ItemId, self).__init__(**kwargs)

    def to_xml(self, version):
        self.clean(version=version)
        elem = create_element(self.request_tag())
        # Use .set() to not fill up the create_element() cache with unique values
        elem.set(self.ID_ATTR, self.id)
        elem.set(self.CHANGEKEY_ATTR, self.changekey)
        return elem

    @classmethod
    def from_xml(cls, elem, account):
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

    __slots__ = ItemId.__slots__


class ConversationId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899527(v=exchg.150).aspx
    ELEMENT_NAME = 'ConversationId'

    __slots__ = ItemId.__slots__


class Mailbox(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565036(v=exchg.150).aspx
    ELEMENT_NAME = 'Mailbox'

    FIELDS = [
        TextField('name', field_uri='Name'),
        EmailField('email_address', field_uri='EmailAddress'),
        ChoiceField('mailbox_type', field_uri='MailboxType', choices={
            Choice('Mailbox'), Choice('PublicDL'), Choice('PrivateDL'), Choice('Contact'), Choice('PublicFolder'),
            Choice('Unknown'), Choice('OneOff')
        }, default='Mailbox'),
        EWSElementField('item_id', value_cls=ItemId, is_read_only=True),
        # There's also the 'RoutingType' element, but it's optional and must have value "SMTP"
    ]

    __slots__ = ('name', 'email_address', 'mailbox_type', 'item_id')

    def clean(self, version=None):
        super(Mailbox, self).clean(version=version)
        if not self.email_address or not self.item_id:
            # See "Remarks" section of https://msdn.microsoft.com/en-us/library/office/aa565036(v=exchg.150).aspx
            raise ValueError("Mailbox must have either 'email_address' or 'item_id' set")

    def __hash__(self):
        # Exchange may add 'mailbox_type' and 'name' on insert. We're satisfied if the item_id or email address matches.
        if self.item_id:
            return hash(self.item_id)
        return hash(self.email_address.lower())


class Attendee(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580339(v=exchg.150).aspx
    ELEMENT_NAME = 'Attendee'

    FIELDS = [
        MailboxField('mailbox', is_required=True),
        ChoiceField('response_type', field_uri='ResponseType', choices={
            Choice('Unknown'), Choice('Organizer'), Choice('Tentative'), Choice('Accept'), Choice('Decline'),
            Choice('NoResponseReceived')
        }, default='Unknown'),
        DateTimeField('last_response_time', field_uri='LastResponseTime'),
    ]

    __slots__ = ('mailbox', 'response_type', 'last_response_time')

    def __hash__(self):
        # TODO: maybe take 'response_type' and 'last_response_time' into account?
        return hash(self.mailbox)


class RoomList(Mailbox):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899514(v=exchg.150).aspx
    ELEMENT_NAME = 'RoomList'
    NAMESPACE = MNS

    @classmethod
    def response_tag(cls):
        # In a GetRoomLists response, room lists are delivered as Address elements
        # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899404(v=exchg.150).aspx
        return '{%s}Address' % TNS


class Room(Mailbox):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899479(v=exchg.150).aspx
    ELEMENT_NAME = 'Room'

    @classmethod
    def from_xml(cls, elem, account):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (elem.tag, cls.response_tag())
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

    __slots__ = ('create_associated', 'create_contents', 'create_hierarchy', 'delete', 'modify', 'read',
                 'view_private_items')

    def __contains__(self, item):
        return getattr(self, item, False)
