import pickle
from collections import namedtuple
from unittest.mock import patch

from exchangelib.account import Account
from exchangelib.attachments import FileAttachment
from exchangelib.configuration import Configuration
from exchangelib.credentials import DELEGATE, Credentials
from exchangelib.errors import (
    ErrorAccessDenied,
    ErrorDelegateNoUser,
    ErrorFolderNotFound,
    ErrorInvalidUserSid,
    ErrorNotDelegate,
    UnauthorizedError,
    UnknownTimeZone,
)
from exchangelib.ewsdatetime import UTC
from exchangelib.folders import Calendar
from exchangelib.items import Message
from exchangelib.properties import (
    Actions,
    Conditions,
    DelegatePermissions,
    DelegateUser,
    Exceptions,
    MailTips,
    OutOfOffice,
    RecipientAddress,
    Rule,
    SendingAs,
    UserId,
)
from exchangelib.protocol import FaultTolerance, Protocol
from exchangelib.services import GetDelegate, GetMailTips
from exchangelib.version import EXCHANGE_2007_SP1, Version

from .common import EWSTest, get_random_string


class AccountTest(EWSTest):
    """Test features of the Account object."""

    def test_magic(self):
        self.account.fullname = "John Doe"
        self.assertIn(self.account.primary_smtp_address, str(self.account))
        self.assertIn(self.account.fullname, str(self.account))

    def test_validation(self):
        with self.assertRaises(ValueError) as e:
            # Must have valid email address
            Account(primary_smtp_address="blah")
        self.assertEqual(str(e.exception), "primary_smtp_address 'blah' is not an email address")
        with self.assertRaises(AttributeError) as e:
            # Non-autodiscover requires a config
            Account(primary_smtp_address="blah@example.com", autodiscover=False)
        self.assertEqual(str(e.exception), "non-autodiscover requires a config")
        with self.assertRaises(ValueError) as e:
            Account(primary_smtp_address="blah@example.com", access_type=123)
        self.assertEqual(str(e.exception), "'access_type' 123 must be one of ['delegate', 'impersonation']")
        with self.assertRaises(TypeError) as e:
            # locale must be a string
            Account(primary_smtp_address="blah@example.com", locale=123)
        self.assertEqual(str(e.exception), "'locale' 123 must be of type <class 'str'>")
        with self.assertRaises(TypeError) as e:
            # default timezone must be an EWSTimeZone
            Account(primary_smtp_address="blah@example.com", default_timezone=123)
        self.assertEqual(
            str(e.exception), "'default_timezone' 123 must be of type <class 'exchangelib.ewsdatetime.EWSTimeZone'>"
        )
        with self.assertRaises(TypeError) as e:
            # config must be a Configuration
            Account(primary_smtp_address="blah@example.com", config=123)
        self.assertEqual(
            str(e.exception), "'config' 123 must be of type <class 'exchangelib.configuration.Configuration'>"
        )

    @patch("locale.getlocale", side_effect=ValueError())
    def test_getlocale_failure(self, m):
        a = Account(
            primary_smtp_address=self.account.primary_smtp_address,
            access_type=DELEGATE,
            config=Configuration(
                service_endpoint=self.account.protocol.service_endpoint,
                credentials=Credentials("john@example.com", "WRONG_PASSWORD"),
                version=self.account.version,
                retry_policy=self.retry_policy,
            ),
            autodiscover=False,
        )
        self.assertEqual(a.locale, None)

    @patch("tzlocal.get_localzone", side_effect=UnknownTimeZone(""))
    def test_tzlocal_failure(self, m):
        a = Account(
            primary_smtp_address=self.account.primary_smtp_address,
            access_type=DELEGATE,
            config=Configuration(
                service_endpoint=self.account.protocol.service_endpoint,
                credentials=Credentials("john@example.com", "WRONG_PASSWORD"),
                version=self.account.version,
                retry_policy=self.retry_policy,
            ),
            autodiscover=False,
        )
        self.assertEqual(a.default_timezone, UTC)

    def test_get_default_folder(self):
        # Test a normal folder lookup with GetFolder
        folder = self.account.root.get_default_folder(Calendar)
        self.assertIsInstance(folder, Calendar)
        self.assertNotEqual(folder.id, None)
        self.assertEqual(folder.to_id().id, Calendar.DISTINGUISHED_FOLDER_ID)
        self.assertEqual(folder.name.lower(), Calendar.localized_names(self.account.locale)[0])

        class MockCalendar1(Calendar):
            @classmethod
            def get_distinguished(cls, root):
                raise ErrorAccessDenied("foo")

        # Test an indirect folder lookup with FindItem, when we're not allowed to do a GetFolder. We don't get the
        # folder element back from the server, just test for existence indirectly be asking for items in the folder.
        # Therefore, we don't expect ID or name values.
        folder = self.account.root.get_default_folder(MockCalendar1)
        self.assertIsInstance(folder, MockCalendar1)
        self.assertEqual(folder.id, None)
        self.assertEqual(folder.to_id().id, Calendar.DISTINGUISHED_FOLDER_ID)
        self.assertEqual(folder.name, None)

        class MockCalendar2(Calendar):
            @classmethod
            def get_distinguished(cls, root):
                raise ErrorFolderNotFound("foo")

        # Test using the one folder of this folder type
        with self.assertRaises(ErrorFolderNotFound):
            # This fails because there are no folders of type MockCalendar
            self.account.root.get_default_folder(MockCalendar2)

        _orig = Calendar.get_distinguished
        try:
            Calendar.get_distinguished = MockCalendar2.get_distinguished
            folder = self.account.root.get_default_folder(Calendar)
            self.assertIsInstance(folder, Calendar)
            self.assertNotEqual(folder.id, None)
            self.assertEqual(folder.name.lower(), MockCalendar2.localized_names(self.account.locale)[0])
        finally:
            Calendar.get_distinguished = _orig

    def test_pickle(self):
        # Test that we can pickle various objects
        item = Message(folder=self.account.inbox, subject="XXX", categories=self.categories).save()
        attachment = FileAttachment(name="pickle_me.txt", content=b"")
        for o in (
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
        self.assertEqual(self.account.mail_tips.recipient_address.email_address, self.account.primary_smtp_address)
        # recipients must not be empty
        list(
            GetMailTips(protocol=self.account.protocol).call(
                sending_as=SendingAs(email_address=self.account.primary_smtp_address),
                recipients=[],
                mail_tips_requested="All",
            )
        )
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body>
        <m:GetMailTipsResponse ResponseClass="Success"
                   xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
                   xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
            <m:ResponseCode>NoError</m:ResponseCode>
            <m:ResponseMessages>
                <m:MailTipsResponseMessageType ResponseClass="Success">
                    <m:ResponseCode>NoError</m:ResponseCode>
                    <m:MailTips>
                        <t:RecipientAddress>
                            <t:EmailAddress>user2@contoso.com</t:EmailAddress>
                            <t:RoutingType>SMTP</t:RoutingType>
                        </t:RecipientAddress>
                        <t:OutOfOffice>
                            <t:ReplyBody>
                                <t:Message/>
                            </t:ReplyBody>
                        </t:OutOfOffice>
                        <t:CustomMailTip>Hello World Mailtips</t:CustomMailTip>
                    </m:MailTips>
                </m:MailTipsResponseMessageType>
            </m:ResponseMessages>
        </m:GetMailTipsResponse>
    </s:Body>
</s:Envelope>"""
        self.assertEqual(
            list(GetMailTips(protocol=None).parse(xml)),
            [
                MailTips(
                    recipient_address=RecipientAddress(email_address="user2@contoso.com"),
                    out_of_office=OutOfOffice(),
                    custom_mail_tip="Hello World Mailtips",
                )
            ],
        )

    def test_delegate(self):
        # The test server does not have any delegate info. Test that account.delegates works, and mock to test parsing
        # of a non-empty response.
        self.assertGreaterEqual(len(self.account.delegates), 0)
        with self.assertRaises(ErrorInvalidUserSid):
            list(GetDelegate(account=self.account).call(user_ids=[UserId(sid="XXX")], include_permissions=True))
        with self.assertRaises(ErrorDelegateNoUser):
            list(GetDelegate(account=self.account).call(user_ids=["foo@example.com"], include_permissions=True))
        with self.assertRaises(ErrorNotDelegate):
            list(
                GetDelegate(account=self.account).call(
                    user_ids=[self.account.primary_smtp_address], include_permissions=True
                )
            )

        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <m:GetDelegateResponse ResponseClass="Success"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
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
  </s:Body>
</s:Envelope>"""

        MockTZ = namedtuple("EWSTimeZone", ["ms_id"])
        MockAccount = namedtuple("Account", ["access_type", "primary_smtp_address", "default_timezone", "protocol"])
        MockProtocol = namedtuple("Protocol", ["version"])
        p = MockProtocol(version=Version(build=EXCHANGE_2007_SP1))
        a = MockAccount(DELEGATE, "foo@example.com", MockTZ("XXX"), protocol=p)

        ws = GetDelegate(account=a)
        delegates = list(ws.parse(xml))
        self.assertListEqual(
            delegates,
            [
                DelegateUser(
                    user_id=UserId(sid="SOME_SID", primary_smtp_address="foo@example.com", display_name="Foo Bar"),
                    delegate_permissions=DelegatePermissions(
                        calendar_folder_permission_level="Author",
                        inbox_folder_permission_level="Reviewer",
                        contacts_folder_permission_level="None",
                        notes_folder_permission_level="None",
                        journal_folder_permission_level="None",
                        tasks_folder_permission_level="None",
                    ),
                    receive_copies_of_meeting_messages=False,
                    view_private_items=True,
                )
            ],
        )

    def test_login_failure_and_credentials_update(self):
        # Create an account that does not need to create any connections
        account = Account(
            primary_smtp_address=self.account.primary_smtp_address,
            access_type=DELEGATE,
            config=Configuration(
                service_endpoint=self.account.protocol.service_endpoint,
                credentials=Credentials("john@example.com", "WRONG_PASSWORD"),
                version=self.account.version,
                retry_policy=self.retry_policy,
            ),
            autodiscover=False,
            locale="da_DK",
        )

        # Should fail when credentials are wrong, but UnauthorizedError is caught and retried. Mock the needed methods
        class Mock1(FaultTolerance):
            def raise_response_errors(self, response):
                if response.status_code == 401:
                    raise UnauthorizedError(f"Invalid credentials for {response.url}")
                return super().raise_response_errors(response)

        try:
            account.protocol.config.retry_policy = Mock1()
            with self.assertRaises(UnauthorizedError):
                account.root.refresh()
        finally:
            account.protocol.config.retry_policy = self.retry_policy

        # Cannot update from Configuration object
        with self.assertRaises(AttributeError):
            account.protocol.config.credentials = self.account.protocol.credentials
        # Should succeed after credentials update
        account.protocol.config.auth_type = self.account.protocol.config.auth_type
        account.protocol.credentials = self.account.protocol.credentials
        account.root.refresh()

    def test_protocol_default_values(self):
        # Test that retry_policy and auth_type always get a value regardless of how we create an Account. autodiscover
        # args are tested in AutodiscoverTest.
        a = Account(
            self.account.primary_smtp_address,
            autodiscover=False,
            config=Configuration(
                server=self.settings["server"],
                credentials=self.account.protocol.credentials,
            ),
        )
        self.assertIsNotNone(a.protocol.auth_type)
        self.assertIsNotNone(a.protocol.retry_policy)

    def test_inbox_rules(self):
        # Clean up first
        for rule in self.account.rules:
            self.account.delete_rule(rule)

        self.assertEqual(len(self.account.rules), 0)

        # Create rule
        display_name = get_random_string(16)
        rule = Rule(
            display_name=display_name,
            priority=1,
            is_enabled=True,
            conditions=Conditions(contains_sender_strings=[get_random_string(8)]),
            exceptions=Exceptions(),
            actions=Actions(delete=True),
        )
        self.assertIsNone(rule.id)
        self.account.create_rule(rule=rule)
        self.assertIsNotNone(rule.id)
        self.assertEqual(len(self.account.rules), 1)
        self.assertEqual(self.account.rules[0].display_name, display_name)

        # Update rule
        rule.display_name = get_random_string(16)
        self.account.set_rule(rule=rule)
        self.assertEqual(len(self.account.rules), 1)
        self.assertNotEqual(self.account.rules[0].display_name, display_name)

        # Delete rule
        self.account.delete_rule(rule=rule)
        self.assertEqual(len(self.account.rules), 0)
