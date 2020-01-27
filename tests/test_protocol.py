import datetime
import os
import socket
import tempfile
import warnings

import psutil
import requests_mock

from exchangelib import Version, NTLM, FailFast, Credentials, Configuration, OofSettings, EWSTimeZone, EWSDateTime, \
    EWSDate, Mailbox, DLMailbox, UTC, CalendarItem
from exchangelib.errors import SessionPoolMinSizeReached, ErrorNameResolutionNoResults, ErrorAccessDenied, \
    TransportError
from exchangelib.properties import TimeZone, RoomList, FreeBusyView, Room, AlternateId, ID_FORMATS, EWS_ID
from exchangelib.protocol import Protocol, BaseProtocol, NoVerifyHTTPAdapter
from exchangelib.services import GetServerTimeZones, GetRoomLists, GetRooms, ResolveNames
from exchangelib.transport import NOAUTH
from exchangelib.version import Build
from exchangelib.winzone import CLDR_TO_MS_TIMEZONE_MAP

from .common import EWSTest, MockResponse, get_random_datetime_range


class ProtocolTest(EWSTest):

    @requests_mock.mock()
    def test_session(self, m):
        m.get('https://example.com/EWS/types.xsd', status_code=200)
        protocol = Protocol(config=Configuration(
            service_endpoint='https://example.com/Foo.asmx', credentials=Credentials('A', 'B'),
            auth_type=NTLM, version=Version(Build(15, 1)), retry_policy=FailFast()
        ))
        session = protocol.create_session()
        new_session = protocol.renew_session(session)
        self.assertNotEqual(id(session), id(new_session))

    @requests_mock.mock()
    def test_protocol_instance_caching(self, m):
        # Verify that we get the same Protocol instance for the same combination of (endpoint, credentials)
        m.get('https://example.com/EWS/types.xsd', status_code=200)
        base_p = Protocol(config=Configuration(
            service_endpoint='https://example.com/Foo.asmx', credentials=Credentials('A', 'B'),
            auth_type=NTLM, version=Version(Build(15, 1)), retry_policy=FailFast()
        ))

        for i in range(10):
            p = Protocol(config=Configuration(
                service_endpoint='https://example.com/Foo.asmx', credentials=Credentials('A', 'B'),
                auth_type=NTLM, version=Version(Build(15, 1)), retry_policy=FailFast()
            ))
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
        protocol = Protocol(config=Configuration(
            service_endpoint='http://example.com', credentials=Credentials('A', 'B'),
            auth_type=NOAUTH, version=Version(Build(15, 1)), retry_policy=FailFast()
        ))
        session = protocol.get_session()
        session.get('http://example.com')
        self.assertEqual(len({p.raddr[0] for p in proc.connections() if p.raddr[0] in ip_addresses}), 1)
        protocol.release_session(session)
        protocol.close()
        self.assertEqual(len({p.raddr[0] for p in proc.connections() if p.raddr[0] in ip_addresses}), 0)

    def test_poolsize(self):
        self.assertEqual(self.account.protocol.SESSION_POOLSIZE, 4)

    def test_decrease_poolsize(self):
        protocol = Protocol(config=Configuration(
            service_endpoint='https://example.com/Foo.asmx', credentials=Credentials('A', 'B'),
            auth_type=NTLM, version=Version(Build(15, 1)), retry_policy=FailFast()
        ))
        self.assertEqual(protocol._session_pool.qsize(), Protocol.SESSION_POOLSIZE)
        protocol.decrease_poolsize()
        self.assertEqual(protocol._session_pool.qsize(), 3)
        protocol.decrease_poolsize()
        self.assertEqual(protocol._session_pool.qsize(), 2)
        protocol.decrease_poolsize()
        self.assertEqual(protocol._session_pool.qsize(), 1)
        with self.assertRaises(SessionPoolMinSizeReached):
            protocol.decrease_poolsize()
        self.assertEqual(protocol._session_pool.qsize(), 1)

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

        with self.assertRaises(ValueError):
            self.account.protocol.get_free_busy_info(accounts=[('XXX', 'XXX', 'XXX')], start=0, end=0)
        with self.assertRaises(ValueError):
            self.account.protocol.get_free_busy_info(accounts=[(self.account, 'XXX', 'XXX')], start=0, end=0)
        with self.assertRaises(ValueError):
            self.account.protocol.get_free_busy_info(accounts=[(self.account, 'Organizer', 'XXX')], start=0, end=0)
        with self.assertRaises(ValueError):
            self.account.protocol.get_free_busy_info(accounts=accounts, start=end, end=start)
        with self.assertRaises(ValueError):
            self.account.protocol.get_free_busy_info(accounts=accounts, start=start, end=end,
                                                     merged_free_busy_interval='XXX')
        with self.assertRaises(ValueError):
            self.account.protocol.get_free_busy_info(accounts=accounts, start=start, end=end, requested_view='XXX')

        for view_info in self.account.protocol.get_free_busy_info(accounts=accounts, start=start, end=end):
            self.assertIsInstance(view_info, FreeBusyView)
            self.assertIsInstance(view_info.working_hours_timezone, TimeZone)
            ms_id = view_info.working_hours_timezone.to_server_timezone(server_timezones, start.year)
            self.assertIn(ms_id, {t[0] for t in CLDR_TO_MS_TIMEZONE_MAP.values()})

    def test_get_roomlists(self):
        # The test server is not guaranteed to have any room lists which makes this test less useful
        ws = GetRoomLists(self.account.protocol)
        roomlists = ws.call()
        self.assertEqual(list(roomlists), [])
        # Test shortcut
        self.assertEqual(list(self.account.protocol.get_roomlists()), [])

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
        header, body = ws._get_soap_parts(content=MockResponse(xml))
        res = ws._get_elements_in_response(response=ws._get_soap_messages(body=body))
        self.assertSetEqual(
            {RoomList.from_xml(elem=elem, account=None).email_address for elem in res},
            {'roomlist1@example.com', 'roomlist2@example.com'}
        )

    def test_get_rooms(self):
        # The test server is not guaranteed to have any rooms or room lists which makes this test less useful
        roomlist = RoomList(email_address='my.roomlist@example.com')
        ws = GetRooms(self.account.protocol)
        with self.assertRaises(ErrorNameResolutionNoResults):
            list(ws.call(roomlist=roomlist))
        # Test shortcut
        with self.assertRaises(ErrorNameResolutionNoResults):
            list(self.account.protocol.get_rooms('my.roomlist@example.com'))

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
        header, body = ws._get_soap_parts(content=MockResponse(xml))
        res = ws._get_elements_in_response(response=ws._get_soap_messages(body=body))
        self.assertSetEqual(
            {Room.from_xml(elem=elem, account=None).email_address for elem in res},
            {'room1@example.com', 'room2@example.com'}
        )

    def test_resolvenames(self):
        with self.assertRaises(ValueError):
            self.account.protocol.resolve_names(names=[], search_scope='XXX')
        with self.assertRaises(ValueError):
            self.account.protocol.resolve_names(names=[], shape='XXX')
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
        header, body = ws._get_soap_parts(content=MockResponse(xml))
        res = ws._get_elements_in_response(response=ws._get_soap_messages(body=body))
        self.assertSetEqual(
            {Mailbox.from_xml(elem=elem.find(Mailbox.response_tag()), account=None).email_address for elem in res},
            {'anne@example.com', 'john@example.com'}
        )

    def test_get_searchable_mailboxes(self):
        # Insufficient privileges for the test account, so let's just test the exception
        with self.assertRaises(ErrorAccessDenied):
            self.account.protocol.get_searchable_mailboxes('non_existent_distro@example.com')

    def test_expanddl(self):
        with self.assertRaises(ErrorNameResolutionNoResults):
            self.account.protocol.expand_dl('non_existent_distro@example.com')
        with self.assertRaises(ErrorNameResolutionNoResults):
            self.account.protocol.expand_dl(
                DLMailbox(email_address='non_existent_distro@example.com', mailbox_type='PublicDL')
            )

    def test_oof_settings(self):
        # First, ensure a common starting point
        self.account.oof_settings = OofSettings(state=OofSettings.DISABLED)

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

    def test_convert_id(self):
        i = 'AAMkADQyYzZmYmUxLTJiYjItNDg2Ny1iMzNjLTIzYWE1NDgxNmZhNABGAAAAAADUebQDarW2Q7G2Ji8hKofPBwAl9iKCsfCfSa9cmjh' \
            '+JCrCAAPJcuhjAAB0l+JSKvzBRYP+FXGewReXAABj6DrMAAA='
        for fmt in ID_FORMATS:
            res = list(self.account.protocol.convert_ids(
                    [AlternateId(id=i, format=EWS_ID, mailbox=self.account.primary_smtp_address)],
                    destination_format=fmt))
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0].format, fmt)

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

    def test_disable_ssl_verification(self):
        # Test that we can make requests when SSL verification is turned off. I don't know how to mock TLS responses
        if not self.verify_ssl:
            # We can only run this test if we haven't already disabled TLS
            raise self.skipTest('TLS verification already disabled')

        default_adapter_cls = BaseProtocol.HTTP_ADAPTER_CLS

        # Just test that we can query
        self.account.root.all().exists()

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

                # Setting the credentials is just an easy way of resetting the session pool. This will let requests
                # pick up the new environment variable. Now the request should fail
                self.account.protocol.credentials = self.account.protocol.credentials
                with self.assertRaises(TransportError):
                    self.account.root.all().exists()

                # Disable insecure TLS warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    # Make sure we can handle TLS validation errors when using the custom adapter
                    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
                    self.account.protocol.credentials = self.account.protocol.credentials
                    self.account.root.all().exists()

                    # Test that the custom adapter also works when validation is OK again
                    del os.environ['REQUESTS_CA_BUNDLE']
                    self.account.protocol.credentials = self.account.protocol.credentials
                    self.account.root.all().exists()
            finally:
                # Reset environment
                os.environ.pop('REQUESTS_CA_BUNDLE', None)  # May already have been deleted
                BaseProtocol.HTTP_ADAPTER_CLS = default_adapter_cls
