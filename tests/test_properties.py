from inspect import isclass
from itertools import chain

from exchangelib.extended_properties import ExternId, Flag
from exchangelib.fields import GenericEventListField, InvalidField, InvalidFieldForVersion, TextField, TypeValueField
from exchangelib.folders import Folder, RootOfHierarchy
from exchangelib.indexed_properties import PhysicalAddress
from exchangelib.items import BulkCreateResult, Item
from exchangelib.properties import UID, Body, DLMailbox, EWSElement, Fields, HTMLBody, ItemId, Mailbox, MessageHeader
from exchangelib.util import TNS, to_xml
from exchangelib.version import EXCHANGE_2010, EXCHANGE_2013, Version

from .common import TimedTestCase


class PropertiesTest(TimedTestCase):
    def test_ews_element_sanity(self):
        from exchangelib import (
            attachments,
            extended_properties,
            folders,
            indexed_properties,
            items,
            properties,
            recurrence,
            settings,
        )

        for module in (
            attachments,
            properties,
            items,
            folders,
            indexed_properties,
            extended_properties,
            recurrence,
            settings,
        ):
            for cls in vars(module).values():
                if not isclass(cls) or not issubclass(cls, EWSElement):
                    continue
                with self.subTest(cls=cls):
                    # Make sure that we have an ELEMENT_NAME on all models
                    if cls != BulkCreateResult and not (cls.__doc__ and cls.__doc__.startswith("Base class ")):
                        self.assertIsNotNone(cls.ELEMENT_NAME, f"{cls} must have an ELEMENT_NAME")
                    # Assert that all FIELDS names are unique on the model. Also assert that the class defines
                    # __slots__, that all fields are mentioned in __slots__ and that __slots__ is unique.
                    field_names = set()
                    all_slots = tuple(chain(*(getattr(c, "__slots__", ()) for c in cls.__mro__)))
                    self.assertEqual(
                        len(all_slots),
                        len(set(all_slots)),
                        f"Model {cls}: __slots__ contains duplicates: {sorted(all_slots)}",
                    )
                    for f in cls.FIELDS:
                        with self.subTest(f=f):
                            self.assertNotIn(
                                f.name, field_names, f"Field name {f.name!r} is not unique on model {cls.__name__!r}"
                            )
                            self.assertIn(
                                f.name, all_slots, f"Field name {f.name!r} is not in __slots__ on model {cls.__name__}"
                            )
                            value_cls = f.value_cls  # Make sure lazy imports work
                            if not isinstance(f, (TypeValueField, GenericEventListField)):
                                # All other fields must define a value type
                                self.assertIsNotNone(value_cls)
                            field_names.add(f.name)
                    # Finally, test that all models have a link to MSDN documentation
                    if issubclass(cls, Folder):
                        # We have a long list of folders subclasses. Don't require a docstring for each
                        continue
                    self.assertIsNotNone(cls.__doc__, f"{cls} is missing a docstring")
                    if cls in (DLMailbox, BulkCreateResult, ExternId, Flag):
                        # Some classes are allowed to not have a link
                        continue
                    if cls.__doc__.startswith("Base class "):
                        # Base classes don't have an MSDN link
                        continue
                    if cls.__name__.startswith("_"):
                        # Non-public item class
                        continue
                    if issubclass(cls, RootOfHierarchy):
                        # Root folders don't have an MSDN link
                        continue
                    # collapse multiline docstrings
                    docstring = " ".join(doc.strip() for doc in cls.__doc__.split("\n"))
                    self.assertIn(
                        "MSDN: https://docs.microsoft.com", docstring, f"{cls} is missing an MSDN link in the docstring"
                    )

    def test_uid(self):
        # Test translation of calendar UIDs. See #453
        self.assertEqual(
            UID("261cbc18-1f65-5a0a-bd11-23b1e224cc2f"),
            b"\x04\x00\x00\x00\x82\x00\xe0\x00t\xc5\xb7\x10\x1a\x82\xe0\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x001\x00\x00\x00vCal-Uid\x01\x00\x00\x00"
            b"261cbc18-1f65-5a0a-bd11-23b1e224cc2f\x00",
        )
        self.assertEqual(
            UID.to_global_object_id(
                "040000008200E00074C5B7101A82E00800000000FF7FEDCAA34CD701000000000000000010000000DA513DCB6FE1904891890D"
                "BA92380E52"
            ),
            b"\x04\x00\x00\x00\x82\x00\xe0\x00t\xc5\xb7\x10\x1a\x82\xe0\x08\x00\x00\x00\x00\xff\x7f\xed\xca\xa3L\xd7"
            b"\x01\x00\x00\x00\x00\x00\x00\x00\x00\x10\x00\x00\x00\xdaQ=\xcbo\xe1\x90H\x91\x89\r\xba\x928\x0eR",
        )

    def test_internet_message_headers(self):
        # Message headers are read-only, and an integration test is difficult because we can't reliably AND quickly
        # generate emails that pass through some relay server that adds headers. Create a unit test instead.
        payload = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:InternetMessageHeaders>
        <t:InternetMessageHeader HeaderName="Received">from foo by bar</t:InternetMessageHeader>
        <t:InternetMessageHeader HeaderName="DKIM-Signature">Hello from DKIM</t:InternetMessageHeader>
        <t:InternetMessageHeader HeaderName="MIME-Version">1.0</t:InternetMessageHeader>
        <t:InternetMessageHeader HeaderName="X-Mailer">Contoso Mail</t:InternetMessageHeader>
        <t:InternetMessageHeader HeaderName="Return-Path">foo@example.com</t:InternetMessageHeader>
    </t:InternetMessageHeaders>
</Envelope>"""
        headers_elem = to_xml(payload).find(f"{{{TNS}}}InternetMessageHeaders")
        headers = {}
        for elem in headers_elem.findall(f"{{{TNS}}}InternetMessageHeader"):
            header = MessageHeader.from_xml(elem=elem, account=None)
            headers[header.name] = header.value
        self.assertDictEqual(
            headers,
            {
                "Received": "from foo by bar",
                "DKIM-Signature": "Hello from DKIM",
                "MIME-Version": "1.0",
                "X-Mailer": "Contoso Mail",
                "Return-Path": "foo@example.com",
            },
        )

    def test_physical_address(self):
        # Test that we can enter an integer zipcode and that it's converted to a string by clean()
        zipcode = 98765
        addr = PhysicalAddress(zipcode=zipcode)
        addr.clean()
        self.assertEqual(addr.zipcode, str(zipcode))

    def test_invalid_kwargs(self):
        with self.assertRaises(AttributeError):
            Mailbox(foo="XXX")

    def test_invalid_field(self):
        test_field = Item.get_field_by_fieldname(fieldname="text_body")
        self.assertIsInstance(test_field, TextField)
        self.assertEqual(test_field.name, "text_body")

        with self.assertRaises(InvalidField):
            Item.get_field_by_fieldname(fieldname="xxx")

        Item.validate_field(field=test_field, version=Version(build=EXCHANGE_2013))
        with self.assertRaises(InvalidFieldForVersion) as e:
            Item.validate_field(field=test_field, version=Version(build=EXCHANGE_2010))
        self.assertEqual(
            e.exception.args[0],
            "Field 'text_body' only supports server versions from 15.0.0.0 to * (server has Build=14.0.0.0, "
            "API=Exchange2010, Fullname=Microsoft Exchange Server 2010)",
        )

    def test_add_field(self):
        field = TextField("foo", field_uri="bar")
        Item.add_field(field, insert_after="subject")
        try:
            self.assertEqual(Item.get_field_by_fieldname("foo"), field)
        finally:
            Item.remove_field(field)

    def test_itemid_equality(self):
        self.assertEqual(ItemId("X", "Y"), ItemId("X", "Y"))
        self.assertNotEqual(ItemId("X", "Y"), ItemId("X", "Z"))
        self.assertNotEqual(ItemId("Z", "Y"), ItemId("X", "Y"))
        self.assertNotEqual(ItemId("X", "Y"), ItemId("Z", "Z"))
        self.assertNotEqual(ItemId("X", "Y"), None)

    def test_mailbox(self):
        mbx = Mailbox(name="XXX")
        with self.assertRaises(ValueError):
            mbx.clean()  # Must have either item_id or email_address set
        mbx = Mailbox(email_address="XXX")
        self.assertEqual(hash(mbx), hash("xxx"))
        mbx.item_id = "YYY"
        self.assertEqual(hash(mbx), hash("YYY"))  # If we have an item_id, use that for uniqueness

    def test_body(self):
        # Test that string formatting a Body and HTMLBody instance works and keeps the type
        self.assertEqual(str(Body("foo")), "foo")
        self.assertEqual(str(Body("%s") % "foo"), "foo")
        self.assertEqual(str(Body("{}").format("foo")), "foo")

        self.assertIsInstance(Body("foo"), Body)
        self.assertIsInstance(Body("") + "foo", Body)
        foo = Body("")
        foo += "foo"
        self.assertIsInstance(foo, Body)
        self.assertIsInstance(Body("%s") % "foo", Body)
        self.assertIsInstance(Body("{}").format("foo"), Body)

        self.assertEqual(str(HTMLBody("foo")), "foo")
        self.assertEqual(str(HTMLBody("%s") % "foo"), "foo")
        self.assertEqual(str(HTMLBody("{}").format("foo")), "foo")

        self.assertIsInstance(HTMLBody("foo"), HTMLBody)
        self.assertIsInstance(HTMLBody("") + "foo", HTMLBody)
        foo = HTMLBody("")
        foo += "foo"
        self.assertIsInstance(foo, HTMLBody)
        self.assertIsInstance(HTMLBody("%s") % "foo", HTMLBody)
        self.assertIsInstance(HTMLBody("{}").format("foo"), HTMLBody)

    def test_invalid_attribute(self):
        # For a random EWSElement subclass, test that we cannot assign an unsupported attribute
        item = ItemId(id="xxx", changekey="yyy")
        with self.assertRaises(AttributeError) as e:
            item.invalid_attr = 123
        self.assertEqual(
            e.exception.args[0], "'invalid_attr' is not a valid attribute. See ItemId.FIELDS for valid field names"
        )

    def test_fields(self):
        with self.assertRaises(ValueError) as e:
            Fields(
                TextField(name="xxx"),
                TextField(name="xxx"),
            )
        self.assertIn("is a duplicate", e.exception.args[0])
        fields = Fields(TextField(name="xxx"), TextField(name="yyy"))
        self.assertEqual(fields, fields.copy())
        self.assertFalse(123 in fields)
        with self.assertRaises(ValueError) as e:
            fields.index_by_name("zzz")
        self.assertEqual(e.exception.args[0], "Unknown field name 'zzz'")
        with self.assertRaises(ValueError) as e:
            fields.insert(0, TextField(name="xxx"))
        self.assertIn("is a duplicate", e.exception.args[0])
