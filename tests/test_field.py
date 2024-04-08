import datetime
import warnings
from collections import namedtuple
from decimal import Decimal

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from exchangelib.extended_properties import ExternId
from exchangelib.fields import (
    Base64Field,
    BooleanField,
    CharField,
    CharListField,
    Choice,
    ChoiceField,
    DateField,
    DateTimeField,
    DecimalField,
    EnumField,
    EnumListField,
    ExtendedPropertyField,
    ExtendedPropertyListField,
    IntegerField,
    InvalidChoiceForVersion,
    InvalidFieldForVersion,
    TextField,
    TimeZoneField,
)
from exchangelib.indexed_properties import SingleFieldIndexedElement
from exchangelib.util import TNS, to_xml
from exchangelib.version import EXCHANGE_2007, EXCHANGE_2010, EXCHANGE_2013, Version

from .common import TimedTestCase


class FieldTest(TimedTestCase):
    def test_value_validation(self):
        field = TextField("foo", field_uri="bar", is_required=True, default=None)
        with self.assertRaises(ValueError) as e:
            field.clean(None)  # Must have a default value on None input
        self.assertEqual(str(e.exception), "'foo' is a required field with no default")

        field = TextField("foo", field_uri="bar", is_required=True, default="XXX")
        self.assertEqual(field.clean(None), "XXX")

        field = CharListField("foo", field_uri="bar")
        with self.assertRaises(TypeError) as e:
            field.clean("XXX")  # Must be a list type
        self.assertEqual(str(e.exception), "Field 'foo' value 'XXX' must be of type <class 'list'>")

        field = CharListField("foo", field_uri="bar")
        with self.assertRaises(TypeError) as e:
            field.clean([1, 2, 3])  # List items must be correct type
        self.assertEqual(str(e.exception), "Field 'foo' value 1 must be of type <class 'str'>")

        field = CharField("foo", field_uri="bar")
        with self.assertRaises(TypeError) as e:
            field.clean(1)  # Value must be correct type
        self.assertEqual(str(e.exception), "Field 'foo' value 1 must be of type <class 'str'>")
        with self.assertRaises(ValueError) as e:
            field.clean("X" * 256)  # Value length must be within max_length
        self.assertEqual(
            str(e.exception),
            "'foo' value 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX' exceeds length 255",
        )

        field = DateTimeField("foo", field_uri="bar")
        with self.assertRaises(ValueError) as e:
            field.clean(datetime.datetime(2017, 1, 1))  # Datetime values must be timezone aware
        self.assertEqual(
            str(e.exception), "Value datetime.datetime(2017, 1, 1, 0, 0) on field 'foo' must be timezone aware"
        )

        field = ChoiceField("foo", field_uri="bar", choices=[Choice("foo"), Choice("bar")])
        with self.assertRaises(ValueError) as e:
            field.clean("XXX")  # Value must be a valid choice
        self.assertEqual(str(e.exception), "Invalid choice 'XXX' for field 'foo'. Valid choices are ['bar', 'foo']")

        # A few tests on extended properties that override base methods
        field = ExtendedPropertyField("foo", value_cls=ExternId, is_required=True)
        with self.assertRaises(ValueError) as e:
            field.clean(None)  # Value is required
        self.assertEqual(str(e.exception), "'foo' is a required field")
        with self.assertRaises(TypeError) as e:
            field.clean(123)  # Correct type is required
        self.assertEqual(str(e.exception), "Field 'ExternId' value 123 must be of type <class 'str'>")
        self.assertEqual(field.clean("XXX"), "XXX")  # We can clean a simple value and keep it as a simple value
        self.assertEqual(field.clean(ExternId("XXX")), ExternId("XXX"))  # We can clean an ExternId instance as well

        class ExternIdArray(ExternId):
            property_type = "StringArray"

        field = ExtendedPropertyListField("foo", value_cls=ExternIdArray, is_required=True)
        with self.assertRaises(ValueError) as e:
            field.clean(None)  # Value is required
        self.assertEqual(str(e.exception), "'foo' is a required field")
        with self.assertRaises(TypeError) as e:
            field.clean(123)  # Must be an iterable
        self.assertEqual(str(e.exception), "Field 'ExternIdArray' value 123 must be of type <class 'list'>")
        with self.assertRaises(TypeError) as e:
            field.clean([123])  # Correct type is required
        self.assertEqual(str(e.exception), "Field 'ExternIdArray' list value 123 must be of type <class 'str'>")

        # Test min/max on IntegerField
        field = IntegerField("foo", field_uri="bar", min=5, max=10)
        with self.assertRaises(ValueError) as e:
            field.clean(2)
        self.assertEqual(str(e.exception), "Value 2 on field 'foo' must be greater than 5")
        with self.assertRaises(ValueError) as e:
            field.clean(12)
        self.assertEqual(str(e.exception), "Value 12 on field 'foo' must be less than 10")

        # Test min/max on DecimalField
        field = DecimalField("foo", field_uri="bar", min=5, max=10)
        with self.assertRaises(ValueError) as e:
            field.clean(Decimal(2))
        self.assertEqual(str(e.exception), "Value Decimal('2') on field 'foo' must be greater than 5")
        with self.assertRaises(ValueError) as e:
            field.clean(Decimal(12))
        self.assertEqual(str(e.exception), "Value Decimal('12') on field 'foo' must be less than 10")

        # Test enum validation
        field = EnumField("foo", field_uri="bar", enum=["a", "b", "c"])
        with self.assertRaises(ValueError) as e:
            field.clean(0)  # Enums start at 1
        self.assertEqual(str(e.exception), "Value 0 on field 'foo' must be greater than 1")
        with self.assertRaises(ValueError) as e:
            field.clean(4)  # Spills over list
        self.assertEqual(str(e.exception), "Value 4 on field 'foo' must be less than 3")
        with self.assertRaises(ValueError) as e:
            field.clean("d")  # Value not in enum
        self.assertEqual(str(e.exception), "Value 'd' on field 'foo' must be one of ['a', 'b', 'c']")

        # Test enum list validation
        field = EnumListField("foo", field_uri="bar", enum=["a", "b", "c"])
        with self.assertRaises(ValueError) as e:
            field.clean([])
        self.assertEqual(str(e.exception), "Value [] on field 'foo' must not be empty")
        with self.assertRaises(ValueError) as e:
            field.clean([0])
        self.assertEqual(str(e.exception), "Value 0 on field 'foo' must be greater than 1")
        with self.assertRaises(ValueError) as e:
            field.clean([1, 1])  # Values must be unique
        self.assertEqual(str(e.exception), "List entries [1, 1] on field 'foo' must be unique")
        with self.assertRaises(ValueError) as e:
            field.clean(["d"])
        self.assertEqual(str(e.exception), "List value 'd' on field 'foo' must be one of ['a', 'b', 'c']")

    def test_garbage_input(self):
        # Test that we can survive garbage input for common field types
        tz = zoneinfo.ZoneInfo("Europe/Copenhagen")
        account = namedtuple("Account", ["default_timezone"])(default_timezone=tz)
        payload = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:Foo>THIS_IS_GARBAGE</t:Foo>
    </t:Item>
</Envelope>"""
        elem = to_xml(payload).find(f"{{{TNS}}}Item")
        for field_cls in (Base64Field, BooleanField, IntegerField, DateField, DateTimeField, DecimalField):
            field = field_cls("foo", field_uri="item:Foo", is_required=True, default="DUMMY")
            self.assertEqual(field.from_xml(elem=elem, account=account), None)

        # Test MS timezones
        payload = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:Foo Id="THIS_IS_GARBAGE"></t:Foo>
    </t:Item>
</Envelope>"""
        elem = to_xml(payload).find(f"{{{TNS}}}Item")
        field = TimeZoneField("foo", field_uri="item:Foo", default="DUMMY")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tz = field.from_xml(elem=elem, account=account)
        self.assertEqual(tz, None)
        self.assertEqual(
            str(w[0].message),
            """\
Cannot convert value 'THIS_IS_GARBAGE' on field 'foo' to type 'EWSTimeZone' (unknown timezone ID).
You can fix this by adding a custom entry into the timezone translation map:

from exchangelib.winzone import MS_TIMEZONE_TO_IANA_MAP, CLDR_TO_MS_TIMEZONE_MAP

# Replace "Some_Region/Some_Location" with a reasonable value from CLDR_TO_MS_TIMEZONE_MAP.keys()
MS_TIMEZONE_TO_IANA_MAP['THIS_IS_GARBAGE'] = "Some_Region/Some_Location"

# Your code here""",
        )

    def test_versioned_field(self):
        field = TextField("foo", field_uri="bar", supported_from=EXCHANGE_2010)
        with self.assertRaises(InvalidFieldForVersion):
            field.clean("baz", version=Version(EXCHANGE_2007))
        field.clean("baz", version=Version(EXCHANGE_2010))
        field.clean("baz", version=Version(EXCHANGE_2013))

    def test_versioned_choice(self):
        field = ChoiceField("foo", field_uri="bar", choices={Choice("c1"), Choice("c2", supported_from=EXCHANGE_2010)})
        with self.assertRaises(ValueError):
            field.clean("XXX")  # Value must be a valid choice
        field.clean("c2", version=None)
        with self.assertRaises(InvalidChoiceForVersion):
            field.clean("c2", version=Version(EXCHANGE_2007))
        field.clean("c2", version=Version(EXCHANGE_2010))
        field.clean("c2", version=Version(EXCHANGE_2013))

    def test_naive_datetime(self):
        # Test that we can survive naive datetimes on a datetime field
        tz = zoneinfo.ZoneInfo("Europe/Copenhagen")
        utc = zoneinfo.ZoneInfo("UTC")
        account = namedtuple("Account", ["default_timezone"])(default_timezone=tz)
        default_value = datetime.datetime(2017, 1, 2, 3, 4, tzinfo=tz)
        field = DateTimeField("foo", field_uri="item:DateTimeSent", default=default_value)

        # TZ-aware datetime string
        payload = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:DateTimeSent>2017-06-21T18:40:02Z</t:DateTimeSent>
    </t:Item>
</Envelope>"""
        elem = to_xml(payload).find(f"{{{TNS}}}Item")
        self.assertEqual(
            field.from_xml(elem=elem, account=account), datetime.datetime(2017, 6, 21, 18, 40, 2, tzinfo=utc)
        )

        # Naive datetime string is localized to tz of the account
        payload = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:DateTimeSent>2017-06-21T18:40:02</t:DateTimeSent>
    </t:Item>
</Envelope>"""
        elem = to_xml(payload).find(f"{{{TNS}}}Item")
        self.assertEqual(
            field.from_xml(elem=elem, account=account), datetime.datetime(2017, 6, 21, 18, 40, 2, tzinfo=tz)
        )

        # Garbage string returns None
        payload = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:DateTimeSent>THIS_IS_GARBAGE</t:DateTimeSent>
    </t:Item>
</Envelope>"""
        elem = to_xml(payload).find(f"{{{TNS}}}Item")
        self.assertEqual(field.from_xml(elem=elem, account=account), None)

        # Element not found returns default value
        payload = b"""\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
    </t:Item>
</Envelope>"""
        elem = to_xml(payload).find(f"{{{TNS}}}Item")
        self.assertEqual(field.from_xml(elem=elem, account=account), default_value)

    def test_single_field_indexed_element(self):
        # A SingleFieldIndexedElement must have only one field defined
        class TestField(SingleFieldIndexedElement):
            a = CharField()
            b = CharField()

        with self.assertRaises(ValueError) as e:
            TestField.value_field(version=Version(EXCHANGE_2013))
        self.assertEqual(
            e.exception.args[0],
            "Class <class 'tests.test_field.FieldTest.test_single_field_indexed_element.<locals>.TestField'> "
            "must have only one value field (found ('a', 'b'))",
        )
