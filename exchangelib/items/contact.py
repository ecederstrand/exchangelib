import datetime
import logging

from ..fields import (
    Base64Field,
    BodyContentAttributedValueField,
    BooleanField,
    CharField,
    Choice,
    ChoiceField,
    DateTimeBackedDateField,
    DateTimeField,
    EmailAddressAttributedValueField,
    EmailAddressesField,
    EmailAddressField,
    EWSElementField,
    EWSElementListField,
    IdElementField,
    MailboxField,
    MailboxListField,
    MemberListField,
    PersonaPhoneNumberField,
    PhoneNumberAttributedValueField,
    PhoneNumberField,
    PhysicalAddressField,
    PostalAddressAttributedValueField,
    StringAttributedValueField,
    TextField,
    TextListField,
    URIField,
)
from ..properties import Address, Attribution, CompleteName, EmailAddress, FolderId, IdChangeKeyMixIn, PersonaId
from ..util import TNS
from ..version import EXCHANGE_2010, EXCHANGE_2010_SP2
from .item import Item

log = logging.getLogger(__name__)


class Contact(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/contact"""

    ELEMENT_NAME = "Contact"

    file_as = TextField(field_uri="contacts:FileAs")
    file_as_mapping = ChoiceField(
        field_uri="contacts:FileAsMapping",
        choices={
            Choice("None"),
            Choice("LastCommaFirst"),
            Choice("FirstSpaceLast"),
            Choice("Company"),
            Choice("LastCommaFirstCompany"),
            Choice("CompanyLastFirst"),
            Choice("LastFirst"),
            Choice("LastFirstCompany"),
            Choice("CompanyLastCommaFirst"),
            Choice("LastFirstSuffix"),
            Choice("LastSpaceFirstCompany"),
            Choice("CompanyLastSpaceFirst"),
            Choice("LastSpaceFirst"),
            Choice("DisplayName"),
            Choice("FirstName"),
            Choice("LastFirstMiddleSuffix"),
            Choice("LastName"),
            Choice("Empty"),
        },
    )
    display_name = TextField(field_uri="contacts:DisplayName", is_required=True)
    given_name = CharField(field_uri="contacts:GivenName")
    initials = TextField(field_uri="contacts:Initials")
    middle_name = CharField(field_uri="contacts:MiddleName")
    nickname = TextField(field_uri="contacts:Nickname")
    complete_name = EWSElementField(field_uri="contacts:CompleteName", value_cls=CompleteName, is_read_only=True)
    company_name = TextField(field_uri="contacts:CompanyName")
    email_addresses = EmailAddressesField(field_uri="contacts:EmailAddress")
    physical_addresses = PhysicalAddressField(field_uri="contacts:PhysicalAddress")
    phone_numbers = PhoneNumberField(field_uri="contacts:PhoneNumber")
    assistant_name = TextField(field_uri="contacts:AssistantName")
    birthday = DateTimeBackedDateField(field_uri="contacts:Birthday", default_time=datetime.time(11, 59))
    business_homepage = URIField(field_uri="contacts:BusinessHomePage")
    children = TextListField(field_uri="contacts:Children")
    companies = TextListField(field_uri="contacts:Companies", is_searchable=False)
    contact_source = ChoiceField(
        field_uri="contacts:ContactSource", choices={Choice("Store"), Choice("ActiveDirectory")}, is_read_only=True
    )
    department = TextField(field_uri="contacts:Department")
    generation = TextField(field_uri="contacts:Generation")
    im_addresses = CharField(field_uri="contacts:ImAddresses", is_read_only=True)
    job_title = TextField(field_uri="contacts:JobTitle")
    manager = TextField(field_uri="contacts:Manager")
    mileage = TextField(field_uri="contacts:Mileage")
    office = TextField(field_uri="contacts:OfficeLocation")
    postal_address_index = ChoiceField(
        field_uri="contacts:PostalAddressIndex",
        choices={Choice("Business"), Choice("Home"), Choice("Other"), Choice("None")},
        default="None",
        is_required_after_save=True,
    )
    profession = TextField(field_uri="contacts:Profession")
    spouse_name = TextField(field_uri="contacts:SpouseName")
    surname = CharField(field_uri="contacts:Surname")
    wedding_anniversary = DateTimeBackedDateField(
        field_uri="contacts:WeddingAnniversary", default_time=datetime.time(11, 59)
    )
    has_picture = BooleanField(field_uri="contacts:HasPicture", supported_from=EXCHANGE_2010, is_read_only=True)
    phonetic_full_name = TextField(
        field_uri="contacts:PhoneticFullName", supported_from=EXCHANGE_2010_SP2, is_read_only=True
    )
    phonetic_first_name = TextField(
        field_uri="contacts:PhoneticFirstName", supported_from=EXCHANGE_2010_SP2, is_read_only=True
    )
    phonetic_last_name = TextField(
        field_uri="contacts:PhoneticLastName", supported_from=EXCHANGE_2010_SP2, is_read_only=True
    )
    email_alias = EmailAddressField(field_uri="contacts:Alias", is_read_only=True, supported_from=EXCHANGE_2010_SP2)
    # 'notes' is documented in MSDN but apparently unused. Writing to it raises ErrorInvalidPropertyRequest. OWA
    # put entries into the 'notes' form field into the 'body' field.
    notes = CharField(field_uri="contacts:Notes", supported_from=EXCHANGE_2010_SP2, is_read_only=True)
    # 'photo' is documented in MSDN but apparently unused. Writing to it raises ErrorInvalidPropertyRequest. OWA
    # adds photos as FileAttachments on the contact item (with 'is_contact_photo=True'), which automatically flips
    # the 'has_picture' field.
    photo = Base64Field(field_uri="contacts:Photo", supported_from=EXCHANGE_2010_SP2, is_read_only=True)
    user_smime_certificate = Base64Field(
        field_uri="contacts:UserSMIMECertificate", supported_from=EXCHANGE_2010_SP2, is_read_only=True
    )
    ms_exchange_certificate = Base64Field(
        field_uri="contacts:MSExchangeCertificate", supported_from=EXCHANGE_2010_SP2, is_read_only=True
    )
    directory_id = TextField(field_uri="contacts:DirectoryId", supported_from=EXCHANGE_2010_SP2, is_read_only=True)
    manager_mailbox = MailboxField(
        field_uri="contacts:ManagerMailbox", supported_from=EXCHANGE_2010_SP2, is_read_only=True
    )
    direct_reports = MailboxListField(
        field_uri="contacts:DirectReports", supported_from=EXCHANGE_2010_SP2, is_read_only=True
    )
    # O365 throws ErrorInternalServerError "[0x004f0102] MapiReplyToBlob" if UniqueBody is requested
    unique_body_idx = Item.FIELDS.index_by_name("unique_body")
    FIELDS = Item.FIELDS[:unique_body_idx] + Item.FIELDS[unique_body_idx + 1 :]


class Persona(IdChangeKeyMixIn):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/persona"""

    ELEMENT_NAME = "Persona"
    ID_ELEMENT_CLS = PersonaId

    _id = IdElementField(field_uri="persona:PersonaId", value_cls=ID_ELEMENT_CLS, namespace=TNS)
    persona_type = CharField(field_uri="persona:PersonaType")
    persona_object_type = TextField(field_uri="persona:PersonaObjectStatus")
    creation_time = DateTimeField(field_uri="persona:CreationTime")
    bodies = BodyContentAttributedValueField(field_uri="persona:Bodies")
    display_name_first_last_sort_key = TextField(field_uri="persona:DisplayNameFirstLastSortKey")
    display_name_last_first_sort_key = TextField(field_uri="persona:DisplayNameLastFirstSortKey")
    company_sort_key = TextField(field_uri="persona:CompanyNameSortKey")
    home_sort_key = TextField(field_uri="persona:HomeCitySortKey")
    work_city_sort_key = TextField(field_uri="persona:WorkCitySortKey")
    display_name_first_last_header = CharField(field_uri="persona:DisplayNameFirstLastHeader")
    display_name_last_first_header = CharField(field_uri="persona:DisplayNameLastFirstHeader")
    file_as_header = TextField(field_uri="persona:FileAsHeader")
    display_name = CharField(field_uri="persona:DisplayName")
    display_name_first_last = CharField(field_uri="persona:DisplayNameFirstLast")
    display_name_last_first = CharField(field_uri="persona:DisplayNameLastFirst")
    file_as = CharField(field_uri="persona:FileAs")
    file_as_id = TextField(field_uri="persona:FileAsId")
    display_name_prefix = CharField(field_uri="persona:DisplayNamePrefix")
    given_name = CharField(field_uri="persona:GivenName")
    middle_name = CharField(field_uri="persona:MiddleName")
    surname = CharField(field_uri="persona:Surname")
    generation = CharField(field_uri="persona:Generation")
    nickname = TextField(field_uri="persona:Nickname")
    yomi_company_name = TextField(field_uri="persona:YomiCompanyName")
    yomi_first_name = TextField(field_uri="persona:YomiFirstName")
    yomi_last_name = TextField(field_uri="persona:YomiLastName")
    title = CharField(field_uri="persona:Title")
    department = TextField(field_uri="persona:Department")
    company_name = CharField(field_uri="persona:CompanyName")
    email_address = EWSElementField(field_uri="persona:EmailAddress", value_cls=EmailAddress)
    email_addresses = EWSElementListField(field_uri="persona:EmailAddresses", value_cls=Address)
    PhoneNumber = PersonaPhoneNumberField(field_uri="persona:PhoneNumber")
    im_address = CharField(field_uri="persona:ImAddress")
    home_city = CharField(field_uri="persona:HomeCity")
    work_city = CharField(field_uri="persona:WorkCity")
    relevance_score = CharField(field_uri="persona:RelevanceScore")
    folder_ids = EWSElementListField(field_uri="persona:FolderIds", value_cls=FolderId)
    attributions = EWSElementListField(field_uri="persona:Attributions", value_cls=Attribution)
    display_names = StringAttributedValueField(field_uri="persona:DisplayNames")
    file_ases = StringAttributedValueField(field_uri="persona:FileAses")
    file_as_ids = StringAttributedValueField(field_uri="persona:FileAsIds")
    display_name_prefixes = StringAttributedValueField(field_uri="persona:DisplayNamePrefixes")
    given_names = StringAttributedValueField(field_uri="persona:GivenNames")
    middle_names = StringAttributedValueField(field_uri="persona:MiddleNames")
    surnames = StringAttributedValueField(field_uri="persona:Surnames")
    generations = StringAttributedValueField(field_uri="persona:Generations")
    nicknames = StringAttributedValueField(field_uri="persona:Nicknames")
    initials = StringAttributedValueField(field_uri="persona:Initials")
    yomi_company_names = StringAttributedValueField(field_uri="persona:YomiCompanyNames")
    yomi_first_names = StringAttributedValueField(field_uri="persona:YomiFirstNames")
    yomi_last_names = StringAttributedValueField(field_uri="persona:YomiLastNames")
    business_phone_numbers = PhoneNumberAttributedValueField(field_uri="persona:BusinessPhoneNumbers")
    business_phone_numbers2 = PhoneNumberAttributedValueField(field_uri="persona:BusinessPhoneNumbers2")
    home_phones = PhoneNumberAttributedValueField(field_uri="persona:HomePhones")
    home_phones2 = PhoneNumberAttributedValueField(field_uri="persona:HomePhones2")
    mobile_phones = PhoneNumberAttributedValueField(field_uri="persona:MobilePhones")
    mobile_phones2 = PhoneNumberAttributedValueField(field_uri="persona:MobilePhones2")
    assistant_phone_numbers = PhoneNumberAttributedValueField(field_uri="persona:AssistantPhoneNumbers")
    callback_phones = PhoneNumberAttributedValueField(field_uri="persona:CallbackPhones")
    car_phones = PhoneNumberAttributedValueField(field_uri="persona:CarPhones")
    home_faxes = PhoneNumberAttributedValueField(field_uri="persona:HomeFaxes")
    organization_main_phones = PhoneNumberAttributedValueField(field_uri="persona:OrganizationMainPhones")
    other_faxes = PhoneNumberAttributedValueField(field_uri="persona:OtherFaxes")
    other_telephones = PhoneNumberAttributedValueField(field_uri="persona:OtherTelephones")
    other_phones2 = PhoneNumberAttributedValueField(field_uri="persona:OtherPhones2")
    pagers = PhoneNumberAttributedValueField(field_uri="persona:Pagers")
    radio_phones = PhoneNumberAttributedValueField(field_uri="persona:RadioPhones")
    telex_numbers = PhoneNumberAttributedValueField(field_uri="persona:TelexNumbers")
    tty_tdd_phone_numbers = PhoneNumberAttributedValueField(field_uri="persona:TTYTDDPhoneNumbers")
    work_faxes = PhoneNumberAttributedValueField(field_uri="persona:WorkFaxes")
    emails1 = EmailAddressAttributedValueField(field_uri="persona:Emails1")
    emails2 = EmailAddressAttributedValueField(field_uri="persona:Emails2")
    emails3 = EmailAddressAttributedValueField(field_uri="persona:Emails3")
    business_home_pages = StringAttributedValueField(field_uri="persona:BusinessHomePages")
    personal_home_pages = StringAttributedValueField(field_uri="persona:PersonalHomePages")
    office_locations = StringAttributedValueField(field_uri="persona:OfficeLocations")
    im_addresses = StringAttributedValueField(field_uri="persona:ImAddresses")
    im_addresses2 = StringAttributedValueField(field_uri="persona:ImAddresses2")
    im_addresses3 = StringAttributedValueField(field_uri="persona:ImAddresses3")
    business_addresses = PostalAddressAttributedValueField(field_uri="persona:BusinessAddresses")
    home_addresses = PostalAddressAttributedValueField(field_uri="persona:HomeAddresses")
    other_addresses = PostalAddressAttributedValueField(field_uri="persona:OtherAddresses")
    titles = StringAttributedValueField(field_uri="persona:Titles")
    departments = StringAttributedValueField(field_uri="persona:Departments")
    company_names = StringAttributedValueField(field_uri="persona:CompanyNames")
    managers = StringAttributedValueField(field_uri="persona:Managers")
    assistant_names = StringAttributedValueField(field_uri="persona:AssistantNames")
    professions = StringAttributedValueField(field_uri="persona:Professions")
    spouse_names = StringAttributedValueField(field_uri="persona:SpouseNames")
    children = StringAttributedValueField(field_uri="persona:Children")
    schools = StringAttributedValueField(field_uri="persona:Schools")
    hobbies = StringAttributedValueField(field_uri="persona:Hobbies")
    wedding_anniversaries = StringAttributedValueField(field_uri="persona:WeddingAnniversaries")
    birthdays = StringAttributedValueField(field_uri="persona:Birthdays")
    locations = StringAttributedValueField(field_uri="persona:Locations")
    # This class has an additional field of type "ExtendedPropertyAttributedValueField" and
    # field_uri 'persona:ExtendedProperties'


class DistributionList(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/distributionlist"""

    ELEMENT_NAME = "DistributionList"

    display_name = CharField(field_uri="contacts:DisplayName", is_required=True)
    file_as = CharField(field_uri="contacts:FileAs", is_read_only=True)
    contact_source = ChoiceField(
        field_uri="contacts:ContactSource", choices={Choice("Store"), Choice("ActiveDirectory")}, is_read_only=True
    )
    members = MemberListField(field_uri="distributionlist:Members")

    # O365 throws ErrorInternalServerError "[0x004f0102] MapiReplyToBlob" if UniqueBody is requested
    unique_body_idx = Item.FIELDS.index_by_name("unique_body")
    FIELDS = Item.FIELDS[:unique_body_idx] + Item.FIELDS[unique_body_idx + 1 :]
