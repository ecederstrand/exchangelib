import datetime
import zoneinfo

from exchangelib.errors import ErrorInvalidIdMalformed
from exchangelib.folders import Contacts
from exchangelib.indexed_properties import EmailAddress, PhoneNumber, PhysicalAddress
from exchangelib.items import Contact, DistributionList, Persona
from exchangelib.properties import (
    Attribution,
)
from exchangelib.properties import EmailAddress as EmailAddressProp
from exchangelib.properties import (
    FolderId,
    Mailbox,
    Member,
    PersonaPhoneNumberTypeValue,
    PhoneNumberAttributedValue,
    SourceId,
    StringAttributedValue,
)
from exchangelib.services import FindPeople, GetPersona

from ..common import get_random_email, get_random_string
from .test_basics import CommonItemTest


class ContactsTest(CommonItemTest):
    TEST_FOLDER = "contacts"
    FOLDER_CLASS = Contacts
    ITEM_CLASS = Contact

    def test_order_by_on_indexed_field(self):
        # Test order_by() on IndexedField (simple and multi-subfield). Only Contact items have these
        test_items = []
        label = self.random_val(EmailAddress.get_field_by_fieldname("label"))
        for i in range(4):
            item = self.get_test_item()
            item.email_addresses = [EmailAddress(email=f"{i}@foo.com", label=label)]
            test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = self.test_folder.filter(categories__contains=self.categories)
        self.assertEqual(
            [i[0].email for i in qs.order_by(f"email_addresses__{label}").values_list("email_addresses", flat=True)],
            ["0@foo.com", "1@foo.com", "2@foo.com", "3@foo.com"],
        )
        self.assertEqual(
            [i[0].email for i in qs.order_by(f"-email_addresses__{label}").values_list("email_addresses", flat=True)],
            ["3@foo.com", "2@foo.com", "1@foo.com", "0@foo.com"],
        )
        self.bulk_delete(qs)

        test_items = []
        label = self.random_val(PhysicalAddress.get_field_by_fieldname("label"))
        for i in range(4):
            item = self.get_test_item()
            item.physical_addresses = [PhysicalAddress(street=f"Elm St {i}", label=label)]
            test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = self.test_folder.filter(categories__contains=self.categories)
        self.assertEqual(
            [
                i[0].street
                for i in qs.order_by(f"physical_addresses__{label}__street").values_list(
                    "physical_addresses", flat=True
                )
            ],
            ["Elm St 0", "Elm St 1", "Elm St 2", "Elm St 3"],
        )
        self.assertEqual(
            [
                i[0].street
                for i in qs.order_by(f"-physical_addresses__{label}__street").values_list(
                    "physical_addresses", flat=True
                )
            ],
            ["Elm St 3", "Elm St 2", "Elm St 1", "Elm St 0"],
        )
        self.bulk_delete(qs)

    def test_order_by_failure(self):
        # Test error handling on indexed properties with labels and subfields
        qs = self.test_folder.filter(categories__contains=self.categories)
        with self.assertRaises(ValueError):
            qs.order_by("email_addresses")  # Must have label
        with self.assertRaises(ValueError):
            qs.order_by("email_addresses__FOO")  # Must have a valid label
        with self.assertRaises(ValueError):
            qs.order_by("email_addresses__EmailAddress1__FOO")  # Must not have a subfield
        with self.assertRaises(ValueError):
            qs.order_by("physical_addresses__Business")  # Must have a subfield
        with self.assertRaises(ValueError):
            qs.order_by("physical_addresses__Business__FOO")  # Must have a valid subfield

    def test_update_on_single_field_indexed_field(self):
        home = PhoneNumber(label="HomePhone", phone_number="123")
        business = PhoneNumber(label="BusinessPhone", phone_number="456")
        item = self.get_test_item()
        item.phone_numbers = [home]
        item.save()
        item.phone_numbers = [business]
        item.save(update_fields=["phone_numbers"])
        item.refresh()
        self.assertListEqual(item.phone_numbers, [business])

    def test_update_on_multi_field_indexed_field(self):
        home = PhysicalAddress(label="Home", street="ABC")
        business = PhysicalAddress(label="Business", street="DEF", city="GHI")
        item = self.get_test_item()
        item.physical_addresses = [home]
        item.save()
        item.physical_addresses = [business]
        item.save(update_fields=["physical_addresses"])
        item.refresh()
        self.assertListEqual(item.physical_addresses, [business])

    def test_distribution_lists(self):
        dl = DistributionList(folder=self.test_folder, display_name=get_random_string(255), categories=self.categories)
        dl.save()
        new_dl = self.test_folder.get(categories__contains=dl.categories)
        self.assertEqual(new_dl.display_name, dl.display_name)
        self.assertEqual(new_dl.members, None)
        dl.refresh()

        # We set mailbox_type to OneOff because otherwise the email address must be an actual account
        dl.members = {
            Member(mailbox=Mailbox(email_address=get_random_email(), mailbox_type="OneOff")) for _ in range(4)
        }
        dl.save()
        new_dl = self.test_folder.get(categories__contains=dl.categories)
        self.assertEqual({m.mailbox.email_address for m in new_dl.members}, dl.members)

        dl.delete()

    def test_fetch_personas(self):
        # Test QuerySet input
        self.assertGreaterEqual(
            len(list(self.account.fetch_personas(self.test_folder.people().filter(display_name="john")))), 0
        )

    def test_find_people(self):
        # The test server may not have any contacts. Just test that the FindPeople and GetPersona services work.
        self.assertGreaterEqual(len(list(self.test_folder.people())), 0)
        self.assertGreaterEqual(
            len(
                list(
                    self.test_folder.people().only("display_name").filter(display_name="john").order_by("display_name")
                )
            ),
            0,
        )
        # Test with a querystring filter
        self.assertGreaterEqual(len(list(self.test_folder.people().filter("DisplayName:john"))), 0)
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
   <s:Body>
      <m:FindPeopleResponse ResponseClass="Success"
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
      <m:ResponseCode>NoError</m:ResponseCode>
      <m:People>
        <m:Persona>
          <t:PersonaId Id="AAAA=" />
          <t:DisplayName>Foo B. Smith</t:DisplayName>
          <t:EmailAddress>
            <t:Name>Foo Smith</t:Name>
            <t:EmailAddress>foo@example.com</t:EmailAddress>
            <t:RoutingType>SMTP</t:RoutingType>
          </t:EmailAddress>
          <t:RelevanceScore>2147483647</t:RelevanceScore>
        </m:Persona>
      </m:People>
      <m:TotalNumberOfPeopleInView>1</m:TotalNumberOfPeopleInView>
    </m:FindPeopleResponse>
  </s:Body>
</s:Envelope>"""
        self.assertListEqual(
            list(FindPeople(account=self.account).parse(xml)),
            [
                Persona(
                    id="AAAA=",
                    display_name="Foo B. Smith",
                    email_address=EmailAddressProp(name="Foo Smith", email_address="foo@example.com"),
                    relevance_score="2147483647",
                )
            ],
        )

    def test_get_persona(self):
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
   <s:Body>
      <m:GetPersonaResponseMessage ResponseClass="Success"
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
         <m:ResponseCode>NoError</m:ResponseCode>
         <m:Persona>
            <t:PersonaId Id="AAQkADEzAQAKtOtR="/>
            <t:PersonaType>Person</t:PersonaType>
            <t:CreationTime>2012-06-01T17:00:34Z</t:CreationTime>
            <t:DisplayName>Brian Johnson</t:DisplayName>
            <t:RelevanceScore>4255550110</t:RelevanceScore>
            <t:Attributions>
               <t:Attribution>
                  <t:Id>0</t:Id>
                  <t:SourceId Id="AAMkA =" ChangeKey="EQAAABY+"/>
                  <t:DisplayName>Outlook</t:DisplayName>
                  <t:IsWritable>true</t:IsWritable>
                  <t:IsQuickContact>false</t:IsQuickContact>
                  <t:IsHidden>false</t:IsHidden>
                  <t:FolderId Id="AAMkA=" ChangeKey="AQAAAA=="/>
               </t:Attribution>
            </t:Attributions>
            <t:DisplayNames>
               <t:StringAttributedValue>
                  <t:Value>Brian Johnson</t:Value>
                  <t:Attributions>
                     <t:Attribution>2</t:Attribution>
                     <t:Attribution>3</t:Attribution>
                  </t:Attributions>
               </t:StringAttributedValue>
            </t:DisplayNames>
            <t:MobilePhones>
               <t:PhoneNumberAttributedValue>
                  <t:Value>
                     <t:Number>(425)555-0110</t:Number>
                     <t:Type>Mobile</t:Type>
                  </t:Value>
                  <t:Attributions>
                     <t:Attribution>0</t:Attribution>
                  </t:Attributions>
               </t:PhoneNumberAttributedValue>
               <t:PhoneNumberAttributedValue>
                  <t:Value>
                     <t:Number>(425)555-0111</t:Number>
                     <t:Type>Mobile</t:Type>
                  </t:Value>
                  <t:Attributions>
                     <t:Attribution>1</t:Attribution>
                  </t:Attributions>
               </t:PhoneNumberAttributedValue>
            </t:MobilePhones>
         </m:Persona>
      </m:GetPersonaResponseMessage>
   </s:Body>
</s:Envelope>"""
        ws = GetPersona(account=self.account)
        persona = list(ws.parse(xml))[0]
        self.assertEqual(persona.id, "AAQkADEzAQAKtOtR=")
        self.assertEqual(persona.persona_type, "Person")
        self.assertEqual(
            persona.creation_time, datetime.datetime(2012, 6, 1, 17, 0, 34, tzinfo=zoneinfo.ZoneInfo("UTC"))
        )
        self.assertEqual(persona.display_name, "Brian Johnson")
        self.assertEqual(persona.relevance_score, "4255550110")
        self.assertEqual(
            persona.attributions[0],
            Attribution(
                ID=None,
                _id=SourceId(id="AAMkA =", changekey="EQAAABY+"),
                display_name="Outlook",
                is_writable=True,
                is_quick_contact=False,
                is_hidden=False,
                folder_id=FolderId(id="AAMkA=", changekey="AQAAAA=="),
            ),
        )
        self.assertEqual(
            persona.display_names,
            [
                StringAttributedValue(value="Brian Johnson", attributions=["2", "3"]),
            ],
        )
        self.assertEqual(
            persona.mobile_phones,
            [
                PhoneNumberAttributedValue(
                    value=PersonaPhoneNumberTypeValue(number="(425)555-0110", type="Mobile"),
                    attributions=["0"],
                ),
                PhoneNumberAttributedValue(
                    value=PersonaPhoneNumberTypeValue(number="(425)555-0111", type="Mobile"),
                    attributions=["1"],
                ),
            ],
        )

    def test_get_persona_failure(self):
        # The test server may not have any personas. Just test that the service response with something we can parse
        persona = Persona(id="AAA=", changekey="xxx")
        with self.assertRaises(ErrorInvalidIdMalformed):
            GetPersona(account=self.account).get(personas=[persona])
