import os
import unittest
import datetime
import random
import string
from decimal import Decimal
import time

import requests
from yaml import load

from exchangelib import close_connections
from exchangelib.account import Account
from exchangelib.autodiscover import discover
from exchangelib.configuration import Configuration
from exchangelib.credentials import DELEGATE, Credentials
from exchangelib.errors import RelativeRedirect, ErrorItemNotFound
from exchangelib.ewsdatetime import EWSDateTime, EWSDate, EWSTimeZone, UTC, UTC_NOW
from exchangelib.folders import CalendarItem, Attendee, Mailbox, Message, ExternId, Choice, Email, Contact, Task, \
    EmailAddress, PhysicalAddress, PhoneNumber, IndexedField, RoomList, Calendar, DeletedItems, Drafts, Inbox, Outbox, \
    SentItems, JunkEmail, Tasks, Contacts, AnyURI, BodyType, ALL_OCCURRENCIES, ItemId
from exchangelib.queryset import QuerySet, DoesNotExist, MultipleObjectsReturned
from exchangelib.restriction import Restriction, Q
from exchangelib.services import GetServerTimeZones, GetRoomLists, GetRooms
from exchangelib.util import xml_to_str, chunkify, peek, get_redirect_url
from exchangelib.version import Build


class BuildTest(unittest.TestCase):
    def test_magic(self):
        with self.assertRaises(ValueError):
            Build(7, 0)
        self.assertEqual(str(Build(9, 8, 7, 6)), '9.8.7.6')

    def test_compare(self):
        self.assertEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 2))
        self.assertLess(Build(15, 0, 1, 2), Build(15, 0, 1, 3))
        self.assertLess(Build(15, 0, 1, 2), Build(15, 0, 2, 2))
        self.assertLess(Build(15, 0, 1, 2), Build(15, 1, 1, 2))
        self.assertLess(Build(15, 0, 1, 2), Build(16, 0, 1, 2))
        self.assertLessEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 2))
        self.assertGreater(Build(15, 0, 1, 2), Build(15, 0, 1, 1))
        self.assertGreater(Build(15, 0, 1, 2), Build(15, 0, 0, 2))
        self.assertGreater(Build(15, 1, 1, 2), Build(15, 0, 1, 2))
        self.assertGreater(Build(15, 0, 1, 2), Build(14, 0, 1, 2))
        self.assertGreaterEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 2))

    def test_api_version(self):
        self.assertEqual(Build(8, 0).api_version(), 'Exchange2007')
        self.assertEqual(Build(8, 1).api_version(), 'Exchange2007_SP1')
        self.assertEqual(Build(8, 2).api_version(), 'Exchange2007_SP1')
        self.assertEqual(Build(8, 3).api_version(), 'Exchange2007_SP1')
        self.assertEqual(Build(15, 0, 1, 1).api_version(), 'Exchange2013')
        self.assertEqual(Build(15, 0, 1, 1).api_version(), 'Exchange2013')
        self.assertEqual(Build(15, 0, 847, 0).api_version(), 'Exchange2013_SP1')
        with self.assertRaises(KeyError):
            Build(16, 0).api_version()
        with self.assertRaises(KeyError):
            Build(15, 4).api_version()


class CredentialsTest(unittest.TestCase):
    def test_hash(self):
        # Test that we can use credentials as a dict key
        self.assertEqual(hash(Credentials('a', 'b')), hash(Credentials('a', 'b')))
        self.assertNotEqual(hash(Credentials('a', 'b')), hash(Credentials('a', 'a')))
        self.assertNotEqual(hash(Credentials('a', 'b')), hash(Credentials('b', 'b')))

    def test_equality(self):
        self.assertEqual(Credentials('a', 'b'), Credentials('a', 'b'))
        self.assertNotEqual(Credentials('a', 'b'), Credentials('a', 'a'))
        self.assertNotEqual(Credentials('a', 'b'), Credentials('b', 'b'))

    def test_type(self):
        self.assertEqual(Credentials('a', 'b').type, Credentials.UPN)
        self.assertEqual(Credentials('a@example.com', 'b').type, Credentials.EMAIL)
        self.assertEqual(Credentials('a\\n', 'b').type, Credentials.DOMAIN)


class EWSDateTest(unittest.TestCase):
    def test_ewsdatetime(self):
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.ms_id, 'Romance Standard Time')
        self.assertEqual(tz.ms_name, '(UTC+01:00) Brussels, Copenhagen, Madrid, Paris')

        dt = tz.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        self.assertIsInstance(dt, EWSDateTime)
        self.assertIsInstance(dt.tzinfo, EWSTimeZone)
        self.assertEqual(dt.tzinfo.ms_id, tz.ms_id)
        self.assertEqual(dt.tzinfo.ms_name, tz.ms_name)
        self.assertEqual(str(dt), '2000-01-02 03:04:05+01:00')
        self.assertEqual(
            repr(dt),
            "EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=<DstTzInfo 'Europe/Copenhagen' CET+1:00:00 STD>)"
        )
        self.assertIsInstance(dt + datetime.timedelta(days=1), EWSDateTime)
        self.assertIsInstance(dt - datetime.timedelta(days=1), EWSDateTime)
        self.assertIsInstance(dt - EWSDateTime.now(tz=tz), datetime.timedelta)
        self.assertIsInstance(EWSDateTime.now(tz=tz), EWSDateTime)
        self.assertEqual(dt, EWSDateTime.from_datetime(tz.localize(datetime.datetime(2000, 1, 2, 3, 4, 5))))
        self.assertEqual(dt.ewsformat(), '2000-01-02T03:04:05')
        utc_tz = EWSTimeZone.timezone('UTC')
        self.assertEqual(dt.astimezone(utc_tz).ewsformat(), '2000-01-02T02:04:05Z')
        # Test summertime
        dt = tz.localize(EWSDateTime(2000, 8, 2, 3, 4, 5))
        self.assertEqual(dt.astimezone(utc_tz).ewsformat(), '2000-08-02T01:04:05Z')
        # Test error when tzinfo is set directly
        with self.assertRaises(ValueError):
            EWSDateTime(2000, 1, 1, tzinfo=tz)


class RestrictionTest(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_parse(self):
        r = Restriction.from_source("start > '2016-01-15T13:45:56Z' and (not subject == 'EWS Test')", folder_class=Calendar)
        result = '''\
<m:Restriction>
    <t:And>
        <t:Not>
            <t:IsEqualTo>
                <t:FieldURI FieldURI="item:Subject" />
                <t:FieldURIOrConstant>
                    <t:Constant Value="EWS Test" />
                </t:FieldURIOrConstant>
            </t:IsEqualTo>
        </t:Not>
        <t:IsGreaterThan>
            <t:FieldURI FieldURI="calendar:Start" />
            <t:FieldURIOrConstant>
                <t:Constant Value="2016-01-15T13:45:56Z" />
            </t:FieldURIOrConstant>
        </t:IsGreaterThan>
    </t:And>
</m:Restriction>'''
        self.assertEqual(xml_to_str(r.xml), ''.join(l.lstrip() for l in result.split('\n')))
        # from_source() calls from parser.expr which is a security risk. Make sure stupid things can't happen
        with self.assertRaises(SyntaxError):
            Restriction.from_source('raise Exception()', folder_class=Calendar)

    def test_q(self):
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        start = tz.localize(EWSDateTime(1900, 9, 26, 8, 0, 0))
        end = tz.localize(EWSDateTime(2200, 9, 26, 11, 0, 0))
        result = '''\
<m:Restriction>
    <t:And>
        <t:Or>
            <t:Contains ContainmentComparison="Exact" ContainmentMode="Substring">
                <t:FieldURI FieldURI="item:Categories" />
                <t:Constant Value="FOO" />
            </t:Contains>
            <t:Contains ContainmentComparison="Exact" ContainmentMode="Substring">
                <t:FieldURI FieldURI="item:Categories" />
                <t:Constant Value="BAR" />
            </t:Contains>
        </t:Or>
        <t:IsGreaterThan>
            <t:FieldURI FieldURI="calendar:End" />
            <t:FieldURIOrConstant>
                <t:Constant Value="1900-09-26T07:10:00Z" />
            </t:FieldURIOrConstant>
        </t:IsGreaterThan>
        <t:IsLessThan>
            <t:FieldURI FieldURI="calendar:Start" />
            <t:FieldURIOrConstant>
                <t:Constant Value="2200-09-26T10:00:00Z" />
            </t:FieldURIOrConstant>
        </t:IsLessThan>
    </t:And>
</m:Restriction>'''
        q = Q(Q(categories__contains='FOO') | Q(categories__contains='BAR'), start__lt=end, end__gt=start)
        r = Restriction(q.translate_fields(folder_class=Calendar))
        self.assertEqual(str(r), ''.join(l.lstrip() for l in result.split('\n')))
        # Test empty Q
        q = Q()
        self.assertEqual(q.to_xml(folder_class=Calendar), None)
        with self.assertRaises(ValueError):
            Restriction(q.translate_fields(folder_class=Calendar))

    def test_q_expr(self):
        self.assertEqual(Q().expr(), None)
        self.assertEqual((~Q()).expr(), None)
        self.assertEqual(Q(x=5).expr(), 'x == 5')
        self.assertEqual((~Q(x=5)).expr(), 'x != 5')
        q = (Q(b__contains='a', x__contains=5) | Q(~Q(a__contains='c'), f__gt=3, c=6)) & ~Q(y=9, z__contains='b')
        self.assertEqual(
            q.expr(),
            "((b contains 'a' AND x contains 5) OR (NOT a contains 'c' AND c == 6 AND f > 3)) "
            "AND NOT (y == 9 AND z contains 'b')"
        )


class UtilTest(unittest.TestCase):
    def test_chunkify(self):
        # Test list, tuple, set, range, map and generator
        seq = [1, 2, 3, 4, 5]
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[1, 2], [3, 4], [5]])

        seq = (1, 2, 3, 4, 6, 7, 9)
        self.assertEqual(list(chunkify(seq, chunksize=3)), [(1, 2, 3), (4, 6, 7), (9,)])

        seq = {1, 2, 3, 4, 5}
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[1, 2], [3, 4], [5, ]])

        seq = range(5)
        self.assertEqual(list(chunkify(seq, chunksize=2)), [range(0, 2), range(2, 4), range(4, 5)])

        seq = map(int, range(5))
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[0, 1], [2, 3], [4]])

        seq = (i for i in range(5))
        self.assertEqual(list(chunkify(seq, chunksize=2)), [[0, 1], [2, 3], [4]])

    def test_peek(self):
        # Test peeking into various sequence types

        # tuple
        is_empty, seq = peek(tuple())
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek((1, 2, 3))
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # list
        is_empty, seq = peek([])
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek([1, 2, 3])
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # set
        is_empty, seq = peek(set())
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek({1, 2, 3})
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # range
        is_empty, seq = peek(range(0))
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek(range(1, 4))
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # map
        is_empty, seq = peek(map(int, []))
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek(map(int, [1, 2, 3]))
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

        # generator
        is_empty, seq = peek((i for i in []))
        self.assertEqual((is_empty, list(seq)), (True, []))
        is_empty, seq = peek((i for i in [1, 2, 3]))
        self.assertEqual((is_empty, list(seq)), (False, [1, 2, 3]))

    def test_get_redirect_url(self):
        r = requests.get('https://httpbin.org/redirect-to?url=https://example.com/', allow_redirects=False)
        url, server, has_ssl = get_redirect_url(r)
        self.assertEqual(url, 'https://example.com/')
        self.assertEqual(server, 'example.com')
        self.assertEqual(has_ssl, True)
        r = requests.get('https://httpbin.org/redirect-to?url=http://example.com/', allow_redirects=False)
        url, server, has_ssl = get_redirect_url(r)
        self.assertEqual(url, 'http://example.com/')
        self.assertEqual(server, 'example.com')
        self.assertEqual(has_ssl, False)
        r = requests.get('https://httpbin.org/redirect-to?url=/example', allow_redirects=False)
        url, server, has_ssl = get_redirect_url(r)
        self.assertEqual(url, 'https://httpbin.org/example')
        self.assertEqual(server, 'httpbin.org')
        self.assertEqual(has_ssl, True)
        with self.assertRaises(RelativeRedirect):
            r = requests.get('https://httpbin.org/redirect-to?url=https://example.com', allow_redirects=False)
            get_redirect_url(r, require_relative=True)
        with self.assertRaises(RelativeRedirect):
            r = requests.get('https://httpbin.org/redirect-to?url=/example', allow_redirects=False)
            get_redirect_url(r, allow_relative=False)

    def test_close_connections(self):
        close_connections()


class EWSTest(unittest.TestCase):
    def setUp(self):
        # There's no official Exchange server we can test against, and we can't really provide credentials for our
        # own test server to anyone on the Internet. You need to create your own settings.yml with credentials for
        # your own test server. 'settings.yml.sample' is provided as a template.
        try:
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'settings.yml')) as f:
                settings = load(f)
        except FileNotFoundError:
            print('Skipping %s - no settings.yml file found' % self.__class__.__name__)
            print('Copy settings.yml.sample to settings.yml and enter values for your test server')
            raise unittest.SkipTest('Skipping %s - no settings.yml file found' % self.__class__.__name__)
        self.tz = EWSTimeZone.timezone('Europe/Copenhagen')
        self.categories = ['Test']
        self.config = Configuration(server=settings['server'],
                                    credentials=Credentials(settings['username'], settings['password']),
                                    verify_ssl=settings['verify_ssl'])
        self.account = Account(primary_smtp_address=settings['account'], access_type=DELEGATE, config=self.config)
        self.maxDiff = None

    def random_val(self, field_type):
        if field_type == ExternId:
            return get_random_string(255)
        if field_type == str:
            return get_random_string(255)
        if field_type == BodyType:
            return get_random_string(255)
        if field_type == AnyURI:
            return get_random_url()
        if field_type == [str]:
            return [get_random_string(16) for _ in range(random.randint(1, 4))]
        if field_type == int:
            return get_random_int(0, 256)
        if field_type == Decimal:
            return get_random_decimal(0, 100)
        if field_type == bool:
            return get_random_bool()
        if field_type == EWSDateTime:
            return get_random_datetime()
        if field_type == Email:
            return get_random_email()
        if field_type == Mailbox:
            # email_address must be a real account on the server(?)
            # TODO: Mailbox has multiple optional args, but they must match the server account, so we can't easily test.
            return Mailbox(email_address=self.account.primary_smtp_address)
        if field_type == [Mailbox]:
            # Mailbox must be a real mailbox on the server(?). We're only sure to have one
            return [self.random_val(Mailbox)]
        if field_type == Attendee:
            with_last_response_time = get_random_bool()
            if with_last_response_time:
                return Attendee(mailbox=self.random_val(Mailbox), response_type='Accept',
                                last_response_time=self.random_val(EWSDateTime))
            else:
                return Attendee(mailbox=self.random_val(Mailbox), response_type='Accept')
        if field_type == [Attendee]:
            # Attendee must refer to a real mailbox on the server(?). We're only sure to have one
            return [self.random_val(Attendee)]
        if field_type == EmailAddress:
            return EmailAddress(email=get_random_email())
        if field_type == [EmailAddress]:
            addrs = []
            for label in EmailAddress.LABELS:
                addr = self.random_val(EmailAddress)
                addr.label = label
                addrs.append(addr)
            return addrs
        if field_type == PhysicalAddress:
            return PhysicalAddress(
                street=get_random_string(32), city=get_random_string(32), state=get_random_string(32),
                country=get_random_string(32), zipcode=get_random_string(8))
        if field_type == [PhysicalAddress]:
            addrs = []
            for label in PhysicalAddress.LABELS:
                addr = self.random_val(PhysicalAddress)
                addr.label = label
                addrs.append(addr)
            return addrs
        if field_type == PhoneNumber:
            return PhoneNumber(phone_number=get_random_string(16))
        if field_type == [PhoneNumber]:
            pns = []
            for label in PhoneNumber.LABELS:
                pn = self.random_val(PhoneNumber)
                pn.label = label
                pns.append(pn)
            return pns
        assert False, 'Unknown field type %s' % field_type


class CommonTest(EWSTest):
    def test_credentials(self):
        self.assertEqual(self.account.access_type, DELEGATE)
        self.assertTrue(self.config.protocol.test())

    def test_get_timezones(self):
        ws = GetServerTimeZones(self.config.protocol)
        data = ws.call()
        self.assertAlmostEqual(len(data), 100, delta=10, msg=data)

    def test_get_roomlists(self):
        # The test server is not guaranteed to have any room lists which makes this test less useful
        ws = GetRoomLists(self.config.protocol)
        roomlists = ws.call()
        self.assertEqual(roomlists, [])

    def test_get_rooms(self):
        # The test server is not guaranteed to have any rooms or room lists which makes this test less useful
        roomlist = RoomList(email_address='my.roomlist@example.com')
        ws = GetRooms(self.config.protocol)
        roomlists = ws.call(roomlist=roomlist)
        self.assertEqual(roomlists, [])

    def test_folders(self):
        folders = self.account.folders
        for fld in (Calendar, DeletedItems, Drafts, Inbox, Outbox, SentItems, JunkEmail, Tasks, Contacts):
            self.assertTrue(fld in folders)
        for folder_cls, cls_folders in folders.items():
            for f in cls_folders:
                f.test_access()
        # Test shortcuts
        for f, cls in (
                (self.account.trash, DeletedItems),
                (self.account.drafts, Drafts),
                (self.account.inbox, Inbox),
                (self.account.outbox, Outbox),
                (self.account.sent, SentItems),
                (self.account.junk, JunkEmail),
                (self.account.contacts, Contacts),
                (self.account.tasks, Tasks),
                (self.account.calendar, Calendar),
        ):
            self.assertIsInstance(f, cls)

    def test_getfolders(self):
        folders = self.account.root.get_folders()
        self.assertEqual(len(folders), 61, sorted(f.name for f in folders))

    def test_sessionpool(self):
        # First, empty the calendar
        start = self.tz.localize(EWSDateTime(2011, 10, 12, 8))
        end = self.tz.localize(EWSDateTime(2011, 10, 12, 10))
        self.account.calendar.filter(start__lt=end, end__gt=start, categories__contains=self.categories).delete()
        items = []
        for i in range(75):
            subject = 'Test Subject %s' % i
            item = CalendarItem(start=start, end=end, subject=subject, categories=self.categories)
            items.append(item)
        return_ids = self.account.calendar.bulk_create(items=items)
        self.assertEqual(len(return_ids), len(items))
        ids = self.account.calendar.filter(start__lt=end, end__gt=start, categories__contains=self.categories)\
            .values_list('item_id', 'changekey')
        self.assertEqual(len(ids), len(items))
        items = self.account.calendar.fetch(return_ids)
        for i, item in enumerate(items):
            subject = 'Test Subject %s' % i
            self.assertEqual(item.start, start)
            self.assertEqual(item.end, end)
            self.assertEqual(item.subject, subject)
            self.assertEqual(item.categories, self.categories)
        status = self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)
        self.assertEqual(set(status), {(True, None)})

    def test_magic(self):
        self.assertIn(self.config.protocol.version.api_version, str(self.config.protocol))
        self.assertIn(self.config.credentials.username, str(self.config.credentials))
        self.assertIn(self.account.primary_smtp_address, str(self.account))
        self.assertIn(str(self.account.version.build.major_version), repr(self.account.version))
        repr(self.config)
        repr(self.config.protocol)
        repr(self.account.version)
        # Folders
        repr(self.account.trash)
        repr(self.account.drafts)
        repr(self.account.inbox)
        repr(self.account.outbox)
        repr(self.account.sent)
        repr(self.account.junk)
        repr(self.account.contacts)
        repr(self.account.tasks)
        repr(self.account.calendar)

    def test_configuration(self):
        with self.assertRaises(AttributeError):
            Configuration(credentials=Credentials(username='foo', password='bar'))
        with self.assertRaises(AttributeError):
            Configuration(credentials=Credentials(username='foo', password='bar'),
                          service_endpoint='http://example.com/svc',
                          auth_type='XXX')

    def test_autodiscover(self):
        primary_smtp_address, protocol = discover(email=self.account.primary_smtp_address,
                                                  credentials=self.config.credentials)
        self.assertEqual(primary_smtp_address, self.account.primary_smtp_address)
        self.assertEqual(protocol.service_endpoint.lower(), self.config.protocol.service_endpoint.lower())
        self.assertEqual(protocol.version.build, self.config.protocol.version.build)

    def test_autodiscover_from_account(self):
        from exchangelib.autodiscover import _autodiscover_cache
        _autodiscover_cache.clear()
        account = Account(primary_smtp_address=self.account.primary_smtp_address, credentials=self.config.credentials,
                          autodiscover=True)
        self.assertEqual(account.primary_smtp_address, self.account.primary_smtp_address)
        self.assertEqual(account.protocol.service_endpoint.lower(), self.config.protocol.service_endpoint.lower())
        self.assertEqual(account.protocol.version.build, self.config.protocol.version.build)
        # Make sure cache is full
        self.assertTrue((account.domain, self.config.credentials, True) in _autodiscover_cache)
        # Test that autodiscover works with a full cache
        account = Account(primary_smtp_address=self.account.primary_smtp_address, credentials=self.config.credentials,
                          autodiscover=True)
        self.assertEqual(account.primary_smtp_address, self.account.primary_smtp_address)
        # Test cache manipulation
        key = (account.domain, self.config.credentials, True)
        self.assertTrue(key in _autodiscover_cache)
        del _autodiscover_cache[key]
        self.assertFalse(key in _autodiscover_cache)
        del _autodiscover_cache


class BaseItemTest(EWSTest):
    TEST_FOLDER = None
    ITEM_CLASS = None

    @classmethod
    def setUpClass(cls):
        if cls is BaseItemTest:
            raise unittest.SkipTest("Skip BaseItemTest, it's only for inheritance")
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.test_folder = getattr(self.account, self.TEST_FOLDER)
        self.assertEqual(self.test_folder.DISTINGUISHED_FOLDER_ID, self.TEST_FOLDER)
        self.test_folder.filter(categories__contains=self.categories).delete()

    def tearDown(self):
        self.test_folder.filter(categories__contains=self.categories).delete()

    def get_random_insert_kwargs(self):
        insert_kwargs = {}
        for f in self.ITEM_CLASS.fieldnames():
            if f in self.ITEM_CLASS.readonly_fields():
                # These cannot be created
                continue
            if f == 'resources':
                # The test server doesn't have any resources
                continue
            if f == 'optional_attendees':
                # 'optional_attendees' and 'required_attendees' are mutually exclusive
                insert_kwargs[f] = None
                continue
            if f == 'start':
                insert_kwargs['start'], insert_kwargs['end'] = get_random_datetime_range()
                continue
            if f == 'end':
                continue
            if f == 'due_date':
                # start_date must be before due_date
                insert_kwargs['start_date'], insert_kwargs['due_date'] = get_random_datetime_range()
                continue
            if f == 'start_date':
                continue
            if f == 'status':
                # Start with an incomplete task
                status = get_random_choice(Task.choices_for_field(f) - {Task.COMPLETED})
                insert_kwargs[f] = status
                insert_kwargs['percent_complete'] = Decimal(0) if status == Task.NOT_STARTED else get_random_decimal(0, 100)
                continue
            if f == 'percent_complete':
                continue
            field_type = self.ITEM_CLASS.type_for_field(f)
            if field_type == Choice:
                insert_kwargs[f] = get_random_choice(self.ITEM_CLASS.choices_for_field(f))
                continue
            insert_kwargs[f] = self.random_val(field_type)
        return insert_kwargs

    def get_random_update_kwargs(self, insert_kwargs):
        update_kwargs = {}
        now = UTC_NOW()
        for f in self.ITEM_CLASS.fieldnames():
            if f in self.ITEM_CLASS.readonly_fields():
                # These cannot be changed
                continue
            if f == 'resources':
                # The test server doesn't have any resources
                continue
            field_type = self.ITEM_CLASS.type_for_field(f)
            if isinstance(field_type, list):
                if issubclass(field_type[0], IndexedField):
                    # TODO: We don't know how to update IndexedField types yet
                    continue
            if f == 'start':
                update_kwargs['start'], update_kwargs['end'] = get_random_datetime_range()
                continue
            if f == 'end':
                continue
            if f == 'due_date':
                # start_date must be before due_date, and before complete_date which must be in the past
                d1, d2 = get_random_datetime(end_date=now), get_random_datetime(end_date=now)
                update_kwargs['start_date'], update_kwargs['due_date'] = sorted([d1, d2])
                continue
            if f == 'start_date':
                continue
            if f == 'status':
                # Update task to a completed state. complete_date must be a date in the past, and < than start_date
                update_kwargs[f] = Task.COMPLETED
                update_kwargs['percent_complete'] = Decimal(100)
                continue
            if f == 'percent_complete':
                continue
            if f == 'reminder_is_set' and self.ITEM_CLASS == Task:
                # Task type doesn't allow updating 'reminder_is_set' to True. TODO: Really?
                update_kwargs[f] = False
                continue
            field_type = self.ITEM_CLASS.type_for_field(f)
            if field_type == bool:
                update_kwargs[f] = not(insert_kwargs[f])
                continue
            if field_type == Choice:
                update_kwargs[f] = get_random_choice(self.ITEM_CLASS.choices_for_field(f))
                continue
            if field_type in (Mailbox, [Mailbox], Attendee, [Attendee]):
                if insert_kwargs[f] is None:
                    update_kwargs[f] = self.random_val(field_type)
                else:
                    update_kwargs[f] = None
                continue
            update_kwargs[f] = self.random_val(field_type)
        return update_kwargs

    def get_test_item(self, folder=None, categories=None):
        item_kwargs = self.get_random_insert_kwargs()
        item_kwargs['categories'] = categories or self.categories
        return self.ITEM_CLASS(folder=folder or self.test_folder, **item_kwargs)

    def test_magic(self):
        item = self.get_test_item()
        self.assertIn('item_id', str(item))
        self.assertIn(item.__class__.__name__, repr(item))

    def test_empty_args(self):
        # We allow empty sequences for these methods
        self.assertEqual(self.test_folder.bulk_create(items=[]), [])
        self.assertEqual(self.test_folder.fetch(ids=[]), [])
        self.assertEqual(self.account.bulk_update(items=[]), [])
        self.assertEqual(self.account.bulk_delete(ids=[]), [])

    def test_error_policy(self):
        # Test the is_service_account flag. This is difficult to test thoroughly
        self.account.protocol.credentials.is_service_account = False
        item = self.get_test_item()
        item.subject = get_random_string(16)
        self.test_folder.all()
        self.account.protocol.credentials.is_service_account = True

    def test_queryset_copy(self):
        qs = QuerySet(self.test_folder)
        qs.q = Q()
        qs.only_fields = ('a', 'b')
        qs.order_fields = ('c', 'd')
        qs.reversed = True
        qs.return_format = QuerySet.NONE

        # Initially, immutable items have the same id()
        new_qs = qs.copy()
        self.assertNotEqual(id(qs), id(new_qs))
        self.assertEqual(id(qs.folder), id(new_qs.folder))
        self.assertEqual(id(qs._cache), id(new_qs._cache))
        self.assertEqual(qs._cache, new_qs._cache)
        self.assertNotEqual(id(qs.q), id(new_qs.q))
        self.assertEqual(qs.q, new_qs.q)
        self.assertEqual(id(qs.only_fields), id(new_qs.only_fields))
        self.assertEqual(qs.only_fields, new_qs.only_fields)
        self.assertEqual(id(qs.order_fields), id(new_qs.order_fields))
        self.assertEqual(qs.order_fields, new_qs.order_fields)
        self.assertEqual(id(qs.reversed), id(new_qs.reversed))
        self.assertEqual(qs.reversed, new_qs.reversed)
        self.assertEqual(id(qs.return_format), id(new_qs.return_format))
        self.assertEqual(qs.return_format, new_qs.return_format)

        # Set the same values, forcing a new id()
        new_qs.q = Q()
        new_qs.only_fields = ('a', 'b')
        new_qs.order_fields = ('c', 'd')
        new_qs.reversed = True
        new_qs.return_format = QuerySet.NONE

        self.assertNotEqual(id(qs), id(new_qs))
        self.assertEqual(id(qs.folder), id(new_qs.folder))
        self.assertEqual(id(qs._cache), id(new_qs._cache))
        self.assertEqual(qs._cache, new_qs._cache)
        self.assertNotEqual(id(qs.q), id(new_qs.q))
        self.assertEqual(qs.q, new_qs.q)
        self.assertNotEqual(id(qs.only_fields), id(new_qs.only_fields))
        self.assertEqual(qs.only_fields, new_qs.only_fields)
        self.assertNotEqual(id(qs.order_fields), id(new_qs.order_fields))
        self.assertEqual(qs.order_fields, new_qs.order_fields)
        self.assertEqual(id(qs.reversed), id(new_qs.reversed))  # True and False are singletons in Python
        self.assertEqual(qs.reversed, new_qs.reversed)
        self.assertEqual(id(qs.return_format), id(new_qs.return_format))  # String literals are also singletons
        self.assertEqual(qs.return_format, new_qs.return_format)

        # Set the new values, forcing a new id()
        new_qs.q = Q(foo=5)
        new_qs.only_fields = ('c', 'd')
        new_qs.order_fields = ('e', 'f')
        new_qs.reversed = False
        new_qs.return_format = QuerySet.VALUES

        self.assertNotEqual(id(qs), id(new_qs))
        self.assertEqual(id(qs.folder), id(new_qs.folder))
        self.assertEqual(id(qs._cache), id(new_qs._cache))
        self.assertEqual(qs._cache, new_qs._cache)
        self.assertNotEqual(id(qs.q), id(new_qs.q))
        self.assertNotEqual(qs.q, new_qs.q)
        self.assertNotEqual(id(qs.only_fields), id(new_qs.only_fields))
        self.assertNotEqual(qs.only_fields, new_qs.only_fields)
        self.assertNotEqual(id(qs.order_fields), id(new_qs.order_fields))
        self.assertNotEqual(qs.order_fields, new_qs.order_fields)
        self.assertNotEqual(id(qs.reversed), id(new_qs.reversed))
        self.assertNotEqual(qs.reversed, new_qs.reversed)
        self.assertNotEqual(id(qs.return_format), id(new_qs.return_format))
        self.assertNotEqual(qs.return_format, new_qs.return_format)

    def test_querysets(self):
        self.test_folder.filter(categories__contains=self.categories).delete()
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Item %s' % i
            test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = QuerySet(self.test_folder).filter(categories__contains=self.categories)
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs),
            {('Item 0', 'Test'), ('Item 1', 'Test'), ('Item 2', 'Test'), ('Item 3', 'Test')}
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.none()],
            []
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.filter(subject__startswith='Item 2')],
            [('Item 2', 'Test')]
        )
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs.exclude(subject__startswith='Item 2')),
            {('Item 0', 'Test'), ('Item 1', 'Test'), ('Item 3', 'Test')}
        )
        self.assertEqual(
            set((i.subject, i.categories) for i in qs.only('subject')),
            {('Item 0', None), ('Item 1', None), ('Item 2', None), ('Item 3', None)}
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.order_by('subject')],
            [('Item 0', 'Test'), ('Item 1', 'Test'), ('Item 2', 'Test'), ('Item 3', 'Test')]
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.order_by('subject').reverse()],
            [('Item 3', 'Test'), ('Item 2', 'Test'), ('Item 1', 'Test'), ('Item 0', 'Test')]
        )
        self.assertEqual(
            [i for i in qs.order_by('subject').values('subject')],
            [{'subject': 'Item 0'}, {'subject': 'Item 1'}, {'subject': 'Item 2'}, {'subject': 'Item 3'}]
        )
        self.assertEqual(
            set(i for i in qs.values_list('subject')),
            {('Item 0',), ('Item 1',), ('Item 2',), ('Item 3',)}
        )
        self.assertEqual(
            set(i for i in qs.values_list('subject', flat=True)),
            {'Item 0', 'Item 1', 'Item 2', 'Item 3'}
        )
        self.assertEqual(
            qs.values_list('subject', flat=True).get(subject='Item 2'),
            'Item 2'
        )
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs.exclude(subject__startswith='Item 2')),
            {('Item 0', 'Test'), ('Item 1', 'Test'), ('Item 3', 'Test')}
        )
        # Test that we can sort on a field that we don't want
        self.assertEqual(
            [i.categories[0] for i in qs.only('categories').order_by('subject')],
            ['Test', 'Test', 'Test', 'Test']
        )
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs.iterator()),
            {('Item 0', 'Test'), ('Item 1', 'Test'), ('Item 2', 'Test'), ('Item 3', 'Test')}
        )
        self.assertEqual(qs.get(subject='Item 3').subject, 'Item 3')
        with self.assertRaises(DoesNotExist):
            qs.get(subject='Item XXX')
        with self.assertRaises(MultipleObjectsReturned):
            qs.get(subject__startswith='Item')
        self.assertEqual(qs.count(), 4)
        self.assertEqual(qs.exists(), True)
        self.assertEqual(qs.filter(subject='Test XXX').exists(), False)
        self.assertEqual(
            qs.filter(subject__startswith='Item').delete(),
            [(True, None), (True, None), (True, None), (True, None)]
        )

    def test_finditems(self):
        now = UTC_NOW()

        # Test argument types
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        # No arguments. There may be leftover items in the folder, so just make sure there's at least one.
        self.assertGreaterEqual(
            len(self.test_folder.filter()),
            1
        )
        # Search expr
        self.assertEqual(
            len(self.test_folder.filter("subject == '%s'" % item.subject)),
            1
        )
        # Search expr with Q
        self.assertEqual(
            len(self.test_folder.filter("subject == '%s'" % item.subject, Q())),
            1
        )
        # Search expr with kwargs
        self.assertEqual(
            len(self.test_folder.filter("subject == '%s'" % item.subject, categories__contains=item.categories)),
            1
        )
        # Q object
        self.assertEqual(
            len(self.test_folder.filter(Q(subject=item.subject))),
            1
        )
        # Multiple Q objects
        self.assertEqual(
            len(self.test_folder.filter(Q(subject=item.subject), ~Q(subject=item.subject + 'XXX'))),
            1
        )
        # Multiple Q object and kwargs
        self.assertEqual(
            len(self.test_folder.filter(Q(subject=item.subject), categories__contains=item.categories)),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test categories which are handled specially - only '__contains' and '__in' lookups are supported
        # First, delete any leftovers from last run. tearDown(doesn't do that since we're using non-devault categories)
        ids = self.test_folder.filter(categories__contains=['TestA', 'TestB'])
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)
        item = self.get_test_item(categories=['TestA', 'TestB'])
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(self.test_folder.filter(categories__contains='ci6xahH1')),  # Plain string
            0
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__contains=['ci6xahH1'])),  # Same, but as list
            0
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__contains=['TestA', 'TestC'])),  # One wrong category
            0
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__contains=['TESTA'])),  # Test case insensitivity
            1
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__contains=['testa'])),  # Test case insensitivity
            1
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__contains=['TestA'])),  # Partial
            1
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__contains=item.categories)),  # Exact match
            1
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__in='ci6xahH1')),  # Plain string
            0
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__in=['ci6xahH1'])),  # Same, but as list
            0
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__in=['TestA', 'TestC'])),  # One wrong category
            1
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__in=['TestA'])),  # Partial
            1
        )
        self.assertEqual(
            len(self.test_folder.filter(categories__in=item.categories)),  # Exact match
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        common_qs = self.test_folder.filter(categories__contains=self.categories)
        one_hour = datetime.timedelta(hours=1)
        two_hours = datetime.timedelta(hours=2)
        # Test 'range'
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            len(common_qs.filter(datetime_created__range=(now + one_hour, now + two_hours))),
            0
        )
        self.assertEqual(
            len(common_qs.filter(datetime_created__range=(now - one_hour, now + one_hour))),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test '>'
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            len(common_qs.filter(datetime_created__gt=now + one_hour)),
            0
        )
        self.assertEqual(
            len(common_qs.filter(datetime_created__gt=now - one_hour)),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test '>='
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            len(common_qs.filter(datetime_created__gte=now + one_hour)),
            0
        )
        self.assertEqual(
            len(common_qs.filter(datetime_created__gte=now - one_hour)),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test '<'
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            len(common_qs.filter(datetime_created__lt=now - one_hour)),
            0
        )
        self.assertEqual(
            len(common_qs.filter(datetime_created__lt=now + one_hour)),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test '<='
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            len(common_qs.filter(datetime_created__lte=now - one_hour)),
            0
        )
        self.assertEqual(
            len(common_qs.filter(datetime_created__lte=now + one_hour)),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test '='
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject=item.subject + 'XXX')),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject=item.subject)),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test '!='
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__not=item.subject)),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__not=item.subject + 'XXX')),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test 'exact'
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__iexact=item.subject + 'XXX')),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__exact=item.subject.lower())),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__exact=item.subject.upper())),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__exact=item.subject)),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test 'iexact'
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__iexact=item.subject + 'XXX')),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__iexact=item.subject.lower())),
            1
        )
        self.assertEqual(
            len(common_qs.filter(subject__iexact=item.subject.upper())),
            1
        )
        self.assertEqual(
            len(common_qs.filter(subject__iexact=item.subject)),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test 'contains'
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__contains=item.subject[2:14] + 'XXX')),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__contains=item.subject[2:14].lower())),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__contains=item.subject[2:14].upper())),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__contains=item.subject[2:14])),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test 'icontains'
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__icontains=item.subject[2:14] + 'XXX')),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__icontains=item.subject[2:14].lower())),
            1
        )
        self.assertEqual(
            len(common_qs.filter(subject__icontains=item.subject[2:14].upper())),
            1
        )
        self.assertEqual(
            len(common_qs.filter(subject__icontains=item.subject[2:14])),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test 'startswith'
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__startswith='XXX' + item.subject[:12])),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__startswith=item.subject[:12].lower())),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__startswith=item.subject[:12].upper())),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__startswith=item.subject[:12])),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

        # Test 'istartswith'
        item = self.get_test_item()
        item.subject = get_random_string(16)
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__istartswith='XXX' + item.subject[:12])),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__istartswith=item.subject[:12].lower())),
            1
        )
        self.assertEqual(
            len(common_qs.filter(subject__istartswith=item.subject[:12].upper())),
            1
        )
        self.assertEqual(
            len(common_qs.filter(subject__istartswith=item.subject[:12])),
            1
        )
        self.account.bulk_delete(ids, affected_task_occurrences=ALL_OCCURRENCIES)

    def test_getitems(self):
        item = self.get_test_item()
        self.test_folder.bulk_create(items=[item, item])
        ids = self.test_folder.filter(categories__contains=item.categories)
        items = self.test_folder.fetch(ids=ids)
        for item in items:
            assert isinstance(item, self.ITEM_CLASS)
        self.assertEqual(len(items), 2)
        self.account.bulk_delete(items, affected_task_occurrences=ALL_OCCURRENCIES)

    def test_only_fields(self):
        item = self.get_test_item()
        self.test_folder.bulk_create(items=[item, item])
        items = self.test_folder.filter(categories__contains=item.categories)
        for item in items:
            assert isinstance(item, self.ITEM_CLASS)
            for f in self.ITEM_CLASS.fieldnames():
                self.assertTrue(hasattr(item, f))
                if f in ('optional_attendees', 'required_attendees', 'resources'):
                    continue
                elif f in self.ITEM_CLASS.readonly_fields():
                    continue
                self.assertIsNotNone(getattr(item, f), (f, getattr(item, f)))
        self.assertEqual(len(items), 2)
        only_fields = ('subject', 'body', 'categories')
        items = self.test_folder.filter(categories__contains=item.categories).only(*only_fields)
        for item in items:
            assert isinstance(item, self.ITEM_CLASS)
            for f in self.ITEM_CLASS.fieldnames():
                self.assertTrue(hasattr(item, f))
                if f in only_fields:
                    self.assertIsNotNone(getattr(item, f), (f, getattr(item, f)))
                elif f not in self.ITEM_CLASS.required_fields():
                    self.assertIsNone(getattr(item, f), (f, getattr(item, f)))
        self.assertEqual(len(items), 2)
        self.account.bulk_delete(items, affected_task_occurrences=ALL_OCCURRENCIES)

    def test_save_and_delete(self):
        # Test that we can create, update and delete single items using methods directly on the item
        insert_kwargs = self.get_random_insert_kwargs()
        item = self.ITEM_CLASS(folder=self.test_folder, **insert_kwargs)
        self.assertIsNone(item.item_id)
        self.assertIsNone(item.changekey)

        # Create
        item.save()
        self.assertIsNotNone(item.item_id)
        self.assertIsNotNone(item.changekey)

        # Update
        update_kwargs = self.get_random_update_kwargs(insert_kwargs)
        for k, v in update_kwargs.items():
            setattr(item, k, v)
        item.save()
        updated_item = self.test_folder.fetch(ids=[item])[0]
        for k, v in update_kwargs.items():
            self.assertEqual(getattr(updated_item, k), v, (k, getattr(updated_item, k), v))

        # Hard delete
        item_id = (item.item_id, item.changekey)
        item.delete(affected_task_occurrences=ALL_OCCURRENCIES)
        with self.assertRaises(ErrorItemNotFound):
            # It's gone from the account
            self.test_folder.fetch(ids=[item_id])
            # Really gone, not just changed ItemId
            items = self.test_folder.filter(categories__contains=item.categories)
            self.assertEqual(len(items), 0)

    def test_soft_delete(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        self.account.recoverable_deleted_items.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        item_id = (item.item_id, item.changekey)
        # Soft delete
        item.soft_delete(affected_task_occurrences=ALL_OCCURRENCIES)
        with self.assertRaises(ErrorItemNotFound):
            # It's gone from the test folder
            self.test_folder.fetch(ids=[item_id])
        with self.assertRaises(ErrorItemNotFound):
            # It's gone from the trash folder
            self.account.trash.fetch(ids=[item_id])
        # Really gone, not just changed ItemId
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 0)
        self.assertEqual(len(self.account.trash.filter(categories__contains=item.categories)), 0)
        # But we can find it in the recoverable items folder
        self.assertEqual(len(self.account.recoverable_deleted_items.filter(categories__contains=item.categories)), 1)

    def test_move_to_trash(self):
        # First, empty trash bin
        self.account.trash.all().delete()
        item = self.get_test_item().save()
        item_id = (item.item_id, item.changekey)
        # Move to trash
        item.move_to_trash(affected_task_occurrences=ALL_OCCURRENCIES)
        with self.assertRaises(ErrorItemNotFound):
            # Not in the test folder anymore
            self.test_folder.fetch(ids=[item_id])
        # Really gone, not just changed ItemId
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 0)
        # Test that the item moved to trash
        # TODO: This only works for Messages. Maybe our support for trash can only handle Message objects?
        item = self.account.trash.get(categories__contains=item.categories)
        moved_item = self.account.trash.fetch(ids=[item])[0]
        # The item was copied, so the ItemId has changed. Let's compare the subject instead
        self.assertEqual(item.subject, moved_item.subject)

    def test_item(self):
        # Test insert
        insert_kwargs = self.get_random_insert_kwargs()
        item = self.ITEM_CLASS(**insert_kwargs)
        # Test with generator as argument
        insert_ids = self.test_folder.bulk_create(items=(i for i in [item]))
        self.assertEqual(len(insert_ids), 1)
        assert isinstance(insert_ids[0], tuple)
        find_ids = self.test_folder.filter(categories__contains=item.categories).values_list('item_id', 'changekey')
        self.assertEqual(len(find_ids), 1)
        self.assertEqual(len(find_ids[0]), 2)
        self.assertEqual(insert_ids, list(find_ids))
        # Test with generator as argument
        item = self.test_folder.fetch(ids=(i for i in find_ids))[0]
        for f in self.ITEM_CLASS.fieldnames():
            if f in self.ITEM_CLASS.readonly_fields():
                continue
            if f == 'resources':
                continue
            if isinstance(self.ITEM_CLASS.type_for_field(f), list):
                if not (getattr(item, f) is None and insert_kwargs[f] is None):
                    self.assertSetEqual(set(getattr(item, f)), set(insert_kwargs[f]), (f, repr(item), insert_kwargs))
            else:
                self.assertEqual(getattr(item, f), insert_kwargs[f], (f, repr(item), insert_kwargs))

        # Test update
        update_kwargs = self.get_random_update_kwargs(insert_kwargs)
        update_fieldnames = update_kwargs.keys()
        for k, v in update_kwargs.items():
            setattr(item, k, v)
        # Test with generator as argument
        update_ids = self.account.bulk_update(items=(i for i in [(item, update_fieldnames), ]))
        self.assertEqual(len(update_ids), 1)
        self.assertEqual(len(update_ids[0]), 2, update_ids)
        self.assertEqual(insert_ids[0][0], update_ids[0][0])  # ID should be the same
        self.assertNotEqual(insert_ids[0][1], update_ids[0][1])  # Changekey should not be the same when item is updated
        item = self.test_folder.fetch(update_ids)[0]
        for f in self.ITEM_CLASS.fieldnames():
            if f in self.ITEM_CLASS.readonly_fields():
                continue
            if f == 'resources':
                # The test server doesn't have any resources
                continue
            field_type = self.ITEM_CLASS.type_for_field(f)
            if isinstance(field_type, list):
                if issubclass(field_type[0], IndexedField):
                    # TODO: We don't know how to update IndexedField types yet
                    continue
                if not (getattr(item, f) is None and update_kwargs[f] is None):
                    self.assertSetEqual(set(getattr(item, f)), set(update_kwargs[f]), (f, repr(item), update_kwargs))
            else:
                self.assertEqual(getattr(item, f), update_kwargs[f], (f, repr(item), update_kwargs))

        # Test wiping or removing string, int, Choice and bool fields
        wipe_kwargs = {}
        for f in self.ITEM_CLASS.fieldnames():
            if f in self.ITEM_CLASS.required_fields():
                # These cannot be deleted
                continue
            if f in self.ITEM_CLASS.readonly_fields():
                # These cannot be changed
                continue
            field_type = self.ITEM_CLASS.type_for_field(f)
            if field_type == ExternId:
                wipe_kwargs[f] = ''
            elif field_type in (bool, str, int, Choice, Email):
                wipe_kwargs[f] = None
        update_fieldnames = wipe_kwargs.keys()
        for k, v in wipe_kwargs.items():
            setattr(item, k, v)
        wipe_ids = self.account.bulk_update([(item, update_fieldnames), ])
        self.assertEqual(len(wipe_ids), 1)
        self.assertEqual(len(wipe_ids[0]), 2, wipe_ids)
        self.assertEqual(insert_ids[0][0], wipe_ids[0][0])  # ID should be the same
        self.assertNotEqual(insert_ids[0][1], wipe_ids[0][1])  # Changekey should not be the same when item is updated
        item = self.test_folder.fetch(wipe_ids)[0]
        for f in self.ITEM_CLASS.fieldnames():
            if f in self.ITEM_CLASS.required_fields():
                continue
            if f in self.ITEM_CLASS.readonly_fields():
                continue
            field_type = self.ITEM_CLASS.type_for_field(f)
            if field_type in (str, ExternId, bool, int, Choice, Email):
                self.assertEqual(getattr(item, f), wipe_kwargs[f], (f, repr(item), insert_kwargs))

        # Test extern_id = None, which deletes the extended property entirely
        extern_id = None
        item.extern_id = extern_id
        wipe2_ids = self.account.bulk_update([(item, ['extern_id']), ])
        self.assertEqual(len(wipe2_ids), 1)
        self.assertEqual(len(wipe2_ids[0]), 2, wipe2_ids)
        self.assertEqual(insert_ids[0][0], wipe2_ids[0][0])  # ID should be the same
        self.assertNotEqual(insert_ids[0][1], wipe2_ids[0][1])  # Changekey should not be the same when item is updated
        item = self.test_folder.fetch(wipe2_ids)[0]
        self.assertEqual(item.extern_id, extern_id)

        # Remove test item. Test with generator as argument
        status = self.account.bulk_delete(ids=(i for i in wipe2_ids), affected_task_occurrences=ALL_OCCURRENCIES)
        self.assertEqual(status, [(True, None)])

    def test_export_and_upload(self):
        # 15 new items which we will attempt to export and re-upload
        items = [self.get_test_item(self.test_folder).save() for _ in range(15)]
        ids = [ItemId(i.item_id, i.changekey) for i in items]
        # re-fetch items because there will be some extra fields added by the
        #  server
        items = self.test_folder.fetch(ids)

        # Try exporting and making sure we get the right response
        export_results = self.account.export(ids)
        self.assertEqual(len(items), len(export_results))
        for original_id, result in zip(ids, export_results):
            self.assertEqual(original_id, result[0])
            self.assertIsInstance(result[1], str)

        # Try reuploading our results
        upload_results = self.account.upload([data for _, data in export_results],
                                             [self.test_folder for _ in export_results])
        self.assertEqual(len(items), len(upload_results))
        for result in upload_results:
            # Must be a completely new ItemId
            self.assertIsInstance(result, ItemId)
            self.assertNotIn(result, ids)

        # Check the items uploaded are the same as the original items
        def to_dict(item):
            dict_item = {}
            # fieldnames is everything except the ID so we'll use it to
            #  compare
            for attribute in item.fieldnames():
                # datetime_created and last_modified_time aren't copied, but
                # instead are added to the new item after uploading
                if attribute not in {'datetime_created', 'last_modified_time'}:
                    dict_item[attribute] = getattr(item, attribute)
            return dict_item

        uploaded_items = self.test_folder.fetch(upload_results)
        original_items = [to_dict(item) for item in items]
        for item in uploaded_items:
            dict_item = to_dict(item)
            try:
                original_items.remove(dict_item)
            except ValueError:
                raise AssertionError("Uploaded item: '%s' not equal to any of the items we originally inserted" % repr(item))

        # Clean up after yourself
        self.account.bulk_delete(ids=upload_results, affected_task_occurrences=ALL_OCCURRENCIES)
        self.account.bulk_delete(ids=ids, affected_task_occurrences=ALL_OCCURRENCIES)

    def test_export_with_error(self):
        # 15 new items which we will attempt to export and re-upload
        items = [self.get_test_item(self.test_folder).save() for _ in range(15)]
        ids = [ItemId(i.item_id, i.changekey) for i in items]
        # Delete one of the items, this will cause an error
        items[3].delete(affected_task_occurrences=ALL_OCCURRENCIES)

        export_results = self.account.export(ids)
        self.assertEqual(len(items), len(export_results))
        for idx, (original_ids, result) in enumerate(zip(ids, export_results)):
            self.assertIsInstance(result, tuple)
            self.assertEqual(original_ids, result[0])
            if idx == 3:
                # If it is the one returning the error
                self.assertIsInstance(result[1], tuple)
                self.assertEqual(result[1][0], False)
                self.assertIsInstance(result[1][1], str)
            else:
                self.assertIsInstance(result[1], str)

class CalendarTest(BaseItemTest):
    TEST_FOLDER = 'calendar'
    ITEM_CLASS = CalendarItem


class MessagesTest(BaseItemTest):
    # Just test one of the Message-type folders
    TEST_FOLDER = 'inbox'
    ITEM_CLASS = Message

    def test_send(self):
        # Test that we can send (only) Message items
        item = self.get_test_item()
        item.send()
        self.assertIsNone(item.item_id)
        self.assertIsNone(item.changekey)
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 0)

    def test_send_and_save(self):
        # Test that we can send_and_save Message items
        item = self.get_test_item()
        item.send_and_save()
        self.assertIsNone(item.item_id)
        self.assertIsNone(item.changekey)
        time.sleep(1)  # Requests are supposed to be transactional, but apparently not...
        ids = self.test_folder.filter(categories__contains=item.categories).values_list('item_id', 'changekey')
        self.assertEqual(len(ids), 1)
        item.item_id, item.changekey = ids[0]
        item.delete()


class TasksTest(BaseItemTest):
    TEST_FOLDER = 'tasks'
    ITEM_CLASS = Task


class ContactsTest(BaseItemTest):
    TEST_FOLDER = 'contacts'
    ITEM_CLASS = Contact


def get_random_bool():
    return bool(random.randint(0, 1))


def get_random_int(min=0, max=2147483647):
    return random.randint(min, max)


def get_random_decimal(min=0, max=100):
    # Return a random decimal with 6-digit precision
    major = get_random_int(min, max)
    minor = 0 if major == max else get_random_int(0, 999999)
    return Decimal('%s.%s' % (major, minor))


def get_random_choice(choices):
    return random.sample(choices, 1)[0]


def get_random_string(length, spaces=True, special=True):
    chars = string.ascii_letters + string.digits
    if special:
        chars += ':.-_'
    if spaces:
        chars += ' '
    # We want random strings that don't end in spaces - Exchange strips these
    res = ''.join(map(lambda i: random.choice(chars), range(length))).strip()
    if len(res) < length:
        # If strip() made the string shorter, make sure to fill it up
        res += get_random_string(length - len(res), spaces=False)
    return res


def get_random_url():
    path_len = random.randint(1, 16)
    domain_len = random.randint(1, 30)
    tld_len = random.randint(2, 4)
    return 'http://%s.%s/%s.html' % tuple(map(
        lambda i: get_random_string(i, spaces=False, special=False).lower(),
        (domain_len, tld_len, path_len)
    ))


def get_random_email():
    account_len = random.randint(1, 6)
    domain_len = random.randint(1, 30)
    tld_len = random.randint(2, 4)
    return '%s@%s.%s' % tuple(map(
        lambda i: get_random_string(i, spaces=False, special=False).lower(),
        (account_len, domain_len, tld_len)
    ))


def get_random_date(start_date=datetime.date(1900, 1, 1), end_date=datetime.date(2100, 1, 1)):
    return EWSDate.fromordinal(random.randint(start_date.toordinal(), end_date.toordinal()))


def get_random_datetime(start_date=datetime.date(1900, 1, 1), end_date=datetime.date(2100, 1, 1)):
    # Create a random datetime with minute precision
    random_date = get_random_date(start_date=start_date, end_date=end_date)
    random_datetime = datetime.datetime.combine(random_date, datetime.time.min) \
                      + datetime.timedelta(minutes=random.randint(0, 60*24))
    return UTC.localize(EWSDateTime.from_datetime(random_datetime))


def get_random_datetime_range():
    # Create two random datetimes. Calendar items raise ErrorCalendarDurationIsTooLong if duration is > 5 years.
    dt1 = get_random_datetime()
    dt2 = dt1 + datetime.timedelta(minutes=random.randint(0, 60*24*365*5))
    return dt1, dt2


if __name__ == '__main__':
    import logging
    # loglevel = logging.DEBUG
    loglevel = logging.WARNING
    logging.basicConfig(level=loglevel)
    logging.getLogger('exchangelib').setLevel(loglevel)
    unittest.main()
