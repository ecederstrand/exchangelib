from collections import namedtuple
import pickle

from exchangelib import Account, Credentials, FaultTolerance, Message, FileAttachment, DELEGATE, Configuration
from exchangelib.errors import ErrorAccessDenied, ErrorFolderNotFound, UnauthorizedError
from exchangelib.folders import Calendar
from exchangelib.properties import DelegateUser, UserId, DelegatePermissions
from exchangelib.protocol import Protocol
from exchangelib.services import GetDelegate

from .common import EWSTest, MockResponse


class AccountTest(EWSTest):
    def test_magic(self):
        self.account.fullname = 'John Doe'
        self.assertIn(self.account.primary_smtp_address, str(self.account))
        self.assertIn(self.account.fullname, str(self.account))

    def test_validation(self):
        with self.assertRaises(ValueError) as e:
            # Must have valid email address
            Account(primary_smtp_address='blah')
        self.assertEqual(str(e.exception), "primary_smtp_address 'blah' is not an email address")
        with self.assertRaises(AttributeError) as e:
            # Non-autodiscover requires a config
            Account(primary_smtp_address='blah@example.com', autodiscover=False)
        self.assertEqual(str(e.exception), 'non-autodiscover requires a config')
        with self.assertRaises(ValueError) as e:
            # access type must be one of ACCESS_TYPES
            Account(primary_smtp_address='blah@example.com', access_type=123)
        self.assertEqual(str(e.exception), "'access_type' 123 must be one of ('impersonation', 'delegate')")
        with self.assertRaises(ValueError) as e:
            # locale must be a string
            Account(primary_smtp_address='blah@example.com', locale=123)
        self.assertEqual(str(e.exception), "Expected 'locale' to be a string, got 123")
        with self.assertRaises(ValueError) as e:
            # default timezone must be an EWSTimeZone
            Account(primary_smtp_address='blah@example.com', default_timezone=123)
        self.assertEqual(str(e.exception), "Expected 'default_timezone' to be an EWSTimeZone, got 123")
        with self.assertRaises(ValueError) as e:
            # config must be a Configuration
            Account(primary_smtp_address='blah@example.com', config=123)
        self.assertEqual(str(e.exception), "Expected 'config' to be a Configuration, got 123")

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
        attachment = FileAttachment(name='pickle_me.txt', content=b'')
        for o in (
            Credentials('XXX', 'YYY'),
            FaultTolerance(max_wait=3600),
            self.account.protocol,
            attachment,
            self.account.root,
            self.account.inbox,
            self.account,
            item,
        ):
            with self.subTest(o=o):
                pickled_o = pickle.dumps(o)
                unpickled_o = pickle.loads(pickled_o)
                self.assertIsInstance(unpickled_o, type(o))
                if not isinstance(o, (Account, Protocol, FaultTolerance)):
                    # __eq__ is not defined on some classes
                    self.assertEqual(o, unpickled_o)

    def test_mail_tips(self):
        # Test that mail tips work
        self.assertEqual(self.account.mail_tips.recipient_address, self.account.primary_smtp_address)

    def test_delegate(self):
        # The test server does not have any delegate info. Mock instead.
        xml = b'''<?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:xsd="http://www.w3.org/2001/XMLSchema">
          <soap:Header>
            <t:ServerVersionInfo MajorBuildNumber="845" MajorVersion="15" MinorBuildNumber="22" MinorVersion="1"
                                 Version="V2016_10_10"
                                 xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types" />
          </soap:Header>
          <soap:Body>
            <m:GetDelegateResponse xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
                                   ResponseClass="Success"
                                   xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
              <m:ResponseCode>NoError</m:ResponseCode>
              <m:ResponseMessages>
                <m:DelegateUserResponseMessageType ResponseClass="Success">
                  <m:ResponseCode>NoError</m:ResponseCode>
                  <m:DelegateUser>
                      <t:UserId>
                        <t:SID>SOME_SID</t:SID>
                        <t:PrimarySmtpAddress>foo@example.com</t:PrimarySmtpAddress>
                        <t:DisplayName>Foo Bar</t:DisplayName>
                      </t:UserId>
                      <t:DelegatePermissions>
                        <t:CalendarFolderPermissionLevel>Author</t:CalendarFolderPermissionLevel>
                        <t:InboxFolderPermissionLevel>Reviewer</t:ContactsFolderPermissionLevel>
                      </t:DelegatePermissions>
                      <t:ReceiveCopiesOfMeetingMessages>false</t:ReceiveCopiesOfMeetingMessages>
                    <t:ViewPrivateItems>true</t:ViewPrivateItems>
                    </m:DelegateUser>
                  </m:DelegateUserResponseMessageType>
              </m:ResponseMessages>
              <m:DeliverMeetingRequests>DelegatesAndMe</m:DeliverMeetingRequests>
              </m:GetDelegateResponse>
          </soap:Body>
        </soap:Envelope>'''

        MockTZ = namedtuple('EWSTimeZone', ['ms_id'])
        MockAccount = namedtuple('Account', ['access_type', 'primary_smtp_address', 'default_timezone', 'protocol'])
        a = MockAccount(DELEGATE, 'foo@example.com', MockTZ('XXX'), protocol='foo')

        ws = GetDelegate(account=a)
        header, body = ws._get_soap_parts(content=MockResponse(xml))
        res = ws._get_elements_in_response(response=ws._get_soap_messages(body=body))
        delegates = [DelegateUser.from_xml(elem=elem, account=a) for elem in res]
        self.assertListEqual(
            delegates,
            [
                DelegateUser(
                    user_id=UserId(sid='SOME_SID', primary_smtp_address='foo@example.com', display_name='Foo Bar'),
                    delegate_permissions=DelegatePermissions(
                        calendar_folder_permission_level='Author',
                        inbox_folder_permission_level='Reviewer',
                        contacts_folder_permission_level='None',
                        notes_folder_permission_level='None',
                        journal_folder_permission_level='None',
                        tasks_folder_permission_level='None',
                    ),
                    receive_copies_of_meeting_messages=False,
                    view_private_items=True,
                )
            ]
        )

    def test_login_failure_and_credentials_update(self):
        # Create an account that does not need to create any connections
        account = Account(
            primary_smtp_address=self.account.primary_smtp_address,
            access_type=DELEGATE,
            config=Configuration(
                service_endpoint=self.account.protocol.service_endpoint,
                credentials=Credentials(self.account.protocol.credentials.username, 'WRONG_PASSWORD'),
                version=self.account.version,
                auth_type=self.account.protocol.auth_type,
                retry_policy=self.retry_policy,
            ),
            autodiscover=False,
            locale='da_DK',
        )
        # Should fail when credentials are wrong, but UnauthorizedError is caught and retried. Mock the needed methods
        import exchangelib.util

        _orig1 = exchangelib.util._may_retry_on_error
        _orig2 = exchangelib.util._raise_response_errors

        def _mock1(response, retry_policy, wait):
            if response.status_code == 401:
                return False
            return _orig1(response, retry_policy, wait)

        def _mock2(response, protocol, log_msg, log_vals):
            if response.status_code == 401:
                raise UnauthorizedError('Wrong username or password for %s' % response.url)
            return _orig2(response, protocol, log_msg, log_vals)

        exchangelib.util._may_retry_on_error = _mock1
        exchangelib.util._raise_response_errors = _mock2
        try:
            with self.assertRaises(UnauthorizedError):
                account.root.refresh()
        finally:
            exchangelib.util._may_retry_on_error = _orig1
            exchangelib.util._raise_response_errors = _orig2

        # Cannot update from Configuration object
        with self.assertRaises(AttributeError):
            account.protocol.config.credentials = self.account.protocol.credentials
        # Should succeed after credentials update
        account.protocol.credentials = self.account.protocol.credentials
        account.root.refresh()
