import datetime
import os
import pickle
import socket
import tempfile
import warnings
from contextlib import suppress
from unittest.mock import Mock, patch

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

import psutil
import requests_mock
from oauthlib.oauth2 import InvalidClientIdError

from exchangelib import close_connections
from exchangelib.configuration import Configuration
from exchangelib.credentials import Credentials, OAuth2AuthorizationCodeCredentials, OAuth2Credentials
from exchangelib.errors import (
    ErrorAccessDenied,
    ErrorMailRecipientNotFound,
    ErrorNameResolutionNoResults,
    RateLimitError,
    SessionPoolMaxSizeReached,
    SessionPoolMinSizeReached,
    TransportError,
)
from exchangelib.items import SEARCH_SCOPE_CHOICES, CalendarItem
from exchangelib.properties import (
    EWS_ID,
    ID_FORMATS,
    AlternateId,
    DaylightTime,
    DLMailbox,
    FailedMailbox,
    FreeBusyView,
    FreeBusyViewOptions,
    ItemId,
    Mailbox,
    MailboxData,
    Period,
    RoomList,
    SearchableMailbox,
    StandardTime,
    TimeZone,
)
from exchangelib.protocol import BaseProtocol, FailFast, FaultTolerance, NoVerifyHTTPAdapter, Protocol
from exchangelib.services import (
    ExpandDL,
    GetRoomLists,
    GetRooms,
    GetSearchableMailboxes,
    GetServerTimeZones,
    ResolveNames,
    SetUserOofSettings,
)
from exchangelib.settings import OofSettings
from exchangelib.transport import NOAUTH, NTLM, OAUTH2
from exchangelib.util import DummyResponse
from exchangelib.version import EXCHANGE_2010_SP1, Build, Version
from exchangelib.winzone import CLDR_TO_MS_TIMEZONE_MAP

from .common import (
    RANDOM_DATE_MAX,
    RANDOM_DATE_MIN,
    EWSTest,
    get_random_datetime_range,
    get_random_hostname,
    get_random_string,
)


class ProtocolTest(EWSTest):
    @staticmethod
    def get_test_protocol(**kwargs):
        return Protocol(
            config=Configuration(
                server=kwargs.get("server"),
                service_endpoint=kwargs.get("service_endpoint", f"https://{get_random_hostname()}/Foo.asmx"),
                credentials=kwargs.get("credentials", Credentials(get_random_string(8), get_random_string(8))),
                auth_type=kwargs.get("auth_type", NTLM),
                version=kwargs.get("version", Version(Build(15, 1))),
                retry_policy=kwargs.get("retry_policy", FailFast()),
                max_connections=kwargs.get("max_connections"),
            )
        )

    def test_magic(self):
        p = self.get_test_protocol()
        self.assertEqual(
            str(p),
            f"""\
EWS url: {p.service_endpoint}
Product name: Microsoft Exchange Server 2016
EWS API version: Exchange2016
Build number: 15.1.0.0
EWS auth: NTLM""",
        )
        p.config.version = None
        self.assertEqual(
            str(p),
            f"""\
EWS url: {p.service_endpoint}
Product name: [unknown]
EWS API version: [unknown]
Build number: [unknown]
EWS auth: NTLM""",
        )

    def test_close_connections_helper(self):
        # Just test that it doesn't break
        close_connections()

    def test_init(self):
        with self.assertRaises(TypeError) as e:
            Protocol(config="XXX")
        self.assertEqual(
            e.exception.args[0], "'config' 'XXX' must be of type <class 'exchangelib.configuration.Configuration'>"
        )
        with self.assertRaises(AttributeError) as e:
            Protocol(config=Configuration())
        self.assertEqual(e.exception.args[0], "'config.service_endpoint' must be set")

    def test_pickle(self):
        # Test that we can pickle, repr and str Protocols
        o = self.get_test_protocol()
        pickled_o = pickle.dumps(o)
        unpickled_o = pickle.loads(pickled_o)
        self.assertIsInstance(unpickled_o, type(o))
        self.assertEqual(repr(o), repr(unpickled_o))
        self.assertEqual(str(o), str(unpickled_o))

    @requests_mock.mock()
    def test_session(self, m):
        protocol = self.get_test_protocol()
        session = protocol.create_session()
        new_session = protocol.renew_session(session)
        self.assertNotEqual(id(session), id(new_session))

    @requests_mock.mock()
    def test_protocol_instance_caching(self, m):
        # Verify that we get the same Protocol instance for the same combination of (endpoint, credentials)
        config = Configuration(
            service_endpoint="https://example.com/Foo.asmx",
            credentials=Credentials(get_random_string(8), get_random_string(8)),
            auth_type=NTLM,
            version=Version(Build(15, 1)),
            retry_policy=FailFast(),
        )
        # Test CachingProtocol.__getitem__
        with self.assertRaises(KeyError):
            _ = Protocol[config]
        base_p = Protocol(config=config)
        self.assertEqual(base_p, Protocol[config][0])

        # Make sure we always return the same item when creating a Protocol with the same endpoint and creds
        for _ in range(10):
            p = Protocol(config=config)
            self.assertEqual(base_p, p)
            self.assertEqual(id(base_p), id(p))
            self.assertEqual(hash(base_p), hash(p))
            self.assertEqual(id(base_p._session_pool), id(p._session_pool))

        # Test CachingProtocol.__delitem__
        del Protocol[config]
        with self.assertRaises(KeyError):
            _ = Protocol[config]

        # Make sure we get a fresh instance after we cleared the cache
        p = Protocol(config=config)
        self.assertNotEqual(base_p, p)

        Protocol.clear_cache()

    def test_close(self):
        # Don't use example.com here - it does not resolve or answer on all ISPs
        proc = psutil.Process()
        hostname = "httpbin.org"
        ip_addresses = {
            info[4][0]
            for info in socket.getaddrinfo(hostname, 80, socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
        }

        def conn_count():
            return len([p for p in proc.connections() if p.raddr[0] in ip_addresses])

        self.assertGreater(len(ip_addresses), 0)
        url = f"http://{hostname}"
        protocol = self.get_test_protocol(service_endpoint=url, auth_type=NOAUTH, max_connections=3)
        # Merely getting a session should not create connections
        session = protocol.get_session()
        self.assertEqual(conn_count(), 0)
        # Open one URL - we have 1 connection
        session.get(url)
        self.assertEqual(conn_count(), 1)
        # Open the same URL - we should still have 1 connection
        session.get(url)
        self.assertEqual(conn_count(), 1)

        # Open some more connections
        s2 = protocol.get_session()
        s2.get(url)
        s3 = protocol.get_session()
        s3.get(url)
        self.assertEqual(conn_count(), 3)

        # Releasing the sessions does not close the connections
        protocol.release_session(session)
        protocol.release_session(s2)
        protocol.release_session(s3)
        self.assertEqual(conn_count(), 3)

        # But closing explicitly does
        protocol.close()
        self.assertEqual(conn_count(), 0)

    def test_decrease_poolsize(self):
        # Test increasing and decreasing the pool size
        max_connections = 3
        protocol = self.get_test_protocol(max_connections=max_connections)
        self.assertEqual(protocol._session_pool.qsize(), 0)
        self.assertEqual(protocol.session_pool_size, 0)
        protocol.increase_poolsize()
        protocol.increase_poolsize()
        protocol.increase_poolsize()
        with self.assertRaises(SessionPoolMaxSizeReached):
            protocol.increase_poolsize()
        self.assertEqual(protocol._session_pool.qsize(), max_connections)
        self.assertEqual(protocol.session_pool_size, max_connections)
        protocol.decrease_poolsize()
        protocol.decrease_poolsize()
        with self.assertRaises(SessionPoolMinSizeReached):
            protocol.decrease_poolsize()
        self.assertEqual(protocol._session_pool.qsize(), 1)

    def test_max_usage_count(self):
        protocol = self.get_test_protocol(max_connections=1)
        session = protocol.get_session()
        protocol.release_session(session)
        self.assertEqual(session.usage_count, 1)
        for _ in range(2):
            session = protocol.get_session()
            protocol.release_session(session)
        self.assertEqual(session.usage_count, 3)
        tmp = Protocol.MAX_SESSION_USAGE_COUNT
        try:
            Protocol.MAX_SESSION_USAGE_COUNT = 1
            for _ in range(2):
                session = protocol.get_session()
                protocol.release_session(session)
            self.assertEqual(session.usage_count, 1)
        finally:
            Protocol.MAX_SESSION_USAGE_COUNT = tmp

    def test_get_timezones(self):
        # Test shortcut
        data = list(self.account.protocol.get_timezones())
        self.assertAlmostEqual(len(list(self.account.protocol.get_timezones())), 130, delta=30, msg=data)
        # Test translation to TimeZone objects
        for tz_definition in self.account.protocol.get_timezones(return_full_timezone_data=True):
            with suppress(ValueError):
                tz = TimeZone.from_server_timezone(
                    tz_definition=tz_definition,
                    for_year=2018,
                )
                self.assertEqual(tz.bias, tz_definition.get_std_and_dst(for_year=2018)[2].bias_in_minutes)

    def test_get_timezones_parsing(self):
        # Test static XML since it's non-standard
        xml = b"""\
<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Header xmlns="http://schemas.xmlsoap.org/soap/envelope/">
    <ServerVersionInfo
        xmlns="http://schemas.microsoft.com/exchange/services/2006/types"
        MajorVersion="14"
        MinorVersion="2"
        MajorBuildNumber="390"
        MinorBuildNumber="3"
        Version="Exchange2010_SP2"/>
  </Header>
  <soap:Body>
    <m:GetServerTimeZonesResponse
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
      <m:ResponseMessages>
        <m:GetServerTimeZonesResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:TimeZoneDefinitions>
            <t:TimeZoneDefinition
                Id="W. Europe Standard Time"
                Name="(UTC+01:00) Amsterdam, Berlin, Bern, Rome, Stockholm, Vienna">
              <t:Periods>
                <t:Period Bias="-PT60M" Name="Standard" Id="std"/>
                <t:Period Bias="-PT120M" Name="Daylight" Id="dlt"/>
              </t:Periods>
              <t:TransitionsGroups>
                <t:TransitionsGroup Id="0">
                  <t:RecurringDayTransition>
                    <t:To Kind="Period">std</t:To>
                    <t:TimeOffset>PT180M</t:TimeOffset>
                    <t:Month>10</t:Month>
                    <t:DayOfWeek>Sunday</t:DayOfWeek>
                    <t:Occurrence>-1</t:Occurrence>
                  </t:RecurringDayTransition>
                  <t:RecurringDayTransition>
                    <t:To Kind="Period">dlt</t:To>
                    <t:TimeOffset>PT120M</t:TimeOffset>
                    <t:Month>3</t:Month>
                    <t:DayOfWeek>Sunday</t:DayOfWeek>
                    <t:Occurrence>-1</t:Occurrence>
                  </t:RecurringDayTransition>
                </t:TransitionsGroup>
              </t:TransitionsGroups>
              <t:Transitions>
                <t:Transition>
                  <t:To Kind="Group">0</t:To>
                </t:Transition>
              </t:Transitions>
            </t:TimeZoneDefinition>
          </m:TimeZoneDefinitions>
        </m:GetServerTimeZonesResponseMessage>
      </m:ResponseMessages>
    </m:GetServerTimeZonesResponse>
  </soap:Body>
</soap:Envelope>"""
        ws = GetServerTimeZones(self.account.protocol)
        timezones = list(ws.parse(xml))
        self.assertEqual(1, len(timezones))
        (standard_transition, daylight_transition, standard_period) = timezones[0].get_std_and_dst(2022)
        self.assertEqual(
            standard_transition,
            StandardTime(bias=0, time=datetime.time(hour=3), occurrence=5, iso_month=10, weekday=7),
        )
        self.assertEqual(
            daylight_transition,
            DaylightTime(bias=-60, time=datetime.time(hour=2), occurrence=5, iso_month=3, weekday=7),
        )
        self.assertEqual(
            standard_period,
            Period(id="std", name="Standard", bias=datetime.timedelta(minutes=-60)),
        )

    def test_get_free_busy_info(self):
        tz = self.account.default_timezone
        server_timezones = list(self.account.protocol.get_timezones(return_full_timezone_data=True))
        start = datetime.datetime.now(tz=tz)
        end = datetime.datetime.now(tz=tz) + datetime.timedelta(hours=6)
        accounts = [(self.account, "Organizer", False)]

        with self.assertRaises(TypeError) as e:
            list(self.account.protocol.get_free_busy_info(accounts=[(123, "XXX", "XXX")], start=start, end=end))
        self.assertEqual(
            e.exception.args[0], "Field 'email' value 123 must be of type <class 'exchangelib.properties.Email'>"
        )
        with self.assertRaises(ValueError) as e:
            list(
                self.account.protocol.get_free_busy_info(accounts=[(self.account, "XXX", "XXX")], start=start, end=end)
            )
        self.assertEqual(
            e.exception.args[0],
            f"Invalid choice 'XXX' for field 'attendee_type'. Valid choices are {sorted(MailboxData.ATTENDEE_TYPES)}",
        )
        with self.assertRaises(TypeError) as e:
            list(
                self.account.protocol.get_free_busy_info(
                    accounts=[(self.account, "Organizer", "X")], start=start, end=end
                )
            )
        self.assertEqual(e.exception.args[0], "Field 'exclude_conflicts' value 'X' must be of type <class 'bool'>")
        with self.assertRaises(ValueError) as e:
            list(self.account.protocol.get_free_busy_info(accounts=accounts, start=end, end=start))
        self.assertIn("'start' must be less than 'end'", e.exception.args[0])
        with self.assertRaises(TypeError) as e:
            list(
                self.account.protocol.get_free_busy_info(
                    accounts=accounts, start=start, end=end, merged_free_busy_interval="XXX"
                )
            )
        self.assertEqual(
            e.exception.args[0], "Field 'merged_free_busy_interval' value 'XXX' must be of type <class 'int'>"
        )
        with self.assertRaises(ValueError) as e:
            list(
                self.account.protocol.get_free_busy_info(accounts=accounts, start=start, end=end, requested_view="XXX")
            )
        self.assertEqual(
            e.exception.args[0],
            f"Invalid choice 'XXX' for field 'requested_view'. Valid choices are "
            f"{sorted(FreeBusyViewOptions.REQUESTED_VIEWS)}",
        )

        for view_info in self.account.protocol.get_free_busy_info(accounts=accounts, start=start, end=end):
            self.assertIsInstance(view_info, FreeBusyView)
            self.assertIsInstance(view_info.working_hours_timezone, TimeZone)
            ms_id = view_info.working_hours_timezone.to_server_timezone(server_timezones, start.year)
            self.assertIn(ms_id, {t[0] for t in CLDR_TO_MS_TIMEZONE_MAP.values()})

        # Test account as simple email
        for view_info in self.account.protocol.get_free_busy_info(
            accounts=[(self.account.primary_smtp_address, "Organizer", False)], start=start, end=end
        ):
            self.assertIsInstance(view_info, FreeBusyView)

        # Test non-existing address
        for view_info in self.account.protocol.get_free_busy_info(
            accounts=[(f"unlikely-to-exist-{self.account.primary_smtp_address}", "Organizer", False)],
            start=start,
            end=end,
        ):
            self.assertIsInstance(view_info, ErrorMailRecipientNotFound)

        # Test +100 addresses
        for view_info in self.account.protocol.get_free_busy_info(
            accounts=[(f"unknown-{i}-{self.account.primary_smtp_address}", "Organizer", False) for i in range(101)],
            start=start,
            end=end,
        ):
            self.assertIsInstance(view_info, ErrorMailRecipientNotFound)

        # Test non-existing and existing address
        view_infos = list(
            self.account.protocol.get_free_busy_info(
                accounts=[
                    (f"unlikely-to-exist-{self.account.primary_smtp_address}", "Organizer", False),
                    (self.account.primary_smtp_address, "Organizer", False),
                ],
                start=start,
                end=end,
            )
        )
        self.assertIsInstance(view_infos[0], ErrorMailRecipientNotFound)
        self.assertIsInstance(view_infos[1], FreeBusyView)

    def test_get_roomlists(self):
        # The test server is not guaranteed to have any room lists which makes this test less useful
        ws = GetRoomLists(self.account.protocol)
        roomlists = ws.call()
        self.assertEqual(list(roomlists), [])
        # Test shortcut
        self.assertEqual(list(self.account.protocol.get_roomlists()), [])

    def test_get_roomlists_parsing(self):
        # Test static XML since server has no roomlists
        xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:GetRoomListsResponse ResponseClass="Success"
                xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
                xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
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
</s:Envelope>"""
        ws = GetRoomLists(self.account.protocol)
        self.assertSetEqual(
            {rl.email_address for rl in ws.parse(xml)}, {"roomlist1@example.com", "roomlist2@example.com"}
        )

    def test_get_rooms(self):
        # The test server is not guaranteed to have any rooms or room lists which makes this test less useful
        roomlist = RoomList(email_address="my.roomlist@example.com")
        ws = GetRooms(self.account.protocol)
        with self.assertRaises(ErrorNameResolutionNoResults):
            list(ws.call(room_list=roomlist))
        # Test shortcut
        with self.assertRaises(ErrorNameResolutionNoResults):
            list(self.account.protocol.get_rooms("my.roomlist@example.com"))

    def test_get_rooms_parsing(self):
        # Test static XML since server has no rooms
        xml = b"""\
<?xml version="1.0" ?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
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
</s:Envelope>"""
        ws = GetRooms(self.account.protocol)
        self.assertSetEqual({r.email_address for r in ws.parse(xml)}, {"room1@example.com", "room2@example.com"})

    def test_resolvenames(self):
        with self.assertRaises(ValueError) as e:
            self.account.protocol.resolve_names(names=[], search_scope="XXX")
        self.assertEqual(e.exception.args[0], f"'search_scope' 'XXX' must be one of {sorted(SEARCH_SCOPE_CHOICES)}")
        with self.assertRaises(ValueError) as e:
            self.account.protocol.resolve_names(names=[], shape="XXX")
        self.assertEqual(
            e.exception.args[0], "'contact_data_shape' 'XXX' must be one of ['AllProperties', 'Default', 'IdOnly']"
        )
        with self.assertRaises(ValueError) as e:
            ResolveNames(protocol=self.account.protocol, chunk_size=500).call(unresolved_entries=None)
        self.assertEqual(
            e.exception.args[0],
            "Chunk size 500 is too high. ResolveNames supports returning at most 100 candidates for a lookup",
        )
        tmp = self.account.protocol.version
        self.account.protocol.config.version = Version(EXCHANGE_2010_SP1)
        with self.assertRaises(NotImplementedError) as e:
            self.account.protocol.resolve_names(names=["xxx@example.com"], shape="IdOnly")
        self.account.protocol.config.version = tmp
        self.assertEqual(
            e.exception.args[0], "'contact_data_shape' is only supported for Exchange 2010 SP2 servers and later"
        )
        self.assertGreaterEqual(self.account.protocol.resolve_names(names=["xxx@example.com"]), [])
        self.assertGreaterEqual(
            self.account.protocol.resolve_names(names=["xxx@example.com"], search_scope="ActiveDirectoryContacts"), []
        )
        self.assertGreaterEqual(
            self.account.protocol.resolve_names(names=["xxx@example.com"], shape="AllProperties"), []
        )
        self.assertGreaterEqual(
            self.account.protocol.resolve_names(names=["xxx@example.com"], parent_folders=[self.account.contacts]), []
        )
        self.assertEqual(
            self.account.protocol.resolve_names(names=[self.account.primary_smtp_address]),
            [Mailbox(email_address=self.account.primary_smtp_address)],
        )
        # Test something that's not an email
        self.assertEqual(
            self.account.protocol.resolve_names(names=["foo\\bar"]),
            [ErrorNameResolutionNoResults("No results were found.")],
        )
        # Test return_full_contact_data
        mailbox, contact = self.account.protocol.resolve_names(
            names=[self.account.primary_smtp_address], return_full_contact_data=True
        )[0]
        self.assertEqual(mailbox, Mailbox(email_address=self.account.primary_smtp_address))
        self.assertListEqual(
            [e.email.replace("SMTP:", "") for e in contact.email_addresses if e.label == "EmailAddress1"],
            [self.account.primary_smtp_address],
        )

    def test_resolvenames_parsing(self):
        # Test static XML since server has no roomlists
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
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
</s:Envelope>"""
        ws = ResolveNames(self.account.protocol)
        ws.return_full_contact_data = False
        self.assertSetEqual({m.email_address for m in ws.parse(xml)}, {"anne@example.com", "john@example.com"})

    def test_resolvenames_warning(self):
        # Test warning that the returned candidate list is non-exchaustive
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <m:ResolveNamesResponse
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
      <m:ResponseMessages>
        <m:ResolveNamesResponseMessage ResponseClass="Warning">
          <m:MessageText>Multiple results were found.</m:MessageText>
          <m:ResponseCode>ErrorNameResolutionMultipleResults</m:ResponseCode>
          <m:DescriptiveLinkKey>0</m:DescriptiveLinkKey>
          <m:ResolutionSet TotalItemsInView="2" IncludesLastItemInRange="false">
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
</s:Envelope>"""
        ws = ResolveNames(self.account.protocol)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            list(ws.parse(xml))
        self.assertEqual(
            str(w[0].message),
            "The ResolveNames service returns at most 100 candidates and does not support paging. You have reached "
            "this limit and have not received the exhaustive list of candidates.",
        )

    def test_get_searchable_mailboxes(self):
        # Insufficient privileges for the test account, so let's just test the exception
        with self.assertRaises(ErrorAccessDenied):
            self.account.protocol.get_searchable_mailboxes(search_filter="non_existent_distro@example.com")
        with self.assertRaises(ErrorAccessDenied):
            self.account.protocol.get_searchable_mailboxes(expand_group_membership=True)
        guid = "33a408fe-2574-4e3b-49f5-5e1e000a3035"
        email = "LOLgroup@example.com"
        display_name = "LOLgroup"
        reference_id = "/o=First/ou=Exchange(FYLT)/cn=Recipients/cn=81213b958a0b5295b13b3f02b812bf1bc-LOLgroup"
        xml = f"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
   <s:Body xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
           xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
      <m:GetSearchableMailboxesResponse ResponseClass="Success">
         <m:ResponseCode>NoError</m:ResponseCode>
         <m:SearchableMailboxes>
            <t:SearchableMailbox>
               <t:Guid>{guid}</t:Guid>
               <t:PrimarySmtpAddress>{email}</t:PrimarySmtpAddress>
               <t:IsExternalMailbox>false</t:IsExternalMailbox>
               <t:ExternalEmailAddress/>
               <t:DisplayName>{display_name}</t:DisplayName>
               <t:IsMembershipGroup>true</t:IsMembershipGroup>
               <t:ReferenceId>{reference_id}</t:ReferenceId>
            </t:SearchableMailbox>
            <t:FailedMailbox>
               <t:Mailbox>FAILgroup@example.com</t:Mailbox>
               <t:ErrorCode>123</t:ErrorCode>
               <t:ErrorMessage>Catastrophic Failure</t:ErrorMessage>
               <t:IsArchive>true</t:IsArchive>
            </t:FailedMailbox>
         </m:SearchableMailboxes>
      </m:GetSearchableMailboxesResponse>
   </s:Body>
</s:Envelope>""".encode()
        ws = GetSearchableMailboxes(protocol=self.account.protocol)
        self.assertListEqual(
            list(ws.parse(xml)),
            [
                SearchableMailbox(
                    guid=guid,
                    primary_smtp_address=email,
                    is_external=False,
                    external_email=None,
                    display_name=display_name,
                    is_membership_group=True,
                    reference_id=reference_id,
                ),
                FailedMailbox(
                    mailbox="FAILgroup@example.com",
                    error_code=123,
                    error_message="Catastrophic Failure",
                    is_archive=True,
                ),
            ],
        )

    def test_expanddl(self):
        with self.assertRaises(ErrorNameResolutionNoResults):
            self.account.protocol.expand_dl("non_existent_distro@example.com")
        with self.assertRaises(ErrorNameResolutionNoResults):
            self.account.protocol.expand_dl(
                DLMailbox(email_address="non_existent_distro@example.com", mailbox_type="PublicDL")
            )
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <m:ExpandDLResponse ResponseClass="Success"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
      <m:ResponseMessages>
        <m:ExpandDLResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:DLExpansion TotalItemsInView="3" IncludesLastItemInRange="true">
            <t:Mailbox>
              <t:Name>Foo Smith</t:Name>
              <t:EmailAddress>foo@example.com</t:EmailAddress>
              <t:RoutingType>SMTP</t:RoutingType>
              <t:MailboxType>Mailbox</t:MailboxType>
            </t:Mailbox>
            <t:Mailbox>
              <t:Name>Bar Smith</t:Name>
              <t:EmailAddress>bar@example.com</t:EmailAddress>
              <t:RoutingType>SMTP</t:RoutingType>
              <t:MailboxType>Mailbox</t:MailboxType>
            </t:Mailbox>
          </m:DLExpansion>
        </m:ExpandDLResponseMessage>
      </m:ResponseMessages>
    </ExpandDLResponse>
  </soap:Body>
</soap:Envelope>"""
        self.assertListEqual(
            list(ExpandDL(protocol=self.account.protocol).parse(xml)),
            [
                Mailbox(name="Foo Smith", email_address="foo@example.com"),
                Mailbox(name="Bar Smith", email_address="bar@example.com"),
            ],
        )

    def test_oof_settings(self):
        # First, ensure a common starting point
        utc = zoneinfo.ZoneInfo("UTC")
        self.account.oof_settings = OofSettings(
            state=OofSettings.DISABLED,
            start=datetime.datetime.combine(RANDOM_DATE_MIN, datetime.time.min, tzinfo=utc),
            end=datetime.datetime.combine(RANDOM_DATE_MAX, datetime.time.max, tzinfo=utc),
        )

        oof = OofSettings(
            state=OofSettings.ENABLED,
            external_audience="None",
            internal_reply="I'm on holidays. See ya guys!",
            external_reply="Dear Sir, your email has now been deleted.",
        )
        self.account.oof_settings = oof
        self.assertEqual(self.account.oof_settings, oof)

        oof = OofSettings(
            state=OofSettings.ENABLED,
            external_audience="Known",
            internal_reply="XXX",
            external_reply="YYY",
        )
        self.account.oof_settings = oof
        self.assertEqual(self.account.oof_settings, oof)

        # Scheduled duration must not be in the past
        tz = self.account.default_timezone
        start, end = get_random_datetime_range(start_date=datetime.datetime.now(tz).date())
        oof = OofSettings(
            state=OofSettings.SCHEDULED,
            external_audience="Known",
            internal_reply="I'm in the pub. See ya guys!",
            external_reply="I'm having a business dinner in town",
            start=start,
            end=end,
        )
        self.account.oof_settings = oof
        self.assertEqual(self.account.oof_settings, oof)

        oof = OofSettings(
            state=OofSettings.DISABLED,
            start=start,
            end=end,
        )
        with self.assertRaises(TypeError):
            self.account.oof_settings = "XXX"
        with self.assertRaises(TypeError):
            SetUserOofSettings(account=self.account).get(
                oof_settings=oof,
                mailbox="XXX",
            )
        self.account.oof_settings = oof
        # TODO: For some reason, disabling OOF does not always work. Don't assert because we want a stable test suite
        if self.account.oof_settings != oof:
            self.skipTest("Disabling OOF did not work")

    def test_oof_settings_validation(self):
        utc = zoneinfo.ZoneInfo("UTC")
        with self.assertRaises(ValueError):
            # Needs a start and end
            OofSettings(
                state=OofSettings.SCHEDULED,
            ).clean(version=None)
        with self.assertRaises(ValueError):
            # Start must be before end
            OofSettings(
                state=OofSettings.SCHEDULED,
                start=datetime.datetime(2100, 12, 1, tzinfo=utc),
                end=datetime.datetime(2100, 11, 1, tzinfo=utc),
            ).clean(version=None)
        with self.assertRaises(ValueError):
            # End must be in the future
            OofSettings(
                state=OofSettings.SCHEDULED,
                start=datetime.datetime(2000, 11, 1, tzinfo=utc),
                end=datetime.datetime(2000, 12, 1, tzinfo=utc),
            ).clean(version=None)
        with self.assertRaises(ValueError):
            # Must have an internal and external reply
            OofSettings(
                state=OofSettings.SCHEDULED,
                start=datetime.datetime(2100, 11, 1, tzinfo=utc),
                end=datetime.datetime(2100, 12, 1, tzinfo=utc),
            ).clean(version=None)

    def test_convert_id(self):
        i = self.account.root.id
        for fmt in ID_FORMATS:
            res = list(
                self.account.protocol.convert_ids(
                    [AlternateId(id=i, format=EWS_ID, mailbox=self.account.primary_smtp_address)],
                    destination_format=fmt,
                )
            )
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0].format, fmt)
        # Test bad format
        with self.assertRaises(ValueError) as e:
            self.account.protocol.convert_ids(
                [AlternateId(id=i, format=EWS_ID, mailbox=self.account.primary_smtp_address)], destination_format="XXX"
            )
        self.assertEqual(e.exception.args[0], f"'destination_format' 'XXX' must be one of {sorted(ID_FORMATS)}")
        # Test bad item type
        with self.assertRaises(TypeError) as e:
            list(self.account.protocol.convert_ids([ItemId(id=1)], destination_format="EwsId"))
        self.assertIn("must be of type", e.exception.args[0])

    def test_sessionpool(self):
        # First, empty the calendar
        start = datetime.datetime(2011, 10, 12, 8, tzinfo=self.account.default_timezone)
        end = datetime.datetime(2011, 10, 12, 10, tzinfo=self.account.default_timezone)
        self.account.calendar.filter(start__lt=end, end__gt=start, categories__contains=self.categories).delete()
        items = []
        for i in range(75):
            subject = f"Test Subject {i}"
            item = CalendarItem(
                start=start,
                end=end,
                subject=subject,
                categories=self.categories,
            )
            items.append(item)
        return_ids = self.account.calendar.bulk_create(items=items)
        self.assertEqual(len(return_ids), len(items))
        ids = self.account.calendar.filter(
            start__lt=end, end__gt=start, categories__contains=self.categories
        ).values_list("id", "changekey")
        self.assertEqual(ids.count(), len(items))

    def test_disable_ssl_verification(self):
        if isinstance(self.account.protocol.credentials, OAuth2Credentials):
            self.skipTest("OAuth authentication ony works with SSL verification enabled")

        # Test that we can make requests when SSL verification is turned off. I don't know how to mock TLS responses
        if not self.verify_ssl:
            # We can only run this test if we haven't already disabled TLS
            self.skipTest("TLS verification already disabled")

        default_adapter_cls = BaseProtocol.HTTP_ADAPTER_CLS

        # Just test that we can query
        self.account.root.all().exists()

        # Smash TLS verification using an untrusted certificate
        with tempfile.NamedTemporaryFile() as f:
            f.write(
                b"""\
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
-----END CERTIFICATE-----"""
            )
            try:
                os.environ["REQUESTS_CA_BUNDLE"] = f.name
                # Setting the credentials is just an easy way of resetting the session pool. This will let requests
                # pick up the new environment variable. Now the request should fail
                self.account.protocol.credentials = self.account.protocol.credentials
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    # Ignore ResourceWarning for unclosed socket. It does get closed.
                    with self.assertRaises(TransportError) as e:
                        self.account.root.all().exists()
                    self.assertIn("SSLError", e.exception.args[0])

                # Disable insecure TLS warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    # Make sure we can handle TLS validation errors when using the custom adapter
                    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
                    self.account.protocol.credentials = self.account.protocol.credentials
                    self.account.root.all().exists()

                    # Test that the custom adapter also works when validation is OK again
                    del os.environ["REQUESTS_CA_BUNDLE"]
                    self.account.protocol.credentials = self.account.protocol.credentials
                    self.account.root.all().exists()
            finally:
                # Reset environment and connections
                os.environ.pop("REQUESTS_CA_BUNDLE", None)  # May already have been deleted
                BaseProtocol.HTTP_ADAPTER_CLS = default_adapter_cls
                self.account.protocol.credentials = self.account.protocol.credentials

    def test_del_on_error(self):
        # Test that __del__ can handle exceptions on close()
        tmp = Protocol.close
        protocol = self.get_test_protocol()
        Protocol.close = Mock(side_effect=Exception("XXX"))
        with self.assertRaises(Exception):
            protocol.close()
        del protocol
        Protocol.close = tmp

    @requests_mock.mock()
    def test_version_guess(self, m):
        protocol = self.get_test_protocol()
        # Test that we can get the version even on error responses
        m.post(
            protocol.service_endpoint,
            status_code=200,
            content=b"""\
<?xml version='1.0' encoding='utf-8'?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Header>
    <h:ServerVersionInfo xmlns:h="http://schemas.microsoft.com/exchange/services/2006/types"
    MajorVersion="15" MinorVersion="1" MajorBuildNumber="2345" MinorBuildNumber="6789" Version="V2017_07_11"/>
  </s:Header>
  <s:Body>
    <m:ResolveNamesResponse
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
      <m:ResponseMessages>
        <m:ResolveNamesResponseMessage ResponseClass="Error">
          <m:MessageText>Multiple results were found.</m:MessageText>
          <m:ResponseCode>ErrorNameResolutionMultipleResults</m:ResponseCode>
          <m:DescriptiveLinkKey>0</m:DescriptiveLinkKey>
        </m:ResolveNamesResponseMessage>
      </m:ResponseMessages>
    </m:ResolveNamesResponse>
  </s:Body>
</s:Envelope>""",
        )
        Version.guess(protocol)
        self.assertEqual(protocol.version.build, Build(15, 1, 2345, 6789))

        # Test exception when there are no version headers
        m.post(
            protocol.service_endpoint,
            status_code=200,
            content=b"""\
<?xml version='1.0' encoding='utf-8'?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Header>
  </s:Header>
  <s:Body>
    <m:ResolveNamesResponse
    xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
    xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
      <m:ResponseMessages>
        <m:ResolveNamesResponseMessage ResponseClass="Error">
          <m:MessageText>.</m:MessageText>
          <m:ResponseCode>ErrorNameResolutionMultipleResults</m:ResponseCode>
          <m:DescriptiveLinkKey>0</m:DescriptiveLinkKey>
        </m:ResolveNamesResponseMessage>
      </m:ResponseMessages>
    </m:ResolveNamesResponse>
  </s:Body>
</s:Envelope>""",
        )
        with self.assertRaises(TransportError) as e:
            Version.guess(protocol)
        self.assertEqual(
            e.exception.args[0], "No valid version headers found in response (ErrorNameResolutionMultipleResults('.'))"
        )

    @patch("requests.sessions.Session.post", side_effect=ConnectionResetError("XXX"))
    def test_get_service_authtype(self, m):
        with self.assertRaises(TransportError) as e:
            _ = self.get_test_protocol(auth_type=None).auth_type
        self.assertEqual(e.exception.args[0], "XXX")

        with self.assertRaises(RateLimitError) as e:
            _ = self.get_test_protocol(auth_type=None, retry_policy=FaultTolerance(max_wait=0.5)).auth_type
        self.assertEqual(e.exception.args[0], "Max timeout reached")

    @patch("requests.sessions.Session.post", return_value=DummyResponse(status_code=401))
    def test_get_service_authtype_401(self, m):
        with self.assertRaises(TransportError) as e:
            _ = self.get_test_protocol(auth_type=None).auth_type
        self.assertEqual(e.exception.args[0], "Failed to get auth type from service")

    @patch("requests.sessions.Session.post", return_value=DummyResponse(status_code=501))
    def test_get_service_authtype_501(self, m):
        with self.assertRaises(TransportError) as e:
            _ = self.get_test_protocol(auth_type=None).auth_type
        self.assertEqual(e.exception.args[0], "Failed to get auth type from service")

    def test_create_session_failure(self):
        protocol = self.get_test_protocol(auth_type=NOAUTH, credentials=None)
        with self.assertRaises(ValueError) as e:
            protocol.config.auth_type = NTLM
            protocol.credentials = None
            protocol.create_session()
        self.assertEqual(e.exception.args[0], "Auth type 'NTLM' requires credentials")

    def test_noauth_session(self):
        self.assertEqual(self.get_test_protocol(auth_type=NOAUTH, credentials=None).create_session().auth, None)

    def test_oauth2_session(self):
        # Only test failure cases until we have working OAuth2 credentials
        with self.assertRaises(InvalidClientIdError):
            self.get_test_protocol(
                auth_type=OAUTH2, credentials=OAuth2Credentials("XXX", "YYY", "ZZZZ")
            ).create_session()

        protocol = self.get_test_protocol(
            auth_type=OAUTH2,
            credentials=OAuth2AuthorizationCodeCredentials(
                client_id="WWW", client_secret="XXX", authorization_code="YYY", access_token={"access_token": "ZZZ"}
            ),
        )
        session = protocol.create_session()
        protocol.refresh_credentials(session)
