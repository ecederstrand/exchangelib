import datetime
import logging
import warnings

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo
import tzlocal

from .errors import NaiveDateTimeNotAllowed, UnknownTimeZone
from .winzone import IANA_TO_MS_TIMEZONE_MAP, MS_TIMEZONE_TO_IANA_MAP

log = logging.getLogger(__name__)


class EWSDate(datetime.date):
    """Extends the normal date implementation to satisfy EWS"""

    __slots__ = '_year', '_month', '_day', '_hashcode'

    def ewsformat(self):
        """ISO 8601 format to satisfy xs:date as interpreted by EWS. Example: 2009-01-15"""
        return self.isoformat()

    def __add__(self, other):
        dt = super().__add__(other)
        if isinstance(dt, self.__class__):
            return dt
        return self.from_date(dt)  # We want to return EWSDate objects

    def __iadd__(self, other):
        return self + other

    def __sub__(self, other):
        dt = super().__sub__(other)
        if isinstance(dt, datetime.timedelta):
            return dt
        if isinstance(dt, self.__class__):
            return dt
        return self.from_date(dt)  # We want to return EWSDate objects

    def __isub__(self, other):
        return self - other

    @classmethod
    def fromordinal(cls, n):
        dt = super().fromordinal(n)
        if isinstance(dt, cls):
            return dt
        return cls.from_date(dt)  # We want to return EWSDate objects

    @classmethod
    def from_date(cls, d):
        if type(d) != datetime.date:
            raise ValueError("%r must be a date instance" % d)
        return cls(d.year, d.month, d.day)

    @classmethod
    def from_string(cls, date_string):
        # Sometimes, we'll receive a date string with timezone information. Not very useful.
        if date_string.endswith('Z'):
            dt = datetime.datetime.strptime(date_string, '%Y-%m-%dZ')
        elif ':' in date_string:
            if '+' in date_string:
                dt = datetime.datetime.strptime(date_string, '%Y-%m-%d+%H:%M')
            else:
                dt = datetime.datetime.strptime(date_string, '%Y-%m-%d-%H:%M')
        else:
            dt = datetime.datetime.strptime(date_string, '%Y-%m-%d')
        d = dt.date()
        if isinstance(d, cls):
            return d
        return cls.from_date(d)  # We want to return EWSDate objects


class EWSDateTime(datetime.datetime):
    """Extends the normal datetime implementation to satisfy EWS"""

    __slots__ = '_year', '_month', '_day', '_hour', '_minute', '_second', '_microsecond', '_tzinfo', '_hashcode'

    def __new__(cls, *args, **kwargs):
        # pylint: disable=arguments-differ
        if not isinstance(kwargs.get('tzinfo'), (EWSTimeZone, type(None))):
            raise ValueError('tzinfo must be an EWSTimeZone instance')
        return super().__new__(cls, *args, **kwargs)

    def ewsformat(self):
        """ISO 8601 format to satisfy xs:datetime as interpreted by EWS. Examples:
            2009-01-15T13:45:56Z
            2009-01-15T13:45:56+01:00

        """
        if not self.tzinfo:
            raise ValueError('%r must be timezone-aware' % self)
        if self.tzinfo.key == 'UTC':
            return self.strftime('%Y-%m-%dT%H:%M:%SZ')
        return self.replace(microsecond=0).isoformat()

    @classmethod
    def from_datetime(cls, d):
        if type(d) != datetime.datetime:
            raise ValueError("%r must be a datetime instance" % d)
        if d.tzinfo is None:
            tz = None
        elif isinstance(d.tzinfo, EWSTimeZone):
            tz = d.tzinfo
        else:
            # Support some more tzinfo implementations. We could use isinstance(), but then we'd have to have pytz
            # and dateutil as dependencies for this package.
            tz_module = d.tzinfo.__class__.__module__.split('.')[0]
            if tz_module == 'pytz':
                tz = EWSTimeZone.from_pytz(d.tzinfo)
            elif tz_module == 'dateutil':
                tz = EWSTimeZone.from_dateutil(d.tzinfo)
            elif tz_module in ('backports', 'zoneinfo'):
                tz = EWSTimeZone(d.tzinfo.key)
            else:
                raise ValueError('Unsupported tzinfo value: %r' % d.tzinfo)
        return cls(d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond, tzinfo=tz)

    def astimezone(self, tz=None):
        if tz is None:
            tz = EWSTimeZone.localzone()
        t = super().astimezone(tz=tz).replace(tzinfo=tz)
        if isinstance(t, self.__class__):
            return t
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __add__(self, other):
        t = super().__add__(other)
        if isinstance(t, self.__class__):
            return t
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __iadd__(self, other):
        return self + other

    def __sub__(self, other):
        t = super().__sub__(other)
        if isinstance(t, datetime.timedelta):
            return t
        if isinstance(t, self.__class__):
            return t
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __isub__(self, other):
        return self - other

    @classmethod
    def from_string(cls, date_string):
        # Parses several common datetime formats and returns timezone-aware EWSDateTime objects
        if date_string.endswith('Z'):
            # UTC datetime
            return super().strptime(date_string, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)
        if len(date_string) == 19:
            # This is probably a naive datetime. Don't allow this, but signal caller with an appropriate error
            local_dt = super().strptime(date_string, '%Y-%m-%dT%H:%M:%S')
            raise NaiveDateTimeNotAllowed(local_dt)
        # This is probably a datetime value with timezone information. This comes in the form '+/-HH:MM'.
        aware_dt = datetime.datetime.fromisoformat(date_string).astimezone(UTC).replace(tzinfo=UTC)
        if isinstance(aware_dt, cls):
            return aware_dt
        return cls.from_datetime(aware_dt)

    @classmethod
    def fromtimestamp(cls, t, tz=None):
        dt = super().fromtimestamp(t, tz=tz)
        if isinstance(dt, cls):
            return dt
        return cls.from_datetime(dt)  # We want to return EWSDateTime objects

    @classmethod
    def utcfromtimestamp(cls, t):
        dt = super().utcfromtimestamp(t)
        if isinstance(dt, cls):
            return dt
        return cls.from_datetime(dt)  # We want to return EWSDateTime objects

    @classmethod
    def now(cls, tz=None):
        t = super().now(tz=tz)
        if isinstance(t, cls):
            return t
        return cls.from_datetime(t)  # We want to return EWSDateTime objects

    @classmethod
    def utcnow(cls):
        t = super().utcnow()
        if isinstance(t, cls):
            return t
        return cls.from_datetime(t)  # We want to return EWSDateTime objects

    def date(self):
        d = super().date()
        if isinstance(d, EWSDate):
            return d
        return EWSDate.from_date(d)  # We want to return EWSDate objects


class EWSTimeZone(zoneinfo.ZoneInfo):
    """Represents a timezone as expected by the EWS TimezoneContext / TimezoneDefinition XML element, and returned by
    services.GetServerTimeZones.

    """
    IANA_TO_MS_MAP = IANA_TO_MS_TIMEZONE_MAP
    MS_TO_IANA_MAP = MS_TIMEZONE_TO_IANA_MAP

    def __new__(cls, *args, **kwargs):
        try:
            instance = super().__new__(cls, *args, **kwargs)
        except zoneinfo.ZoneInfoNotFoundError as e:
            raise UnknownTimeZone(e.args[0])
        try:
            instance.ms_id = cls.IANA_TO_MS_MAP[instance.key][0]
        except KeyError:
            raise UnknownTimeZone('No Windows timezone name found for timezone "%s"' % instance.key)

        # We don't need the Windows long-format timezone name in long format. It's used in timezone XML elements, but
        # EWS happily accepts empty strings. For a full list of timezones supported by the target server, including
        # long-format names, see output of services.GetServerTimeZones(account.protocol).call()
        instance.ms_name = ''
        return instance

    def __eq__(self, other):
        # Microsoft timezones are less granular than IANA, so an EWSTimeZone created from 'Europe/Copenhagen' may return
        # from the server as 'Europe/Copenhagen'. We're catering for Microsoft here, so base equality on the Microsoft
        # timezone ID.
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.ms_id == other.ms_id

    @classmethod
    def from_ms_id(cls, ms_id):
        # Create a timezone instance from a Microsoft timezone ID. This is lossy because there is not a 1:1 translation
        # from MS timezone ID to IANA timezone.
        try:
            return cls(cls.MS_TO_IANA_MAP[ms_id])
        except KeyError:
            if '/' in ms_id:
                # EWS sometimes returns an ID that has a region/location format, e.g. 'Europe/Copenhagen'. Try the
                # string unaltered.
                return cls(ms_id)
            raise UnknownTimeZone("Windows timezone ID '%s' is unknown by CLDR" % ms_id)

    @classmethod
    def from_pytz(cls, tz):
        return cls(tz.zone)

    @classmethod
    def from_dateutil(cls, tz):
        key = '/'.join(tz._filename.split('/')[-2:])
        return cls(key)

    @classmethod
    def localzone(cls):
        try:
            tz = tzlocal.get_localzone()
        except zoneinfo.ZoneInfoNotFoundError:
            # Older versions of tzlocal will raise a pytz exception. Let's not depend on pytz just for that.
            raise UnknownTimeZone("Failed to guess local timezone")
        # Handle both old and new versions of tzlocal that may return pytz or zoneinfo objects, respectively
        return cls(tz.key if hasattr(tz, 'key') else tz.zone)

    @classmethod
    def timezone(cls, location):
        warnings.warn('replace EWSTimeZone.timezone() with just EWSTimeZone()', DeprecationWarning, stacklevel=2)
        return cls(location)

    def normalize(self, dt, is_dst=False):
        warnings.warn('normalization is now handled gracefully', DeprecationWarning, stacklevel=2)
        return dt

    def localize(self, dt, is_dst=False):
        warnings.warn('replace tz.localize() with dt.replace(tzinfo=tz)', DeprecationWarning, stacklevel=2)
        if dt.tzinfo is not None:
            raise ValueError('%r must be timezone-unaware' % dt)
        dt = dt.replace(tzinfo=self)
        if is_dst is not None:
            # DST dates are assumed to always be after non-DST dates
            dt_before = dt.replace(fold=0)
            dt_after = dt.replace(fold=1)
            dst_before = dt_before.dst()
            dst_after = dt_after.dst()
            if dst_before > dst_after:
                dt = dt_before if is_dst else dt_after
            elif dst_before < dst_after:
                dt = dt_after if is_dst else dt_before
        return dt

    def fromutc(self, dt):
        t = super().fromutc(dt)
        if isinstance(t, EWSDateTime):
            return t
        return EWSDateTime.from_datetime(t)  # We want to return EWSDateTime objects


UTC = EWSTimeZone('UTC')
UTC_NOW = lambda: EWSDateTime.now(tz=UTC)  # noqa: E731
