from exchangelib import Message, Mailbox, CalendarItem
from exchangelib.extended_properties import ExtendedProperty
from exchangelib.folders import Inbox

from .common import get_random_int
from .test_items.test_basics import BaseItemTest


class ExtendedPropertyTest(BaseItemTest):
    TEST_FOLDER = 'inbox'
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message

    def test_register(self):
        # Tests that we can register and de-register custom extended properties
        class TestProp(ExtendedProperty):
            property_set_id = 'deadbeaf-cafe-cafe-cafe-deadbeefcafe'
            property_name = 'Test Property'
            property_type = 'Integer'

        attr_name = 'dead_beef'

        # Before register
        self.assertNotIn(attr_name, {f.name for f in self.ITEM_CLASS.supported_fields(self.account.version)})
        with self.assertRaises(ValueError):
            self.ITEM_CLASS.deregister(attr_name)  # Not registered yet
        with self.assertRaises(ValueError):
            self.ITEM_CLASS.deregister('subject')  # Not an extended property

        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=TestProp)
        try:
            # After register
            self.assertEqual(TestProp.python_type(), int)
            self.assertIn(attr_name, {f.name for f in self.ITEM_CLASS.supported_fields(self.account.version)})

            # Test item creation, refresh, and update
            item = self.get_test_item(folder=self.test_folder)
            prop_val = item.dead_beef
            self.assertTrue(isinstance(prop_val, int))
            item.save()
            item.refresh()
            self.assertEqual(prop_val, item.dead_beef)
            new_prop_val = get_random_int(0, 256)
            item.dead_beef = new_prop_val
            item.save()
            item.refresh()
            self.assertEqual(new_prop_val, item.dead_beef)

            # Test deregister
            with self.assertRaises(ValueError):
                self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=TestProp)  # Already registered
            with self.assertRaises(ValueError):
                self.ITEM_CLASS.register(attr_name='XXX', attr_cls=Mailbox)  # Not an extended property
        finally:
            self.ITEM_CLASS.deregister(attr_name=attr_name)
        self.assertNotIn(attr_name, {f.name for f in self.ITEM_CLASS.supported_fields(self.account.version)})

    def test_extended_property_arraytype(self):
        # Tests array type extended properties
        class TestArayProp(ExtendedProperty):
            property_set_id = 'deadcafe-beef-beef-beef-deadcafebeef'
            property_name = 'Test Array Property'
            property_type = 'IntegerArray'

        attr_name = 'dead_beef_array'
        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=TestArayProp)
        try:
            # Test item creation, refresh, and update
            item = self.get_test_item(folder=self.test_folder)
            prop_val = item.dead_beef_array
            self.assertTrue(isinstance(prop_val, list))
            item.save()
            item.refresh()
            self.assertEqual(prop_val, item.dead_beef_array)
            new_prop_val = self.random_val(self.ITEM_CLASS.get_field_by_fieldname(attr_name))
            item.dead_beef_array = new_prop_val
            item.save()
            item.refresh()
            self.assertEqual(new_prop_val, item.dead_beef_array)
        finally:
            self.ITEM_CLASS.deregister(attr_name=attr_name)

    def test_extended_property_with_tag(self):
        class Flag(ExtendedProperty):
            property_tag = 0x1090
            property_type = 'Integer'

        attr_name = 'my_flag'
        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=Flag)
        try:
            # Test item creation, refresh, and update
            item = self.get_test_item(folder=self.test_folder)
            prop_val = item.my_flag
            self.assertTrue(isinstance(prop_val, int))
            item.save()
            item.refresh()
            self.assertEqual(prop_val, item.my_flag)
            new_prop_val = self.random_val(self.ITEM_CLASS.get_field_by_fieldname(attr_name))
            item.my_flag = new_prop_val
            item.save()
            item.refresh()
            self.assertEqual(new_prop_val, item.my_flag)
        finally:
            self.ITEM_CLASS.deregister(attr_name=attr_name)

    def test_extended_property_with_invalid_tag(self):
        class InvalidProp(ExtendedProperty):
            property_tag = '0x8000'
            property_type = 'Integer'

        with self.assertRaises(ValueError):
            InvalidProp('Foo').clean()  # property_tag is in protected range

    def test_extended_property_with_string_tag(self):
        class Flag(ExtendedProperty):
            property_tag = '0x1090'
            property_type = 'Integer'

        attr_name = 'my_flag'
        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=Flag)
        try:
            # Test item creation, refresh, and update
            item = self.get_test_item(folder=self.test_folder)
            prop_val = item.my_flag
            self.assertTrue(isinstance(prop_val, int))
            item.save()
            item.refresh()
            self.assertEqual(prop_val, item.my_flag)
            new_prop_val = self.random_val(self.ITEM_CLASS.get_field_by_fieldname(attr_name))
            item.my_flag = new_prop_val
            item.save()
            item.refresh()
            self.assertEqual(new_prop_val, item.my_flag)
        finally:
            self.ITEM_CLASS.deregister(attr_name=attr_name)

    def test_extended_distinguished_property(self):
        if self.ITEM_CLASS == CalendarItem:
            # MyMeeting is an extended prop version of the 'CalendarItem.uid' field. They don't work together.
            raise self.skipTest("This extendedproperty doesn't work on CalendarItems")

        class MyMeeting(ExtendedProperty):
            distinguished_property_set_id = 'Meeting'
            property_type = 'Binary'
            property_id = 3

        attr_name = 'my_meeting'
        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=MyMeeting)
        try:
            # Test item creation, refresh, and update
            item = self.get_test_item(folder=self.test_folder)
            prop_val = item.my_meeting
            self.assertTrue(isinstance(prop_val, bytes))
            item.save()
            item = self.get_item_by_id((item.id, item.changekey))
            self.assertEqual(prop_val, item.my_meeting, (prop_val, item.my_meeting))
            new_prop_val = self.random_val(self.ITEM_CLASS.get_field_by_fieldname(attr_name))
            item.my_meeting = new_prop_val
            item.save()
            item = self.get_item_by_id((item.id, item.changekey))
            self.assertEqual(new_prop_val, item.my_meeting)
        finally:
            self.ITEM_CLASS.deregister(attr_name=attr_name)

    def test_extended_property_binary_array(self):
        class MyMeetingArray(ExtendedProperty):
            property_set_id = '00062004-0000-0000-C000-000000000046'
            property_type = 'BinaryArray'
            property_id = 32852

        attr_name = 'my_meeting_array'
        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=MyMeetingArray)

        try:
            # Test item creation, refresh, and update
            item = self.get_test_item(folder=self.test_folder)
            prop_val = item.my_meeting_array
            self.assertTrue(isinstance(prop_val, list))
            item.save()
            item = self.get_item_by_id((item.id, item.changekey))
            self.assertEqual(prop_val, item.my_meeting_array)
            new_prop_val = self.random_val(self.ITEM_CLASS.get_field_by_fieldname(attr_name))
            item.my_meeting_array = new_prop_val
            item.save()
            item = self.get_item_by_id((item.id, item.changekey))
            self.assertEqual(new_prop_val, item.my_meeting_array)
        finally:
            self.ITEM_CLASS.deregister(attr_name=attr_name)

    def test_extended_property_validation(self):
        """
        if cls.property_type not in cls.PROPERTY_TYPES:
            raise ValueError(
                "'property_type' value '%s' must be one of %s" % (cls.property_type, sorted(cls.PROPERTY_TYPES))
            )
        """
        # Must not have property_set_id or property_tag
        class TestProp(ExtendedProperty):
            distinguished_property_set_id = 'XXX'
            property_set_id = 'YYY'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # Must have property_id or property_name
        class TestProp(ExtendedProperty):
            distinguished_property_set_id = 'XXX'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # distinguished_property_set_id must have a valid value
        class TestProp(ExtendedProperty):
            distinguished_property_set_id = 'XXX'
            property_id = 'YYY'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # Must not have distinguished_property_set_id or property_tag
        class TestProp(ExtendedProperty):
            property_set_id = 'XXX'
            property_tag = 'YYY'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # Must have property_id or property_name
        class TestProp(ExtendedProperty):
            property_set_id = 'XXX'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # property_tag is only compatible with property_type
        class TestProp(ExtendedProperty):
            property_tag = 'XXX'
            property_set_id = 'YYY'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # property_tag must be an integer or string that can be converted to int
        class TestProp(ExtendedProperty):
            property_tag = 'XXX'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # property_tag must not be in the reserved range
        class TestProp(ExtendedProperty):
            property_tag = 0x8001
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # Must not have property_id or property_tag
        class TestProp(ExtendedProperty):
            property_name = 'XXX'
            property_id = 'YYY'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # Must have distinguished_property_set_id or property_set_id
        class TestProp(ExtendedProperty):
            property_name = 'XXX'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # Must not have property_name or property_tag
        class TestProp(ExtendedProperty):
            property_id = 'XXX'
            property_name = 'YYY'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()  # This actually hits the check on property_name values

        # Must have distinguished_property_set_id or property_set_id
        class TestProp(ExtendedProperty):
            property_id = 'XXX'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()

        # property_type must be a valid value
        class TestProp(ExtendedProperty):
            property_id = 'XXX'
            property_set_id = 'YYY'
            property_type = 'ZZZ'
        with self.assertRaises(ValueError):
            TestProp.validate_cls()
