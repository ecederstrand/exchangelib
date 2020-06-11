import logging

from ..fields import BooleanField, Base64Field, TextField, ChoiceField, URIField, DateTimeBackedDateField, \
    PhoneNumberField, EmailAddressesField, PhysicalAddressField, Choice, MemberListField, CharField, TextListField, \
    EmailAddressField, IdElementField
from ..properties import PersonaId, IdChangeKeyMixIn, Fields
from ..version import EXCHANGE_2010, EXCHANGE_2013
from .item import Item

log = logging.getLogger(__name__)


class Contact(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/contact"""
    ELEMENT_NAME = 'Contact'
    LOCAL_FIELDS = Fields(
        TextField('file_as', field_uri='contacts:FileAs'),
        ChoiceField('file_as_mapping', field_uri='contacts:FileAsMapping', choices={
            Choice('None'), Choice('LastCommaFirst'), Choice('FirstSpaceLast'), Choice('Company'),
            Choice('LastCommaFirstCompany'), Choice('CompanyLastFirst'), Choice('LastFirst'),
            Choice('LastFirstCompany'), Choice('CompanyLastCommaFirst'), Choice('LastFirstSuffix'),
            Choice('LastSpaceFirstCompany'), Choice('CompanyLastSpaceFirst'), Choice('LastSpaceFirst'),
            Choice('DisplayName'), Choice('FirstName'), Choice('LastFirstMiddleSuffix'), Choice('LastName'),
            Choice('Empty'),
        }),
        TextField('display_name', field_uri='contacts:DisplayName', is_required=True),
        CharField('given_name', field_uri='contacts:GivenName'),
        TextField('initials', field_uri='contacts:Initials'),
        CharField('middle_name', field_uri='contacts:MiddleName'),
        TextField('nickname', field_uri='contacts:Nickname'),
        # Placeholder for CompleteName
        TextField('company_name', field_uri='contacts:CompanyName'),
        EmailAddressesField('email_addresses', field_uri='contacts:EmailAddress'),
        PhysicalAddressField('physical_addresses', field_uri='contacts:PhysicalAddress'),
        PhoneNumberField('phone_numbers', field_uri='contacts:PhoneNumber'),
        TextField('assistant_name', field_uri='contacts:AssistantName'),
        DateTimeBackedDateField('birthday', field_uri='contacts:Birthday'),
        URIField('business_homepage', field_uri='contacts:BusinessHomePage'),
        TextListField('children', field_uri='contacts:Children'),
        TextListField('companies', field_uri='contacts:Companies', is_searchable=False),
        ChoiceField('contact_source', field_uri='contacts:ContactSource', choices={
            Choice('Store'), Choice('ActiveDirectory')
        }, is_read_only=True),
        TextField('department', field_uri='contacts:Department'),
        TextField('generation', field_uri='contacts:Generation'),
        CharField('im_addresses', field_uri='contacts:ImAddresses', is_read_only=True),
        TextField('job_title', field_uri='contacts:JobTitle'),
        TextField('manager', field_uri='contacts:Manager'),
        TextField('mileage', field_uri='contacts:Mileage'),
        TextField('office', field_uri='contacts:OfficeLocation'),
        ChoiceField('postal_address_index', field_uri='contacts:PostalAddressIndex', choices={
            Choice('Business'), Choice('Home'), Choice('Other'), Choice('None')
        }, default='None', is_required_after_save=True),
        TextField('profession', field_uri='contacts:Profession'),
        TextField('spouse_name', field_uri='contacts:SpouseName'),
        CharField('surname', field_uri='contacts:Surname'),
        DateTimeBackedDateField('wedding_anniversary', field_uri='contacts:WeddingAnniversary'),
        BooleanField('has_picture', field_uri='contacts:HasPicture', supported_from=EXCHANGE_2010, is_read_only=True),
        TextField('phonetic_full_name', field_uri='contacts:PhoneticFullName', supported_from=EXCHANGE_2013,
                  is_read_only=True),
        TextField('phonetic_first_name', field_uri='contacts:PhoneticFirstName', supported_from=EXCHANGE_2013,
                  is_read_only=True),
        TextField('phonetic_last_name', field_uri='contacts:PhoneticLastName', supported_from=EXCHANGE_2013,
                  is_read_only=True),
        EmailAddressField('email_alias', field_uri='contacts:Alias', is_read_only=True),
        # 'notes' is documented in MSDN but apparently unused. Writing to it raises ErrorInvalidPropertyRequest. OWA
        # put entries into the 'notes' form field into the 'body' field.
        CharField('notes', field_uri='contacts:Notes', supported_from=EXCHANGE_2013, is_read_only=True),
        # 'photo' is documented in MSDN but apparently unused. Writing to it raises ErrorInvalidPropertyRequest. OWA
        # adds photos as FileAttachments on the contact item (with 'is_contact_photo=True'), which automatically flips
        # the 'has_picture' field.
        Base64Field('photo', field_uri='contacts:Photo', is_read_only=True),
        # Placeholder for UserSMIMECertificate
        # Placeholder for MSExchangeCertificate
        TextField('directory_id', field_uri='contacts:DirectoryId', supported_from=EXCHANGE_2013, is_read_only=True),
        # Placeholder for ManagerMailbox
        # Placeholder for DirectReports
    )
    FIELDS = Item.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)


class Persona(IdChangeKeyMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/persona"""
    ELEMENT_NAME = 'Persona'
    ID_ELEMENT_CLS = PersonaId
    LOCAL_FIELDS = Fields(
        IdElementField('_id', field_uri='persona:PersonaId', value_cls=ID_ELEMENT_CLS),
        CharField('file_as', field_uri='persona:FileAs'),
        CharField('display_name', field_uri='persona:DisplayName'),
        CharField('given_name', field_uri='persona:GivenName'),
        TextField('middle_name', field_uri='persona:MiddleName'),
        CharField('surname', field_uri='persona:Surname'),
        TextField('generation', field_uri='persona:Generation'),
        TextField('nickname', field_uri='persona:Nickname'),
        CharField('title', field_uri='persona:Title'),
        TextField('department', field_uri='persona:Department'),
        CharField('company_name', field_uri='persona:CompanyName'),
        CharField('im_address', field_uri='persona:ImAddress'),
        TextField('initials', field_uri='persona:Initials'),
    )
    FIELDS = IdChangeKeyMixIn.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)


class DistributionList(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/distributionlist"""
    ELEMENT_NAME = 'DistributionList'
    LOCAL_FIELDS = Fields(
        CharField('display_name', field_uri='contacts:DisplayName', is_required=True),
        CharField('file_as', field_uri='contacts:FileAs', is_read_only=True),
        ChoiceField('contact_source', field_uri='contacts:ContactSource', choices={
            Choice('Store'), Choice('ActiveDirectory')
        }, is_read_only=True),
        MemberListField('members', field_uri='distributionlist:Members'),
    )
    FIELDS = Item.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)
