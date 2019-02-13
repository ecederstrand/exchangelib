# coding=utf-8
from collections import namedtuple
import datetime
from decimal import Decimal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import glob
from itertools import chain
import io
from keyword import kwlist
import logging
import os
import pickle
import random
import socket
import string
import tempfile
import time
import unittest
import unittest.util
import warnings

from dateutil.relativedelta import relativedelta
import dns.resolver
import psutil
import pytz
import requests
import requests_mock
from six import PY2
from yaml import safe_load

from exchangelib import close_connections
from exchangelib.account import Account, SAVE_ONLY, SEND_ONLY, SEND_AND_SAVE_COPY
from exchangelib.attachments import FileAttachment, ItemAttachment, AttachmentId
from exchangelib.autodiscover import AutodiscoverProtocol, discover
import exchangelib.autodiscover
from exchangelib.configuration import Configuration
from exchangelib.credentials import DELEGATE, IMPERSONATION, Credentials, ServiceAccount
from exchangelib.errors import RelativeRedirect, ErrorItemNotFound, ErrorInvalidOperation, AutoDiscoverRedirect, \
    AutoDiscoverCircularRedirect, AutoDiscoverFailed, ErrorNonExistentMailbox, UnknownTimeZone, \
    ErrorNameResolutionNoResults, TransportError, RedirectError, CASError, RateLimitError, UnauthorizedError, \
    ErrorInvalidChangeKey, ErrorInvalidIdMalformed, ErrorContainsFilterWrongType, ErrorAccessDenied, \
    ErrorFolderNotFound, ErrorInvalidRequest, SOAPError, ErrorInvalidServerVersion, NaiveDateTimeNotAllowed, \
    AmbiguousTimeError, NonExistentTimeError, ErrorUnsupportedPathForQuery, ErrorInvalidPropertyForOperation, \
    ErrorInvalidValueForProperty, ErrorPropertyUpdate, ErrorDeleteDistinguishedFolder, \
    ErrorNoPublicFolderReplicaAvailable, ErrorServerBusy, ErrorInvalidPropertySet, ErrorObjectTypeChanged, \
    ErrorInvalidIdMalformed
from exchangelib.ewsdatetime import EWSDateTime, EWSDate, EWSTimeZone, UTC, UTC_NOW
from exchangelib.extended_properties import ExtendedProperty, ExternId
from exchangelib.fields import BooleanField, IntegerField, DecimalField, TextField, EmailAddressField, URIField, \
    ChoiceField, BodyField, DateTimeField, Base64Field, PhoneNumberField, EmailAddressesField, TimeZoneField, \
    PhysicalAddressField, ExtendedPropertyField, MailboxField, AttendeesField, AttachmentField, CharListField, \
    MailboxListField, Choice, FieldPath, EWSElementField, CultureField, DateField, EnumField, EnumListField, IdField, \
    CharField, TextListField, MONDAY, WEDNESDAY, FEBRUARY, AUGUST, SECOND, LAST, DAY, WEEK_DAY, WEEKEND_DAY
from exchangelib.folders import Calendar, DeletedItems, Drafts, Inbox, Outbox, SentItems, JunkEmail, Messages, Tasks, \
    Contacts, Folder, RecipientCache, GALContacts, System, AllContacts, MyContactsExtended, Reminders, Favorites, \
    AllItems, ConversationSettings, Friends, RSSFeeds, Sharing, IMContactList, QuickContacts, Journal, Notes, \
    SyncIssues, MyContacts, ToDoSearch, FolderCollection, DistinguishedFolderId
from exchangelib.indexed_properties import EmailAddress, PhysicalAddress, PhoneNumber, \
    SingleFieldIndexedElement, MultiFieldIndexedElement
from exchangelib.items import Item, CalendarItem, Message, Contact, Task, DistributionList, Persona
from exchangelib.properties import Attendee, Mailbox, RoomList, MessageHeader, Room, ItemId, Member, EWSElement, Body, \
    HTMLBody, TimeZone, FreeBusyView, PersonaId, UID, InvalidField, InvalidFieldForVersion
from exchangelib.protocol import BaseProtocol, Protocol, NoVerifyHTTPAdapter
from exchangelib.queryset import QuerySet, DoesNotExist, MultipleObjectsReturned
from exchangelib.recurrence import Recurrence, AbsoluteYearlyPattern, RelativeYearlyPattern, AbsoluteMonthlyPattern, \
    RelativeMonthlyPattern, WeeklyPattern, DailyPattern, FirstOccurrence, LastOccurrence, Occurrence, \
    NoEndPattern, EndDatePattern, NumberedPattern, ExtraWeekdaysField
from exchangelib.restriction import Restriction, Q
from exchangelib.settings import OofSettings
from exchangelib.services import GetServerTimeZones, GetRoomLists, GetRooms, GetAttachment, ResolveNames, GetPersona, \
    GetFolder, TNS
from exchangelib.transport import NOAUTH, BASIC, DIGEST, NTLM, wrap, _get_auth_method_from_response
from exchangelib.util import chunkify, peek, get_redirect_url, to_xml, BOM_UTF8, get_domain, value_to_xml_text, \
    post_ratelimited, create_element, CONNECTION_ERRORS, PrettyXmlHandler, xml_to_str, ParseError
from exchangelib.version import Build, Version, EXCHANGE_2007, EXCHANGE_2010, EXCHANGE_2013
from exchangelib.winzone import generate_map, CLDR_TO_MS_TIMEZONE_MAP

if PY2:
    FileNotFoundError = IOError

mock_account = namedtuple('mock_account', ('protocol', 'version'))
mock_protocol = namedtuple('mock_protocol', ('version', 'service_endpoint'))
mock_version = namedtuple('mock_version', ('build',))

# Show full repr() output for object instances in unittest error messages
unittest.util._MAX_LENGTH = 2000


def mock_post(url, status_code, headers, text=''):
    req = namedtuple('request', ['headers'])(headers={})
    c = text.encode('utf-8')
    return lambda **kwargs: namedtuple(
        'response', ['status_code', 'headers', 'text', 'content', 'request', 'history', 'url']
    )(status_code=status_code, headers=headers, text=text, content=c, request=req, history=None, url=url)


def mock_session_exception(exc_cls):
    def raise_exc(**kwargs):
        raise exc_cls()

    return raise_exc


class MockResponse(object):
    def __init__(self, c):
        self.c = c

    def iter_content(self):
        return self.c


class BuildTest(unittest.TestCase):
    def test_magic(self):
        with self.assertRaises(ValueError):
            Build(7, 0)
        self.assertEqual(str(Build(9, 8, 7, 6)), '9.8.7.6')

    def test_compare(self):
        self.assertEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 2))
        self.assertNotEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 3))
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
        with self.assertRaises(ValueError):
            Build(16, 0).api_version()
        with self.assertRaises(ValueError):
            Build(15, 4).api_version()


class VersionTest(unittest.TestCase):
    def test_default_api_version(self):
        # Test that a version gets a reasonable api_version value if we don't set one explicitly
        version = Version(build=Build(15, 1, 2, 3))
        self.assertEqual(version.api_version, 'Exchange2016')

    @requests_mock.mock()  # Just to make sure we don't make any requests
    def test_from_response(self, m):
        # Test fallback to suggested api_version value when there is a version mismatch and response version is fishy
        version = Version.from_response(
            'Exchange2007',
            b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1" Version="V2016_10_10"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>
</s:Envelope>'''
        )
        self.assertEqual(version.api_version, EXCHANGE_2007.api_version())
        self.assertEqual(version.api_version, 'Exchange2007')
        self.assertEqual(version.build, Build(15, 1, 845, 22))

        # Test that override the suggested version if the response version is not fishy
        version = Version.from_response(
            'Exchange2013',
            b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1" Version="HELLO_FROM_EXCHANGELIB"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>
</s:Envelope>'''
        )
        self.assertEqual(version.api_version, 'HELLO_FROM_EXCHANGELIB')

        # Test that we override the suggested version with the version deduced from the build number if a version is not
        # present in the response
        version = Version.from_response(
            'Exchange2013',
            b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>
</s:Envelope>'''
        )
        self.assertEqual(version.api_version, 'Exchange2016')

        # Test that we use the version deduced from the build number when a version is not present in the response and
        # there was no suggested version.
        version = Version.from_response(
            None,
            b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Header>
    <h:ServerVersionInfo
        MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>
</s:Envelope>'''
        )
        self.assertEqual(version.api_version, 'Exchange2016')

        # Test various parse failures
        with self.assertRaises(TransportError):
            Version.from_response(
                'Exchange2013',
                b'XXX'
            )
        with self.assertRaises(TransportError):
            Version.from_response(
                'Exchange2013',
                b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
</s:Envelope>'''
            )
        with self.assertRaises(TransportError):
            Version.from_response(
                'Exchange2013',
                b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Header>
</s:Header>
</s:Envelope>'''
            )
        with self.assertRaises(TransportError):
            Version.from_response(
                'Exchange2013',
                b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Header>
    <h:ServerVersionInfo MajorBuildNumber="845" MajorVersion="15" Version="V2016_10_10"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"/>
</s:Header>
</s:Envelope>'''
            )


class ConfigurationTest(unittest.TestCase):
    def test_magic(self):
        config = Configuration(
            server='example.com',
            has_ssl=True,
            credentials=Credentials('foo', 'bar'),
            auth_type=NTLM,
            version=Version(build=Build(15, 1, 2, 3), api_version='foo'),
        )
        # Just test that these work
        str(config)
        repr(config)

    @requests_mock.mock()  # Just to make sure we don't make any requests
    def test_hardcode_all(self, m):
        # Test that we can hardcode everything without having a working server. This is useful if neither tasting or
        # guessing missing values works.
        Configuration(
            server='example.com',
            has_ssl=True,
            credentials=Credentials('foo', 'bar'),
            auth_type=NTLM,
            version=Version(build=Build(15, 1, 2, 3), api_version='foo'),
        )


class ProtocolTest(unittest.TestCase):

    @requests_mock.mock()
    def test_session(self, m):
        m.get('https://example.com/EWS/types.xsd', status_code=200)
        protocol = Protocol(service_endpoint='https://example.com/Foo.asmx', credentials=Credentials('A', 'B'),
                            auth_type=NTLM, version=Version(Build(15, 1)))
        session = protocol.create_session()
        new_session = protocol.renew_session(session)
        self.assertNotEqual(id(session), id(new_session))

    @requests_mock.mock()
    def test_protocol_instance_caching(self, m):
        # Verify that we get the same Protocol instance for the same combination of (endpoint, credentials)
        m.get('https://example.com/EWS/types.xsd', status_code=200)
        base_p = Protocol(service_endpoint='https://example.com/Foo.asmx', credentials=Credentials('A', 'B'),
                          auth_type=NTLM, version=Version(Build(15, 1)))

        for i in range(10):
            p = Protocol(service_endpoint='https://example.com/Foo.asmx', credentials=Credentials('A', 'B'),
                         auth_type=NTLM, version=Version(Build(15, 1)))
            self.assertEqual(base_p, p)
            self.assertEqual(id(base_p), id(p))
            self.assertEqual(hash(base_p), hash(p))
            self.assertEqual(id(base_p.thread_pool), id(p.thread_pool))
            self.assertEqual(id(base_p._session_pool), id(p._session_pool))

    def test_close(self):
        proc = psutil.Process()
        ip_addresses = {info[4][0] for info in socket.getaddrinfo(
            'example.com', 80, socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP
        )}
        self.assertGreater(len(ip_addresses), 0)
        protocol = Protocol(service_endpoint='http://example.com', credentials=Credentials('A', 'B'),
                            auth_type=NOAUTH, version=Version(Build(15, 1)))
        session = protocol.get_session()
        session.get('http://example.com')
        self.assertEqual(len({p.raddr[0] for p in proc.connections() if p.raddr[0] in ip_addresses}), 1)
        protocol.release_session(session)
        protocol.close()
        self.assertEqual(len({p.raddr[0] for p in proc.connections() if p.raddr[0] in ip_addresses}), 0)


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


class EWSDateTimeTest(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_super_methods(self):
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        self.assertIsInstance(EWSDateTime.now(), EWSDateTime)
        self.assertIsInstance(EWSDateTime.now(tz=tz), EWSDateTime)
        self.assertIsInstance(EWSDateTime.utcnow(), EWSDateTime)
        self.assertIsInstance(EWSDateTime.fromtimestamp(123456789), EWSDateTime)
        self.assertIsInstance(EWSDateTime.fromtimestamp(123456789, tz=tz), EWSDateTime)
        self.assertIsInstance(EWSDateTime.utcfromtimestamp(123456789), EWSDateTime)

    def test_ewstimezone(self):
        # Test autogenerated translations
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.zone, 'Europe/Copenhagen')
        self.assertEqual(tz.ms_id, 'Romance Standard Time')
        # self.assertEqual(EWSTimeZone.timezone('Europe/Copenhagen').ms_name, '')  # EWS works fine without the ms_name

        # Test localzone()
        tz = EWSTimeZone.localzone()
        self.assertIsInstance(tz, EWSTimeZone)

        # Test common helpers
        tz = EWSTimeZone.timezone('UTC')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.zone, 'UTC')
        self.assertEqual(tz.ms_id, 'UTC')
        tz = EWSTimeZone.timezone('GMT')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.zone, 'GMT')
        self.assertEqual(tz.ms_id, 'UTC')

        # Test mapper contents. Latest map from unicode.org has 394 entries
        self.assertGreater(len(EWSTimeZone.PYTZ_TO_MS_MAP), 300)
        for k, v in EWSTimeZone.PYTZ_TO_MS_MAP.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, tuple)
            self.assertEqual(len(v),2)
            self.assertIsInstance(v[0], str)

        # Test timezone unknown by pytz
        with self.assertRaises(UnknownTimeZone):
            EWSTimeZone.timezone('UNKNOWN')

        # Test timezone known by pytz but with no Winzone mapping
        tz = pytz.timezone('Africa/Tripoli')
        # This hack smashes the pytz timezone cache. Don't reuse the original timezone name for other tests
        tz.zone = 'UNKNOWN'
        with self.assertRaises(UnknownTimeZone):
            EWSTimeZone.from_pytz(tz)

    def test_localize(self):
        # Test some cornercases around DST
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        self.assertEqual(
            str(tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0))),
            '2023-10-29 02:36:00+01:00'
        )
        with self.assertRaises(AmbiguousTimeError):
            tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0), is_dst=None)
        self.assertEqual(
            str(tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0), is_dst=True)),
            '2023-10-29 02:36:00+02:00'
        )
        self.assertEqual(
            str(tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0))),
            '2023-03-26 02:36:00+01:00'
        )
        with self.assertRaises(NonExistentTimeError):
            tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0), is_dst=None)
        self.assertEqual(
            str(tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0), is_dst=True)),
            '2023-03-26 02:36:00+02:00'
        )

    def test_ewsdatetime(self):
        # Test a static timezone
        tz = EWSTimeZone.timezone('Etc/GMT-5')
        dt = tz.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        self.assertIsInstance(dt, EWSDateTime)
        self.assertIsInstance(dt.tzinfo, EWSTimeZone)
        self.assertEqual(dt.tzinfo.ms_id, tz.ms_id)
        self.assertEqual(dt.tzinfo.ms_name, tz.ms_name)
        self.assertEqual(str(dt), '2000-01-02 03:04:05+05:00')
        self.assertEqual(
            repr(dt),
            "EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=<StaticTzInfo 'Etc/GMT-5'>)"
        )

        # Test a DST timezone
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
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

        # Test from_string
        with self.assertRaises(NaiveDateTimeNotAllowed):
            EWSDateTime.from_string('2000-01-02T03:04:05')
        self.assertEqual(
            EWSDateTime.from_string('2000-01-02T03:04:05+01:00'),
            UTC.localize(EWSDateTime(2000, 1, 2, 2, 4, 5))
        )
        self.assertEqual(
            EWSDateTime.from_string('2000-01-02T03:04:05Z'),
            UTC.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        )
        self.assertIsInstance(EWSDateTime.from_string('2000-01-02T03:04:05+01:00'), EWSDateTime)
        self.assertIsInstance(EWSDateTime.from_string('2000-01-02T03:04:05Z'), EWSDateTime)

        # Test addition, subtraction, summertime etc
        self.assertIsInstance(dt + datetime.timedelta(days=1), EWSDateTime)
        self.assertIsInstance(dt - datetime.timedelta(days=1), EWSDateTime)
        self.assertIsInstance(dt - EWSDateTime.now(tz=tz), datetime.timedelta)
        self.assertIsInstance(EWSDateTime.now(tz=tz), EWSDateTime)
        self.assertEqual(dt, EWSDateTime.from_datetime(tz.localize(datetime.datetime(2000, 1, 2, 3, 4, 5))))
        self.assertEqual(dt.ewsformat(), '2000-01-02T03:04:05+01:00')
        utc_tz = EWSTimeZone.timezone('UTC')
        self.assertEqual(dt.astimezone(utc_tz).ewsformat(), '2000-01-02T02:04:05Z')
        # Test summertime
        dt = tz.localize(EWSDateTime(2000, 8, 2, 3, 4, 5))
        self.assertEqual(dt.astimezone(utc_tz).ewsformat(), '2000-08-02T01:04:05Z')
        # Test normalize, for completeness
        self.assertEqual(tz.normalize(dt).ewsformat(), '2000-08-02T03:04:05+02:00')
        self.assertEqual(utc_tz.normalize(dt, is_dst=True).ewsformat(), '2000-08-02T01:04:05Z')

        # Test in-place add and subtract
        dt = tz.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        dt += datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDateTime)
        self.assertEqual(dt, tz.localize(EWSDateTime(2000, 1, 3, 3, 4, 5)))
        dt = tz.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        dt -= datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDateTime)
        self.assertEqual(dt, tz.localize(EWSDateTime(2000, 1, 1, 3, 4, 5)))

    def test_generate(self):
        try:
            self.assertDictEqual(generate_map(), CLDR_TO_MS_TIMEZONE_MAP)
        except CONNECTION_ERRORS:
            # generate_map() requires access to unicode.org, which may be unavailable. Don't fail test, since this is
            # out of our control.
            pass

    def test_ewsdate(self):
        self.assertEqual(EWSDate(2000, 1, 1).ewsformat(), '2000-01-01')
        self.assertEqual(EWSDate.from_string('2000-01-01'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01Z'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01+01:00'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01-01:00'), EWSDate(2000, 1, 1))
        self.assertIsInstance(EWSDate(2000, 1, 2) - EWSDate(2000, 1, 1), datetime.timedelta)
        self.assertIsInstance(EWSDate(2000, 1, 2) + datetime.timedelta(days=1), EWSDate)
        self.assertIsInstance(EWSDate(2000, 1, 2) - datetime.timedelta(days=1), EWSDate)

        # Test in-place add and subtract
        dt = EWSDate(2000, 1, 2)
        dt += datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDate)
        self.assertEqual(dt, EWSDate(2000, 1, 3))
        dt = EWSDate(2000, 1, 2)
        dt -= datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDate)
        self.assertEqual(dt, EWSDate(2000, 1, 1))


class PropertiesTest(unittest.TestCase):
    def test_uid(self):
        # Test translation of calendar UIDs. See #453
        self.assertEqual(
            UID('261cbc18-1f65-5a0a-bd11-23b1e224cc2f'),
            b'\x04\x00\x00\x00\x82\x00\xe0\x00t\xc5\xb7\x10\x1a\x82\xe0\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x001\x00\x00\x00vCal-Uid\x01\x00\x00\x00261cbc18-1f65-5a0a-bd11-23b1e224cc2f\x00'
        )

    def test_internet_message_headers(self):
        # Message headers are read-only, and an integration test is difficult because we can't reliably AND quickly
        # generate emails that pass through some relay server that adds headers. Create a unit test instead.
        payload = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:InternetMessageHeaders>
        <t:InternetMessageHeader HeaderName="Received">from foo by bar</t:InternetMessageHeader>
        <t:InternetMessageHeader HeaderName="DKIM-Signature">Hello from DKIM</t:InternetMessageHeader>
        <t:InternetMessageHeader HeaderName="MIME-Version">1.0</t:InternetMessageHeader>
        <t:InternetMessageHeader HeaderName="X-Mailer">Contoso Mail</t:InternetMessageHeader>
        <t:InternetMessageHeader HeaderName="Return-Path">foo@example.com</t:InternetMessageHeader>
    </t:InternetMessageHeaders>
</Envelope>'''
        headers_elem = to_xml(payload).find('{%s}InternetMessageHeaders' % TNS)
        headers = {}
        for elem in headers_elem.findall('{%s}InternetMessageHeader' % TNS):
            header = MessageHeader.from_xml(elem=elem, account=None)
            headers[header.name] = header.value
        self.assertDictEqual(
            headers,
            {
                'Received': 'from foo by bar',
                'DKIM-Signature': 'Hello from DKIM',
                'MIME-Version': '1.0',
                'X-Mailer': 'Contoso Mail',
                'Return-Path': 'foo@example.com',
            }
        )

    def test_physical_address(self):
        # Test that we can enter an integer zipcode and that it's converted to a string by clean()
        zipcode = 98765
        addr = PhysicalAddress(zipcode=zipcode)
        addr.clean()
        self.assertEqual(addr.zipcode, str(zipcode))

    def test_invalid_kwargs(self):
        with self.assertRaises(AttributeError):
            Mailbox(foo='XXX')

    def test_invalid_field(self):
        test_field = Item.get_field_by_fieldname(fieldname='text_body')
        self.assertIsInstance(test_field, TextField)
        self.assertEqual(test_field.name, 'text_body')

        with self.assertRaises(InvalidField):
            Item.get_field_by_fieldname(fieldname='xxx')

        Item.validate_field(field=test_field, version=None)
        with self.assertRaises(InvalidFieldForVersion) as e:
            Item.validate_field(field=test_field, version=Version(build=EXCHANGE_2010))
        self.assertEqual(
            e.exception.args[0],
            "Field 'text_body' is not supported on server version Build=14.0.0.0, API=Exchange2010, Fullname=Microsoft "
            "Exchange Server 2010 (supported from: 15.0.0.0, deprecated from: None)"
        )

    def test_add_field(self):
        field = TextField('foo', field_uri='bar')
        Item.add_field(field, insert_after='subject')
        self.assertEqual(Item.get_field_by_fieldname('foo'), field)
        Item.remove_field(field)

    def test_itemid_equality(self):
        self.assertEqual(ItemId('X', 'Y'), ItemId('X', 'Y'))
        self.assertNotEqual(ItemId('X', 'Y'), ItemId('X', 'Z'))
        self.assertNotEqual(ItemId('Z', 'Y'), ItemId('X', 'Y'))
        self.assertNotEqual(ItemId('X', 'Y'), ItemId('Z', 'Z'))
        self.assertNotEqual(ItemId('X', 'Y'), None)

    def test_mailbox(self):
        mbx = Mailbox(name='XXX')
        with self.assertRaises(ValueError):
            mbx.clean()  # Must have either item_id or email_address set
        mbx = Mailbox(email_address='XXX')
        self.assertEqual(hash(mbx), hash('xxx'))
        mbx.item_id = 'YYY'
        self.assertEqual(hash(mbx), hash('YYY'))  # If we have an item_id, use that for uniqueness

    def test_body(self):
        # Test that string formatting a Body and HTMLBody instance works and keeps the type
        self.assertEqual(str(Body('foo')), 'foo')
        self.assertEqual(str(Body('%s') % 'foo'), 'foo')
        self.assertEqual(str(Body('{}').format('foo')), 'foo')

        self.assertIsInstance(Body('foo'), Body)
        self.assertIsInstance(Body('') + 'foo', Body)
        foo = Body('')
        foo += 'foo'
        self.assertIsInstance(foo, Body)
        self.assertIsInstance(Body('%s') % 'foo', Body)
        self.assertIsInstance(Body('{}').format('foo'), Body)

        self.assertEqual(str(HTMLBody('foo')), 'foo')
        self.assertEqual(str(HTMLBody('%s') % 'foo'), 'foo')
        self.assertEqual(str(HTMLBody('{}').format('foo')), 'foo')

        self.assertIsInstance(HTMLBody('foo'), HTMLBody)
        self.assertIsInstance(HTMLBody('') + 'foo', HTMLBody)
        foo = HTMLBody('')
        foo += 'foo'
        self.assertIsInstance(foo, HTMLBody)
        self.assertIsInstance(HTMLBody('%s') % 'foo', HTMLBody)
        self.assertIsInstance(HTMLBody('{}').format('foo'), HTMLBody)


class FieldTest(unittest.TestCase):
    def test_value_validation(self):
        field = TextField('foo', field_uri='bar', is_required=True, default=None)
        with self.assertRaises(ValueError):
            field.clean(None)  # Must have a default value on None input

        field = TextField('foo', field_uri='bar', is_required=True, default='XXX')
        self.assertEqual(field.clean(None), 'XXX')

        field = CharListField('foo', field_uri='bar')
        with self.assertRaises(ValueError):
            field.clean('XXX')  # Must be a list type

        field = CharListField('foo', field_uri='bar')
        with self.assertRaises(TypeError):
            field.clean([1, 2, 3])  # List items must be correct type

        field = CharField('foo', field_uri='bar')
        with self.assertRaises(TypeError):
            field.clean(1)  # Value must be correct type
        with self.assertRaises(ValueError):
            field.clean('X' * 256)  # Value length must be within max_length

        field = DateTimeField('foo', field_uri='bar')
        with self.assertRaises(ValueError):
            field.clean(EWSDateTime(2017, 1, 1))  # Datetime values must be timezone aware

        field = ChoiceField('foo', field_uri='bar', choices={Choice('foo'), Choice('bar')})
        with self.assertRaises(ValueError):
            field.clean('XXX')  # Value must be a valid choice

        # A few tests on extended properties that override base methods
        field = ExtendedPropertyField('foo', value_cls=ExternId, is_required=True)
        with self.assertRaises(ValueError):
            field.clean(None)  # Value is required
        self.assertEqual(field.clean('XXX'), 'XXX')  # We can clean a simple value and keep it as a simple value
        self.assertEqual(field.clean(ExternId('XXX')), ExternId('XXX'))  # We can clean an ExternId instance as well

        # Test min/max on IntegerField
        field = IntegerField('foo', field_uri='bar', min=5, max=10)
        with self.assertRaises(ValueError):
            field.clean(2)
        with self.assertRaises(ValueError):
            field.clean(12)

        # Test enum validation
        field = EnumField('foo', field_uri='bar', enum=['a', 'b', 'c'])
        with self.assertRaises(ValueError):
            field.clean(0)  # Enums start at 1
        with self.assertRaises(ValueError):
            field.clean(4)  # Spills over list
        with self.assertRaises(ValueError):
            field.clean('d')  # Value not in enum

        # Test enum list validation
        field = EnumListField('foo', field_uri='bar', enum=['a', 'b', 'c'])
        with self.assertRaises(ValueError):
            field.clean([])
        with self.assertRaises(ValueError):
            field.clean([0])
        with self.assertRaises(ValueError):
            field.clean([1, 1])  # Values must be unique
        with self.assertRaises(ValueError):
            field.clean(['d'])

        # Test ExtraWeekdaysField. Normal weedays are passed as lists, extra options as strings
        field = ExtraWeekdaysField('foo', field_uri='bar')
        for val in (DAY, WEEK_DAY, WEEKEND_DAY, (MONDAY, WEDNESDAY), 3, 10, (5, 7)):
            field.clean(val)
        for val in ('foo', ('foo', 'bar'), (3, 3), 0, 11, (1, 11)):
            with self.assertRaises(ValueError):
                field.clean(val)

    def test_garbage_input(self):
        # Test that we can survive garbage input for common field types
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        account = namedtuple('Account', ['default_timezone'])(default_timezone=tz)
        payload = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:Foo>THIS_IS_GARBAGE</t:Foo>
    </t:Item>
</Envelope>'''
        elem = to_xml(payload).find('{%s}Item' % TNS)
        for field_cls in (Base64Field, BooleanField, IntegerField, DateField, DateTimeField, DecimalField):
            field = field_cls('foo', field_uri='item:Foo', is_required=True, default='DUMMY')
            self.assertEqual(field.from_xml(elem=elem, account=account), None)

        # Test MS timezones
        payload = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:Foo Id="THIS_IS_GARBAGE"></t:Foo>
    </t:Item>
</Envelope>'''
        elem = to_xml(payload).find('{%s}Item' % TNS)
        field = TimeZoneField('foo', field_uri='item:Foo', default='DUMMY')
        self.assertEqual(field.from_xml(elem=elem, account=account), None)

    def test_versioned_field(self):
        field = TextField('foo', field_uri='bar', supported_from=EXCHANGE_2010)
        with self.assertRaises(ErrorInvalidServerVersion):
            field.clean('baz', version=Version(EXCHANGE_2007))
        field.clean('baz', version=Version(EXCHANGE_2010))
        field.clean('baz', version=Version(EXCHANGE_2013))

    def test_versioned_choice(self):
        field = ChoiceField('foo', field_uri='bar', choices={
            Choice('c1'), Choice('c2', supported_from=EXCHANGE_2010)
        })
        with self.assertRaises(ValueError):
            field.clean('XXX')  # Value must be a valid choice
        field.clean('c2', version=None)
        with self.assertRaises(ErrorInvalidServerVersion):
            field.clean('c2', version=Version(EXCHANGE_2007))
        field.clean('c2', version=Version(EXCHANGE_2010))
        field.clean('c2', version=Version(EXCHANGE_2013))

    def test_naive_datetime(self):
        # Test that we can survive naive datetimes on a datetime field
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        account = namedtuple('Account', ['default_timezone'])(default_timezone=tz)
        default_value = tz.localize(EWSDateTime(2017, 1, 2, 3, 4))
        field = DateTimeField('foo', field_uri='item:DateTimeSent', default=default_value)

        # TZ-aware datetime string
        payload = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:DateTimeSent>2017-06-21T18:40:02Z</t:DateTimeSent>
    </t:Item>
</Envelope>'''
        elem = to_xml(payload).find('{%s}Item' % TNS)
        self.assertEqual(field.from_xml(elem=elem, account=account), UTC.localize(EWSDateTime(2017, 6, 21, 18, 40, 2)))

        # Naive datetime string is localized to tz of the account
        payload = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:DateTimeSent>2017-06-21T18:40:02</t:DateTimeSent>
    </t:Item>
</Envelope>'''
        elem = to_xml(payload).find('{%s}Item' % TNS)
        self.assertEqual(field.from_xml(elem=elem, account=account), tz.localize(EWSDateTime(2017, 6, 21, 18, 40, 2)))

        # Garbage string returns None
        payload = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
        <t:DateTimeSent>THIS_IS_GARBAGE</t:DateTimeSent>
    </t:Item>
</Envelope>'''
        elem = to_xml(payload).find('{%s}Item' % TNS)
        self.assertEqual(field.from_xml(elem=elem, account=account), None)

        # Element not found returns default value
        payload = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
    <t:Item>
    </t:Item>
</Envelope>'''
        elem = to_xml(payload).find('{%s}Item' % TNS)
        self.assertEqual(field.from_xml(elem=elem, account=account), default_value)


class ItemTest(unittest.TestCase):
    def test_item_id_deprecation(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Message(id='XXX', changekey='YYY').item_id
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Message.get_field_by_fieldname('item_id')
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Message(item_id='XXX')
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))

    def test_task_validation(self):
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        task = Task(due_date=tz.localize(EWSDateTime(2017, 1, 1)), start_date=tz.localize(EWSDateTime(2017, 2, 1)))
        task.clean()
        # We reset due date if it's before start date
        self.assertEqual(task.due_date, tz.localize(EWSDateTime(2017, 2, 1)))
        self.assertEqual(task.due_date, task.start_date)

        task = Task(complete_date=tz.localize(EWSDateTime(2099, 1, 1)), status=Task.NOT_STARTED)
        task.clean()
        # We reset status if complete_date is set
        self.assertEqual(task.status, Task.COMPLETED)
        # We also reset complete date to now() if it's in the future
        self.assertEqual(task.complete_date.date(), UTC_NOW().date())

        task = Task(complete_date=tz.localize(EWSDateTime(2017, 1, 1)), start_date=tz.localize(EWSDateTime(2017, 2, 1)))
        task.clean()
        # We also reset complete date to start_date if it's before start_date
        self.assertEqual(task.complete_date, task.start_date)

        task = Task(percent_complete=Decimal('50.0'), status=Task.COMPLETED)
        task.clean()
        # We reset percent_complete to 100.0 if state is completed
        self.assertEqual(task.percent_complete, Decimal(100))

        task = Task(percent_complete=Decimal('50.0'), status=Task.NOT_STARTED)
        task.clean()
        # We reset percent_complete to 0.0 if state is not_started
        self.assertEqual(task.percent_complete, Decimal(0))


class RecurrenceTest(unittest.TestCase):
    def test_item_id_deprecation(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Occurrence(id='XXX', changekey='YYY').item_id
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Occurrence.get_field_by_fieldname('item_id')
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Occurrence(item_id='XXX')
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))

    def test_magic(self):
        pattern = AbsoluteYearlyPattern(month=FEBRUARY, day_of_month=28)
        self.assertEqual(str(pattern), 'Occurs on day 28 of February')
        pattern = RelativeYearlyPattern(month=AUGUST, week_number=SECOND, weekdays=[MONDAY, WEDNESDAY])
        self.assertEqual(str(pattern), 'Occurs on weekdays Monday, Wednesday in the Second week of August')
        pattern = AbsoluteMonthlyPattern(interval=3, day_of_month=31)
        self.assertEqual(str(pattern), 'Occurs on day 31 of every 3 month(s)')
        pattern = RelativeMonthlyPattern(interval=2, week_number=LAST, weekdays=[5, 7])
        self.assertEqual(str(pattern), 'Occurs on weekdays Friday, Sunday in the Last week of every 2 month(s)')
        pattern = WeeklyPattern(interval=4, weekdays=WEEKEND_DAY, first_day_of_week=7)
        self.assertEqual(str(pattern),
                         'Occurs on weekdays WeekendDay of every 4 week(s) where the first day of the week is Sunday')
        pattern = DailyPattern(interval=6)
        self.assertEqual(str(pattern), 'Occurs every 6 day(s)')

    def test_validation(self):
        p = DailyPattern(interval=3)
        d_start = EWSDate(2017, 9, 1)
        d_end = EWSDate(2017, 9, 7)
        with self.assertRaises(ValueError):
            Recurrence(pattern=p, boundary='foo', start='bar')  # Specify *either* boundary *or* start, end and number
        with self.assertRaises(ValueError):
            Recurrence(pattern=p, start='foo', end='bar', number='baz')  # number is invalid when end is present
        with self.assertRaises(ValueError):
            Recurrence(pattern=p, end='bar', number='baz')  # Must have start
        r = Recurrence(pattern=p, start=d_start)
        self.assertEqual(r.boundary, NoEndPattern(start=d_start))
        r = Recurrence(pattern=p, start=d_start, end=d_end)
        self.assertEqual(r.boundary, EndDatePattern(start=d_start, end=d_end))
        r = Recurrence(pattern=p, start=d_start, number=1)
        self.assertEqual(r.boundary, NumberedPattern(start=d_start, number=1))


class RestrictionTest(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_magic(self):
        self.assertEqual(str(Q()), 'Q()')

    def test_q(self):
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        start = tz.localize(EWSDateTime(1950, 9, 26, 8, 0, 0))
        end = tz.localize(EWSDateTime(2050, 9, 26, 11, 0, 0))
        result = '''\
<m:Restriction xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
    <t:And xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
        <t:Or>
            <t:Contains ContainmentComparison="Exact" ContainmentMode="Substring">
                <t:FieldURI FieldURI="item:Categories"/>
                <t:Constant Value="FOO"/>
            </t:Contains>
            <t:Contains ContainmentComparison="Exact" ContainmentMode="Substring">
                <t:FieldURI FieldURI="item:Categories"/>
                <t:Constant Value="BAR"/>
            </t:Contains>
        </t:Or>
        <t:IsGreaterThan>
            <t:FieldURI FieldURI="calendar:End"/>
            <t:FieldURIOrConstant>
                <t:Constant Value="1950-09-26T08:00:00+01:00"/>
            </t:FieldURIOrConstant>
        </t:IsGreaterThan>
        <t:IsLessThan>
            <t:FieldURI FieldURI="calendar:Start"/>
            <t:FieldURIOrConstant>
                <t:Constant Value="2050-09-26T11:00:00+01:00"/>
            </t:FieldURIOrConstant>
        </t:IsLessThan>
    </t:And>
</m:Restriction>'''
        q = Q(Q(categories__contains='FOO') | Q(categories__contains='BAR'), start__lt=end, end__gt=start)
        r = Restriction(q, folders=[Calendar()], applies_to=Restriction.ITEMS)
        self.assertEqual(str(r), ''.join(l.lstrip() for l in result.split('\n')))
        # Test empty Q
        q = Q()
        self.assertEqual(q.to_xml(folders=[Calendar()], version=None, applies_to=Restriction.ITEMS), None)
        with self.assertRaises(ValueError):
            Restriction(q, folders=[Calendar()], applies_to=Restriction.ITEMS)
        # Test validation
        with self.assertRaises(ValueError):
            Q(datetime_created__range=(1,))  # Must have exactly 2 args
        with self.assertRaises(ValueError):
            Q(datetime_created__range=(1, 2, 3))  # Must have exactly 2 args
        with self.assertRaises(TypeError):
            Q(datetime_created=Build(15, 1)).clean()  # Must be serializable
        with self.assertRaises(ValueError):
            Q(datetime_created=EWSDateTime(2017, 1, 1)).clean()  # Must be tz-aware date
        with self.assertRaises(ValueError):
            Q(categories__contains=[[1, 2], [3, 4]]).clean()  # Must be single value

    def test_q_expr(self):
        self.assertEqual(Q().expr(), None)
        self.assertEqual((~Q()).expr(), None)
        self.assertEqual(Q(x=5).expr(), 'x == 5')
        self.assertEqual((~Q(x=5)).expr(), 'x != 5')
        q = (Q(b__contains='a', x__contains=5) | Q(~Q(a__contains='c'), f__gt=3, c=6)) & ~Q(y=9, z__contains='b')
        self.assertEqual(
            str(q),  # str() calls expr()
            "((b contains 'a' AND x contains 5) OR (NOT a contains 'c' AND c == 6 AND f > 3)) "
            "AND NOT (y == 9 AND z contains 'b')"
        )
        self.assertEqual(
            repr(q),
            "Q('AND', Q('OR', Q('AND', Q(b contains 'a'), Q(x contains 5)), Q('AND', Q('NOT', Q(a contains 'c')), "
            "Q(c == 6), Q(f > 3))), Q('NOT', Q('AND', Q(y == 9), Q(z contains 'b'))))"
        )
        # Test simulated IN expression
        in_q = Q(foo__in=[1, 2, 3])
        self.assertEqual(in_q.conn_type, Q.OR)
        self.assertEqual(len(in_q.children), 3)

    def test_q_inversion(self):
        self.assertEqual((~Q(foo=5)).op, Q.NE)
        self.assertEqual((~Q(foo__not=5)).op, Q.EQ)
        self.assertEqual((~Q(foo__lt=5)).op, Q.GTE)
        self.assertEqual((~Q(foo__lte=5)).op, Q.GT)
        self.assertEqual((~Q(foo__gt=5)).op, Q.LTE)
        self.assertEqual((~Q(foo__gte=5)).op, Q.LT)
        # Test not not Q on a non-leaf
        self.assertEqual(Q(foo__contains=('bar', 'baz')).conn_type, Q.AND)
        self.assertEqual((~Q(foo__contains=('bar', 'baz'))).conn_type, Q.NOT)
        self.assertEqual((~~Q(foo__contains=('bar', 'baz'))).conn_type, Q.AND)
        self.assertEqual(Q(foo__contains=('bar', 'baz')), ~~Q(foo__contains=('bar', 'baz')))
        # Test generated XML of 'Not' statement when there is only one child. Skip 't:And' between 't:Not' and 't:Or'.
        result = '''\
<m:Restriction xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
    <t:Not xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
        <t:Or>
            <t:IsEqualTo>
                <t:FieldURI FieldURI="item:Subject"/>
                <t:FieldURIOrConstant>
                    <t:Constant Value="bar"/>
                </t:FieldURIOrConstant>
            </t:IsEqualTo>
            <t:IsEqualTo>
                <t:FieldURI FieldURI="item:Subject"/>
                <t:FieldURIOrConstant>
                    <t:Constant Value="baz"/>
                </t:FieldURIOrConstant>
            </t:IsEqualTo>
        </t:Or>
    </t:Not>
</m:Restriction>'''
        q = ~(Q(subject='bar') | Q(subject='baz'))
        self.assertEqual(
            xml_to_str(q.to_xml(folders=[Calendar()], version=None, applies_to=Restriction.ITEMS)),
            ''.join(l.lstrip() for l in result.split('\n'))
        )

    def test_q_boolean_ops(self):
        self.assertEqual((Q(foo=5) & Q(foo=6)).conn_type, Q.AND)
        self.assertEqual((Q(foo=5) | Q(foo=6)).conn_type, Q.OR)

    def test_q_failures(self):
        with self.assertRaises(ValueError):
            # Invalid value
            Q(foo=None).clean()


class QuerySetTest(unittest.TestCase):
    def test_magic(self):
        self.assertEqual(
            str(QuerySet(
                folder_collection=FolderCollection(account=None, folders=[Inbox(root='XXX', name='FooBox')]))
            ),
            'QuerySet(q=Q(), folders=[Inbox (FooBox)])'
        )

    def test_from_folder(self):
        MockRoot = namedtuple('Root', ['account'])
        folder = Inbox(root=MockRoot(account='XXX'))
        self.assertIsInstance(folder.all(), QuerySet)
        self.assertIsInstance(folder.none(), QuerySet)
        self.assertIsInstance(folder.filter(subject='foo'), QuerySet)
        self.assertIsInstance(folder.exclude(subject='foo'), QuerySet)

    def test_queryset_copy(self):
        qs = QuerySet(folder_collection=FolderCollection(account=None, folders=[Inbox(root='XXX')]))
        qs.q = Q()
        qs.only_fields = ('a', 'b')
        qs.order_fields = ('c', 'd')
        qs.return_format = QuerySet.NONE

        # Initially, immutable items have the same id()
        new_qs = qs.copy()
        self.assertNotEqual(id(qs), id(new_qs))
        self.assertEqual(id(qs.folder_collection), id(new_qs.folder_collection))
        self.assertEqual(id(qs._cache), id(new_qs._cache))
        self.assertEqual(qs._cache, new_qs._cache)
        self.assertNotEqual(id(qs.q), id(new_qs.q))
        self.assertEqual(qs.q, new_qs.q)
        self.assertEqual(id(qs.only_fields), id(new_qs.only_fields))
        self.assertEqual(qs.only_fields, new_qs.only_fields)
        self.assertEqual(id(qs.order_fields), id(new_qs.order_fields))
        self.assertEqual(qs.order_fields, new_qs.order_fields)
        self.assertEqual(id(qs.return_format), id(new_qs.return_format))
        self.assertEqual(qs.return_format, new_qs.return_format)

        # Set the same values, forcing a new id()
        new_qs.q = Q()
        new_qs.only_fields = ('a', 'b')
        new_qs.order_fields = ('c', 'd')
        new_qs.return_format = QuerySet.NONE

        self.assertNotEqual(id(qs), id(new_qs))
        self.assertEqual(id(qs.folder_collection), id(new_qs.folder_collection))
        self.assertEqual(id(qs._cache), id(new_qs._cache))
        self.assertEqual(qs._cache, new_qs._cache)
        self.assertNotEqual(id(qs.q), id(new_qs.q))
        self.assertEqual(qs.q, new_qs.q)
        self.assertEqual(qs.only_fields, new_qs.only_fields)
        self.assertEqual(qs.order_fields, new_qs.order_fields)
        self.assertEqual(qs.return_format, new_qs.return_format)

        # Set the new values, forcing a new id()
        new_qs.q = Q(foo=5)
        new_qs.only_fields = ('c', 'd')
        new_qs.order_fields = ('e', 'f')
        new_qs.return_format = QuerySet.VALUES

        self.assertNotEqual(id(qs), id(new_qs))
        self.assertEqual(id(qs.folder_collection), id(new_qs.folder_collection))
        self.assertEqual(id(qs._cache), id(new_qs._cache))
        self.assertEqual(qs._cache, new_qs._cache)
        self.assertNotEqual(id(qs.q), id(new_qs.q))
        self.assertNotEqual(qs.q, new_qs.q)
        self.assertNotEqual(id(qs.only_fields), id(new_qs.only_fields))
        self.assertNotEqual(qs.only_fields, new_qs.only_fields)
        self.assertNotEqual(id(qs.order_fields), id(new_qs.order_fields))
        self.assertNotEqual(qs.order_fields, new_qs.order_fields)
        self.assertNotEqual(id(qs.return_format), id(new_qs.return_format))
        self.assertNotEqual(qs.return_format, new_qs.return_format)


class ServicesTest(unittest.TestCase):
    def test_invalid_server_version(self):
        # Test that we get a client-side error if we call a service that was only implemented in a later version
        version = mock_version(build=EXCHANGE_2007)
        account = mock_account(version=version, protocol=mock_protocol(version=version, service_endpoint='example.com'))
        with self.assertRaises(NotImplementedError):
            GetServerTimeZones(protocol=account.protocol).call()
        with self.assertRaises(NotImplementedError):
            GetRoomLists(protocol=account.protocol).call()
        with self.assertRaises(NotImplementedError):
            GetRooms(protocol=account.protocol).call('XXX')


class TransportTest(unittest.TestCase):
    @requests_mock.mock()
    def test_get_auth_method_from_response(self, m):
        url = 'http://example.com/noauth'
        m.get(url, status_code=200)
        r = requests.get(url)
        self.assertEqual(_get_auth_method_from_response(r), NOAUTH)  # No authentication needed

        url = 'http://example.com/redirect'
        m.get(url, status_code=302, headers={'location': 'http://contoso.com'})
        r = requests.get(url, allow_redirects=False)
        with self.assertRaises(RedirectError):
            _get_auth_method_from_response(r)  # Redirect to another host

        url = 'http://example.com/relativeredirect'
        m.get(url, status_code=302, headers={'location': 'http://example.com/'})
        r = requests.get(url, allow_redirects=False)
        with self.assertRaises(TransportError):
            _get_auth_method_from_response(r)  # Redirect to same host

        url = 'http://example.com/internalerror'
        m.get(url, status_code=501)
        r = requests.get(url)
        with self.assertRaises(TransportError):
            _get_auth_method_from_response(r)  # Non-401 status code

        url = 'http://example.com/no_auth_headers'
        m.get(url, status_code=401)
        r = requests.get(url)
        with self.assertRaises(UnauthorizedError):
            _get_auth_method_from_response(r)  # 401 status code but no auth headers

        url = 'http://example.com/no_supported_auth'
        m.get(url, status_code=401, headers={'WWW-Authenticate': 'FANCYAUTH'})
        r = requests.get(url)
        with self.assertRaises(UnauthorizedError):
            _get_auth_method_from_response(r)  # 401 status code but no auth headers

        url = 'http://example.com/basic_auth'
        m.get(url, status_code=401, headers={'WWW-Authenticate': 'Basic'})
        r = requests.get(url)
        self.assertEqual(_get_auth_method_from_response(r), BASIC)

        url = 'http://example.com/basic_auth_empty_realm'
        m.get(url, status_code=401, headers={'WWW-Authenticate': 'Basic realm=""'})
        r = requests.get(url)
        self.assertEqual(_get_auth_method_from_response(r), BASIC)

        url = 'http://example.com/basic_auth_realm'
        m.get(url, status_code=401, headers={'WWW-Authenticate': 'Basic realm="some realm"'})
        r = requests.get(url)
        self.assertEqual(_get_auth_method_from_response(r), BASIC)

        url = 'http://example.com/digest'
        m.get(url, status_code=401, headers={
            'WWW-Authenticate': 'Digest realm="foo@bar.com", qop="auth,auth-int", nonce="mumble", opaque="bumble"'
        })
        r = requests.get(url)
        self.assertEqual(_get_auth_method_from_response(r), DIGEST)

        url = 'http://example.com/ntlm'
        m.get(url, status_code=401, headers={'WWW-Authenticate': 'NTLM'})
        r = requests.get(url)
        self.assertEqual(_get_auth_method_from_response(r), NTLM)

        # Make sure we prefer the most secure auth method if multiple methods are supported
        url = 'http://example.com/mixed'
        m.get(url, status_code=401, headers={'WWW-Authenticate': 'Basic realm="X1", Digest realm="X2", NTLM'})
        r = requests.get(url)
        self.assertEqual(_get_auth_method_from_response(r), DIGEST)


class UtilTest(unittest.TestCase):
    def test_chunkify(self):
        # Test tuple, list, set, range, map, chain and generator
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

        seq = chain(*[[i] for i in range(5)])
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

    @requests_mock.mock()
    def test_get_redirect_url(self, m):
        m.get('https://httpbin.org/redirect-to', status_code=302, headers={'location': 'https://example.com/'})
        r = requests.get('https://httpbin.org/redirect-to?url=https://example.com/', allow_redirects=False)
        self.assertEqual(get_redirect_url(r), 'https://example.com/')

        m.get('https://httpbin.org/redirect-to', status_code=302, headers={'location': 'http://example.com/'})
        r = requests.get('https://httpbin.org/redirect-to?url=http://example.com/', allow_redirects=False)
        self.assertEqual(get_redirect_url(r), 'http://example.com/')

        m.get('https://httpbin.org/redirect-to', status_code=302, headers={'location': '/example'})
        r = requests.get('https://httpbin.org/redirect-to?url=/example', allow_redirects=False)
        self.assertEqual(get_redirect_url(r), 'https://httpbin.org/example')

        m.get('https://httpbin.org/redirect-to', status_code=302, headers={'location': 'https://example.com'})
        with self.assertRaises(RelativeRedirect):
            r = requests.get('https://httpbin.org/redirect-to?url=https://example.com', allow_redirects=False)
            get_redirect_url(r, require_relative=True)

        m.get('https://httpbin.org/redirect-to', status_code=302, headers={'location': '/example'})
        with self.assertRaises(RelativeRedirect):
            r = requests.get('https://httpbin.org/redirect-to?url=/example', allow_redirects=False)
            get_redirect_url(r, allow_relative=False)

    def test_to_xml(self):
        to_xml(b'<?xml version="1.0" encoding="UTF-8"?><foo></foo>')
        to_xml(BOM_UTF8+b'<?xml version="1.0" encoding="UTF-8"?><foo></foo>')
        to_xml(BOM_UTF8+b'<?xml version="1.0" encoding="UTF-8"?><foo>&broken</foo>')
        with self.assertRaises(ParseError):
            to_xml(b'foo')
        try:
            to_xml(b'<t:Foo><t:Bar>Baz</t:Bar></t:Foo>')
        except ParseError as e:
            # Not all lxml versions throw an error here, so we can't use assertRaises
            self.assertIn('Offending text: [...]<t:Foo><t:Bar>Baz</t[...]', e.args[0])

    def test_get_domain(self):
        self.assertEqual(get_domain('foo@example.com'), 'example.com')
        with self.assertRaises(ValueError):
            get_domain('blah')

    def test_pretty_xml_handler(self):
        # Test that a normal, non-XML log record is passed through unchanged
        stream = io.BytesIO() if PY2 else io.StringIO()
        stream.isatty = lambda: True
        h = PrettyXmlHandler(stream=stream)
        self.assertTrue(h.is_tty())
        r = logging.LogRecord(
            name='baz', level=logging.INFO, pathname='/foo/bar', lineno=1, msg='hello', args=(), exc_info=None
        )
        h.emit(r)
        h.stream.seek(0)
        self.assertEqual(h.stream.read(), 'hello\n')

        # Test formatting of an XML record. It should contain newlines and color codes.
        stream = io.BytesIO() if PY2 else io.StringIO()
        stream.isatty = lambda: True
        h = PrettyXmlHandler(stream=stream)
        r = logging.LogRecord(
            name='baz', level=logging.DEBUG, pathname='/foo/bar', lineno=1, msg='hello %(xml_foo)s',
            args=({'xml_foo': b'<?xml version="1.0" encoding="UTF-8"?><foo>bar</foo>'},), exc_info=None)
        h.emit(r)
        h.stream.seek(0)
        self.assertEqual(
            h.stream.read(),
            "hello \x1b[36m<?xml version='1.0' encoding='utf-8'?>\x1b[39;49;00m\n\x1b[34;01m"
            "<foo\x1b[39;49;00m\x1b[34;01m>\x1b[39;49;00mbar\x1b[34;01m</foo>\x1b[39;49;00m\n\n"
        )


class EWSTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # There's no official Exchange server we can test against, and we can't really provide credentials for our
        # own test server to everyone on the Internet. Travis-CI uses the encrypted settings.yml.enc for testing.
        #
        # If you want to test against your own server and account, create your own settings.yml with credentials for
        # that server. 'settings.yml.sample' is provided as a template.
        try:
            with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'settings.yml')) as f:
                settings = safe_load(f)
        except FileNotFoundError:
            print('Skipping %s - no settings.yml file found' % cls.__name__)
            print('Copy settings.yml.sample to settings.yml and enter values for your test server')
            raise unittest.SkipTest('Skipping %s - no settings.yml file found' % cls.__name__)

        cls.verify_ssl = settings.get('verify_ssl', True)
        if not cls.verify_ssl:
            # Allow unverified TLS if requested in settings file
            BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter

        # Speed up tests a bit. We don't need to wait 10 seconds for every nonexisting server in the discover dance
        AutodiscoverProtocol.TIMEOUT = 2

        # Create an account shared by all tests
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        config = Configuration(
            server=settings['server'],
            credentials=Credentials(settings['username'], settings['password'])
        )
        cls.account = Account(primary_smtp_address=settings['account'], access_type=DELEGATE, config=config,
                              locale='da_DK', default_timezone=tz)

    def setUp(self):
        # Create a random category for each test to avoid crosstalk
        self.categories = [get_random_string(length=16, spaces=False, special=False)]
        self.maxDiff = None

    def wipe_test_account(self):
        # Deletes up all deleteable items in the test account. Not run in a normal test run
        self.account.root.wipe()

    def bulk_delete(self, ids):
        # Clean up items and check return values
        for res in self.account.bulk_delete(ids):
            self.assertEqual(res, True)

    def random_val(self, field):
        if isinstance(field, ExtendedPropertyField):
            if field.value_cls.property_type == 'StringArray':
                return [get_random_string(255) for _ in range(random.randint(1, 4))]
            if field.value_cls.property_type == 'IntegerArray':
                return [get_random_int(0, 256) for _ in range(random.randint(1, 4))]
            if field.value_cls.property_type == 'BinaryArray':
                return [get_random_string(255).encode() for _ in range(random.randint(1, 4))]
            if field.value_cls.property_type == 'String':
                return get_random_string(255)
            if field.value_cls.property_type == 'Integer':
                return get_random_int(0, 256)
            if field.value_cls.property_type == 'Binary':
                # In the test_extended_distinguished_property test, EWS rull return 4 NULL bytes after char 16 if we
                # send a longer bytes sequence.
                return get_random_string(16).encode()
            raise ValueError('Unsupported field %s' % field)
        if isinstance(field, URIField):
            return get_random_url()
        if isinstance(field, EmailAddressField):
            return get_random_email()
        if isinstance(field, ChoiceField):
            return get_random_choice(field.supported_choices(version=self.account.version))
        if isinstance(field, CultureField):
            return get_random_choice(['da-DK', 'de-DE', 'en-US', 'es-ES', 'fr-CA', 'nl-NL', 'ru-RU', 'sv-SE'])
        if isinstance(field, BodyField):
            return get_random_string(400)
        if isinstance(field, CharListField):
            return [get_random_string(16) for _ in range(random.randint(1, 4))]
        if isinstance(field, TextListField):
            return [get_random_string(400) for _ in range(random.randint(1, 4))]
        if isinstance(field, CharField):
            return get_random_string(field.max_length)
        if isinstance(field, TextField):
            return get_random_string(400)
        if isinstance(field, Base64Field):
            return get_random_bytes(400)
        if isinstance(field, BooleanField):
            return get_random_bool()
        if isinstance(field, DecimalField):
            return get_random_decimal(field.min or 1, field.max or 99)
        if isinstance(field, IntegerField):
            return get_random_int(field.min or 0, field.max or 256)
        if isinstance(field, DateTimeField):
            return get_random_datetime(tz=self.account.default_timezone)
        if isinstance(field, AttachmentField):
            return [FileAttachment(name='my_file.txt', content=get_random_bytes(400))]
        if isinstance(field, MailboxListField):
            # email_address must be a real account on the server(?)
            # TODO: Mailbox has multiple optional args but vals must match server account, so we can't easily test
            if get_random_bool():
                return [Mailbox(email_address=self.account.primary_smtp_address)]
            else:
                return [self.account.primary_smtp_address]
        if isinstance(field, MailboxField):
            # email_address must be a real account on the server(?)
            # TODO: Mailbox has multiple optional args but vals must match server account, so we can't easily test
            if get_random_bool():
                return Mailbox(email_address=self.account.primary_smtp_address)
            else:
                return self.account.primary_smtp_address
        if isinstance(field, AttendeesField):
            # Attendee must refer to a real mailbox on the server(?). We're only sure to have one
            if get_random_bool():
                mbx = Mailbox(email_address=self.account.primary_smtp_address)
            else:
                mbx = self.account.primary_smtp_address
            with_last_response_time = get_random_bool()
            if with_last_response_time:
                return [
                    Attendee(mailbox=mbx, response_type='Accept',
                             last_response_time=get_random_datetime(tz=self.account.default_timezone))
                ]
            else:
                if get_random_bool():
                    return [Attendee(mailbox=mbx, response_type='Accept')]
                else:
                    return [self.account.primary_smtp_address]
        if isinstance(field, EmailAddressesField):
            addrs = []
            for label in EmailAddress.get_field_by_fieldname('label').supported_choices(version=self.account.version):
                addr = EmailAddress(email=get_random_email())
                addr.label = label
                addrs.append(addr)
            return addrs
        if isinstance(field, PhysicalAddressField):
            addrs = []
            for label in PhysicalAddress.get_field_by_fieldname('label')\
                    .supported_choices(version=self.account.version):
                addr = PhysicalAddress(street=get_random_string(32), city=get_random_string(32),
                                       state=get_random_string(32), country=get_random_string(32),
                                       zipcode=get_random_string(8))
                addr.label = label
                addrs.append(addr)
            return addrs
        if isinstance(field, PhoneNumberField):
            pns = []
            for label in PhoneNumber.get_field_by_fieldname('label').supported_choices(version=self.account.version):
                pn = PhoneNumber(phone_number=get_random_string(16))
                pn.label = label
                pns.append(pn)
            return pns
        if isinstance(field, EWSElementField):
            if field.value_cls == Recurrence:
                return Recurrence(pattern=DailyPattern(interval=5), start=get_random_date(), number=7)
        if isinstance(field, TimeZoneField):
            while True:
                try:
                    return EWSTimeZone.timezone(random.choice(pytz.all_timezones))
                except UnknownTimeZone:
                    pass
        raise ValueError('Unknown field %s' % field)


class CommonTest(EWSTest):
    def test_wrap(self):
        # Test payload wrapper with both delegation, impersonation and timezones
        MockTZ = namedtuple('EWSTimeZone', ['ms_id'])
        MockAccount = namedtuple('Account', ['access_type', 'primary_smtp_address', 'default_timezone'])
        content = create_element('AAA')
        version = 'BBB'
        account = MockAccount(DELEGATE, 'foo@example.com', MockTZ('XXX'))
        wrapped = wrap(content=content, version=version, account=account)
        self.assertEqual(
            PrettyXmlHandler.prettify_xml(wrapped),
            b'''<?xml version='1.0' encoding='utf-8'?>
<s:Envelope
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Header>
    <t:RequestServerVersion Version="BBB"/>
    <t:TimeZoneContext>
      <t:TimeZoneDefinition Id="XXX"/>
    </t:TimeZoneContext>
  </s:Header>
  <s:Body>
    <AAA/>
  </s:Body>
</s:Envelope>
''')
        account = MockAccount(IMPERSONATION, 'foo@example.com', MockTZ('XXX'))
        wrapped = wrap(content=content, version=version, account=account)
        self.assertEqual(
            PrettyXmlHandler.prettify_xml(wrapped),
            b'''<?xml version='1.0' encoding='utf-8'?>
<s:Envelope
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Header>
    <t:RequestServerVersion Version="BBB"/>
    <t:ExchangeImpersonation>
      <t:ConnectingSID>
        <t:PrimarySmtpAddress>foo@example.com</t:PrimarySmtpAddress>
      </t:ConnectingSID>
    </t:ExchangeImpersonation>
    <t:TimeZoneContext>
      <t:TimeZoneDefinition Id="XXX"/>
    </t:TimeZoneContext>
  </s:Header>
  <s:Body>
    <AAA/>
  </s:Body>
</s:Envelope>
''')

    def test_poolsize(self):
        self.assertEqual(self.account.protocol.SESSION_POOLSIZE, 4)

    def test_error_server_busy(self):
        # Test that we can parse an ErrorServerBusy response
        ws = GetRoomLists(self.account.protocol)
        xml = b'''\
<?xml version='1.0' encoding='utf-8'?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <s:Fault>
      <faultcode xmlns:a="http://schemas.microsoft.com/exchange/services/2006/types">a:ErrorServerBusy</faultcode>
      <faultstring xml:lang="en-US">The server cannot service this request right now. Try again later.</faultstring>
      <detail>
        <e:ResponseCode xmlns:e="http://schemas.microsoft.com/exchange/services/2006/errors">ErrorServerBusy</e:ResponseCode>
        <e:Message xmlns:e="http://schemas.microsoft.com/exchange/services/2006/errors">The server cannot service this request right now. Try again later.</e:Message>
        <t:MessageXml xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
          <t:Value Name="BackOffMilliseconds">297749</t:Value>
        </t:MessageXml>
      </detail>
    </s:Fault>
  </s:Body>
</s:Envelope>'''
        with self.assertRaises(ErrorServerBusy) as cm:
            ws._get_elements_in_response(response=ws._get_soap_payload(response=MockResponse(xml)))
        self.assertEqual(cm.exception.back_off, 297.749)

    def test_get_timezones(self):
        ws = GetServerTimeZones(self.account.protocol)
        data = ws.call()
        self.assertAlmostEqual(len(list(data)), 130, delta=30, msg=data)
        # Test shortcut
        self.assertAlmostEqual(len(list(self.account.protocol.get_timezones())), 130, delta=30, msg=data)
        # Test translation to TimeZone objects
        for tz_id, tz_name, periods, transitions, transitionsgroups in self.account.protocol.get_timezones(
                return_full_timezone_data=True):
            TimeZone.from_server_timezone(periods=periods, transitions=transitions, transitionsgroups=transitionsgroups,
                                          for_year=2018)

    def test_get_free_busy_info(self):
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        server_timezones = list(self.account.protocol.get_timezones(return_full_timezone_data=True))
        start = tz.localize(EWSDateTime.now())
        end = tz.localize(EWSDateTime.now() + datetime.timedelta(hours=6))
        accounts = [(self.account, 'Organizer', False)]
        for view_info in self.account.protocol.get_free_busy_info(accounts=accounts, start=start, end=end):
            self.assertIsInstance(view_info, FreeBusyView)
            self.assertIsInstance(view_info.working_hours_timezone, TimeZone)
            ms_id = view_info.working_hours_timezone.to_server_timezone(server_timezones, start.year)
            self.assertIn(ms_id, {t[0] for t in CLDR_TO_MS_TIMEZONE_MAP.values()})

    def test_get_roomlists(self):
        # The test server is not guaranteed to have any room lists which makes this test less useful
        ws = GetRoomLists(self.account.protocol)
        roomlists = ws.call()
        self.assertEqual(roomlists, [])
        # Test shortcut
        self.assertEqual(self.account.protocol.get_roomlists(), [])

    def test_get_roomlists_parsing(self):
        # Test static XML since server has no roomlists
        ws = GetRoomLists(self.account.protocol)
        xml = b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Header>
        <h:ServerVersionInfo
            MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1" Version="V2016_10_10"
            xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"
            xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
    </s:Header>
    <s:Body>
        <m:GetRoomListsResponse ResponseClass="Success"
                xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
                xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <m:ResponseCode>NoError</m:ResponseCode>
            <m:RoomLists>
                <t:Address>
                    <t:Name>Roomlist</t:Name>
                    <t:EmailAddress>roomlist1@example.com</t:EmailAddress>
                    <t:RoutingType>SMTP</t:RoutingType>
                    <t:MailboxType>PublicDL</t:MailboxType>
                </t:Address>
                <t:Address>
                    <t:Name>Roomlist</t:Name>
                    <t:EmailAddress>roomlist2@example.com</t:EmailAddress>
                    <t:RoutingType>SMTP</t:RoutingType>
                    <t:MailboxType>PublicDL</t:MailboxType>
                </t:Address>
            </m:RoomLists>
        </m:GetRoomListsResponse>
    </s:Body>
</s:Envelope>'''
        res = ws._get_elements_in_response(response=ws._get_soap_payload(response=MockResponse(xml)))
        self.assertSetEqual(
            {RoomList.from_xml(elem=elem, account=None).email_address for elem in res},
            {'roomlist1@example.com', 'roomlist2@example.com'}
        )

    def test_get_rooms(self):
        # The test server is not guaranteed to have any rooms or room lists which makes this test less useful
        roomlist = RoomList(email_address='my.roomlist@example.com')
        ws = GetRooms(self.account.protocol)
        with self.assertRaises(ErrorNameResolutionNoResults):
            ws.call(roomlist=roomlist)
        # Test shortcut
        with self.assertRaises(ErrorNameResolutionNoResults):
            self.account.protocol.get_rooms('my.roomlist@example.com')

    def test_get_rooms_parsing(self):
        # Test static XML since server has no rooms
        ws = GetRooms(self.account.protocol)
        xml = b'''\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Header>
        <h:ServerVersionInfo
            MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1" Version="V2016_10_10"
            xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"
            xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
    </s:Header>
    <s:Body>
        <m:GetRoomsResponse ResponseClass="Success"
                xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
            <m:ResponseCode>NoError</m:ResponseCode>
            <m:Rooms>
                <t:Room>
                    <t:Id>
                        <t:Name>room1</t:Name>
                        <t:EmailAddress>room1@example.com</t:EmailAddress>
                        <t:RoutingType>SMTP</t:RoutingType>
                        <t:MailboxType>Mailbox</t:MailboxType>
                    </t:Id>
                </t:Room>
                <t:Room>
                    <t:Id>
                        <t:Name>room2</t:Name>
                        <t:EmailAddress>room2@example.com</t:EmailAddress>
                        <t:RoutingType>SMTP</t:RoutingType>
                        <t:MailboxType>Mailbox</t:MailboxType>
                    </t:Id>
                </t:Room>
            </m:Rooms>
        </m:GetRoomsResponse>
    </s:Body>
</s:Envelope>'''
        res = ws._get_elements_in_response(response=ws._get_soap_payload(response=MockResponse(xml)))
        self.assertSetEqual(
            {Room.from_xml(elem=elem, account=None).email_address for elem in res},
            {'room1@example.com', 'room2@example.com'}
        )

    def test_resolvenames(self):
        self.assertGreaterEqual(
            self.account.protocol.resolve_names(names=['xxx@example.com']),
            []
        )
        self.assertEqual(
            self.account.protocol.resolve_names(names=[self.account.primary_smtp_address]),
            [Mailbox(email_address=self.account.primary_smtp_address)]
        )
        # Test something that's not an email
        self.assertEqual(
            self.account.protocol.resolve_names(names=['foo\\bar']),
            []
        )
        # Test return_full_contact_data
        mailbox, contact = self.account.protocol.resolve_names(
            names=[self.account.primary_smtp_address],
            return_full_contact_data=True
        )[0]
        self.assertEqual(
            mailbox,
            Mailbox(email_address=self.account.primary_smtp_address)
        )
        self.assertListEqual(
            [e.email.replace('SMTP:', '') for e in contact.email_addresses if e.label == 'EmailAddress1'],
            [self.account.primary_smtp_address]
        )

    def test_resolvenames_parsing(self):
        # Test static XML since server has no roomlists
        ws = ResolveNames(self.account.protocol)
        xml = b'''\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Header>
    <h:ServerVersionInfo
        MajorVersion="15" MinorVersion="0" MajorBuildNumber="1293" MinorBuildNumber="4" Version="V2_23"
        xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
  </s:Header>
  <s:Body>
    <m:ResolveNamesResponse
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
      <m:ResponseMessages>
        <m:ResolveNamesResponseMessage ResponseClass="Warning">
          <m:MessageText>Multiple results were found.</m:MessageText>
          <m:ResponseCode>ErrorNameResolutionMultipleResults</m:ResponseCode>
          <m:DescriptiveLinkKey>0</m:DescriptiveLinkKey>
          <m:ResolutionSet TotalItemsInView="2" IncludesLastItemInRange="true">
            <t:Resolution>
              <t:Mailbox>
                <t:Name>John Doe</t:Name>
                <t:EmailAddress>anne@example.com</t:EmailAddress>
                <t:RoutingType>SMTP</t:RoutingType>
                <t:MailboxType>Mailbox</t:MailboxType>
              </t:Mailbox>
            </t:Resolution>
            <t:Resolution>
              <t:Mailbox>
                <t:Name>John Deer</t:Name>
                <t:EmailAddress>john@example.com</t:EmailAddress>
                <t:RoutingType>SMTP</t:RoutingType>
                <t:MailboxType>Mailbox</t:MailboxType>
              </t:Mailbox>
            </t:Resolution>
          </m:ResolutionSet>
        </m:ResolveNamesResponseMessage>
      </m:ResponseMessages>
    </m:ResolveNamesResponse>
  </s:Body>
</s:Envelope>'''
        res = ws._get_elements_in_response(response=ws._get_soap_payload(response=MockResponse(xml)))
        self.assertSetEqual(
            {Mailbox.from_xml(elem=elem.find(Mailbox.response_tag()), account=None).email_address for elem in res},
            {'anne@example.com', 'john@example.com'}
        )

    def test_expanddl(self):
        self.assertEqual(
            len(self.account.protocol.expand_dl('non_existent_distro@example.com')),
            0
        )

    def test_oof_settings(self):
        oof = OofSettings(
            state=OofSettings.ENABLED,
            external_audience='None',
            internal_reply="I'm on holidays. See ya guys!",
            external_reply='Dear Sir, your email has now been deleted.',
        )
        self.account.oof_settings = oof
        self.assertEqual(self.account.oof_settings, oof)

        oof = OofSettings(
            state=OofSettings.ENABLED,
            external_audience='Known',
            internal_reply='XXX',
            external_reply='YYY',
        )
        self.account.oof_settings = oof
        self.assertEqual(self.account.oof_settings, oof)

        # Scheduled duration must not be in the past
        start, end = get_random_datetime_range(start_date=EWSDate.today())
        oof = OofSettings(
            state=OofSettings.SCHEDULED,
            external_audience='Known',
            internal_reply="I'm in the pub. See ya guys!",
            external_reply="I'm having a business dinner in town",
            start=start,
            end=end,
        )
        self.account.oof_settings = oof
        self.assertEqual(self.account.oof_settings, oof)

        oof = OofSettings(
            state=OofSettings.DISABLED,
        )
        self.account.oof_settings = oof
        self.assertEqual(self.account.oof_settings, oof)

    def test_oof_settings_validation(self):
        with self.assertRaises(ValueError):
            # Needs a start and end
            OofSettings(
                state=OofSettings.SCHEDULED,
            ).clean(version=None)
        with self.assertRaises(ValueError):
            # Start must be before end
            OofSettings(
                state=OofSettings.SCHEDULED,
                start=UTC.localize(EWSDateTime(2100, 12, 1)),
                end=UTC.localize(EWSDateTime(2100, 11, 1)),
            ).clean(version=None)
        with self.assertRaises(ValueError):
            # End must be in the future
            OofSettings(
                state=OofSettings.SCHEDULED,
                start=UTC.localize(EWSDateTime(2000, 11, 1)),
                end=UTC.localize(EWSDateTime(2000, 12, 1)),
            ).clean(version=None)
        with self.assertRaises(ValueError):
            # Must have an internal and external reply
            OofSettings(
                state=OofSettings.SCHEDULED,
                start=UTC.localize(EWSDateTime(2100, 11, 1)),
                end=UTC.localize(EWSDateTime(2100, 12, 1)),
            ).clean(version=None)

    def test_sessionpool(self):
        # First, empty the calendar
        start = self.account.default_timezone.localize(EWSDateTime(2011, 10, 12, 8))
        end = self.account.default_timezone.localize(EWSDateTime(2011, 10, 12, 10))
        self.account.calendar.filter(start__lt=end, end__gt=start, categories__contains=self.categories).delete()
        items = []
        for i in range(75):
            subject = 'Test Subject %s' % i
            item = CalendarItem(
                start=start,
                end=end,
                subject=subject,
                categories=self.categories,
            )
            items.append(item)
        return_ids = self.account.calendar.bulk_create(items=items)
        self.assertEqual(len(return_ids), len(items))
        ids = self.account.calendar.filter(start__lt=end, end__gt=start, categories__contains=self.categories) \
            .values_list('id', 'changekey')
        self.assertEqual(len(ids), len(items))
        return_items = list(self.account.fetch(return_ids))
        self.bulk_delete(return_items)

    def test_magic(self):
        self.assertIn(self.account.protocol.version.api_version, str(self.account.protocol))
        self.assertIn(self.account.protocol.credentials.username, str(self.account.protocol.credentials))
        self.assertIn(self.account.primary_smtp_address, str(self.account))
        self.assertIn(str(self.account.version.build.major_version), repr(self.account.version))
        for item in (
                self.account.protocol,
                self.account.version,
        ):
            # Just test that these at least don't throw errors
            repr(item)
            str(item)
        for attr in (
                'admin_audit_logs',
                'archive_deleted_items',
                'archive_inbox',
                'archive_msg_folder_root',
                'archive_recoverable_items_deletions',
                'archive_recoverable_items_purges',
                'archive_recoverable_items_root',
                'archive_recoverable_items_versions',
                'archive_root',
                'calendar',
                'conflicts',
                'contacts',
                'conversation_history',
                'directory',
                'drafts',
                'favorites',
                'im_contact_list',
                'inbox',
                'journal',
                'junk',
                'local_failures',
                'msg_folder_root',
                'my_contacts',
                'notes',
                'outbox',
                'people_connect',
                'public_folders_root',
                'quick_contacts',
                'recipient_cache',
                'recoverable_items_deletions',
                'recoverable_items_purges',
                'recoverable_items_root',
                'recoverable_items_versions',
                'search_folders',
                'sent',
                'server_failures',
                'sync_issues',
                'tasks',
                'todo_search',
                'trash',
                'voice_mail',
        ):
            # Test distinguished folder shortcuts. Some may raise ErrorAccessDenied
            try:
                item = getattr(self.account, attr)
            except (ErrorAccessDenied, ErrorFolderNotFound, ErrorItemNotFound, ErrorInvalidOperation,
                    ErrorNoPublicFolderReplicaAvailable):
                continue
            else:
                repr(item)
                str(item)
                self.assertTrue(item.is_distinguished)

    def test_configuration(self):
        with self.assertRaises(AttributeError):
            Configuration(credentials=Credentials(username='foo', password='bar'))
        with self.assertRaises(ValueError):
            Configuration(credentials=Credentials(username='foo', password='bar'),
                          service_endpoint='http://example.com/svc',
                          auth_type='XXX')

    def test_failed_login(self):
        with self.assertRaises(UnauthorizedError):
            Configuration(
                service_endpoint=self.account.protocol.service_endpoint,
                credentials=Credentials(self.account.protocol.credentials.username, 'WRONG_PASSWORD'))
        with self.assertRaises(AutoDiscoverFailed):
            Account(
                primary_smtp_address=self.account.primary_smtp_address,
                access_type=DELEGATE,
                credentials=Credentials(self.account.protocol.credentials.username, 'WRONG_PASSWORD'),
                autodiscover=True,
                locale='da_DK')

    def test_post_ratelimited(self):
        url = 'https://example.com'

        protocol = self.account.protocol
        credentials = protocol.credentials
        # Make sure we fail fast in error cases
        protocol.credentials = Credentials(username=credentials.username, password=credentials.password)

        session = protocol.get_session()

        # Test the straight, HTTP 200 path
        session.post = mock_post(url, 200, {}, 'foo')
        r, session = post_ratelimited(protocol=protocol, session=session, url='http://', headers=None, data='')
        self.assertEqual(r.content, b'foo')

        # Test exceptions raises by the POST request
        for err_cls in CONNECTION_ERRORS:
            session.post = mock_session_exception(err_cls)
            with self.assertRaises(err_cls):
                r, session = post_ratelimited(protocol=protocol, session=session, url='http://', headers=None, data='')

        # Test bad exit codes and headers
        session.post = mock_post(url, 401, {})
        with self.assertRaises(UnauthorizedError):
            r, session = post_ratelimited(protocol=protocol, session=session, url='http://', headers=None, data='')
        session.post = mock_post(url, 999, {'connection': 'close'})
        with self.assertRaises(TransportError):
            r, session = post_ratelimited(protocol=protocol, session=session, url='http://', headers=None, data='')
        session.post = mock_post(url, 302, {'location': '/ews/genericerrorpage.htm?aspxerrorpath=/ews/exchange.asmx'})
        with self.assertRaises(TransportError):
            r, session = post_ratelimited(protocol=protocol, session=session, url='http://', headers=None, data='')
        session.post = mock_post(url, 503, {})
        with self.assertRaises(TransportError):
            r, session = post_ratelimited(protocol=protocol, session=session, url='http://', headers=None, data='')

        # No redirect header
        session.post = mock_post(url, 302, {})
        with self.assertRaises(TransportError):
            r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data='')
        # Redirect header to same location
        session.post = mock_post(url, 302, {'location': url})
        with self.assertRaises(TransportError):
            r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data='')
        # Redirect header to relative location
        session.post = mock_post(url, 302, {'location': url + '/foo'})
        with self.assertRaises(RedirectError):
            r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data='')
        # Redirect header to other location and allow_redirects=False
        session.post = mock_post(url, 302, {'location': 'https://contoso.com'})
        with self.assertRaises(TransportError):
            r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data='')
        # Redirect header to other location and allow_redirects=True
        import exchangelib.util
        exchangelib.util.MAX_REDIRECTS = 0
        session.post = mock_post(url, 302, {'location': 'https://contoso.com'})
        with self.assertRaises(TransportError):
            r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data='',
                                          allow_redirects=True)

        # CAS error
        session.post = mock_post(url, 999, {'X-CasErrorCode': 'AAARGH!'})
        with self.assertRaises(CASError):
            r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data='')

        # Allow XML data in a non-HTTP 200 response
        session.post = mock_post(url, 500, {}, '<?xml version="1.0" ?><foo></foo>')
        r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data='')
        self.assertEqual(r.content, b'<?xml version="1.0" ?><foo></foo>')

        # Bad status_code and bad text
        session.post = mock_post(url, 999, {})
        with self.assertRaises(TransportError):
            r, session = post_ratelimited(protocol=protocol, session=session, url=url, headers=None, data='')

        # Rate limit exceeded
        protocol.credentials = ServiceAccount(username=credentials.username, password=credentials.password, max_wait=1)
        session.post = mock_post(url, 503, {'connection': 'close'})
        protocol.renew_session = lambda s: s  # Return the same session so it's still mocked
        with self.assertRaises(RateLimitError) as rle:
            r, session = post_ratelimited(protocol=protocol, session=session, url='http://', headers=None, data='')
        self.assertEqual(rle.exception.url, url)
        self.assertEqual(rle.exception.status_code, 503)
        # Test something larger than the default wait, so we retry at least once
        protocol.credentials.max_wait = 15
        session.post = mock_post(url, 503, {'connection': 'close'})
        with self.assertRaises(RateLimitError) as rle:
            r, session = post_ratelimited(protocol=protocol, session=session, url='http://', headers=None, data='')
        self.assertEqual(rle.exception.url, url)
        self.assertEqual(rle.exception.status_code, 503)
        protocol.release_session(session)
        protocol.credentials = credentials

    def test_version_renegotiate(self):
        # Test that we can recover from a wrong API version. This is needed in version guessing and when the
        # autodiscover response returns a wrong server version for the account
        old_version = self.account.version.api_version
        self.account.version.api_version = 'XXX'
        list(self.account.inbox.filter(subject=get_random_string(16)))
        self.assertEqual(old_version, self.account.version.api_version)

    def test_soap_error(self):
        soap_xml = """\
<?xml version="1.0" encoding="utf-8" ?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Header>
    <t:ServerVersionInfo MajorVersion="8" MinorVersion="0" MajorBuildNumber="685" MinorBuildNumber="8"
                         xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types" />
  </soap:Header>
  <soap:Body>
    <soap:Fault>
      <faultcode>{faultcode}</faultcode>
      <faultstring>{faultstring}</faultstring>
      <faultactor>https://CAS01.example.com/EWS/Exchange.asmx</faultactor>
      <detail>
        <ResponseCode xmlns="http://schemas.microsoft.com/exchange/services/2006/errors">{responsecode}</ResponseCode>
        <Message xmlns="http://schemas.microsoft.com/exchange/services/2006/errors">{message}</Message>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>"""
        with self.assertRaises(SOAPError) as e:
            ResolveNames._get_soap_payload(response=MockResponse(soap_xml.format(
                faultcode='YYY', faultstring='AAA', responsecode='XXX', message='ZZZ'
            ).encode('utf-8')))
        self.assertIn('AAA', e.exception.args[0])
        self.assertIn('YYY', e.exception.args[0])
        self.assertIn('ZZZ', e.exception.args[0])
        with self.assertRaises(ErrorNonExistentMailbox) as e:
            ResolveNames._get_soap_payload(response=MockResponse(soap_xml.format(
                faultcode='ErrorNonExistentMailbox', faultstring='AAA', responsecode='XXX', message='ZZZ'
            ).encode('utf-8')))
        self.assertIn('AAA', e.exception.args[0])
        with self.assertRaises(ErrorNonExistentMailbox) as e:
            ResolveNames._get_soap_payload(response=MockResponse(soap_xml.format(
                faultcode='XXX', faultstring='AAA', responsecode='ErrorNonExistentMailbox', message='YYY'
            ).encode('utf-8')))
        self.assertIn('YYY', e.exception.args[0])

        # Test bad XML (no body)
        soap_xml = b"""\
<?xml version="1.0" encoding="utf-8" ?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header>
    <t:ServerVersionInfo MajorVersion="8" MinorVersion="0" MajorBuildNumber="685" MinorBuildNumber="8"
                         xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types" />
  </soap:Header>
  </soap:Body>
</soap:Envelope>"""
        with self.assertRaises(TransportError):
            ResolveNames._get_soap_payload(response=MockResponse(soap_xml))

        # Test bad XML (no fault)
        soap_xml = b"""\
<?xml version="1.0" encoding="utf-8" ?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header>
    <t:ServerVersionInfo MajorVersion="8" MinorVersion="0" MajorBuildNumber="685" MinorBuildNumber="8"
                         xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types" />
  </soap:Header>
  <soap:Body>
    <soap:Fault>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>"""
        with self.assertRaises(TransportError):
            ResolveNames._get_soap_payload(response=MockResponse(soap_xml))

    def test_element_container(self):
        svc = ResolveNames(self.account.protocol)
        soap_xml = b"""\
<?xml version="1.0" encoding="utf-8" ?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <m:ResolveNamesResponse xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
      <m:ResponseMessages>
        <m:ResolveNamesResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
        </m:ResolveNamesResponseMessage>
      </m:ResponseMessages>
    </m:ResolveNamesResponse>
  </soap:Body>
</soap:Envelope>"""
        resp = svc._get_soap_payload(response=MockResponse(soap_xml))
        with self.assertRaises(TransportError) as e:
            # Missing ResolutionSet elements
            list(svc._get_elements_in_response(response=resp))
        self.assertIn('ResolutionSet elements in ResponseMessage', e.exception.args[0])

    def test_get_elements(self):
        # Test that we can handle SOAP-level error messages
        svc = ResolveNames(self.account.protocol)
        with self.assertRaises(ErrorInvalidRequest):
            svc._get_elements(create_element('XXX'))

    @requests_mock.mock()
    def test_invalid_soap_response(self, m):
        m.post(self.account.protocol.service_endpoint, text='XXX')
        with self.assertRaises(SOAPError):
            self.account.inbox.all().count()

    def test_from_xml(self):
        # Test for all EWSElement classes that they handle None as input to from_xml()
        import exchangelib
        for mod in (exchangelib.attachments, exchangelib.extended_properties, exchangelib.indexed_properties,
                    exchangelib.folders, exchangelib.items, exchangelib.properties):
            for k, v in vars(mod).items():
                if type(v) != type:
                    continue
                if not issubclass(v, EWSElement):
                    continue
                # from_xml() does not support None input
                with self.assertRaises(Exception):
                    v.from_xml(elem=None, account=None)


class AccountTest(EWSTest):
    def test_magic(self):
        self.account.fullname = 'John Doe'
        self.assertIn(self.account.primary_smtp_address, str(self.account))
        self.assertIn(self.account.fullname, str(self.account))

    def test_validation(self):
        with self.assertRaises(ValueError):
            # Must have valid email address
            Account(primary_smtp_address='blah')
        with self.assertRaises(AttributeError):
            # Autodiscover requires credentials
            Account(primary_smtp_address='blah@example.com', autodiscover=True)
        with self.assertRaises(AttributeError):
            # Autodiscover must have credentials but must not have config
            Account(primary_smtp_address='blah@example.com', credentials='FOO', config='FOO', autodiscover=True)
        with self.assertRaises(AttributeError):
            # Non-autodiscover requires a config
            Account(primary_smtp_address='blah@example.com', autodiscover=False)

    def test_get_default_folder(self):
        # Test a normal folder lookup with GetFolder
        folder = self.account.root.get_default_folder(Calendar)
        self.assertIsInstance(folder, Calendar)
        self.assertNotEqual(folder.id, None)
        self.assertEqual(folder.name.lower(), Calendar.localized_names(self.account.locale)[0])

        class MockCalendar(Calendar):
            @classmethod
            def get_distinguished(cls, root):
                raise ErrorAccessDenied('foo')

        # Test an indirect folder lookup with FindItems
        folder = self.account.root.get_default_folder(MockCalendar)
        self.assertIsInstance(folder, MockCalendar)
        self.assertEqual(folder.id, None)
        self.assertEqual(folder.name, MockCalendar.DISTINGUISHED_FOLDER_ID)

        class MockCalendar(Calendar):
            @classmethod
            def get_distinguished(cls, root):
                raise ErrorFolderNotFound('foo')

        # Test using the one folder of this folder type
        with self.assertRaises(ErrorFolderNotFound):
            # This fails because there are no folders of type MockCalendar
            self.account.root.get_default_folder(MockCalendar)

        _orig = Calendar.get_distinguished
        try:
            Calendar.get_distinguished = MockCalendar.get_distinguished
            folder = self.account.root.get_default_folder(Calendar)
            self.assertIsInstance(folder, Calendar)
            self.assertNotEqual(folder.id, None)
            self.assertEqual(folder.name.lower(), MockCalendar.localized_names(self.account.locale)[0])
        finally:
            Calendar.get_distinguished = _orig

    def test_pickle(self):
        # Test that we can pickle various objects
        item = Message(folder=self.account.inbox, subject='XXX', categories=self.categories).save()
        pickle.dumps(item)
        try:
            for o in (
                item,
                self.account.protocol,
                self.account.root,
                self.account.inbox,
                self.account,
                Credentials('XXX', 'YYY'),
                ServiceAccount('XXX', 'YYY'),
            ):
                pickled_o = pickle.dumps(o)
                unpickled_o = pickle.loads(pickled_o)
                self.assertIsInstance(unpickled_o, type(o))
                if not isinstance(o, (Account, Protocol)):
                    # __eq__ is not defined on Protocol and Account
                    self.assertEqual(o, unpickled_o)
        finally:
            item.delete()


class AutodiscoverTest(EWSTest):
    def test_magic(self):
        # Just test we don't fail
        from exchangelib.autodiscover import _autodiscover_cache
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        str(_autodiscover_cache)
        repr(_autodiscover_cache)
        for protocol in _autodiscover_cache._protocols.values():
            str(protocol)
            repr(protocol)

    def test_autodiscover(self):
        primary_smtp_address, protocol = discover(email=self.account.primary_smtp_address,
                                                  credentials=self.account.protocol.credentials)
        self.assertEqual(primary_smtp_address, self.account.primary_smtp_address)
        self.assertEqual(protocol.service_endpoint.lower(), self.account.protocol.service_endpoint.lower())
        self.assertEqual(protocol.version.build, self.account.protocol.version.build)

    def test_autodiscover_failure(self):
        # Empty the cache
        from exchangelib.autodiscover import _autodiscover_cache
        _autodiscover_cache.clear()
        with self.assertRaises(ErrorNonExistentMailbox):
            # Test that error is raised with an empty cache
            discover(email='XXX.' + self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        with self.assertRaises(ErrorNonExistentMailbox):
            # Test that error is raised with a full cache
            discover(email='XXX.' + self.account.primary_smtp_address, credentials=self.account.protocol.credentials)

    def test_close_autodiscover_connections(self):
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        close_connections()

    def test_autodiscover_gc(self):
        # This is what Python garbage collection does
        from exchangelib.autodiscover import _autodiscover_cache
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        del _autodiscover_cache

    def test_autodiscover_direct_gc(self):
        # This is what Python garbage collection does
        from exchangelib.autodiscover import _autodiscover_cache
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        _autodiscover_cache.__del__()

    @requests_mock.mock(real_http=True)
    def test_autodiscover_cache(self, m):
        # Empty the cache
        from exchangelib.autodiscover import _autodiscover_cache
        _autodiscover_cache.clear()
        cache_key = (self.account.domain, self.account.protocol.credentials)
        # Not cached
        self.assertNotIn(cache_key, _autodiscover_cache)
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        # Now it's cached
        self.assertIn(cache_key, _autodiscover_cache)
        # Make sure the cache can be looked by value, not by id(). This is important for multi-threading/processing
        self.assertIn((
            self.account.primary_smtp_address.split('@')[1],
            Credentials(self.account.protocol.credentials.username, self.account.protocol.credentials.password),
            True
        ), _autodiscover_cache)
        # Poison the cache. discover() must survive and rebuild the cache
        _autodiscover_cache[cache_key] = AutodiscoverProtocol(
            service_endpoint='https://example.com/blackhole.asmx',
            credentials=Credentials('leet_user', 'cannaguess'),
            auth_type=NTLM
        )
        m.post('https://example.com/blackhole.asmx', status_code=404)
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        self.assertIn(cache_key, _autodiscover_cache)

        # Make sure that the cache is actually used on the second call to discover()
        _orig = exchangelib.autodiscover._try_autodiscover

        def _mock(*args, **kwargs):
            raise NotImplementedError()
        exchangelib.autodiscover._try_autodiscover = _mock
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        # Fake that another thread added the cache entry into the persistent storage but we don't have it in our
        # in-memory cache. The cache should work anyway.
        _autodiscover_cache._protocols.clear()
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        exchangelib.autodiscover._try_autodiscover = _orig
        # Make sure we can delete cache entries even though we don't have it in our in-memory cache
        _autodiscover_cache._protocols.clear()
        del _autodiscover_cache[cache_key]
        # This should also work if the cache does not contain the entry anymore
        del _autodiscover_cache[cache_key]

    def test_corrupt_autodiscover_cache(self):
        # Insert a fake Protocol instance into the cache
        from exchangelib.autodiscover import _autodiscover_cache
        key = (2, 'foo', 4)
        _autodiscover_cache[key] = namedtuple('P', ['service_endpoint', 'auth_type'])(1, 'bar')
        # Check that it exists. 'in' goes directly to the file
        self.assertTrue(key in _autodiscover_cache)
        # Destroy the backing cache file(s)
        for db_file in glob.glob(_autodiscover_cache._storage_file + '*'):
            with open(db_file, 'w') as f:
                f.write('XXX')
        # Check that we can recover from a destroyed file and that the entry no longer exists
        self.assertFalse(key in _autodiscover_cache)

    def test_autodiscover_from_account(self):
        from exchangelib.autodiscover import _autodiscover_cache
        _autodiscover_cache.clear()
        account = Account(primary_smtp_address=self.account.primary_smtp_address,
                          credentials=self.account.protocol.credentials,
                          autodiscover=True, locale='da_DK')
        self.assertEqual(account.primary_smtp_address, self.account.primary_smtp_address)
        self.assertEqual(account.protocol.service_endpoint.lower(), self.account.protocol.service_endpoint.lower())
        self.assertEqual(account.protocol.version.build, self.account.protocol.version.build)
        # Make sure cache is full
        self.assertTrue((account.domain, self.account.protocol.credentials, True) in _autodiscover_cache)
        # Test that autodiscover works with a full cache
        account = Account(primary_smtp_address=self.account.primary_smtp_address,
                          credentials=self.account.protocol.credentials,
                          autodiscover=True, locale='da_DK')
        self.assertEqual(account.primary_smtp_address, self.account.primary_smtp_address)
        # Test cache manipulation
        key = (account.domain, self.account.protocol.credentials, True)
        self.assertTrue(key in _autodiscover_cache)
        del _autodiscover_cache[key]
        self.assertFalse(key in _autodiscover_cache)
        del _autodiscover_cache

    def test_autodiscover_redirect(self):
        # Prime the cache
        email, p = discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        _orig = exchangelib.autodiscover._autodiscover_quick

        # Test that we can get another address back than the address we're looking up
        def _mock1(credentials, email, protocol):
            return 'john@example.com', p
        exchangelib.autodiscover._autodiscover_quick = _mock1
        test_email, p = discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        self.assertEqual(test_email, 'john@example.com')

        # Test that we can survive being asked to lookup with another address
        def _mock2(credentials, email, protocol):
            if email == 'xxxxxx@%s' % self.account.domain:
                raise ErrorNonExistentMailbox(email)
            raise AutoDiscoverRedirect(redirect_email='xxxxxx@'+self.account.domain)
        exchangelib.autodiscover._autodiscover_quick = _mock2
        with self.assertRaises(ErrorNonExistentMailbox):
            discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)

        # Test that we catch circular redirects
        def _mock3(credentials, email, protocol):
            raise AutoDiscoverRedirect(redirect_email=self.account.primary_smtp_address)
        exchangelib.autodiscover._autodiscover_quick = _mock3
        with self.assertRaises(AutoDiscoverCircularRedirect):
            discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        exchangelib.autodiscover._autodiscover_quick = _orig

        # Test that we catch circular redirects when cache is empty. This is a different code path
        _orig = exchangelib.autodiscover._try_autodiscover
        def _mock4(hostname, credentials, email):
            raise AutoDiscoverRedirect(redirect_email=self.account.primary_smtp_address)
        exchangelib.autodiscover._try_autodiscover = _mock4
        exchangelib.autodiscover._autodiscover_cache.clear()
        with self.assertRaises(AutoDiscoverCircularRedirect):
            discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        exchangelib.autodiscover._try_autodiscover = _orig

        # Test that we can survive being asked to lookup with another address, when cache is empty
        def _mock5(hostname, credentials, email):
            if email == 'xxxxxx@%s' % self.account.domain:
                raise ErrorNonExistentMailbox(email)
            raise AutoDiscoverRedirect(redirect_email='xxxxxx@'+self.account.domain)
        exchangelib.autodiscover._try_autodiscover = _mock5
        exchangelib.autodiscover._autodiscover_cache.clear()
        with self.assertRaises(ErrorNonExistentMailbox):
            discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
        exchangelib.autodiscover._try_autodiscover = _orig

    def test_canonical_lookup(self):
        from exchangelib.autodiscover import _get_canonical_name
        self.assertEqual(_get_canonical_name('example.com'), None)
        self.assertEqual(_get_canonical_name('example.com.'), 'example.com')
        self.assertEqual(_get_canonical_name('example.XXXXX.'), None)

    def test_srv(self):
        from exchangelib.autodiscover import _get_hostname_from_srv
        with self.assertRaises(AutoDiscoverFailed):
            # Unknown doomain
            _get_hostname_from_srv('example.XXXXX.')
        with self.assertRaises(AutoDiscoverFailed):
            # No SRV record
            _get_hostname_from_srv('example.com.')
        # Finding a real server that has a correct SRV record is not easy. Mock it
        _orig = dns.resolver.Resolver

        class _Mock1:
            def query(self, hostname, cat):
                class A:
                    def to_text(self):
                        # Return a valid record
                        return '1 2 3 example.com.'
                return [A()]
        dns.resolver.Resolver = _Mock1
        # Test a valid record
        self.assertEqual(_get_hostname_from_srv('example.com.'), 'example.com')

        class _Mock2:
            def query(self, hostname, cat):
                class A:
                    def to_text(self):
                        # Return malformed data
                        return 'XXXXXXX'
                return [A()]
        dns.resolver.Resolver = _Mock2
        # Test an invalid record
        with self.assertRaises(AutoDiscoverFailed):
            _get_hostname_from_srv('example.com.')
        dns.resolver.Resolver = _orig

    def test_parse_response(self):
        from exchangelib.autodiscover import _parse_response
        with self.assertRaises(AutoDiscoverFailed):
            _parse_response(b'XXX')  # Invalid response

        xml = b'''<?xml version="1.0" encoding="utf-8"?><foo>bar</foo>'''
        with self.assertRaises(AutoDiscoverFailed):
            _parse_response(xml)  # Invalid XML response

        # Redirection
        xml = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <Action>redirectAddr</Action>
            <RedirectAddr>foo@example.com</RedirectAddr>
        </Account>
    </Response>
</Autodiscover>'''
        with self.assertRaises(AutoDiscoverRedirect) as e:
            _parse_response(xml)  # Redirect to primary email
        self.assertEqual(e.exception.redirect_email, 'foo@example.com')

        # Select EXPR if it's there, and there are multiple available
        xml = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <AccountType>email</AccountType>
            <Action>settings</Action>
            <Protocol>
                <Type>EXCH</Type>
                <EwsUrl>https://exch.example.com/EWS/Exchange.asmx</EwsUrl>
            </Protocol>
            <Protocol>
                <Type>EXPR</Type>
                <EwsUrl>https://expr.example.com/EWS/Exchange.asmx</EwsUrl>
            </Protocol>
        </Account>
    </Response>
</Autodiscover>'''
        self.assertEqual(_parse_response(xml)[0], 'https://expr.example.com/EWS/Exchange.asmx')

        # Select EXPR if EXPR is unavailable
        xml = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <AccountType>email</AccountType>
            <Action>settings</Action>
            <Protocol>
                <Type>EXCH</Type>
                <EwsUrl>https://exch.example.com/EWS/Exchange.asmx</EwsUrl>
            </Protocol>
        </Account>
    </Response>
</Autodiscover>'''
        self.assertEqual(_parse_response(xml)[0], 'https://exch.example.com/EWS/Exchange.asmx')

        # Fail if neither EXPR nor EXPR are unavailable
        xml = b'''\
<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
    <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
        <User>
            <AutoDiscoverSMTPAddress>john@demo.affect-it.dk</AutoDiscoverSMTPAddress>
        </User>
        <Account>
            <AccountType>email</AccountType>
            <Action>settings</Action>
            <Protocol>
                <Type>XXX</Type>
                <EwsUrl>https://xxx.example.com/EWS/Exchange.asmx</EwsUrl>
            </Protocol>
        </Account>
    </Response>
</Autodiscover>'''
        with self.assertRaises(AutoDiscoverFailed):
            _parse_response(xml)

    def test_disable_ssl_verification(self):
        if not self.verify_ssl:
            # We can only run this test if we haven't already disabled TLS
            raise self.skipTest('TLS verification already disabled')
        import exchangelib.autodiscover

        default_adapter_cls = BaseProtocol.HTTP_ADAPTER_CLS

        # A normal discover should succeed
        exchangelib.autodiscover._autodiscover_cache.clear()
        discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)

        # Smash TLS verification using an untrusted certificate
        with tempfile.NamedTemporaryFile() as f:
            f.write(b'''\
 -----BEGIN CERTIFICATE-----
MIIENzCCAx+gAwIBAgIJAOYfYfw7NCOcMA0GCSqGSIb3DQEBBQUAMIGxMQswCQYD
VQQGEwJVUzERMA8GA1UECAwITWFyeWxhbmQxFDASBgNVBAcMC0ZvcmVzdCBIaWxs
MScwJQYDVQQKDB5UaGUgQXBhY2hlIFNvZnR3YXJlIEZvdW5kYXRpb24xFjAUBgNV
BAsMDUFwYWNoZSBUaHJpZnQxEjAQBgNVBAMMCWxvY2FsaG9zdDEkMCIGCSqGSIb3
DQEJARYVZGV2QHRocmlmdC5hcGFjaGUub3JnMB4XDTE0MDQwNzE4NTgwMFoXDTIy
MDYyNDE4NTgwMFowgbExCzAJBgNVBAYTAlVTMREwDwYDVQQIDAhNYXJ5bGFuZDEU
MBIGA1UEBwwLRm9yZXN0IEhpbGwxJzAlBgNVBAoMHlRoZSBBcGFjaGUgU29mdHdh
cmUgRm91bmRhdGlvbjEWMBQGA1UECwwNQXBhY2hlIFRocmlmdDESMBAGA1UEAwwJ
bG9jYWxob3N0MSQwIgYJKoZIhvcNAQkBFhVkZXZAdGhyaWZ0LmFwYWNoZS5vcmcw
ggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCqE9TE9wEXp5LRtLQVDSGQ
GV78+7ZtP/I/ZaJ6Q6ZGlfxDFvZjFF73seNhAvlKlYm/jflIHYLnNOCySN8I2Xw6
L9MbC+jvwkEKfQo4eDoxZnOZjNF5J1/lZtBeOowMkhhzBMH1Rds351/HjKNg6ZKg
2Cldd0j7HbDtEixOLgLbPRpBcaYrLrNMasf3Hal+x8/b8ue28x93HSQBGmZmMIUw
AinEu/fNP4lLGl/0kZb76TnyRpYSPYojtS6CnkH+QLYnsRREXJYwD1Xku62LipkX
wCkRTnZ5nUsDMX6FPKgjQFQCWDXG/N096+PRUQAChhrXsJ+gF3NqWtDmtrhVQF4n
AgMBAAGjUDBOMB0GA1UdDgQWBBQo8v0wzQPx3EEexJPGlxPK1PpgKjAfBgNVHSME
GDAWgBQo8v0wzQPx3EEexJPGlxPK1PpgKjAMBgNVHRMEBTADAQH/MA0GCSqGSIb3
DQEBBQUAA4IBAQBGFRiJslcX0aJkwZpzTwSUdgcfKbpvNEbCNtVohfQVTI4a/oN5
U+yqDZJg3vOaOuiAZqyHcIlZ8qyesCgRN314Tl4/JQ++CW8mKj1meTgo5YFxcZYm
T9vsI3C+Nzn84DINgI9mx6yktIt3QOKZRDpzyPkUzxsyJ8J427DaimDrjTR+fTwD
1Dh09xeeMnSa5zeV1HEDyJTqCXutLetwQ/IyfmMBhIx+nvB5f67pz/m+Dv6V0r3I
p4HCcdnDUDGJbfqtoqsAATQQWO+WWuswB6mOhDbvPTxhRpZq6AkgWqv4S+u3M2GO
r5p9FrBgavAw5bKO54C0oQKpN/5fta5l6Ws0
-----END CERTIFICATE-----''')
            try:
                os.environ['REQUESTS_CA_BUNDLE'] = f.name

                # Now discover should fail. TLS errors mean we exhaust all autodiscover attempts
                with self.assertRaises(AutoDiscoverFailed):
                    exchangelib.autodiscover._autodiscover_cache.clear()
                    discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)

                # Disable insecure TLS warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    # Make sure we can survive TLS validation errors when using the custom adapter
                    exchangelib.autodiscover._autodiscover_cache.clear()
                    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
                    discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)

                    # Test that the custom adapter also works when validation is OK again
                    del os.environ['REQUESTS_CA_BUNDLE']
                    exchangelib.autodiscover._autodiscover_cache.clear()
                    discover(email=self.account.primary_smtp_address, credentials=self.account.protocol.credentials)
            finally:
                # Reset environment
                os.environ.pop('REQUESTS_CA_BUNDLE', None)  # May already have been deleted
                exchangelib.autodiscover._autodiscover_cache.clear()
                BaseProtocol.HTTP_ADAPTER_CLS = default_adapter_cls


class FolderTest(EWSTest):
    def test_folder_id_deprecation(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Folder(id='XXX', changekey='YYY').folder_id
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Folder.get_field_by_fieldname('folder_id')
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Folder(folder_id='XXX')
            self.assertEqual(len(w), 1, w)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))

    def test_item_id_deprecation(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Messages(root=self.account.root, id='ZZZ').get(item_id='XXX')
            self.assertGreaterEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Messages(root=self.account.root, id='ZZZ').all().only('item_id')
            self.assertGreaterEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Messages(root=self.account.root, id='ZZZ').all().values('item_id')
            self.assertGreaterEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Trigger a warning
            Messages(root=self.account.root, id='ZZZ').all().values_list('item_id')
            self.assertGreaterEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, PendingDeprecationWarning), w[0].category)
            self.assertIn("Use 'id' instead", str(w[0].message))

    def test_folders(self):
        for f in self.account.root.walk():
            if isinstance(f, System):
                # No access to system folder, apparently
                continue
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
            f.test_access()
            # Test item field lookup
            self.assertEqual(f.get_item_field_by_fieldname('subject').name, 'subject')
            with self.assertRaises(ValueError):
                f.get_item_field_by_fieldname('XXX')

    def test_find_folders(self):
        folders = list(FolderCollection(account=self.account, folders=[self.account.root]).find_folders())
        self.assertGreater(len(folders), 40, sorted(f.name for f in folders))

        # Test that FindFolder can handle FolderId instances
        folders = list(FolderCollection(account=self.account, folders=[DistinguishedFolderId(
            id=Inbox.DISTINGUISHED_FOLDER_ID,
            mailbox=Mailbox(email_address=self.account.primary_smtp_address)
        )]).get_folders())
        self.assertGreaterEqual(len(folders), 0, sorted(f.name for f in folders))

    def test_find_folders_with_restriction(self):
        # Exact match
        folders = list(FolderCollection(account=self.account, folders=[self.account.root])
                       .find_folders(q=Q(name='Top of Information Store')))
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))
        # Startswith
        folders = list(FolderCollection(account=self.account, folders=[self.account.root])
                       .find_folders(q=Q(name__startswith='Top of ')))
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))
        # Wrong case
        folders = list(FolderCollection(account=self.account, folders=[self.account.root])
                       .find_folders(q=Q(name__startswith='top of ')))
        self.assertEqual(len(folders), 0, sorted(f.name for f in folders))
        # Case insensitive
        folders = list(FolderCollection(account=self.account, folders=[self.account.root])
                       .find_folders(q=Q(name__istartswith='top of ')))
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

    def test_get_folders(self):
        folders = list(FolderCollection(account=self.account, folders=[self.account.root]).get_folders())
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

        # Test that GetFolder can handle FolderId instances
        folders = list(FolderCollection(account=self.account, folders=[DistinguishedFolderId(
            id=Inbox.DISTINGUISHED_FOLDER_ID,
            mailbox=Mailbox(email_address=self.account.primary_smtp_address)
        )]).get_folders())
        self.assertEqual(len(folders), 1, sorted(f.name for f in folders))

    def test_get_folders_with_distinguished_id(self):
        # Test that we return an Inbox instance and not a generic Messages or Folder instance when we call GetFolder
        # with a DistinguishedFolderId instance with an ID of Inbox.DISTINGUISHED_FOLDER_ID.
        inbox = list(GetFolder(account=self.account).call(
            folders=[DistinguishedFolderId(
                id=Inbox.DISTINGUISHED_FOLDER_ID,
                mailbox=Mailbox(email_address=self.account.primary_smtp_address))
            ],
            shape='IdOnly',
            additional_fields=[],
        ))[0]
        self.assertIsInstance(inbox, Inbox)

    def test_folder_grouping(self):
        # If you get errors here, you probably need to fill out [folder class].LOCALIZED_NAMES for your locale.
        for f in self.account.root.walk():
            if isinstance(f, (
                    Messages, DeletedItems, AllContacts, MyContactsExtended, Sharing, Favorites, SyncIssues, MyContacts
            )):
                self.assertEqual(f.folder_class, 'IPF.Note')
            elif isinstance(f, GALContacts):
                self.assertEqual(f.folder_class, 'IPF.Contact.GalContacts')
            elif isinstance(f, RecipientCache):
                self.assertEqual(f.folder_class, 'IPF.Contact.RecipientCache')
            elif isinstance(f, Contacts):
                self.assertEqual(f.folder_class, 'IPF.Contact')
            elif isinstance(f, Calendar):
                self.assertEqual(f.folder_class, 'IPF.Appointment')
            elif isinstance(f, (Tasks, ToDoSearch)):
                self.assertEqual(f.folder_class, 'IPF.Task')
            elif isinstance(f, Reminders):
                self.assertEqual(f.folder_class, 'Outlook.Reminder')
            elif isinstance(f, AllItems):
                self.assertEqual(f.folder_class, 'IPF')
            elif isinstance(f, ConversationSettings):
                self.assertEqual(f.folder_class, 'IPF.Configuration')
            elif isinstance(f, Friends):
                self.assertEqual(f.folder_class, 'IPF.Note')
            elif isinstance(f, RSSFeeds):
                self.assertEqual(f.folder_class, 'IPF.Note.OutlookHomepage')
            elif isinstance(f, IMContactList):
                self.assertEqual(f.folder_class, 'IPF.Contact.MOC.ImContactList')
            elif isinstance(f, QuickContacts):
                self.assertEqual(f.folder_class, 'IPF.Contact.MOC.QuickContacts')
            elif isinstance(f, Journal):
                self.assertEqual(f.folder_class, 'IPF.Journal')
            elif isinstance(f, Notes):
                self.assertEqual(f.folder_class, 'IPF.StickyNote')
            else:
                self.assertEqual(f.folder_class, None, (f.name, f.__class__.__name__, f.folder_class))
                self.assertIsInstance(f, Folder)

    def test_counts(self):
        # Test count values on a folder
        f = Folder(parent=self.account.inbox, name=get_random_string(16)).save()
        f.refresh()

        self.assertEqual(f.total_count, 0)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 0)
        # Create some items
        items = []
        for i in range(3):
            subject = 'Test Subject %s' % i
            item = Message(account=self.account, folder=f, is_read=False, subject=subject, categories=self.categories)
            item.save()
            items.append(item)
        # Refresh values and see that total_count and unread_count changes
        f.refresh()
        self.assertEqual(f.total_count, 3)
        self.assertEqual(f.unread_count, 3)
        self.assertEqual(f.child_folder_count, 0)
        for i in items:
            i.is_read = True
            i.save()
        # Refresh values and see that unread_count changes
        f.refresh()
        self.assertEqual(f.total_count, 3)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 0)
        self.bulk_delete(items)
        # Refresh values and see that total_count changes
        f.refresh()
        self.assertEqual(f.total_count, 0)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 0)
        # Create some subfolders
        subfolders = []
        for i in range(3):
            subfolders.append(Folder(parent=f, name=get_random_string(16)).save())
        # Refresh values and see that child_folder_count changes
        f.refresh()
        self.assertEqual(f.total_count, 0)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 3)
        for sub_f in subfolders:
            sub_f.delete()
        # Refresh values and see that child_folder_count changes
        f.refresh()
        self.assertEqual(f.total_count, 0)
        self.assertEqual(f.unread_count, 0)
        self.assertEqual(f.child_folder_count, 0)
        f.delete()

    def test_refresh(self):
        # Test that we can refresh folders
        for f in self.account.root.walk():
            if isinstance(f, System):
                # Can't refresh the 'System' folder for some reason
                        continue
            old_values = {}
            for field in f.FIELDS:
                old_values[field.name] = getattr(f, field.name)
                if field.name in ('account', 'id', 'changekey', 'parent_folder_id'):
                    # These are needed for a successful refresh()
                    continue
                if field.is_read_only:
                    continue
                setattr(f, field.name, self.random_val(field))
            f.refresh()
            for field in f.FIELDS:
                if field.name == 'changekey':
                    # folders may change while we're testing
                    continue
                if field.is_read_only:
                    # count values may change during the test
                    continue
                self.assertEqual(getattr(f, field.name), old_values[field.name], field.name)

        # Test refresh of root
        all_folders = sorted(f.name for f in self.account.root.walk())
        self.account.root.refresh()
        self.assertIsNone(self.account.root._subfolders)
        self.assertEqual(
            sorted(f.name for f in self.account.root.walk()),
            all_folders
        )

        folder = Folder()
        with self.assertRaises(ValueError):
            folder.refresh()  # Must have an account
        folder.root = 'XXX'
        with self.assertRaises(ValueError):
            folder.refresh()  # Must have an id

    def test_parent(self):
        self.assertEqual(
            self.account.calendar.parent.name,
            'Top of Information Store'
        )
        self.assertEqual(
            self.account.calendar.parent.parent.name,
            'root'
        )

    def test_children(self):
        self.assertIn(
            'Top of Information Store',
            [c.name for c in self.account.root.children]
        )

    def test_parts(self):
        self.assertEqual(
            [p.name for p in self.account.calendar.parts],
            ['root', 'Top of Information Store', self.account.calendar.name]
        )

    def test_absolute(self):
        self.assertEqual(
            self.account.calendar.absolute,
            '/root/Top of Information Store/' + self.account.calendar.name
        )

    def test_walk(self):
        self.assertGreaterEqual(len(list(self.account.root.walk())), 20)
        self.assertGreaterEqual(len(list(self.account.contacts.walk())), 2)

    def test_tree(self):
        self.assertTrue(self.account.root.tree().startswith('root'))

    def test_glob(self):
        self.assertGreaterEqual(len(list(self.account.root.glob('*'))), 5)
        self.assertEqual(len(list(self.account.contacts.glob('GAL*'))), 1)
        self.assertGreaterEqual(len(list(self.account.contacts.glob('/'))), 5)
        self.assertGreaterEqual(len(list(self.account.contacts.glob('../*'))), 5)
        self.assertEqual(len(list(self.account.root.glob('**/%s' % self.account.contacts.name))), 1)
        self.assertEqual(len(list(self.account.root.glob('Top of*/%s' % self.account.contacts.name))), 1)

    def test_collection_filtering(self):
        self.assertGreaterEqual(self.account.root.tois.children.all().count(), 0)
        self.assertGreaterEqual(self.account.root.tois.walk().all().count(), 0)
        self.assertGreaterEqual(self.account.root.tois.glob('*').all().count(), 0)

    def test_empty_collections(self):
        self.assertEqual(self.account.trash.children.all().count(), 0)
        self.assertEqual(self.account.trash.walk().all().count(), 0)
        self.assertEqual(self.account.trash.glob('XXX').all().count(), 0)
        self.assertEqual(list(self.account.trash.glob('XXX').get_folders()), [])
        self.assertEqual(list(self.account.trash.glob('XXX').find_folders()), [])

    def test_div_navigation(self):
        self.assertEqual(
            (self.account.root / 'Top of Information Store' / self.account.calendar.name).id,
            self.account.calendar.id
        )
        self.assertEqual(
            (self.account.root / 'Top of Information Store' / '..').id,
            self.account.root.id
        )
        self.assertEqual(
            (self.account.root / '.').id,
            self.account.root.id
        )

    def test_double_div_navigation(self):
        self.account.root.refresh()  # Clear the cache

        # Test normal navigation
        self.assertEqual(
            (self.account.root // 'Top of Information Store' // self.account.calendar.name).id,
            self.account.calendar.id
        )
        self.assertIsNone(self.account.root._subfolders)

        # Test parent ('..') syntax. Should not work
        with self.assertRaises(ValueError) as e:
            self.account.root // 'Top of Information Store' // '..'
        self.assertEqual(e.exception.args[0], 'Cannot get parent without a folder cache')
        self.assertIsNone(self.account.root._subfolders)

        # Test self ('.') syntax
        self.assertEqual(
            (self.account.root // '.').id,
            self.account.root.id
        )
        self.assertIsNone(self.account.root._subfolders)

    def test_extended_properties(self):
        # Extended properties also work with folders. Here's an example of getting the size (in bytes) of a folder:
        class FolderSize(ExtendedProperty):
            property_tag = 0x0e08
            property_type = 'Integer'

        try:
            Folder.register('size', FolderSize)
            self.account.inbox.refresh()
            self.assertGreater(self.account.inbox.size, 0)
        finally:
            Folder.deregister('size')

    def test_create_update_empty_delete(self):
        f = Messages(parent=self.account.inbox, name=get_random_string(16))
        f.save()
        self.assertIsNotNone(f.id)
        self.assertIsNotNone(f.changekey)

        new_name = get_random_string(16)
        f.name = new_name
        f.save()
        f.refresh()
        self.assertEqual(f.name, new_name)

        with self.assertRaises(ErrorObjectTypeChanged):
            # FolderClass may not be changed
            f.folder_class = get_random_string(16)
            f.save(update_fields=['folder_class'])

        # Create a subfolder
        Messages(parent=f, name=get_random_string(16)).save()
        self.assertEqual(len(list(f.children)), 1)
        f.empty()
        self.assertEqual(len(list(f.children)), 1)
        f.empty(delete_sub_folders=True)
        self.assertEqual(len(list(f.children)), 0)

        # Create a subfolder again, and delete it by wiping
        Messages(parent=f, name=get_random_string(16)).save()
        self.assertEqual(len(list(f.children)), 1)
        f.wipe()
        self.assertEqual(len(list(f.children)), 0)

        f.delete()
        with self.assertRaises(ValueError):
            # No longer has an ID
            f.refresh()

        # Delete all subfolders of inbox
        for c in self.account.inbox.children:
            c.delete()

        with self.assertRaises(ErrorDeleteDistinguishedFolder):
            self.account.inbox.delete()

    def test_generic_folder(self):
        f = Folder(parent=self.account.inbox, name=get_random_string(16))
        f.save()
        f.name = get_random_string(16)
        f.save()
        f.delete()


class BaseItemTest(EWSTest):
    TEST_FOLDER = None
    FOLDER_CLASS = None
    ITEM_CLASS = None

    @classmethod
    def setUpClass(cls):
        if cls is BaseItemTest:
            raise unittest.SkipTest("Skip BaseItemTest, it's only for inheritance")
        super(BaseItemTest, cls).setUpClass()

    def setUp(self):
        super(BaseItemTest, self).setUp()
        self.test_folder = getattr(self.account, self.TEST_FOLDER)
        self.assertEqual(type(self.test_folder), self.FOLDER_CLASS)
        self.assertEqual(self.test_folder.DISTINGUISHED_FOLDER_ID, self.TEST_FOLDER)
        self.test_folder.filter(categories__contains=self.categories).delete()

    def tearDown(self):
        self.test_folder.filter(categories__contains=self.categories).delete()
        # Delete all delivery receipts
        self.test_folder.filter(subject__startswith='Delivered: Subject: ').delete()

    def get_random_insert_kwargs(self):
        insert_kwargs = {}
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_read_only:
                # These cannot be created
                continue
            if f.name == 'mime_content':
                # This needs special formatting. See separate test_mime_content() test
                continue
            if f.name == 'attachments':
                # Testing attachments is heavy. Leave this to specific tests
                insert_kwargs[f.name] = []
                continue
            if f.name == 'resources':
                # The test server doesn't have any resources
                insert_kwargs[f.name] = []
                continue
            if f.name == 'optional_attendees':
                # 'optional_attendees' and 'required_attendees' are mutually exclusive
                insert_kwargs[f.name] = None
                continue
            if f.name == 'start':
                start = get_random_date()
                insert_kwargs[f.name], insert_kwargs['end'] = \
                    get_random_datetime_range(start_date=start, end_date=start, tz=self.account.default_timezone)
                insert_kwargs['recurrence'] = self.random_val(self.ITEM_CLASS.get_field_by_fieldname('recurrence'))
                insert_kwargs['recurrence'].boundary.start = insert_kwargs[f.name].date()
                continue
            if f.name == 'end':
                continue
            if f.name == 'recurrence':
                continue
            if f.name == 'due_date':
                # start_date must be before due_date
                insert_kwargs['start_date'], insert_kwargs[f.name] = \
                    get_random_datetime_range(tz=self.account.default_timezone)
                continue
            if f.name == 'start_date':
                continue
            if f.name == 'status':
                # Start with an incomplete task
                status = get_random_choice(f.supported_choices(version=self.account.version) - {Task.COMPLETED})
                insert_kwargs[f.name] = status
                if status == Task.NOT_STARTED:
                    insert_kwargs['percent_complete'] = Decimal(0)
                else:
                    insert_kwargs['percent_complete'] = get_random_decimal(1, 99)
                continue
            if f.name == 'percent_complete':
                continue
            insert_kwargs[f.name] = self.random_val(f)
        return insert_kwargs

    def get_random_update_kwargs(self, item, insert_kwargs):
        update_kwargs = {}
        now = UTC_NOW()
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_read_only:
                # These cannot be changed
                continue
            if not item.is_draft and f.is_read_only_after_send:
                # These cannot be changed when the item is no longer a draft
                continue
            if f.name == 'message_id' and f.is_read_only_after_send:
                # Cannot be updated, regardless of draft status
                continue
            if f.name == 'attachments':
                # Testing attachments is heavy. Leave this to specific tests
                update_kwargs[f.name] = []
                continue
            if f.name == 'resources':
                # The test server doesn't have any resources
                update_kwargs[f.name] = []
                continue
            if isinstance(f, AttachmentField):
                # Attachments are handled separately
                continue
            if f.name == 'start':
                start = get_random_date(start_date=insert_kwargs['end'].date())
                update_kwargs[f.name], update_kwargs['end'] = \
                    get_random_datetime_range(start_date=start, end_date=start, tz=self.account.default_timezone)
                update_kwargs['recurrence'] = self.random_val(self.ITEM_CLASS.get_field_by_fieldname('recurrence'))
                update_kwargs['recurrence'].boundary.start = update_kwargs[f.name].date()
                continue
            if f.name == 'end':
                continue
            if f.name == 'recurrence':
                continue
            if f.name == 'due_date':
                # start_date must be before due_date, and before complete_date which must be in the past
                update_kwargs['start_date'], update_kwargs[f.name] = \
                    get_random_datetime_range(end_date=now.date(), tz=self.account.default_timezone)
                continue
            if f.name == 'start_date':
                continue
            if f.name == 'status':
                # Update task to a completed state. complete_date must be a date in the past, and < than start_date
                update_kwargs[f.name] = Task.COMPLETED
                update_kwargs['percent_complete'] = Decimal(100)
                continue
            if f.name == 'percent_complete':
                continue
            if f.name == 'reminder_is_set':
                if self.ITEM_CLASS == Task:
                    # Task type doesn't allow updating 'reminder_is_set' to True
                    update_kwargs[f.name] = False
                else:
                    update_kwargs[f.name] = not insert_kwargs[f.name]
                continue
            if isinstance(f, BooleanField):
                update_kwargs[f.name] = not insert_kwargs[f.name]
                continue
            if f.value_cls in (Mailbox, Attendee):
                if insert_kwargs[f.name] is None:
                    update_kwargs[f.name] = self.random_val(f)
                else:
                    update_kwargs[f.name] = None
                continue
            update_kwargs[f.name] = self.random_val(f)
        if update_kwargs.get('is_all_day', False):
            # For is_all_day items, EWS will remove the time part of start and end values
            update_kwargs['start'] = update_kwargs['start'].replace(hour=0, minute=0, second=0, microsecond=0)
            update_kwargs['end'] = \
                update_kwargs['end'].replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        if self.ITEM_CLASS == CalendarItem:
            # EWS always sets due date to 'start'
            update_kwargs['reminder_due_by'] = update_kwargs['start']
        return update_kwargs

    def get_test_item(self, folder=None, categories=None):
        item_kwargs = self.get_random_insert_kwargs()
        item_kwargs['categories'] = categories or self.categories
        return self.ITEM_CLASS(folder=folder or self.test_folder, **item_kwargs)

    def test_field_names(self):
        # Test that fieldnames don't clash with Python keywords
        for f in self.ITEM_CLASS.FIELDS:
            self.assertNotIn(f.name, kwlist)

    def test_magic(self):
        item = self.get_test_item()
        self.assertIn('subject=', str(item))
        self.assertIn(item.__class__.__name__, repr(item))

    def test_validation(self):
        item = self.get_test_item()
        item.clean()
        for f in self.ITEM_CLASS.FIELDS:
            # Test field max_length
            if isinstance(f, CharField) and f.max_length:
                with self.assertRaises(ValueError):
                    setattr(item, f.name, 'a' * (f.max_length + 1))
                    item.clean()
                    setattr(item, f.name, 'a')

    def test_empty_args(self):
        # We allow empty sequences for these methods
        self.assertEqual(self.test_folder.bulk_create(items=[]), [])
        self.assertEqual(list(self.account.fetch(ids=[])), [])
        self.assertEqual(self.account.bulk_create(folder=self.test_folder, items=[]), [])
        self.assertEqual(self.account.bulk_update(items=[]), [])
        self.assertEqual(self.account.bulk_delete(ids=[]), [])
        self.assertEqual(self.account.bulk_send(ids=[]), [])
        self.assertEqual(self.account.bulk_copy(ids=[], to_folder=self.account.trash), [])
        self.assertEqual(self.account.bulk_move(ids=[], to_folder=self.account.trash), [])
        self.assertEqual(self.account.upload(data=[]), [])
        self.assertEqual(self.account.export(items=[]), [])

    def test_qs_args(self):
        # We allow querysets for these methods
        qs = self.test_folder.none()
        self.assertEqual(list(self.account.fetch(ids=qs)), [])
        with self.assertRaises(ValueError):
            # bulk_update() does not allow queryset input
            self.assertEqual(self.account.bulk_update(items=qs), [])
        self.assertEqual(self.account.bulk_delete(ids=qs), [])
        self.assertEqual(self.account.bulk_send(ids=qs), [])
        self.assertEqual(self.account.bulk_copy(ids=qs, to_folder=self.account.trash), [])
        self.assertEqual(self.account.bulk_move(ids=qs, to_folder=self.account.trash), [])
        with self.assertRaises(ValueError):
            # upload() does not allow queryset input
            self.assertEqual(self.account.upload(data=qs), [])
        self.assertEqual(self.account.export(items=qs), [])

    def test_no_kwargs(self):
        self.assertEqual(self.test_folder.bulk_create([]), [])
        self.assertEqual(list(self.account.fetch([])), [])
        self.assertEqual(self.account.bulk_create(self.test_folder, []), [])
        self.assertEqual(self.account.bulk_update([]), [])
        self.assertEqual(self.account.bulk_delete([]), [])
        self.assertEqual(self.account.bulk_send([]), [])
        self.assertEqual(self.account.bulk_copy([], to_folder=self.account.trash), [])
        self.assertEqual(self.account.bulk_move([], to_folder=self.account.trash), [])
        self.assertEqual(self.account.upload([]), [])
        self.assertEqual(self.account.export([]), [])

    def test_invalid_bulk_args(self):
        # Test bulk_create
        with self.assertRaises(ValueError):
            # Folder must belong to account
            self.account.bulk_create(folder=Folder(root=None), items=[])
        with self.assertRaises(AttributeError):
            # Must have folder on save
            self.account.bulk_create(folder=None, items=[], message_disposition=SAVE_ONLY)
        # Test that we can send_and_save with a default folder
        self.account.bulk_create(folder=None, items=[], message_disposition=SEND_AND_SAVE_COPY)
        with self.assertRaises(AttributeError):
            # Must not have folder on send-only
            self.account.bulk_create(folder=self.test_folder, items=[], message_disposition=SEND_ONLY)

        # Test bulk_update
        with self.assertRaises(ValueError):
            # Cannot update in send-only mode
            self.account.bulk_update(items=[], message_disposition=SEND_ONLY)

    def test_invalid_direct_args(self):
        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.account = None
            item.save()  # Must have account on save
        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.id = 'XXX'  # Fake a saved item
            item.account = None
            item.save()  # Must have account on update
        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.save(update_fields=['foo', 'bar'])  # update_fields is only valid on update

        if self.ITEM_CLASS == Message:
            with self.assertRaises(ValueError):
                item = self.get_test_item()
                item.account = None
                item.send()  # Must have account on send
            with self.assertRaises(ErrorItemNotFound):
                item = self.get_test_item()
                item.save()
                item_id, changekey = item.id, item.changekey
                item.delete()
                item.id, item.changekey = item_id, changekey
                item.send()  # Item disappeared
            with self.assertRaises(AttributeError):
                item = self.get_test_item()
                item.send(copy_to_folder=self.account.trash, save_copy=False)  # Inconsistent args

        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.account = None
            item.refresh()  # Must have account on refresh
        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.refresh()  # Refresh an item that has not been saved
        with self.assertRaises(ErrorItemNotFound):
            item = self.get_test_item()
            item.save()
            item_id, changekey = item.id, item.changekey
            item.delete()
            item.id, item.changekey = item_id, changekey
            item.refresh()  # Refresh an item that doesn't exist

        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.account = None
            item.copy(to_folder=self.test_folder)  # Must have an account on copy
        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.copy(to_folder=self.test_folder)  # Must be an existing item
        with self.assertRaises(ErrorItemNotFound):
            item = self.get_test_item()
            item.save()
            item_id, changekey = item.id, item.changekey
            item.delete()
            item.id, item.changekey = item_id, changekey
            item.copy(to_folder=self.test_folder)  # Item disappeared

        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.account = None
            item.move(to_folder=self.test_folder)  # Must have an account on move
        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.move(to_folder=self.test_folder)  # Must be an existing item
        with self.assertRaises(ErrorItemNotFound):
            item = self.get_test_item()
            item.save()
            item_id, changekey = item.id, item.changekey
            item.delete()
            item.id, item.changekey = item_id, changekey
            item.move(to_folder=self.test_folder)  # Item disappeared

        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.account = None
            item.delete()  # Must have an account
        with self.assertRaises(ValueError):
            item = self.get_test_item()
            item.delete()  # Must be an existing item
        with self.assertRaises(ErrorItemNotFound):
            item = self.get_test_item()
            item.save()
            item_id, changekey = item.id, item.changekey
            item.delete()
            item.id, item.changekey = item_id, changekey
            item.delete()  # Item disappeared

    def test_unsupported_fields(self):
        # Create a field that is not supported by any current versions. Test that we fail when using this field
        class UnsupportedProp(ExtendedProperty):
            property_set_id = 'deadcafe-beef-beef-beef-deadcafebeef'
            property_name = 'Unsupported Property'
            property_type = 'String'

        attr_name = 'unsupported_property'
        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=UnsupportedProp)
        try:
            for f in self.ITEM_CLASS.FIELDS:
                if f.name == attr_name:
                    f.supported_from = Build(99, 99, 99, 99)

            with self.assertRaises(ValueError):
                self.test_folder.get(**{attr_name: 'XXX'})
            with self.assertRaises(ValueError):
                list(self.test_folder.filter(**{attr_name: 'XXX'}))
            with self.assertRaises(ValueError):
                list(self.test_folder.all().only(attr_name))
            with self.assertRaises(ValueError):
                list(self.test_folder.all().values(attr_name))
            with self.assertRaises(ValueError):
                list(self.test_folder.all().values_list(attr_name))
        finally:
            self.ITEM_CLASS.deregister(attr_name=attr_name)

    def test_querysets(self):
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Item %s' % i
            item.save()
            test_items.append(item)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        test_cat = self.categories[0]
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs),
            {('Item 0', test_cat), ('Item 1', test_cat), ('Item 2', test_cat), ('Item 3', test_cat)}
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.none()],
            []
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.filter(subject__startswith='Item 2')],
            [('Item 2', test_cat)]
        )
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs.exclude(subject__startswith='Item 2')),
            {('Item 0', test_cat), ('Item 1', test_cat), ('Item 3', test_cat)}
        )
        self.assertEqual(
            set((i.subject, i.categories) for i in qs.only('subject')),
            {('Item 0', None), ('Item 1', None), ('Item 2', None), ('Item 3', None)}
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.order_by('subject')],
            [('Item 0', test_cat), ('Item 1', test_cat), ('Item 2', test_cat), ('Item 3', test_cat)]
        )
        self.assertEqual(  # Test '-some_field' syntax for reverse sorting
            [(i.subject, i.categories[0]) for i in qs.order_by('-subject')],
            [('Item 3', test_cat), ('Item 2', test_cat), ('Item 1', test_cat), ('Item 0', test_cat)]
        )
        self.assertEqual(  # Test ordering on a field that we don't need to fetch
            [(i.subject, i.categories[0]) for i in qs.order_by('-subject').only('categories')],
            [(None, test_cat), (None, test_cat), (None, test_cat), (None, test_cat)]
        )
        self.assertEqual(
            [(i.subject, i.categories[0]) for i in qs.order_by('subject').reverse()],
            [('Item 3', test_cat), ('Item 2', test_cat), ('Item 1', test_cat), ('Item 0', test_cat)]
        )
        with self.assertRaises(ValueError):
            list(qs.values([]))
        self.assertEqual(
            [i for i in qs.order_by('subject').values('subject')],
            [{'subject': 'Item 0'}, {'subject': 'Item 1'}, {'subject': 'Item 2'}, {'subject': 'Item 3'}]
        )

        # Test .values() in combinations of 'id' and 'changekey', which are handled specially
        self.assertEqual(
            list(qs.order_by('subject').values('id')),
            [{'id': i.id} for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values('changekey')),
            [{'changekey': i.changekey} for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values('id', 'changekey')),
            [{k: getattr(i, k) for k in ('id', 'changekey')} for i in test_items]
        )

        self.assertEqual(
            set(i for i in qs.values_list('subject')),
            {('Item 0',), ('Item 1',), ('Item 2',), ('Item 3',)}
        )

        # Test .values_list() in combinations of 'id' and 'changekey', which are handled specially
        self.assertEqual(
            list(qs.order_by('subject').values_list('id')),
            [(i.id,) for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values_list('changekey')),
            [(i.changekey,) for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values_list('id', 'changekey')),
            [(i.id, i.changekey) for i in test_items]
        )

        self.assertEqual(
            set(i.subject for i in qs.only('subject')),
            {'Item 0', 'Item 1', 'Item 2', 'Item 3'}
        )

        # Test .only() in combinations of 'id' and 'changekey', which are handled specially
        self.assertEqual(
            list((i.id,) for i in qs.order_by('subject').only('id')),
            [(i.id,) for i in test_items]
        )
        self.assertEqual(
            list((i.changekey,) for i in qs.order_by('subject').only('changekey')),
            [(i.changekey,) for i in test_items]
        )
        self.assertEqual(
            list((i.id, i.changekey) for i in qs.order_by('subject').only('id', 'changekey')),
            [(i.id, i.changekey) for i in test_items]
        )

        with self.assertRaises(ValueError):
            list(qs.values_list('id', 'changekey', flat=True))
        with self.assertRaises(AttributeError):
            list(qs.values_list('id', xxx=True))
        self.assertEqual(
            list(qs.order_by('subject').values_list('id', flat=True)),
            [i.id for i in test_items]
        )
        self.assertEqual(
            list(qs.order_by('subject').values_list('changekey', flat=True)),
            [i.changekey for i in test_items]
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
            {('Item 0', test_cat), ('Item 1', test_cat), ('Item 3', test_cat)}
        )
        # Test that we can sort on a field that we don't want
        self.assertEqual(
            [i.categories[0] for i in qs.only('categories').order_by('subject')],
            [test_cat, test_cat, test_cat, test_cat]
        )
        # Test iterator
        self.assertEqual(
            set((i.subject, i.categories[0]) for i in qs.iterator()),
            {('Item 0', test_cat), ('Item 1', test_cat), ('Item 2', test_cat), ('Item 3', test_cat)}
        )
        # Test that iterator() preserves the result format
        self.assertEqual(
            set((i[0], i[1][0]) for i in qs.values_list('subject', 'categories').iterator()),
            {('Item 0', test_cat), ('Item 1', test_cat), ('Item 2', test_cat), ('Item 3', test_cat)}
        )
        self.assertEqual(qs.get(subject='Item 3').subject, 'Item 3')
        with self.assertRaises(DoesNotExist):
            qs.get(subject='Item XXX')
        with self.assertRaises(MultipleObjectsReturned):
            qs.get(subject__startswith='Item')
        # len() and count()
        self.assertEqual(len(qs), 4)
        self.assertEqual(qs.count(), 4)
        # Indexing and slicing
        self.assertTrue(isinstance(qs[0], self.ITEM_CLASS))
        self.assertEqual(len(list(qs[1:3])), 2)
        self.assertEqual(len(qs), 4)
        with self.assertRaises(IndexError):
            print(qs[99999])
        # Exists
        self.assertEqual(qs.exists(), True)
        self.assertEqual(qs.filter(subject='Test XXX').exists(), False)
        self.assertEqual(
            qs.filter(subject__startswith='Item').delete(),
            [True, True, True, True]
        )

    def test_cached_queryset_corner_cases(self):
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Item %s' % i
            item.save()
            test_items.append(item)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories).order_by('subject')
        for _ in qs:
            # Build up the cache
            pass
        self.assertEqual(len(qs._cache), 4)
        with self.assertRaises(MultipleObjectsReturned):
            qs.get()  # Get with a full cache
        self.assertEqual(qs[2].subject, 'Item 2')  # Index with a full cache
        self.assertEqual(qs[-2].subject, 'Item 2')  # Negative index with a full cache
        qs.delete()  # Delete with a full cache
        self.assertEqual(qs.count(), 0)  # QuerySet is empty after delete
        self.assertEqual(list(qs.none()), [])

    def test_queryset_get_by_id(self):
        item = self.get_test_item().save()
        with self.assertRaises(ValueError):
            list(self.test_folder.filter(id__in=[item.id]))
        with self.assertRaises(ValueError):
            list(self.test_folder.get(id=item.id, changekey=item.changekey, subject='XXX'))
        with self.assertRaises(ValueError):
            list(self.test_folder.get(id=None, changekey=item.changekey))

        # Test a simple get()
        get_item = self.test_folder.get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertEqual(item.body, get_item.body)

        # Test get() with ID only
        get_item = self.test_folder.get(id=item.id)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertEqual(item.body, get_item.body)
        get_item = self.test_folder.get(id=item.id, changekey=None)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertEqual(item.body, get_item.body)

        # Test a get() from queryset
        get_item = self.test_folder.all().get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertEqual(item.body, get_item.body)

        # Test a get() with only()
        get_item = self.test_folder.all().only('subject').get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.id, get_item.id)
        self.assertEqual(item.changekey, get_item.changekey)
        self.assertEqual(item.subject, get_item.subject)
        self.assertIsNone(get_item.body)

    def test_queryset_nonsearchable_fields(self):
        for f in self.ITEM_CLASS.FIELDS:
            if f.is_searchable or isinstance(f, IdField) or not f.supports_version(self.account.version):
                continue
            if f.name in ('percent_complete', 'allow_new_time_proposal'):
                # These fields don't raise an error when used in a filter, but also don't match anything in a filter
                continue
            try:
                filter_val = f.clean(self.random_val(f))
                filter_kwargs = {'%s__in' % f.name: filter_val} if f.is_list else {f.name: filter_val}

                # We raise ValueError when searching on an is_searchable=False field
                with self.assertRaises(ValueError):
                    list(self.test_folder.filter(**filter_kwargs))

                # Make sure the is_searchable=False setting is correct by searching anyway and testing that this
                # fails server-side. This only works for values that we are actually able to convert to a search
                # string.
                try:
                    value_to_xml_text(filter_val)
                except NotImplementedError:
                    continue

                f.is_searchable = True
                with self.assertRaises((ErrorUnsupportedPathForQuery, ErrorInvalidValueForProperty)):
                    list(self.test_folder.filter(**filter_kwargs))
            finally:
                f.is_searchable = False

    def test_queryset_failure(self):
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        with self.assertRaises(ValueError):
            qs.order_by('XXX')
        with self.assertRaises(ValueError):
            qs.values('XXX')
        with self.assertRaises(ValueError):
            qs.values_list('XXX')
        with self.assertRaises(ValueError):
            qs.only('XXX')
        with self.assertRaises(ValueError):
            qs.reverse()  # We can't reverse when we haven't defined an order yet

    def test_order_by_failure(self):
        # Test error handling on indexed properties with labels and subfields
        if self.ITEM_CLASS == Contact:
            qs = QuerySet(
                folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
            ).filter(categories__contains=self.categories)
            with self.assertRaises(ValueError):
                qs.order_by('email_addresses')  # Must have label
            with self.assertRaises(ValueError):
                qs.order_by('email_addresses__FOO')  # Must have a valid label
            with self.assertRaises(ValueError):
                qs.order_by('email_addresses__EmailAddress1__FOO')  # Must not have a subfield
            with self.assertRaises(ValueError):
                qs.order_by('physical_addresses__Business')  # Must have a subfield
            with self.assertRaises(ValueError):
                qs.order_by('physical_addresses__Business__FOO')  # Must have a valid subfield

    def test_order_by(self):
        # Test order_by() on normal field
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Subj %s' % i
            test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        self.assertEqual(
            [i for i in qs.order_by('subject').values_list('subject', flat=True)],
            ['Subj 0', 'Subj 1', 'Subj 2', 'Subj 3']
        )
        self.assertEqual(
            [i for i in qs.order_by('-subject').values_list('subject', flat=True)],
            ['Subj 3', 'Subj 2', 'Subj 1', 'Subj 0']
        )
        self.bulk_delete(qs)

        # Test order_by() on ExtendedProperty
        test_items = []
        for i in range(4):
            item = self.get_test_item()
            item.extern_id = 'ID %s' % i
            test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        self.assertEqual(
            [i for i in qs.order_by('extern_id').values_list('extern_id', flat=True)],
            ['ID 0', 'ID 1', 'ID 2', 'ID 3']
        )
        self.assertEqual(
            [i for i in qs.order_by('-extern_id').values_list('extern_id', flat=True)],
            ['ID 3', 'ID 2', 'ID 1', 'ID 0']
        )
        self.bulk_delete(qs)

        # Test order_by() on IndexedField (simple and multi-subfield). Only Contact items have these
        if self.ITEM_CLASS == Contact:
            test_items = []
            label = self.random_val(EmailAddress.get_field_by_fieldname('label'))
            for i in range(4):
                item = self.get_test_item()
                item.email_addresses = [EmailAddress(email='%s@foo.com' % i, label=label)]
                test_items.append(item)
            self.test_folder.bulk_create(items=test_items)
            qs = QuerySet(
                folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
            ).filter(categories__contains=self.categories)
            self.assertEqual(
                [i[0].email for i in qs.order_by('email_addresses__%s' % label)
                    .values_list('email_addresses', flat=True)],
                ['0@foo.com', '1@foo.com', '2@foo.com', '3@foo.com']
            )
            self.assertEqual(
                [i[0].email for i in qs.order_by('-email_addresses__%s' % label)
                    .values_list('email_addresses', flat=True)],
                ['3@foo.com', '2@foo.com', '1@foo.com', '0@foo.com']
            )
            self.bulk_delete(qs)

            test_items = []
            label = self.random_val(PhysicalAddress.get_field_by_fieldname('label'))
            for i in range(4):
                item = self.get_test_item()
                item.physical_addresses = [PhysicalAddress(street='Elm St %s' % i, label=label)]
                test_items.append(item)
            self.test_folder.bulk_create(items=test_items)
            qs = QuerySet(
                folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
            ).filter(categories__contains=self.categories)
            self.assertEqual(
                [i[0].street for i in qs.order_by('physical_addresses__%s__street' % label)
                    .values_list('physical_addresses', flat=True)],
                ['Elm St 0', 'Elm St 1', 'Elm St 2', 'Elm St 3']
            )
            self.assertEqual(
                [i[0].street for i in qs.order_by('-physical_addresses__%s__street' % label)
                    .values_list('physical_addresses', flat=True)],
                ['Elm St 3', 'Elm St 2', 'Elm St 1', 'Elm St 0']
            )
            self.bulk_delete(qs)

        # Test sorting on multiple fields
        test_items = []
        for i in range(2):
            for j in range(2):
                item = self.get_test_item()
                item.subject = 'Subj %s' % i
                item.extern_id = 'ID %s' % j
                test_items.append(item)
        self.test_folder.bulk_create(items=test_items)
        qs = QuerySet(
            folder_collection=FolderCollection(account=self.account, folders=[self.test_folder])
        ).filter(categories__contains=self.categories)
        self.assertEqual(
            [i for i in qs.order_by('subject', 'extern_id').values('subject', 'extern_id')],
            [{'subject': 'Subj 0', 'extern_id': 'ID 0'},
             {'subject': 'Subj 0', 'extern_id': 'ID 1'},
             {'subject': 'Subj 1', 'extern_id': 'ID 0'},
             {'subject': 'Subj 1', 'extern_id': 'ID 1'}]
        )
        self.assertEqual(
            [i for i in qs.order_by('-subject', 'extern_id').values('subject', 'extern_id')],
            [{'subject': 'Subj 1', 'extern_id': 'ID 0'},
             {'subject': 'Subj 1', 'extern_id': 'ID 1'},
             {'subject': 'Subj 0', 'extern_id': 'ID 0'},
             {'subject': 'Subj 0', 'extern_id': 'ID 1'}]
        )
        self.assertEqual(
            [i for i in qs.order_by('subject', '-extern_id').values('subject', 'extern_id')],
            [{'subject': 'Subj 0', 'extern_id': 'ID 1'},
             {'subject': 'Subj 0', 'extern_id': 'ID 0'},
             {'subject': 'Subj 1', 'extern_id': 'ID 1'},
             {'subject': 'Subj 1', 'extern_id': 'ID 0'}]
        )
        self.assertEqual(
            [i for i in qs.order_by('-subject', '-extern_id').values('subject', 'extern_id')],
            [{'subject': 'Subj 1', 'extern_id': 'ID 1'},
             {'subject': 'Subj 1', 'extern_id': 'ID 0'},
             {'subject': 'Subj 0', 'extern_id': 'ID 1'},
             {'subject': 'Subj 0', 'extern_id': 'ID 0'}]
        )

    def test_finditems(self):
        now = UTC_NOW()

        # Test argument types
        item = self.get_test_item()
        ids = self.test_folder.bulk_create(items=[item])
        # No arguments. There may be leftover items in the folder, so just make sure there's at least one.
        self.assertGreaterEqual(
            len(self.test_folder.filter()),
            1
        )
        # Q object
        self.assertEqual(
            len(self.test_folder.filter(Q(subject=item.subject))),
            1
        )
        # Multiple Q objects
        self.assertEqual(
            len(self.test_folder.filter(Q(subject=item.subject), ~Q(subject=item.subject[:-3] + 'XXX'))),
            1
        )
        # Multiple Q object and kwargs
        self.assertEqual(
            len(self.test_folder.filter(Q(subject=item.subject), categories__contains=item.categories)),
            1
        )
        self.bulk_delete(ids)

        # Test categories which are handled specially - only '__contains' and '__in' lookups are supported
        item = self.get_test_item(categories=['TestA', 'TestB'])
        ids = self.test_folder.bulk_create(items=[item])
        common_qs = self.test_folder.filter(subject=item.subject)  # Guard against other sumultaneous runs
        with self.assertRaises(ErrorContainsFilterWrongType):
            len(common_qs.filter(categories__contains='ci6xahH1'))  # Plain string is not supported
        self.assertEqual(
            len(common_qs.filter(categories__contains=['ci6xahH1'])),  # Same, but as list
            0
        )
        self.assertEqual(
            len(common_qs.filter(categories__contains=['TestA', 'TestC'])),  # One wrong category
            0
        )
        self.assertEqual(
            len(common_qs.filter(categories__contains=['TESTA'])),  # Test case insensitivity
            1
        )
        self.assertEqual(
            len(common_qs.filter(categories__contains=['testa'])),  # Test case insensitivity
            1
        )
        self.assertEqual(
            len(common_qs.filter(categories__contains=['TestA'])),  # Partial
            1
        )
        self.assertEqual(
            len(common_qs.filter(categories__contains=item.categories)),  # Exact match
            1
        )
        with self.assertRaises(ValueError):
            len(common_qs.filter(categories__in='ci6xahH1'))  # Plain string is not supported
        self.assertEqual(
            len(common_qs.filter(categories__in=['ci6xahH1'])),  # Same, but as list
            0
        )
        self.assertEqual(
            len(common_qs.filter(categories__in=['TestA', 'TestC'])),  # One wrong category
            1
        )
        self.assertEqual(
            len(common_qs.filter(categories__in=['TestA'])),  # Partial
            1
        )
        self.assertEqual(
            len(common_qs.filter(categories__in=item.categories)),  # Exact match
            1
        )
        self.bulk_delete(ids)

        common_qs = self.test_folder.filter(categories__contains=self.categories)
        one_hour = datetime.timedelta(hours=1)
        two_hours = datetime.timedelta(hours=2)
        # Test 'exists'
        ids = self.test_folder.bulk_create(items=[self.get_test_item()])
        self.assertEqual(
            len(common_qs.filter(datetime_created__exists=True)),
            1
        )
        self.assertEqual(
            len(common_qs.filter(datetime_created__exists=False)),
            0
        )
        self.bulk_delete(ids)

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
        self.bulk_delete(ids)

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
        self.bulk_delete(ids)

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
        self.bulk_delete(ids)

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
        self.bulk_delete(ids)

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
        self.bulk_delete(ids)

        # Test '='
        item = self.get_test_item()
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject=item.subject[:-3] + 'XXX')),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject=item.subject)),
            1
        )
        self.bulk_delete(ids)

        # Test '!='
        item = self.get_test_item()
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__not=item.subject)),
            0
        )
        self.assertEqual(
            len(common_qs.filter(subject__not=item.subject[:-3] + 'XXX')),
            1
        )
        self.bulk_delete(ids)

        # Test 'exact'
        item = self.get_test_item()
        item.subject = 'aA' + item.subject[2:]
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__exact=item.subject[:-3] + 'XXX')),
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
        self.bulk_delete(ids)

        # Test 'iexact'
        item = self.get_test_item()
        item.subject = 'aA' + item.subject[2:]
        ids = self.test_folder.bulk_create(items=[item])
        self.assertEqual(
            len(common_qs.filter(subject__iexact=item.subject[:-3] + 'XXX')),
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
        self.bulk_delete(ids)

        # Test 'contains'
        item = self.get_test_item()
        item.subject = item.subject[2:8] + 'aA' + item.subject[8:]
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
        self.bulk_delete(ids)

        # Test 'icontains'
        item = self.get_test_item()
        item.subject = item.subject[2:8] + 'aA' + item.subject[8:]
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
        self.bulk_delete(ids)

        # Test 'startswith'
        item = self.get_test_item()
        item.subject = 'aA' + item.subject[2:]
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
        self.bulk_delete(ids)

        # Test 'istartswith'
        item = self.get_test_item()
        item.subject = 'aA' + item.subject[2:]
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
        self.bulk_delete(ids)

    def test_filter_with_querystring(self):
        # QueryString is only supported from Exchange 2010
        with self.assertRaises(NotImplementedError):
            Q('subject:XXX').to_xml(self.test_folder, version=mock_version(build=EXCHANGE_2007),
                                    applies_to=Restriction.ITEMS)

        # We don't allow QueryString in combination with other restrictions
        with self.assertRaises(ValueError):
            self.test_folder.filter('subject:XXX', foo='bar')
        with self.assertRaises(ValueError):
            self.test_folder.filter('subject:XXX').filter(foo='bar')
        with self.assertRaises(ValueError):
            self.test_folder.filter(foo='bar').filter('subject:XXX')

        item = self.get_test_item()
        item.subject = get_random_string(length=8, spaces=False, special=False)
        item.save()
        # For some reason, the querystring search doesn't work instantly. We may have to wait for up to 60 seconds.
        # I'm too impatient for that, so also allow empty results. This makes the test almost worthless but I blame EWS.
        self.assertIn(
            len(self.test_folder.filter('subject:%s' % item.subject)),
            (0, 1)
        )
        item.delete()

    def test_filter_on_all_fields(self):
        # Test that we can filter on all field names
        # TODO: Test filtering on subfields of IndexedField
        item = self.get_test_item()
        if hasattr(item, 'is_all_day'):
            item.is_all_day = False  # Make sure start- and end dates don't change
        ids = self.test_folder.bulk_create(items=[item])
        common_qs = self.test_folder.filter(categories__contains=self.categories)
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if not f.is_searchable:
                # Cannot be used in a QuerySet
                continue
            val = getattr(item, f.name)
            if val is None:
                # We cannot filter on None values
                continue
            if self.ITEM_CLASS == Contact and f.name in ('body', 'display_name'):
                # filtering 'body' or 'display_name' on Contact items doesn't work at all. Error in EWS?
                continue
            if f.is_list:
                # Filter multi-value fields with =, __in and __contains
                if issubclass(f.value_cls, MultiFieldIndexedElement):
                    # For these, we need to filter on the subfield
                    filter_kwargs = []
                    for v in val:
                        for subfield in f.value_cls.supported_fields(version=self.account.version):
                            field_path = FieldPath(field=f, label=v.label, subfield=subfield)
                            path, subval = field_path.path, field_path.get_value(item)
                            if subval is None:
                                continue
                            filter_kwargs.extend([
                                {path: subval}, {'%s__in' % path: [subval]}, {'%s__contains' % path: [subval]}
                            ])
                elif issubclass(f.value_cls, SingleFieldIndexedElement):
                    # For these, we may filter by item or subfield value
                    filter_kwargs = []
                    for v in val:
                        for subfield in f.value_cls.supported_fields(version=self.account.version):
                            field_path = FieldPath(field=f, label=v.label, subfield=subfield)
                            path, subval = field_path.path, field_path.get_value(item)
                            if subval is None:
                                continue
                            filter_kwargs.extend([
                                {f.name: v}, {path: subval},
                                {'%s__in' % path: [subval]}, {'%s__contains' % path: [subval]}
                            ])
                else:
                    filter_kwargs = [{'%s__in' % f.name: val}, {'%s__contains' % f.name: val}]
            else:
                # Filter all others with =, __in and __contains. We could have more filters here, but these should
                # always match.
                filter_kwargs = [{f.name: val}, {'%s__in' % f.name: [val]}]
                if isinstance(f, TextField) and not isinstance(f, (ChoiceField, BodyField)):
                    # Choice fields cannot be filtered using __contains. BodyField often works in practice but often
                    # fails with generated test data. Ugh.
                    filter_kwargs.append({'%s__contains' % f.name: val[2:10]})
            for kw in filter_kwargs:
                self.assertEqual(len(common_qs.filter(**kw)), 1, (f.name, val, kw))
        self.bulk_delete(ids)

    def test_paging(self):
        # Test that paging services work correctly. Default EWS paging size is 1000 items. Our default is 100 items.
        items = []
        for _ in range(11):
            i = self.get_test_item()
            del i.attachments[:]
            items.append(i)
        self.test_folder.bulk_create(items=items)
        ids = self.test_folder.filter(categories__contains=self.categories).values_list('id', 'changekey')
        ids.page_size = 10
        self.bulk_delete(ids.iterator())

    def test_slicing(self):
        # Test that slicing works correctly
        items = []
        for i in range(4):
            item = self.get_test_item()
            item.subject = 'Subj %s' % i
            del item.attachments[:]
            items.append(item)
        ids = self.test_folder.bulk_create(items=items)
        qs = self.test_folder.filter(categories__contains=self.categories).only('subject').order_by('subject')

        # Test positive index
        self.assertEqual(
            qs.copy()[0].subject,
            'Subj 0'
        )
        # Test positive index
        self.assertEqual(
            qs.copy()[3].subject,
            'Subj 3'
        )
        # Test negative index
        self.assertEqual(
            qs.copy()[-2].subject,
            'Subj 2'
        )
        # Test positive slice
        self.assertEqual(
            [i.subject for i in qs.copy()[0:2]],
            ['Subj 0', 'Subj 1']
        )
        # Test positive slice
        self.assertEqual(
            [i.subject for i in qs.copy()[2:4]],
            ['Subj 2', 'Subj 3']
        )
        # Test positive open slice
        self.assertEqual(
            [i.subject for i in qs.copy()[:2]],
            ['Subj 0', 'Subj 1']
        )
        # Test positive open slice
        self.assertEqual(
            [i.subject for i in qs.copy()[2:]],
            ['Subj 2', 'Subj 3']
        )
        # Test negative slice
        self.assertEqual(
            [i.subject for i in qs.copy()[-3:-1]],
            ['Subj 1', 'Subj 2']
        )
        # Test negative slice
        self.assertEqual(
            [i.subject for i in qs.copy()[1:-1]],
            ['Subj 1', 'Subj 2']
        )
        # Test negative open slice
        self.assertEqual(
            [i.subject for i in qs.copy()[:-2]],
            ['Subj 0', 'Subj 1']
        )
        # Test negative open slice
        self.assertEqual(
            [i.subject for i in qs.copy()[-2:]],
            ['Subj 2', 'Subj 3']
        )
        # Test positive slice with step
        self.assertEqual(
            [i.subject for i in qs.copy()[0:4:2]],
            ['Subj 0', 'Subj 2']
        )
        # Test negative slice with step
        self.assertEqual(
            [i.subject for i in qs.copy()[4:0:-2]],
            ['Subj 3', 'Subj 1']
        )
        self.bulk_delete(ids)

    def test_getitems(self):
        item = self.get_test_item()
        self.test_folder.bulk_create(items=[item, item])
        ids = self.test_folder.filter(categories__contains=item.categories)
        items = list(self.account.fetch(ids=ids))
        for item in items:
            self.assertIsInstance(item, self.ITEM_CLASS)
        self.assertEqual(len(items), 2)

        items = list(self.account.fetch(ids=ids, only_fields=['subject']))
        self.assertEqual(len(items), 2)

        items = list(self.account.fetch(ids=ids, only_fields=[FieldPath.from_string('subject', self.test_folder)]))
        self.assertEqual(len(items), 2)

        self.bulk_delete(ids)

    def test_text_field_settings(self):
        # Test that the max_length and is_complex field settings are correctly set for text fields
        item = self.get_test_item().save()
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if not isinstance(f, TextField):
                continue
            if isinstance(f, ChoiceField):
                # This one can't contain random values
                continue
            if isinstance(f, CultureField):
                # This one can't contain random values
                continue
            if f.is_read_only:
                continue
            if f.name == 'categories':
                # We're filtering on this one, so leave it alone
                continue
            old_max_length = getattr(f, 'max_length', None)
            old_is_complex = f.is_complex
            try:
                # Set a string long enough to not be handled by FindItems
                f.max_length = 4000
                if f.is_list:
                    setattr(item, f.name, [get_random_string(f.max_length) for _ in range(len(getattr(item, f.name)))])
                else:
                    setattr(item, f.name, get_random_string(f.max_length))
                try:
                    item.save(update_fields=[f.name])
                except ErrorPropertyUpdate:
                    # Some fields throw this error when updated to a huge value
                    self.assertIn(f.name, ['given_name', 'middle_name', 'surname'])
                    continue
                except ErrorInvalidPropertySet:
                    # Some fields can not be updated after save
                    self.assertTrue(f.is_read_only_after_send)
                    continue
                # is_complex=True forces the query to use GetItems which will always get the full value
                f.is_complex = True
                new_full_item = self.test_folder.all().only(f.name).get(categories__contains=self.categories)
                new_full = getattr(new_full_item, f.name)
                if old_max_length:
                    if f.is_list:
                        for s in new_full:
                            self.assertLessEqual(len(s), old_max_length, (f.name, len(s), old_max_length))
                    else:
                        self.assertLessEqual(len(new_full), old_max_length, (f.name, len(new_full), old_max_length))

                # is_complex=False forces the query to use FindItems which will only get the short value
                f.is_complex = False
                if isinstance(f, BodyField):
                    with self.assertRaises(ErrorInvalidPropertyForOperation):
                        self.test_folder.all().only(f.name).get(categories__contains=self.categories)
                    continue
                new_short_item = self.test_folder.all().only(f.name).get(categories__contains=self.categories)
                new_short = getattr(new_short_item, f.name)

                if not old_is_complex:
                    self.assertEqual(new_short, new_full, (f.name, new_short, new_full))
            finally:
                if old_max_length:
                    f.max_length = old_max_length
                else:
                    delattr(f, 'max_length')
                f.is_complex = old_is_complex

    def test_complex_fields(self):
        # Test that complex fields can be fetched using only(). This is a test for #141.
        insert_kwargs = self.get_random_insert_kwargs()
        if 'is_all_day' in insert_kwargs:
            insert_kwargs['is_all_day'] = False
        item = self.ITEM_CLASS(account=self.account, folder=self.test_folder, **insert_kwargs).save()
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if f.name in ('optional_attendees', 'required_attendees', 'resources'):
                continue
            if f.is_read_only:
                continue
            if f.name == 'reminder_due_by':
                # EWS sets a default value if it is not set on insert. Ignore
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            old = getattr(item, f.name)
            # Test field as single element in only()
            for fresh_item in self.test_folder.filter(categories__contains=item.categories).only(f.name):
                new = getattr(fresh_item, f.name)
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))
            # Test field as one of the elements in only()
            for fresh_item in self.test_folder.filter(categories__contains=item.categories).only('subject', f.name):
                new = getattr(fresh_item, f.name)
                if f.is_list:
                    old, new = set(old or ()), set(new or ())
                self.assertEqual(old, new, (f.name, old, new))
        self.bulk_delete([item])

    def test_text_body(self):
        if self.account.version.build < EXCHANGE_2013:
            raise self.skipTest('Exchange version too old')
        item = self.get_test_item()
        item.body = 'X' * 500  # Make body longer than the normal 256 char text field limit
        item.save()
        fresh_item = self.test_folder.filter(categories__contains=item.categories).only('text_body')[0]
        self.assertEqual(fresh_item.text_body, item.body)
        item.delete()

    def test_only_fields(self):
        item = self.get_test_item()
        self.test_folder.bulk_create(items=[item, item])
        items = self.test_folder.filter(categories__contains=item.categories)
        for item in items:
            self.assertIsInstance(item, self.ITEM_CLASS)
            for f in self.ITEM_CLASS.FIELDS:
                self.assertTrue(hasattr(item, f.name))
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if f.name in ('optional_attendees', 'required_attendees', 'resources'):
                    continue
                if f.name == 'reminder_due_by' and not item.reminder_is_set:
                    # We delete the due date if reminder is not set
                    continue
                elif f.is_read_only:
                    continue
                self.assertIsNotNone(getattr(item, f.name), (f, getattr(item, f.name)))
        self.assertEqual(len(items), 2)
        only_fields = ('subject', 'body', 'categories')
        items = self.test_folder.filter(categories__contains=item.categories).only(*only_fields)
        for item in items:
            self.assertIsInstance(item, self.ITEM_CLASS)
            for f in self.ITEM_CLASS.FIELDS:
                self.assertTrue(hasattr(item, f.name))
                if not f.supports_version(self.account.version):
                    # Cannot be used with this EWS version
                    continue
                if f.name in only_fields:
                    self.assertIsNotNone(getattr(item, f.name), (f.name, getattr(item, f.name)))
                elif f.is_required:
                    v = getattr(item, f.name)
                    if f.name == 'attachments':
                        self.assertEqual(v, [], (f.name, v))
                    elif f.default is None:
                        self.assertIsNone(v, (f.name, v))
                    else:
                        self.assertEqual(v, f.default, (f.name, v))
        self.assertEqual(len(items), 2)
        self.bulk_delete(items)

    def test_save_and_delete(self):
        # Test that we can create, update and delete single items using methods directly on the item.
        # For CalendarItem instances, the 'is_all_day' attribute affects the 'start' and 'end' values. Changing from
        # 'false' to 'true' removes the time part of these datetimes.
        insert_kwargs = self.get_random_insert_kwargs()
        if 'is_all_day' in insert_kwargs:
            insert_kwargs['is_all_day'] = False
        item = self.ITEM_CLASS(account=self.account, folder=self.test_folder, **insert_kwargs)
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)

        # Create
        item.save()
        self.assertIsNotNone(item.id)
        self.assertIsNotNone(item.changekey)
        for k, v in insert_kwargs.items():
            self.assertEqual(getattr(item, k), v, (k, getattr(item, k), v))
        # Test that whatever we have locally also matches whatever is in the DB
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        for f in item.FIELDS:
            old, new = getattr(item, f.name), getattr(fresh_item, f.name)
            if f.is_read_only and old is None:
                # Some fields are automatically set server-side
                continue
            if f.name == 'reminder_due_by':
                # EWS sets a default value if it is not set on insert. Ignore
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            if f.is_list:
                old, new = set(old or ()), set(new or ())
            self.assertEqual(old, new, (f.name, old, new))

        # Update
        update_kwargs = self.get_random_update_kwargs(item=item, insert_kwargs=insert_kwargs)
        for k, v in update_kwargs.items():
            setattr(item, k, v)
        item.save()
        for k, v in update_kwargs.items():
            self.assertEqual(getattr(item, k), v, (k, getattr(item, k), v))
        # Test that whatever we have locally also matches whatever is in the DB
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        for f in item.FIELDS:
            old, new = getattr(item, f.name), getattr(fresh_item, f.name)
            if f.is_read_only and old is None:
                # Some fields are automatically updated server-side
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            if f.name == 'reminder_due_by':
                if new is None:
                    # EWS does not always return a value if reminder_is_set is False.
                    continue
                if old is not None:
                    # EWS sometimes randomly sets the new reminder due date to one month before or after we
                    # wanted it, and sometimes 30 days before or after. But only sometimes...
                    old_date = old.astimezone(self.account.default_timezone).date()
                    new_date = new.astimezone(self.account.default_timezone).date()
                    if relativedelta(month=1) + new_date == old_date:
                        item.reminder_due_by = new
                        continue
                    if relativedelta(month=1) + old_date == new_date:
                        item.reminder_due_by = new
                        continue
                    elif abs(old_date - new_date) == datetime.timedelta(days=30):
                        item.reminder_due_by = new
                        continue
            if f.is_list:
                old, new = set(old or ()), set(new or ())
            self.assertEqual(old, new, (f.name, old, new))

        # Hard delete
        item_id = (item.id, item.changekey)
        item.delete()
        for e in self.account.fetch(ids=[item_id]):
            # It's gone from the account
            self.assertIsInstance(e, ErrorItemNotFound)
        # Really gone, not just changed ItemId
        items = self.test_folder.filter(categories__contains=item.categories)
        self.assertEqual(len(items), 0)

    def test_save_with_update_fields(self):
        # Create a test item
        insert_kwargs = self.get_random_insert_kwargs()
        if 'is_all_day' in insert_kwargs:
            insert_kwargs['is_all_day'] = False
        item = self.ITEM_CLASS(account=self.account, folder=self.test_folder, **insert_kwargs)
        with self.assertRaises(ValueError):
            item.save(update_fields=['subject'])  # update_fields does not work on item creation
        item.save()
        item.subject = 'XXX'
        item.body = 'YYY'
        item.save(update_fields=['subject'])
        item.refresh()
        self.assertEqual(item.subject, 'XXX')
        self.assertNotEqual(item.body, 'YYY')

        # Test invalid 'update_fields' input
        with self.assertRaises(ValueError) as e:
            item.save(update_fields=['xxx'])
        self.assertEqual(
            e.exception.args[0],
            "Field name(s) 'xxx' are not valid for a '%s' item" % self.ITEM_CLASS.__name__
        )
        with self.assertRaises(ValueError) as e:
            item.save(update_fields='subject')
        self.assertEqual(
            e.exception.args[0],
            "Field name(s) 's', 'u', 'b', 'j', 'e', 'c', 't' are not valid for a '%s' item" % self.ITEM_CLASS.__name__
        )

        self.bulk_delete([item])

    def test_soft_delete(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        self.account.recoverable_items_deletions.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        item_id = (item.id, item.changekey)
        # Soft delete
        item.soft_delete()
        for e in self.account.fetch(ids=[item_id]):
            # It's gone from the test folder
            self.assertIsInstance(e, ErrorItemNotFound)
        # Really gone, not just changed ItemId
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 0)
        self.assertEqual(len(self.account.trash.filter(categories__contains=item.categories)), 0)
        # But we can find it in the recoverable items folder
        self.assertEqual(len(self.account.recoverable_items_deletions.filter(categories__contains=item.categories)), 1)

    def test_move_to_trash(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        item_id = (item.id, item.changekey)
        # Move to trash
        item.move_to_trash()
        for e in self.account.fetch(ids=[item_id]):
            # Not in the test folder anymore
            self.assertIsInstance(e, ErrorItemNotFound)
        # Really gone, not just changed ItemId
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 0)
        # Test that the item moved to trash
        item = self.account.trash.get(categories__contains=item.categories)
        moved_item = list(self.account.fetch(ids=[item]))[0]
        # The item was copied, so the ItemId has changed. Let's compare the subject instead
        self.assertEqual(item.subject, moved_item.subject)

    def test_copy(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        # Copy to trash. We use trash because it can contain all item types.
        copy_item_id, copy_changekey = item.copy(to_folder=self.account.trash)
        # Test that the item still exists in the folder
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 1)
        # Test that the copied item exists in trash
        copied_item = self.account.trash.get(categories__contains=item.categories)
        self.assertNotEqual(item.id, copied_item.id)
        self.assertNotEqual(item.changekey, copied_item.changekey)
        self.assertEqual(copy_item_id, copied_item.id)
        self.assertEqual(copy_changekey, copied_item.changekey)

    def test_move(self):
        # First, empty trash bin
        self.account.trash.filter(categories__contains=self.categories).delete()
        item = self.get_test_item().save()
        item_id = (item.id, item.changekey)
        # Move to trash. We use trash because it can contain all item types. This changes the ItemId
        item.move(to_folder=self.account.trash)
        for e in self.account.fetch(ids=[item_id]):
            # original item ID no longer exists
            self.assertIsInstance(e, ErrorItemNotFound)
        # Test that the item moved to trash
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 0)
        moved_item = self.account.trash.get(categories__contains=item.categories)
        self.assertEqual(item.id, moved_item.id)
        self.assertEqual(item.changekey, moved_item.changekey)

    def test_refresh(self):
        # Test that we can refresh items, and that refresh fails if the item no longer exists on the server
        item = self.get_test_item().save()
        orig_subject = item.subject
        item.subject = 'XXX'
        item.refresh()
        self.assertEqual(item.subject, orig_subject)
        item.delete()
        with self.assertRaises(ValueError):
            # Item no longer has an ID
            item.refresh()

    def test_item(self):
        # Test insert
        # For CalendarItem instances, the 'is_all_day' attribute affects the 'start' and 'end' values. Changing from
        # 'false' to 'true' removes the time part of these datetimes.
        insert_kwargs = self.get_random_insert_kwargs()
        if 'is_all_day' in insert_kwargs:
            insert_kwargs['is_all_day'] = False
        item = self.ITEM_CLASS(**insert_kwargs)
        # Test with generator as argument
        insert_ids = self.test_folder.bulk_create(items=(i for i in [item]))
        self.assertEqual(len(insert_ids), 1)
        self.assertIsInstance(insert_ids[0], Item)
        find_ids = self.test_folder.filter(categories__contains=item.categories).values_list('id', 'changekey')
        self.assertEqual(len(find_ids), 1)
        self.assertEqual(len(find_ids[0]), 2, find_ids[0])
        self.assertEqual(insert_ids, list(find_ids))
        # Test with generator as argument
        item = list(self.account.fetch(ids=(i for i in find_ids)))[0]
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_read_only:
                continue
            if f.name == 'reminder_due_by':
                # EWS sets a default value if it is not set on insert. Ignore
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            old, new = getattr(item, f.name), insert_kwargs[f.name]
            if f.is_list:
                old, new = set(old or ()), set(new or ())
            self.assertEqual(old, new, (f.name, old, new))

        # Test update
        update_kwargs = self.get_random_update_kwargs(item=item, insert_kwargs=insert_kwargs)
        if self.ITEM_CLASS in (Contact, DistributionList):
            # Contact and DistributionList don't support mime_type updates at all
            update_kwargs.pop('mime_content', None)
        update_fieldnames = [f for f in update_kwargs.keys() if f != 'attachments']
        for k, v in update_kwargs.items():
            setattr(item, k, v)
        # Test with generator as argument
        update_ids = self.account.bulk_update(items=(i for i in [(item, update_fieldnames)]))
        self.assertEqual(len(update_ids), 1)
        self.assertEqual(len(update_ids[0]), 2, update_ids)
        self.assertEqual(insert_ids[0].id, update_ids[0][0])  # ID should be the same
        self.assertNotEqual(insert_ids[0].changekey, update_ids[0][1])  # Changekey should change when item is updated
        item = list(self.account.fetch(update_ids))[0]
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_read_only or f.is_read_only_after_send:
                # These cannot be changed
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            old, new = getattr(item, f.name), update_kwargs[f.name]
            if f.name == 'reminder_due_by':
                if old is None:
                    # EWS does not always return a value if reminder_is_set is False. Set one now
                    item.reminder_due_by = new
                    continue
                elif old is not None and new is not None:
                    # EWS sometimes randomly sets the new reminder due date to one month before or after we
                    # wanted it, and sometimes 30 days before or after. But only sometimes...
                    old_date = old.astimezone(self.account.default_timezone).date()
                    new_date = new.astimezone(self.account.default_timezone).date()
                    if relativedelta(month=1) + new_date == old_date:
                        item.reminder_due_by = new
                        continue
                    if relativedelta(month=1) + old_date == new_date:
                        item.reminder_due_by = new
                        continue
                    elif abs(old_date - new_date) == datetime.timedelta(days=30):
                        item.reminder_due_by = new
                        continue
            if f.is_list:
                old, new = set(old or ()), set(new or ())
            self.assertEqual(old, new, (f.name, old, new))

        # Test wiping or removing fields
        wipe_kwargs = {}
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_required or f.is_required_after_save:
                # These cannot be deleted
                continue
            if f.is_read_only or f.is_read_only_after_send:
                # These cannot be changed
                continue
            wipe_kwargs[f.name] = None
        for k, v in wipe_kwargs.items():
            setattr(item, k, v)
        wipe_ids = self.account.bulk_update([(item, update_fieldnames), ])
        self.assertEqual(len(wipe_ids), 1)
        self.assertEqual(len(wipe_ids[0]), 2, wipe_ids)
        self.assertEqual(insert_ids[0].id, wipe_ids[0][0])  # ID should be the same
        self.assertNotEqual(insert_ids[0].changekey,
                            wipe_ids[0][1])  # Changekey should not be the same when item is updated
        item = list(self.account.fetch(wipe_ids))[0]
        for f in self.ITEM_CLASS.FIELDS:
            if not f.supports_version(self.account.version):
                # Cannot be used with this EWS version
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if f.is_required or f.is_required_after_save:
                continue
            if f.is_read_only or f.is_read_only_after_send:
                continue
            old, new = getattr(item, f.name), wipe_kwargs[f.name]
            if f.is_list:
                old, new = set(old or ()), set(new or ())
            self.assertEqual(old, new, (f.name, old, new))

        # Test extern_id = None, which deletes the extended property entirely
        extern_id = None
        item.extern_id = extern_id
        wipe2_ids = self.account.bulk_update([(item, ['extern_id']), ])
        self.assertEqual(len(wipe2_ids), 1)
        self.assertEqual(len(wipe2_ids[0]), 2, wipe2_ids)
        self.assertEqual(insert_ids[0].id, wipe2_ids[0][0])  # ID should be the same
        self.assertNotEqual(insert_ids[0].changekey, wipe2_ids[0][1])  # Changekey should change when item is updated
        item = list(self.account.fetch(wipe2_ids))[0]
        self.assertEqual(item.extern_id, extern_id)

        # Remove test item. Test with generator as argument
        self.bulk_delete(ids=(i for i in wipe2_ids))

    def test_export_and_upload(self):
        # 15 new items which we will attempt to export and re-upload
        items = [self.get_test_item().save() for _ in range(15)]
        ids = [(i.id, i.changekey) for i in items]
        # re-fetch items because there will be some extra fields added by the server
        items = list(self.account.fetch(items))

        # Try exporting and making sure we get the right response
        export_results = self.account.export(items)
        self.assertEqual(len(items), len(export_results))
        for result in export_results:
            self.assertIsInstance(result, str)

        # Try reuploading our results
        upload_results = self.account.upload([(self.test_folder, data) for data in export_results])
        self.assertEqual(len(items), len(upload_results), (items, upload_results))
        for result in upload_results:
            # Must be a completely new ItemId
            self.assertIsInstance(result, tuple)
            self.assertNotIn(result, ids)

        # Check the items uploaded are the same as the original items
        def to_dict(item):
            dict_item = {}
            # fieldnames is everything except the ID so we'll use it to compare
            for f in item.FIELDS:
                # datetime_created and last_modified_time aren't copied, but instead are added to the new item after
                # uploading. This means mime_content and size can also change. Items also get new IDs on upload. And
                # meeting_count values are dependent on contents of current calendar. Form query strings contain the
                # item ID and will also change.
                if f.name in {'id', 'changekey', 'first_occurrence', 'last_occurrence', 'datetime_created',
                              'last_modified_time', 'mime_content', 'size', 'conversation_id',
                              'adjacent_meeting_count', 'conflicting_meeting_count',
                              'web_client_read_form_query_string', 'web_client_edit_form_query_string'}:
                    continue
                dict_item[f.name] = getattr(item, f.name)
                if f.name == 'attachments':
                    # Attachments get new IDs on upload. Wipe them here so we can compare the other fields
                    for a in dict_item[f.name]:
                        a.attachment_id = None
            return dict_item

        uploaded_items = sorted([to_dict(item) for item in self.account.fetch(upload_results)],
                                key=lambda i: i['subject'])
        original_items = sorted([to_dict(item) for item in items], key=lambda i: i['subject'])
        self.assertListEqual(original_items, uploaded_items)

        # Clean up after ourselves
        self.bulk_delete(ids=upload_results)
        self.bulk_delete(ids=ids)

    def test_export_with_error(self):
        # 15 new items which we will attempt to export and re-upload
        items = [self.get_test_item().save() for _ in range(15)]
        # Use id tuples for export here because deleting an item clears it's
        #  id.
        ids = [(item.id, item.changekey) for item in items]
        # Delete one of the items, this will cause an error
        items[3].delete()

        export_results = self.account.export(ids)
        self.assertEqual(len(items), len(export_results))
        for idx, result in enumerate(export_results):
            if idx == 3:
                # If it is the one returning the error
                self.assertIsInstance(result, ErrorItemNotFound)
            else:
                self.assertIsInstance(result, str)

        # Clean up after yourself
        del ids[3]  # Sending the deleted one through will cause an error
        self.bulk_delete(ids)

    def test_register(self):
        # Tests that we can register and de-register custom extended properties
        class TestProp(ExtendedProperty):
            property_set_id = 'deadbeaf-cafe-cafe-cafe-deadbeefcafe'
            property_name = 'Test Property'
            property_type = 'Integer'

        attr_name = 'dead_beef'

        # Before register
        self.assertNotIn(attr_name, {f.name for f in self.ITEM_CLASS.supported_fields()})
        with self.assertRaises(ValueError):
            self.ITEM_CLASS.deregister(attr_name)  # Not registered yet
        with self.assertRaises(ValueError):
            self.ITEM_CLASS.deregister('subject')  # Not an extended property

        self.ITEM_CLASS.register(attr_name=attr_name, attr_cls=TestProp)
        try:
            # After register
            self.assertEqual(TestProp.python_type(), int)
            self.assertIn(attr_name, {f.name for f in self.ITEM_CLASS.supported_fields()})

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
        self.assertNotIn(attr_name, {f.name for f in self.ITEM_CLASS.supported_fields()})

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
            # MyMeeting is an extended prop version of the 'uid' field. We don't want 'uid' to overwrite that.
            # overwriting each other.
            item.uid = None
            prop_val = item.my_meeting
            self.assertTrue(isinstance(prop_val, bytes))
            item.save()
            item = list(self.account.fetch(ids=[(item.id, item.changekey)]))[0]
            self.assertEqual(prop_val, item.my_meeting, (prop_val, item.my_meeting))
            new_prop_val = self.random_val(self.ITEM_CLASS.get_field_by_fieldname(attr_name))
            item.my_meeting = new_prop_val
            # MyMeeting is an extended prop version of the 'uid' field. We don't want 'uid' to overwrite that.
            item.uid = None
            item.save()
            item = list(self.account.fetch(ids=[(item.id, item.changekey)]))[0]
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
            item = list(self.account.fetch(ids=[(item.id, item.changekey)]))[0]
            self.assertEqual(prop_val, item.my_meeting_array)
            new_prop_val = self.random_val(self.ITEM_CLASS.get_field_by_fieldname(attr_name))
            item.my_meeting_array = new_prop_val
            item.save()
            item = list(self.account.fetch(ids=[(item.id, item.changekey)]))[0]
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

    def test_attachment_failure(self):
        att1 = FileAttachment(name='my_file_1.txt', content=u'Hello from unicode æøå'.encode('utf-8'))
        att1.attachment_id = 'XXX'
        with self.assertRaises(ValueError):
            att1.attach()  # Cannot have an attachment ID
        att1.attachment_id = None
        with self.assertRaises(ValueError):
            att1.attach()  # Must have a parent item
        att1.parent_item = Item()
        with self.assertRaises(ValueError):
            att1.attach()  # Parent item must have an account
        att1.parent_item = None
        with self.assertRaises(ValueError):
            att1.detach()  # Must have an attachment ID
        att1.attachment_id = 'XXX'
        with self.assertRaises(ValueError):
            att1.detach()  # Must have a parent item
        att1.parent_item = Item()
        with self.assertRaises(ValueError):
            att1.detach()  # Parent item must have an account
        att1.parent_item = None
        att1.attachment_id = None

    def test_attachment_properties(self):
        binary_file_content = u'Hello from unicode æøå'.encode('utf-8')
        att1 = FileAttachment(name='my_file_1.txt', content=binary_file_content)
        self.assertIn("name='my_file_1.txt'", str(att1))
        att1.content = binary_file_content  # Test property setter
        self.assertEqual(att1.content, binary_file_content)  # Test property getter
        att1.attachment_id = 'xxx'
        self.assertEqual(att1.content, binary_file_content)  # Test property getter when attachment_id is set
        att1._content = None
        with self.assertRaises(ValueError):
            print(att1.content)  # Test property getter when we need to fetch the content

        attached_item1 = self.get_test_item(folder=self.test_folder)
        att2 = ItemAttachment(name='attachment1', item=attached_item1)
        self.assertIn("name='attachment1'", str(att2))
        att2.item = attached_item1  # Test property setter
        self.assertEqual(att2.item, attached_item1)  # Test property getter
        self.assertEqual(att2.item, attached_item1)  # Test property getter
        att2.attachment_id = 'xxx'
        self.assertEqual(att2.item, attached_item1)  # Test property getter when attachment_id is set
        att2._item = None
        with self.assertRaises(ValueError):
            print(att2.item)  # Test property getter when we need to fetch the item

    def test_file_attachments(self):
        item = self.get_test_item(folder=self.test_folder)

        # Test __init__(attachments=...) and attach() on new item
        binary_file_content = u'Hello from unicode æøå'.encode('utf-8')
        att1 = FileAttachment(name='my_file_1.txt', content=binary_file_content)
        self.assertEqual(len(item.attachments), 0)
        item.attach(att1)
        self.assertEqual(len(item.attachments), 1)
        item.save()
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        self.assertEqual(len(fresh_item.attachments), 1)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'my_file_1.txt')
        self.assertEqual(fresh_attachments[0].content, binary_file_content)

        # Test raw call to service
        self.assertEqual(
            list(GetAttachment(account=item.account).call(
                items=[att1.attachment_id],
                include_mime_content=False)
            )[0].find('{%s}Content' % TNS).text,
            'SGVsbG8gZnJvbSB1bmljb2RlIMOmw7jDpQ==')

        # Test attach on saved object
        att2 = FileAttachment(name='my_file_2.txt', content=binary_file_content)
        self.assertEqual(len(item.attachments), 1)
        item.attach(att2)
        self.assertEqual(len(item.attachments), 2)
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        self.assertEqual(len(fresh_item.attachments), 2)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'my_file_1.txt')
        self.assertEqual(fresh_attachments[0].content, binary_file_content)
        self.assertEqual(fresh_attachments[1].name, 'my_file_2.txt')
        self.assertEqual(fresh_attachments[1].content, binary_file_content)

        # Test detach
        item.detach(att1)
        self.assertTrue(att1.attachment_id is None)
        self.assertTrue(att1.parent_item is None)
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        self.assertEqual(len(fresh_item.attachments), 1)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'my_file_2.txt')
        self.assertEqual(fresh_attachments[0].content, binary_file_content)

    def test_streaming_file_attachments(self):
        item = self.get_test_item(folder=self.test_folder)
        large_binary_file_content = get_random_string(2**10).encode('utf-8')
        large_att = FileAttachment(name='my_large_file.txt', content=large_binary_file_content)
        item.attach(large_att)
        item.save()

        # Test streaming file content
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        with fresh_item.attachments[0].fp as fp:
            self.assertEqual(fp.read(), large_binary_file_content)

        # Test partial reads of streaming file content
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        with fresh_item.attachments[0].fp as fp:
            chunked_reads = []
            buffer = fp.read(7)
            while buffer:
                chunked_reads.append(buffer)
                buffer = fp.read(7)
            self.assertListEqual(chunked_reads, list(chunkify(large_binary_file_content, 7)))

    def test_streaming_file_attachment_error(self):
        # Test that we can parse XML error responses in streaming mode.

        # Try to stram an attachment with malformed ID
        att = FileAttachment(
            parent_item=self.get_test_item(folder=self.test_folder),
            attachment_id=AttachmentId(id='AAMk='),
            name='dummy.txt',
            content=b'',
        )
        with self.assertRaises(ErrorInvalidIdMalformed):
            with att.fp as fp:
                fp.read()

        # Try to stream a non-existent attachment
        att.attachment_id.id=\
            'AAMkADQyYzZmYmUxLTJiYjItNDg2Ny1iMzNjLTIzYWE1NDgxNmZhNABGAAAAAADUebQDarW2Q7G2Ji8hKofPBwAl9iKCsfCfS' \
            'a9cmjh+JCrCAAPJcuhjAABioKiOUTCQRI6Q5sRzi0pJAAHnDV3CAAABEgAQAN0zlxDrzlxAteU+kt84qOM='
        with self.assertRaises(ErrorItemNotFound):
            with att.fp as fp:
                fp.read()

    def test_empty_file_attachment(self):
        item = self.get_test_item(folder=self.test_folder)
        att1 = FileAttachment(name='empty_file.txt', content=b'')
        item.attach(att1)
        item.save()
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        self.assertEqual(
            fresh_item.attachments[0].content,
            b''
        )

    def test_item_attachments(self):
        item = self.get_test_item(folder=self.test_folder)
        item.attachments = []

        attached_item1 = self.get_test_item(folder=self.test_folder)
        attached_item1.attachments = []
        if hasattr(attached_item1, 'is_all_day'):
            attached_item1.is_all_day = False
        attached_item1.save()
        attachment1 = ItemAttachment(name='attachment1', item=attached_item1)
        item.attach(attachment1)

        self.assertEqual(len(item.attachments), 1)
        item.save()
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        self.assertEqual(len(fresh_item.attachments), 1)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'attachment1')
        self.assertIsInstance(fresh_attachments[0].item, self.ITEM_CLASS)

        for f in self.ITEM_CLASS.FIELDS:
            # Normalize some values we don't control
            if f.is_read_only:
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if isinstance(f, ExtendedPropertyField):
                # Attachments don't have these values. It may be possible to request it if we can find the FieldURI
                continue
            if f.name == 'is_read':
                # This is always true for item attachments?
                continue
            if f.name == 'reminder_due_by':
                # EWS sets a default value if it is not set on insert. Ignore
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            old_val = getattr(attached_item1, f.name)
            new_val = getattr(fresh_attachments[0].item, f.name)
            if f.is_list:
                old_val, new_val = set(old_val or ()), set(new_val or ())
            self.assertEqual(old_val, new_val, (f.name, old_val, new_val))

        # Test attach on saved object
        attached_item2 = self.get_test_item(folder=self.test_folder)
        attached_item2.attachments = []
        if hasattr(attached_item2, 'is_all_day'):
            attached_item2.is_all_day = False
        attached_item2.save()
        attachment2 = ItemAttachment(name='attachment2', item=attached_item2)
        item.attach(attachment2)

        self.assertEqual(len(item.attachments), 2)
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        self.assertEqual(len(fresh_item.attachments), 2)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)
        self.assertEqual(fresh_attachments[0].name, 'attachment1')
        self.assertIsInstance(fresh_attachments[0].item, self.ITEM_CLASS)

        for f in self.ITEM_CLASS.FIELDS:
            # Normalize some values we don't control
            if f.is_read_only:
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if isinstance(f, ExtendedPropertyField):
                # Attachments don't have these values. It may be possible to request it if we can find the FieldURI
                continue
            if f.name == 'reminder_due_by':
                # EWS sets a default value if it is not set on insert. Ignore
                continue
            if f.name == 'is_read':
                # This is always true for item attachments?
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            old_val = getattr(attached_item1, f.name)
            new_val = getattr(fresh_attachments[0].item, f.name)
            if f.is_list:
                old_val, new_val = set(old_val or ()), set(new_val or ())
            self.assertEqual(old_val, new_val, (f.name, old_val, new_val))

        self.assertEqual(fresh_attachments[1].name, 'attachment2')
        self.assertIsInstance(fresh_attachments[1].item, self.ITEM_CLASS)

        for f in self.ITEM_CLASS.FIELDS:
            # Normalize some values we don't control
            if f.is_read_only:
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if isinstance(f, ExtendedPropertyField):
                # Attachments don't have these values. It may be possible to request it if we can find the FieldURI
                continue
            if f.name == 'reminder_due_by':
                # EWS sets a default value if it is not set on insert. Ignore
                continue
            if f.name == 'is_read':
                # This is always true for item attachments?
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            old_val = getattr(attached_item2, f.name)
            new_val = getattr(fresh_attachments[1].item, f.name)
            if f.is_list:
                old_val, new_val = set(old_val or ()), set(new_val or ())
            self.assertEqual(old_val, new_val, (f.name, old_val, new_val))

        # Test detach
        item.detach(attachment2)
        self.assertTrue(attachment2.attachment_id is None)
        self.assertTrue(attachment2.parent_item is None)
        fresh_item = list(self.account.fetch(ids=[item]))[0]
        self.assertEqual(len(fresh_item.attachments), 1)
        fresh_attachments = sorted(fresh_item.attachments, key=lambda a: a.name)

        for f in self.ITEM_CLASS.FIELDS:
            # Normalize some values we don't control
            if f.is_read_only:
                continue
            if self.ITEM_CLASS == CalendarItem and f in CalendarItem.timezone_fields():
                # Timezone fields will (and must) be populated automatically from the timestamp
                continue
            if isinstance(f, ExtendedPropertyField):
                # Attachments don't have these values. It may be possible to request it if we can find the FieldURI
                continue
            if f.name == 'reminder_due_by':
                # EWS sets a default value if it is not set on insert. Ignore
                continue
            if f.name == 'is_read':
                # This is always true for item attachments?
                continue
            if f.name == 'mime_content':
                # This will change depending on other contents fields
                continue
            old_val = getattr(attached_item1, f.name)
            new_val = getattr(fresh_attachments[0].item, f.name)
            if f.is_list:
                old_val, new_val = set(old_val or ()), set(new_val or ())
            self.assertEqual(old_val, new_val, (f.name, old_val, new_val))

        # Test attach with non-saved item
        attached_item3 = self.get_test_item(folder=self.test_folder)
        attached_item3.attachments = []
        if hasattr(attached_item3, 'is_all_day'):
            attached_item3.is_all_day = False
        attachment3 = ItemAttachment(name='attachment2', item=attached_item3)
        item.attach(attachment3)
        item.detach(attachment3)

    def test_recursive_attachments(self):
        # Test that we can handle an item which has an attached item, which has an attached item...
        item = self.get_test_item(folder=self.test_folder)
        attached_item_level_1 = self.get_test_item(folder=self.test_folder)
        attached_item_level_2 = self.get_test_item(folder=self.test_folder)
        attached_item_level_3 = self.get_test_item(folder=self.test_folder)

        attached_item_level_3.save()
        attachment_level_3 = ItemAttachment(name='attached_item_level_3', item=attached_item_level_3)
        attached_item_level_2.attach(attachment_level_3)
        attached_item_level_2.save()
        attachment_level_2 = ItemAttachment(name='attached_item_level_2', item=attached_item_level_2)
        attached_item_level_1.attach(attachment_level_2)
        attached_item_level_1.save()
        attachment_level_1 = ItemAttachment(name='attached_item_level_1', item=attached_item_level_1)
        item.attach(attachment_level_1)
        item.save()

        self.assertEqual(
            item.attachments[0].item.attachments[0].item.attachments[0].item.subject,
            attached_item_level_3.subject
        )

        # Also test a fresh item
        new_item = self.test_folder.get(id=item.id, changekey=item.changekey)
        self.assertEqual(
            new_item.attachments[0].item.attachments[0].item.attachments[0].item.subject,
            attached_item_level_3.subject
        )

    def test_bulk_failure(self):
        # Test that bulk_* can handle EWS errors and return the errors in order without losing non-failure results
        items1 = [self.get_test_item().save() for _ in range(3)]
        items1[1].changekey = 'XXX'
        for i, res in enumerate(self.account.bulk_delete(items1)):
            if i == 1:
                self.assertIsInstance(res, ErrorInvalidChangeKey)
            else:
                self.assertEqual(res, True)
        items2 = [self.get_test_item().save() for _ in range(3)]
        items2[1].id = 'AAAA=='
        for i, res in enumerate(self.account.bulk_delete(items2)):
            if i == 1:
                self.assertIsInstance(res, ErrorInvalidIdMalformed)
            else:
                self.assertEqual(res, True)
        items3 = [self.get_test_item().save() for _ in range(3)]
        items3[1].id = items1[0].id
        for i, res in enumerate(self.account.fetch(items3)):
            if i == 1:
                self.assertIsInstance(res, ErrorItemNotFound)
            else:
                self.assertIsInstance(res, Item)


class CalendarTest(BaseItemTest):
    TEST_FOLDER = 'calendar'
    FOLDER_CLASS = Calendar
    ITEM_CLASS = CalendarItem

    def test_updating_timestamps(self):
        # Test that we can update an item without changing anything, and maintain the hidden timezone fields as local
        # timezones, and that returned timestamps are in UTC.
        item = self.get_test_item()
        item.reminder_is_set = True
        item.is_all_day = False
        item.save()
        for i in self.account.calendar.filter(categories__contains=self.categories).only('start', 'end', 'categories'):
            self.assertEqual(i.start, item.start)
            self.assertEqual(i.start.tzinfo, UTC)
            self.assertEqual(i.end, item.end)
            self.assertEqual(i.end.tzinfo, UTC)
            self.assertEqual(i._start_timezone, self.account.default_timezone)
            self.assertEqual(i._end_timezone, self.account.default_timezone)
            i.save(update_fields=['start', 'end'])
            self.assertEqual(i.start, item.start)
            self.assertEqual(i.start.tzinfo, UTC)
            self.assertEqual(i.end, item.end)
            self.assertEqual(i.end.tzinfo, UTC)
            self.assertEqual(i._start_timezone, self.account.default_timezone)
            self.assertEqual(i._end_timezone, self.account.default_timezone)
        for i in self.account.calendar.filter(categories__contains=self.categories).only('start', 'end', 'categories'):
            self.assertEqual(i.start, item.start)
            self.assertEqual(i.start.tzinfo, UTC)
            self.assertEqual(i.end, item.end)
            self.assertEqual(i.end.tzinfo, UTC)
            self.assertEqual(i._start_timezone, self.account.default_timezone)
            self.assertEqual(i._end_timezone, self.account.default_timezone)
            i.delete()

    def test_update_to_non_utc_datetime(self):
        # Test updating with non-UTC datetime values. This is a separate code path in UpdateItem code
        item = self.get_test_item()
        item.reminder_is_set = True
        item.is_all_day = False
        item.save()
        # Update start, end and recurrence with timezoned datetimes. For some reason, EWS throws
        # 'ErrorOccurrenceTimeSpanTooBig' is we go back in time.
        start = get_random_date(start_date=item.start.date() + datetime.timedelta(days=1))
        dt_start, dt_end = [dt.astimezone(self.account.default_timezone) for dt in
                            get_random_datetime_range(start_date=start, end_date=start, tz=self.account.default_timezone)]
        item.start, item.end = dt_start, dt_end
        item.recurrence.boundary.start = dt_start.date()
        item.save()
        item.refresh()
        self.assertEqual(item.start, dt_start)
        self.assertEqual(item.end, dt_end)

    def test_all_day_datetimes(self):
        # Test that start and end datetimes for all-day items are returned in the datetime of the account.
        start = get_random_date()
        start_dt, end_dt = get_random_datetime_range(
            start_date=start,
            end_date=start + datetime.timedelta(days=365),
            tz=self.account.default_timezone
        )
        item = self.ITEM_CLASS(folder=self.test_folder, start=start_dt, end=end_dt, is_all_day=True,
                               categories=self.categories)
        item.save()

        item = self.test_folder.all().only('start', 'end').get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.start.astimezone(self.account.default_timezone).time(), datetime.time(0, 0))
        self.assertEqual(item.end.astimezone(self.account.default_timezone).time(), datetime.time(0, 0))
        item.delete()

    def test_view(self):
        item1 = self.ITEM_CLASS(
            account=self.account,
            folder=self.test_folder,
            subject=get_random_string(16),
            start=self.account.default_timezone.localize(EWSDateTime(2016, 1, 1, 8)),
            end=self.account.default_timezone.localize(EWSDateTime(2016, 1, 1, 10)),
            categories=self.categories,
        )
        item2 = self.ITEM_CLASS(
            account=self.account,
            folder=self.test_folder,
            subject=get_random_string(16),
            start=self.account.default_timezone.localize(EWSDateTime(2016, 2, 1, 8)),
            end=self.account.default_timezone.localize(EWSDateTime(2016, 2, 1, 10)),
            categories=self.categories,
        )
        self.test_folder.bulk_create(items=[item1, item2])

        # Test missing args
        with self.assertRaises(TypeError):
            self.test_folder.view()
        # Test bad args
        with self.assertRaises(ValueError):
            list(self.test_folder.view(start=item1.end, end=item1.start))
        with self.assertRaises(TypeError):
            list(self.test_folder.view(start='xxx', end=item1.end))
        with self.assertRaises(ValueError):
            list(self.test_folder.view(start=item1.start, end=item1.end, max_items=0))

        def match_cat(i):
            return set(i.categories) == set(self.categories)

        # Test dates
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.start, end=item1.end) if match_cat(i)]),
            1
        )
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.start, end=item2.end) if match_cat(i)]),
            2
        )
        # Edge cases. Get view from end of item1 to start of item2. Should logically return 0 items, but Exchange wants
        # it differently and returns item1 even though there is no overlap.
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.end, end=item2.start) if match_cat(i)]),
            1
        )
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.start, end=item2.start) if match_cat(i)]),
            1
        )

        # Test max_items
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.start, end=item2.end, max_items=9999) if match_cat(i)]),
            2
        )
        self.assertEqual(
            len(self.test_folder.view(start=item1.start, end=item2.end, max_items=1)),
            1
        )

        # Test chaining
        qs = self.test_folder.view(start=item1.start, end=item2.end)
        self.assertTrue(qs.count() >= 2)
        with self.assertRaises(ErrorInvalidOperation):
            qs.filter(subject=item1.subject).count()  # EWS does not allow restrictions
        self.assertListEqual(
            [i for i in qs.order_by('subject').values('subject') if i['subject'] in (item1.subject, item2.subject)],
            [{'subject': s} for s in sorted([item1.subject, item2.subject])]
        )

    def test_recurring_items(self):
        tz = self.account.default_timezone
        item = CalendarItem(
            folder=self.test_folder,
            start=tz.localize(EWSDateTime(2017, 9, 4, 11)),
            end=tz.localize(EWSDateTime(2017, 9, 4, 13)),
            subject='Hello Recurrence',
            recurrence=Recurrence(
                pattern=WeeklyPattern(interval=3, weekdays=[MONDAY, WEDNESDAY]),
                start=EWSDate(2017, 9, 4),
                number=7
            ),
            categories=self.categories,
        ).save()

        # Occurrence data for the master item
        fresh_item = self.test_folder.get(id=item.id, changekey=item.changekey)
        self.assertEqual(
            str(fresh_item.recurrence),
            'Pattern: Occurs on weekdays Monday, Wednesday of every 3 week(s) where the first day of the week is '
            'Monday, Boundary: NumberedPattern(start=EWSDate(2017, 9, 4), number=7)'
        )
        self.assertIsInstance(fresh_item.first_occurrence, FirstOccurrence)
        self.assertEqual(fresh_item.first_occurrence.start, tz.localize(EWSDateTime(2017, 9, 4, 11)))
        self.assertEqual(fresh_item.first_occurrence.end, tz.localize(EWSDateTime(2017, 9, 4, 13)))
        self.assertIsInstance(fresh_item.last_occurrence, LastOccurrence)
        self.assertEqual(fresh_item.last_occurrence.start, tz.localize(EWSDateTime(2017, 11, 6, 11)))
        self.assertEqual(fresh_item.last_occurrence.end, tz.localize(EWSDateTime(2017, 11, 6, 13)))
        self.assertEqual(fresh_item.modified_occurrences, None)
        self.assertEqual(fresh_item.deleted_occurrences, None)

        # All occurrences expanded
        all_start_times = []
        for i in self.test_folder.view(
                start=tz.localize(EWSDateTime(2017, 9, 1)),
                end=tz.localize(EWSDateTime(2017, 12, 1))
        ).only('start', 'categories').order_by('start'):
            if i.categories != self.categories:
                continue
            all_start_times.append(i.start)
        self.assertListEqual(
            all_start_times,
            [
                tz.localize(EWSDateTime(2017, 9, 4, 11)),
                tz.localize(EWSDateTime(2017, 9, 6, 11)),
                tz.localize(EWSDateTime(2017, 9, 25, 11)),
                tz.localize(EWSDateTime(2017, 9, 27, 11)),
                tz.localize(EWSDateTime(2017, 10, 16, 11)),
                tz.localize(EWSDateTime(2017, 10, 18, 11)),
                tz.localize(EWSDateTime(2017, 11, 6, 11)),
            ]
        )

        # Test updating and deleting
        i = 0
        for occurrence in self.test_folder.view(
                start=tz.localize(EWSDateTime(2017, 9, 1)),
                end=tz.localize(EWSDateTime(2017, 12, 1)),
        ).order_by('start'):
            if occurrence.categories != self.categories:
                continue
            if i % 2:
                # Delete every other occurrence (items 1, 3 and 5)
                occurrence.delete()
            else:
                # Update every other occurrence (items 0, 2, 4 and 6)
                occurrence.refresh()  # changekey is sometimes updated. Possible due to neighbour occurrences changing?
                # We receive timestamps as UTC but want to write them back as local timezone
                occurrence.start = occurrence.start.astimezone(tz)
                occurrence.start += datetime.timedelta(minutes=30)
                occurrence.end = occurrence.end.astimezone(tz)
                occurrence.end += datetime.timedelta(minutes=30)
                occurrence.subject = 'Changed Occurrence'
                occurrence.save()
            i += 1

        # We should only get half the items of before, and start times should be shifted 30 minutes
        updated_start_times = []
        for i in self.test_folder.view(
                start=tz.localize(EWSDateTime(2017, 9, 1)),
                end=tz.localize(EWSDateTime(2017, 12, 1))
        ).only('start', 'subject', 'categories').order_by('start'):
            if i.categories != self.categories:
                continue
            updated_start_times.append(i.start)
            self.assertEqual(i.subject, 'Changed Occurrence')
        self.assertListEqual(
            updated_start_times,
            [
                tz.localize(EWSDateTime(2017, 9, 4, 11, 30)),
                tz.localize(EWSDateTime(2017, 9, 25, 11, 30)),
                tz.localize(EWSDateTime(2017, 10, 16, 11, 30)),
                tz.localize(EWSDateTime(2017, 11, 6, 11, 30)),
            ]
        )

        # Test that the master item sees the deletes and updates
        fresh_item = self.test_folder.get(id=item.id, changekey=item.changekey)
        self.assertEqual(len(fresh_item.modified_occurrences), 4)
        self.assertEqual(len(fresh_item.deleted_occurrences), 3)


class MessagesTest(BaseItemTest):
    # Just test one of the Message-type folders
    TEST_FOLDER = 'inbox'
    FOLDER_CLASS = Inbox
    ITEM_CLASS = Message
    INCOMING_MESSAGE_TIMEOUT = 180

    def get_incoming_message(self, subject):
        t1 = time.time()
        while True:
            t2 = time.time()
            self.assertLess(t2 - t1, self.INCOMING_MESSAGE_TIMEOUT,
                            'Gave up waiting for the incoming message to show up in the inbox')
            try:
                return self.account.inbox.get(subject=subject)
            except DoesNotExist:
                time.sleep(5)

    def test_send(self):
        # Test that we can send (only) Message items
        item = self.get_test_item()
        item.folder = None
        item.send()
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 0)

    def test_send_and_save(self):
        # Test that we can send_and_save Message items
        item = self.get_test_item()
        item.send_and_save()
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)
        time.sleep(5)  # Requests are supposed to be transactional, but apparently not...
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 1)

        # Test update, although it makes little sense
        item = self.get_test_item()
        item.save()
        item.send_and_save()
        time.sleep(5)  # Requests are supposed to be transactional, but apparently not...
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 1)

    def test_send_draft(self):
        item = self.get_test_item()
        item.folder = self.account.drafts
        item.is_draft = True
        item.save()  # Save a draft
        item.send()  # Send the draft
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)
        self.assertIsNone(item.folder)
        self.assertEqual(len(self.test_folder.filter(categories__contains=item.categories)), 0)

    def test_send_and_copy_to_folder(self):
        item = self.get_test_item()
        item.send(save_copy=True, copy_to_folder=self.account.sent)  # Send the draft and save to the sent folder
        self.assertIsNone(item.id)
        self.assertIsNone(item.changekey)
        self.assertEqual(item.folder, self.account.sent)
        time.sleep(5)  # Requests are supposed to be transactional, but apparently not...
        self.assertEqual(len(self.account.sent.filter(categories__contains=item.categories)), 1)

    def test_bulk_send(self):
        with self.assertRaises(AttributeError):
            self.account.bulk_send(ids=[], save_copy=False, copy_to_folder=self.account.trash)
        item = self.get_test_item()
        item.save()
        for res in self.account.bulk_send(ids=[item]):
            self.assertEqual(res, True)
        time.sleep(10)  # Requests are supposed to be transactional, but apparently not...
        # By default, sent items are placed in the sent folder
        ids = self.account.sent.filter(categories__contains=item.categories).values_list('id', 'changekey')
        self.assertEqual(len(ids), 1)
        self.bulk_delete(ids)

    def test_reply(self):
        # Test that we can reply to a Message item. EWS only allows items that have been sent to receive a reply
        item = self.get_test_item()
        item.folder = None
        item.send()  # get_test_item() sets the to_recipients to the test account
        sent_item = self.get_incoming_message(item.subject)
        new_subject = ('Re: %s' % sent_item.subject)[:255]
        sent_item.reply(subject=new_subject, body='Hello reply', to_recipients=[item.author])
        reply = self.get_incoming_message(new_subject)
        self.account.bulk_delete([sent_item, reply])

    def test_reply_all(self):
        # Test that we can reply-all a Message item. EWS only allows items that have been sent to receive a reply
        item = self.get_test_item(folder=None)
        item.folder = None
        item.send()
        sent_item = self.get_incoming_message(item.subject)
        new_subject = ('Re: %s' % sent_item.subject)[:255]
        sent_item.reply_all(subject=new_subject, body='Hello reply')
        reply = self.get_incoming_message(new_subject)
        self.account.bulk_delete([sent_item, reply])

    def test_forward(self):
        # Test that we can forward a Message item. EWS only allows items that have been sent to receive a reply
        item = self.get_test_item(folder=None)
        item.folder = None
        item.send()
        sent_item = self.get_incoming_message(item.subject)
        new_subject = ('Re: %s' % sent_item.subject)[:255]
        sent_item.forward(subject=new_subject, body='Hello reply', to_recipients=[item.author])
        reply = self.get_incoming_message(new_subject)
        reply2 = sent_item.create_forward(subject=new_subject, body='Hello reply', to_recipients=[item.author])
        reply2 = reply2.save(self.account.drafts)
        self.assertIsInstance(reply2, Message)

        self.account.bulk_delete([sent_item, reply, reply2])

    def test_mime_content(self):
        # Tests the 'mime_content' field
        subject = get_random_string(16)
        msg = MIMEMultipart()
        msg['From'] = self.account.primary_smtp_address
        msg['To'] = self.account.primary_smtp_address
        msg['Subject'] = subject
        body = 'MIME test mail'
        msg.attach(MIMEText(body, 'plain', _charset='utf-8'))
        mime_content = msg.as_string().encode('utf-8')
        item = self.ITEM_CLASS(
            folder=self.test_folder,
            to_recipients=[self.account.primary_smtp_address],
            mime_content=mime_content
        ).save()
        self.assertEqual(self.test_folder.get(subject=subject).body, body)
        item.delete()


class TasksTest(BaseItemTest):
    TEST_FOLDER = 'tasks'
    FOLDER_CLASS = Tasks
    ITEM_CLASS = Task

    def test_complete(self):
        item = self.get_test_item().save()
        item.refresh()
        self.assertNotEqual(item.status, Task.COMPLETED)
        self.assertNotEqual(item.percent_complete, Decimal(100))
        item.complete()
        item.refresh()
        self.assertEqual(item.status, Task.COMPLETED)
        self.assertEqual(item.percent_complete, Decimal(100))


class ContactsTest(BaseItemTest):
    TEST_FOLDER = 'contacts'
    FOLDER_CLASS = Contacts
    ITEM_CLASS = Contact

    def test_distribution_lists(self):
        dl = DistributionList(folder=self.test_folder, display_name=get_random_string(255), categories=self.categories)
        dl.save()
        new_dl = self.test_folder.get(categories__contains=dl.categories)
        self.assertEqual(new_dl.display_name, dl.display_name)
        self.assertEqual(new_dl.members, None)
        dl.refresh()

        dl.members = set(
            # We set mailbox_type to OneOff because otherwise the email address must be an actual account
            Member(mailbox=Mailbox(email_address=get_random_email(), mailbox_type='OneOff')) for _ in range(4)
        )
        dl.save()
        new_dl = self.test_folder.get(categories__contains=dl.categories)
        self.assertEqual({m.mailbox.email_address for m in new_dl.members}, dl.members)

        dl.delete()

    def test_find_people(self):
        # The test server may not have any contacts. Just test that the FindPeople service and helpers work
        self.assertGreaterEqual(len(list(self.test_folder.people())), 0)
        self.assertGreaterEqual(
            len(list(
                self.test_folder.people().only('display_name').filter(display_name='john').order_by('display_name')
            )),
            0
        )

    def test_get_persona(self):
        # The test server may not have any personas. Just test that the service response with something we can parse
        persona = Persona(persona_id=PersonaId(id='AAA=', changekey='xxx'))
        try:
            GetPersona(protocol=self.account.protocol).call(persona=persona)
        except ErrorInvalidIdMalformed:
            pass


def get_random_bool():
    return bool(random.randint(0, 1))


def get_random_int(min_val=0, max_val=2147483647):
    return random.randint(min_val, max_val)


def get_random_decimal(min_val=0, max_val=100):
    precision = 2
    val = get_random_int(min_val, max_val * 10**precision) / 10.0**precision
    return Decimal('{:.2f}'.format(val))


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


def get_random_bytes(*args, **kwargs):
    return get_random_string(*args, **kwargs).encode('utf-8')


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


# The timezone we're testing (CET/CEST) had a DST date change in 1996 (see
# https://en.wikipedia.org/wiki/Summer_Time_in_Europe). The Microsoft timezone definition on the server
# does not observe that, but pytz does. So random datetimes before 1996 will fail tests randomly.

def get_random_date(start_date=EWSDate(1996, 1, 1), end_date=EWSDate(2030, 1, 1)):
    # Keep with a reasonable date range. A wider date range is unstable WRT timezones
    return EWSDate.fromordinal(random.randint(start_date.toordinal(), end_date.toordinal()))


def get_random_datetime(start_date=EWSDate(1996, 1, 1), end_date=EWSDate(2030, 1, 1), tz=UTC):
    # Create a random datetime with minute precision. Both dates are inclusive.
    # Keep with a reasonable date range. A wider date range than the default values is unstable WRT timezones.
    while True:
        try:
            random_date = get_random_date(start_date=start_date, end_date=end_date)
            random_datetime = datetime.datetime.combine(random_date, datetime.time.min) \
                + datetime.timedelta(minutes=random.randint(0, 60 * 24))
            return tz.localize(EWSDateTime.from_datetime(random_datetime), is_dst=None)
        except (AmbiguousTimeError, NonExistentTimeError):
            pass


def get_random_datetime_range(start_date=EWSDate(1996, 1, 1), end_date=EWSDate(2030, 1, 1), tz=UTC):
    # Create two random datetimes.  Both dates are inclusive.
    # Keep with a reasonable date range. A wider date range than the default values is unstable WRT timezones.
    # Calendar items raise ErrorCalendarDurationIsTooLong if duration is > 5 years.
    return sorted([
        get_random_datetime(start_date=start_date, end_date=end_date, tz=tz),
        get_random_datetime(start_date=start_date, end_date=end_date, tz=tz),
    ])


if __name__ == '__main__':
    import sys

    if '-q' in sys.argv:
        sys.argv.remove('-q')
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.DEBUG, handlers=[PrettyXmlHandler()])

    unittest.main()
else:
    # Don't print warnings and stack traces mixed with test progress. We'll get the debug info for test failures later.
    logging.basicConfig(level=logging.CRITICAL)
