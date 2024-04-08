import abc
import datetime
import random
import string
import time
import unittest
import unittest.util
from collections import namedtuple
from decimal import Decimal
from pathlib import Path

from yaml import safe_load

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from exchangelib.account import Account, Identity
from exchangelib.attachments import FileAttachment
from exchangelib.configuration import Configuration
from exchangelib.credentials import DELEGATE, IMPERSONATION, Credentials, OAuth2Credentials
from exchangelib.errors import UnknownTimeZone
from exchangelib.ewsdatetime import EWSTimeZone
from exchangelib.fields import (
    AttachmentField,
    AttendeesField,
    Base64Field,
    BodyField,
    BooleanField,
    CharField,
    CharListField,
    ChoiceField,
    CultureField,
    DateField,
    DateTimeBackedDateField,
    DateTimeField,
    DecimalField,
    EmailAddressesField,
    EmailAddressField,
    EWSElementField,
    ExtendedPropertyField,
    IntegerField,
    MailboxField,
    MailboxListField,
    MimeContentField,
    PermissionSetField,
    PhoneNumberField,
    PhysicalAddressField,
    TextField,
    TextListField,
    TimeZoneField,
    URIField,
)
from exchangelib.indexed_properties import EmailAddress, PhoneNumber, PhysicalAddress
from exchangelib.properties import (
    Attendee,
    CompleteName,
    Mailbox,
    Permission,
    PermissionSet,
    ReminderMessageData,
    UserId,
)
from exchangelib.protocol import BaseProtocol, FaultTolerance, NoVerifyHTTPAdapter
from exchangelib.recurrence import DailyPattern, DailyRegeneration, Recurrence, TaskRecurrence
from exchangelib.util import DummyResponse

mock_account = namedtuple("mock_account", ("protocol", "version"))
mock_protocol = namedtuple("mock_protocol", ("version", "service_endpoint"))
mock_version = namedtuple("mock_version", ("build",))


def get_settings():
    return safe_load((Path(__file__).parent.parent / "settings.yml").read_text())


def mock_post(url, status_code, headers, text=""):
    return lambda **kwargs: DummyResponse(
        url=url, headers=headers, request_headers={}, content=text.encode("utf-8"), status_code=status_code
    )


def mock_session_exception(exc_cls):
    def raise_exc(**kwargs):
        raise exc_cls()

    return raise_exc


class TimedTestCase(unittest.TestCase, metaclass=abc.ABCMeta):
    SLOW_TEST_DURATION = 5  # Log tests that are slower than this value (in seconds)

    def setUp(self):
        self.maxDiff = None
        self.t1 = time.monotonic()

    def tearDown(self):
        t2 = time.monotonic() - self.t1
        if t2 > self.SLOW_TEST_DURATION:
            print(f"{t2:07.3f} : {self.id()}")


class EWSTest(TimedTestCase, metaclass=abc.ABCMeta):
    @classmethod
    def setUpClass(cls):
        # There's no official Exchange server we can test against, and we can't really provide credentials for our
        # own test server to everyone on the Internet. GitHub Actions use the encrypted settings.yml.ghenc for testing.
        #
        # If you want to test against your own server and account, create your own settings.yml with credentials for
        # that server. 'settings.yml.sample' is provided as a template.
        try:
            cls.settings = get_settings()
        except FileNotFoundError:
            print(f"Skipping {cls.__name__} - no settings.yml file found")
            print("Copy settings.yml.sample to settings.yml and enter values for your test server")
            raise unittest.SkipTest(f"Skipping {cls.__name__} - no settings.yml file found")

        cls.verify_ssl = cls.settings.get("verify_ssl", True)
        if not cls.verify_ssl:
            # Allow unverified TLS if requested in settings file
            BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter

        # Create an account shared by all tests
        cls.tz = zoneinfo.ZoneInfo("Europe/Copenhagen")
        cls.retry_policy = FaultTolerance(max_wait=600)
        cls.config = Configuration(
            server=cls.settings["server"],
            credentials=cls.credentials(),
            retry_policy=cls.retry_policy,
        )
        cls.account = cls.get_account()

    @classmethod
    def credentials(cls):
        if cls.settings.get("client_id"):
            return OAuth2Credentials(
                client_id=cls.settings["client_id"],
                client_secret=cls.settings["client_secret"],
                tenant_id=cls.settings["tenant_id"],
                identity=Identity(primary_smtp_address=cls.settings["account"]),
            )
        return Credentials(username=cls.settings["username"], password=cls.settings["password"])

    @classmethod
    def get_account(cls):
        return Account(
            primary_smtp_address=cls.settings["account"],
            access_type=IMPERSONATION if isinstance(cls.config.credentials, OAuth2Credentials) else DELEGATE,
            config=cls.config,
            locale="da_DK",
            default_timezone=cls.tz,
        )

    def setUp(self):
        super().setUp()
        # Create a random category for each test to avoid crosstalk
        self.categories = [get_random_string(length=16, spaces=False, special=False)]

    def wipe_test_account(self):
        # Deletes up all deletable items in the test account. Not run in a normal test run
        self.account.root.wipe()
        for rule in self.account.rules:
            rule.delete()

    def bulk_delete(self, ids):
        # Clean up items and check return values
        for res in self.account.bulk_delete(ids):
            self.assertEqual(res, True)

    def random_val(self, field):
        if isinstance(field, ExtendedPropertyField):
            if field.value_cls.property_type == "StringArray":
                return [get_random_string(255) for _ in range(random.randint(1, 4))]
            if field.value_cls.property_type == "IntegerArray":
                return [get_random_int(0, 256) for _ in range(random.randint(1, 4))]
            if field.value_cls.property_type == "BinaryArray":
                return [get_random_string(255).encode() for _ in range(random.randint(1, 4))]
            if field.value_cls.property_type == "String":
                return get_random_string(255)
            if field.value_cls.property_type == "Integer":
                return get_random_int(0, 256)
            if field.value_cls.property_type == "Binary":
                # In the test_extended_distinguished_property test, EWS rull return 4 NULL bytes after char 16 if we
                # send a longer bytes sequence.
                return get_random_string(16).encode()
            raise ValueError(f"Unsupported field {field}")
        if isinstance(field, URIField):
            return get_random_url()
        if isinstance(field, EmailAddressField):
            return get_random_email()
        if isinstance(field, ChoiceField):
            return get_random_choice(field.supported_choices(version=self.account.version))
        if isinstance(field, CultureField):
            return get_random_choice(["da-DK", "de-DE", "en-US", "es-ES", "fr-CA", "nl-NL", "ru-RU", "sv-SE"])
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
        if isinstance(field, MimeContentField):
            return get_random_string(400).encode("utf-8")
        if isinstance(field, Base64Field):
            return get_random_bytes(400)
        if isinstance(field, BooleanField):
            return get_random_bool()
        if isinstance(field, DecimalField):
            return get_random_decimal(field.min or 1, field.max or 99)
        if isinstance(field, IntegerField):
            return get_random_int(field.min or 0, field.max or 256)
        if isinstance(field, DateField):
            return get_random_date()
        if isinstance(field, DateTimeBackedDateField):
            return get_random_date()
        if isinstance(field, DateTimeField):
            return get_random_datetime(tz=self.account.default_timezone)
        if isinstance(field, AttachmentField):
            return [FileAttachment(name="my_file.txt", content=get_random_string(400).encode("utf-8"))]
        if isinstance(field, MailboxListField):
            # email_address must be a real account on the server(?)
            # TODO: Mailbox has multiple optional args but vals must match server account, so we can't easily test
            return [Mailbox(email_address=self.account.primary_smtp_address)]
        if isinstance(field, MailboxField):
            # email_address must be a real account on the server(?)
            # TODO: Mailbox has multiple optional args but vals must match server account, so we can't easily test
            return Mailbox(email_address=self.account.primary_smtp_address)
        if isinstance(field, AttendeesField):
            # Attendee must refer to a real mailbox on the server(?). We're only sure to have one
            mbx = Mailbox(email_address=self.account.primary_smtp_address)
            with_last_response_time = get_random_bool()
            if with_last_response_time:
                return [
                    Attendee(
                        mailbox=mbx,
                        response_type="Accept",
                        last_response_time=get_random_datetime(tz=self.account.default_timezone),
                    )
                ]
            return [Attendee(mailbox=mbx, response_type="Accept")]
        if isinstance(field, EmailAddressesField):
            addrs = []
            for label in EmailAddress.get_field_by_fieldname("label").supported_choices(version=self.account.version):
                addr = EmailAddress(email=get_random_email())
                addr.label = label
                addrs.append(addr)
            return addrs
        if isinstance(field, PhysicalAddressField):
            addrs = []
            for label in PhysicalAddress.get_field_by_fieldname("label").supported_choices(
                version=self.account.version
            ):
                addr = PhysicalAddress(
                    street=get_random_string(32),
                    city=get_random_string(32),
                    state=get_random_string(32),
                    country=get_random_string(32),
                    zipcode=get_random_string(8),
                )
                addr.label = label
                addrs.append(addr)
            return addrs
        if isinstance(field, PhoneNumberField):
            pns = []
            for label in PhoneNumber.get_field_by_fieldname("label").supported_choices(version=self.account.version):
                pn = PhoneNumber(phone_number=get_random_string(16))
                pn.label = label
                pns.append(pn)
            return pns
        if isinstance(field, EWSElementField):
            if field.value_cls == Recurrence:
                return Recurrence(pattern=DailyPattern(interval=5), start=get_random_date(), number=7)
            if field.value_cls == TaskRecurrence:
                return TaskRecurrence(pattern=DailyRegeneration(interval=5), start=get_random_date(), number=7)
            if field.value_cls == ReminderMessageData:
                start = get_random_time()
                end = get_random_time(start_time=start)
                return ReminderMessageData(
                    reminder_text=get_random_string(16),
                    location=get_random_string(16),
                    start_time=start,
                    end_time=end,
                )
        if field.value_cls == CompleteName:
            return CompleteName(
                title=get_random_string(16),
                first_name=get_random_string(16),
                middle_name=get_random_string(16),
                last_name=get_random_string(16),
                suffix=get_random_string(16),
                initials=get_random_string(16),
                full_name=get_random_string(16),
                nickname=get_random_string(16),
                yomi_first_name=get_random_string(16),
                yomi_last_name=get_random_string(16),
            )
        if isinstance(field, TimeZoneField):
            while True:
                tz = zoneinfo.ZoneInfo(random.choice(tuple(zoneinfo.available_timezones())))
                try:
                    EWSTimeZone.from_zoneinfo(tz)
                except UnknownTimeZone:
                    continue
                return tz
        if isinstance(field, PermissionSetField):
            return PermissionSet(
                permissions=[
                    Permission(
                        user_id=UserId(primary_smtp_address=self.account.primary_smtp_address),
                    )
                ]
            )
        raise ValueError(f"Unknown field {field}")


def get_random_bool():
    return bool(random.randint(0, 1))


def get_random_int(min_val=0, max_val=2147483647):
    return random.randint(min_val, max_val)


def get_random_decimal(min_val=0, max_val=100):
    precision = 2
    val = get_random_int(min_val, max_val * 10**precision) / 10.0**precision
    return Decimal(f"{val:.2f}")


def get_random_choice(choices):
    return random.sample(tuple(choices), 1)[0]


def get_random_string(length, spaces=True, special=True):
    chars = string.ascii_letters + string.digits
    if special:
        chars += ":.-_"
    if spaces:
        chars += " "
    # We want random strings that don't end in spaces - Exchange strips these
    res = "".join(map(lambda i: random.choice(chars), range(length))).strip()
    if len(res) < length:
        # If strip() made the string shorter, make sure to fill it up
        res += get_random_string(length - len(res), spaces=False)
    return res


def get_random_substring(val):
    random_start = get_random_int(min_val=0, max_val=len(val) // 2)
    random_end = get_random_int(min_val=len(val) // 2 + 1, max_val=len(val))
    return val[random_start:random_end]


def get_random_byte():
    return get_random_bytes(1)


def get_random_bytes(length):
    return bytes(get_random_int(max_val=255) for _ in range(length))


def get_random_hostname():
    domain_len = random.randint(16, 32)
    tld_len = random.randint(4, 6)
    return "%s.%s" % tuple(get_random_string(i, spaces=False, special=False).lower() for i in (domain_len, tld_len))


def get_random_url():
    path_len = random.randint(1, 16)
    return "http://%s/%s.html" % (get_random_hostname(), get_random_string(path_len, spaces=False, special=False))


def get_random_email():
    account_len = random.randint(1, 6)
    return "%s@%s" % (get_random_string(account_len, spaces=False, special=False).lower(), get_random_hostname())


def _total_minutes(tm):
    return (tm.hour * 60) + tm.minute


def get_random_time(start_time=datetime.time.min, end_time=datetime.time.max):
    # Create a random time with minute precision.
    random_minutes = random.randint(_total_minutes(start_time), _total_minutes(end_time))
    return datetime.time(hour=random_minutes // 60, minute=random_minutes % 60)


# The timezone we're testing (CET/CEST) had a DST date change in 1996 (see
# https://en.wikipedia.org/wiki/Summer_Time_in_Europe). The Microsoft timezone definition on the server
# does not observe that, but IANA does. So random datetimes before 1996 will fail tests randomly.
RANDOM_DATE_MIN = datetime.date(1996, 1, 1)
RANDOM_DATE_MAX = datetime.date(2030, 1, 1)
UTC = zoneinfo.ZoneInfo("UTC")


def get_random_date(start_date=RANDOM_DATE_MIN, end_date=RANDOM_DATE_MAX):
    # Keep with a reasonable date range. A wider date range is unstable WRT timezones
    return datetime.date.fromordinal(random.randint(start_date.toordinal(), end_date.toordinal()))


def get_random_datetime(start_date=RANDOM_DATE_MIN, end_date=RANDOM_DATE_MAX, tz=UTC):
    # Create a random datetime with minute precision. Both dates are inclusive.
    # Keep with a reasonable date range. A wider date range than the default values is unstable WRT timezones.
    random_date = get_random_date(start_date=start_date, end_date=end_date)
    random_datetime = datetime.datetime.combine(random_date, datetime.time.min) + datetime.timedelta(
        minutes=random.randint(0, 60 * 24)
    )
    return random_datetime.replace(tzinfo=tz)


def get_random_datetime_range(start_date=RANDOM_DATE_MIN, end_date=RANDOM_DATE_MAX, tz=UTC):
    # Create two random datetimes.  Both dates are inclusive.
    # Keep with a reasonable date range. A wider date range than the default values is unstable WRT timezones.
    # Calendar items raise ErrorCalendarDurationIsTooLong if duration is > 5 years.
    return sorted(
        [
            get_random_datetime(start_date=start_date, end_date=end_date, tz=tz),
            get_random_datetime(start_date=start_date, end_date=end_date, tz=tz),
        ]
    )
