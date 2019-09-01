# coding=utf-8
from __future__ import unicode_literals

import datetime
import logging

import dateutil.parser
import pytz
import pytz.exceptions
import tzlocal
import six

from .errors import NaiveDateTimeNotAllowed, UnknownTimeZone, AmbiguousTimeError, NonExistentTimeError
from .winzone import PYTZ_TO_MS_TIMEZONE_MAP, MS_TIMEZONE_TO_PYTZ_MAP

log = logging.getLogger(__name__)


class EWSDate(datetime.date):
    """
    Extends the normal date implementation to satisfy EWS
    """

    __slots__ = '_year', '_month', '_day', '_hashcode'

    def ewsformat(self):
        """
        ISO 8601 format to satisfy xs:date as interpreted by EWS. Example: 2009-01-15
        """
        return self.isoformat()

    def __add__(self, other):
        dt = super(EWSDate, self).__add__(other)
        if isinstance(dt, self.__class__):
            return dt
        return self.from_date(dt)  # We want to return EWSDate objects

    def __iadd__(self, other):
        return self + other

    def __sub__(self, other):
        dt = super(EWSDate, self).__sub__(other)
        if isinstance(dt, datetime.timedelta):
            return dt
        if isinstance(dt, self.__class__):
            return dt
        return self.from_date(dt)  # We want to return EWSDate objects

    def __isub__(self, other):
        return self - other

    @classmethod
    def fromordinal(cls, n):
        dt = super(EWSDate, cls).fromordinal(n)
        if isinstance(dt, cls):
            return dt
        return cls.from_date(dt)  # We want to return EWSDate objects

    @classmethod
    def from_date(cls, d):
        if d.__class__ != datetime.date:
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
    """
    Extends the normal datetime implementation to satisfy EWS
    """

    __slots__ = '_year', '_month', '_day', '_hour', '_minute', '_second', '_microsecond', '_tzinfo', '_hashcode'

    def __new__(cls, *args, **kwargs):
        # pylint: disable=arguments-differ
        # Not all Python versions have the same signature for datetime.datetime
        """
        Inherits datetime and adds extra formatting required by EWS. Do not set tzinfo directly. Use
        EWSTimeZone.localize() instead.
        """
        # We can't use the exact signature of datetime.datetime because we get pickle errors, and implementing pickle
        # support requires copy-pasting lots of code from datetime.datetime.
        if not isinstance(kwargs.get('tzinfo'), (EWSTimeZone, type(None))):
            raise ValueError('tzinfo must be an EWSTimeZone instance')
        return super(EWSDateTime, cls).__new__(cls, *args, **kwargs)

    def ewsformat(self):
        """
        ISO 8601 format to satisfy xs:datetime as interpreted by EWS. Examples:
            2009-01-15T13:45:56Z
            2009-01-15T13:45:56+01:00
        """
        if not self.tzinfo:
            raise ValueError('EWSDateTime must be timezone-aware')
        if self.tzinfo.zone == 'UTC':
            return self.strftime('%Y-%m-%dT%H:%M:%SZ')
        return self.replace(microsecond=0).isoformat()

    @classmethod
    def from_datetime(cls, d):
        if d.__class__ != datetime.datetime:
            raise ValueError("%r must be a datetime instance" % d)
        if d.tzinfo is None:
            tz = None
        elif isinstance(d.tzinfo, EWSTimeZone):
            tz = d.tzinfo
        else:
            tz = EWSTimeZone.from_pytz(d.tzinfo)
        return cls(d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond, tzinfo=tz)

    def astimezone(self, tz=None):
        t = super(EWSDateTime, self).astimezone(tz=tz)
        if isinstance(t, self.__class__):
            return t
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __add__(self, other):
        t = super(EWSDateTime, self).__add__(other)
        if isinstance(t, self.__class__):
            return t
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __iadd__(self, other):
        return self + other

    def __sub__(self, other):
        t = super(EWSDateTime, self).__sub__(other)
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
            naive_dt = super(EWSDateTime, cls).strptime(date_string, '%Y-%m-%dT%H:%M:%SZ')
            return UTC.localize(naive_dt)
        if len(date_string) == 19:
            # This is probably a naive datetime. Don't allow this, but signal caller with an appropriate error
            local_dt = super(EWSDateTime, cls).strptime(date_string, '%Y-%m-%dT%H:%M:%S')
            raise NaiveDateTimeNotAllowed(local_dt)
        # This is probably a datetime value with timezone information. This comes in the form '+/-HH:MM' but the Python
        # strptime '%z' directive cannot yet handle full ISO8601 formatted timezone information (see
        # http://bugs.python.org/issue15873). Use the 'dateutil' package instead.
        aware_dt = dateutil.parser.parse(date_string)
        return cls.from_datetime(aware_dt.astimezone(UTC))  # We want to return EWSDateTime objects

    @classmethod
    def fromtimestamp(cls, t, tz=None):
        dt = super(EWSDateTime, cls).fromtimestamp(t, tz=tz)
        if isinstance(dt, cls):
            return dt
        return cls.from_datetime(dt)  # We want to return EWSDateTime objects

    @classmethod
    def utcfromtimestamp(cls, t):
        dt = super(EWSDateTime, cls).utcfromtimestamp(t)
        if isinstance(dt, cls):
            return dt
        return cls.from_datetime(dt)  # We want to return EWSDateTime objects

    @classmethod
    def now(cls, tz=None):
        t = super(EWSDateTime, cls).now(tz=tz)
        if isinstance(t, cls):
            return t
        return cls.from_datetime(t)  # We want to return EWSDateTime objects

    @classmethod
    def utcnow(cls):
        t = super(EWSDateTime, cls).utcnow()
        if isinstance(t, cls):
            return t
        return cls.from_datetime(t)  # We want to return EWSDateTime objects

    def date(self):
        d = super(EWSDateTime, self).date()
        if isinstance(d, EWSDate):
            return d
        return EWSDate.from_date(d)  # We want to return EWSDate objects


class EWSTimeZone(object):
    """
    Represents a timezone as expected by the EWS TimezoneContext / TimezoneDefinition XML element, and returned by
    services.GetServerTimeZones.
    """
    PYTZ_TO_MS_MAP = PYTZ_TO_MS_TIMEZONE_MAP
    MS_TO_PYTZ_MAP = MS_TIMEZONE_TO_PYTZ_MAP

    def __eq__(self, other):
        # Microsoft timezones are less granular than pytz, so an EWSTimeZone created from 'Europe/Copenhagen' may return
        # from the server as 'Europe/Copenhagen'. We're catering for Microsoft here, so base equality on the Microsoft
        # timezone ID.
        if not hasattr(other, 'ms_id'):
            # Due to the type magic in from_pytz(), we cannot use isinstance() here
            return NotImplemented
        return self.ms_id == other.ms_id

    def __hash__(self):
        # We're shuffling around with base classes in from_pytz(). Make sure we have __hash__() implementation.
        return super(EWSTimeZone, self).__hash__()

    @classmethod
    def from_ms_id(cls, ms_id):
        # Create a timezone instance from a Microsoft timezone ID. This is lossy because there is not a 1:1 translation
        # from MS timezone ID to pytz timezone.
        try:
            return cls.timezone(cls.MS_TO_PYTZ_MAP[ms_id])
        except KeyError:
            if '/' in ms_id:
                # EWS sometimes returns an ID that has a region/location format, e.g. 'Europe/Copenhagen'. Try the
                # string unaltered.
                return cls.timezone(ms_id)
            raise UnknownTimeZone("Windows timezone ID '%s' is unknown by CLDR" % ms_id)

    @classmethod
    def from_pytz(cls, tz):
        # pytz timezones are dynamically generated. Subclass the tz.__class__ and add the extra Microsoft timezone
        # labels we need.

        # type() does not allow duplicate base classes. For static timezones, 'cls' and 'tz' are the same class.
        base_classes = (cls,) if cls == tz.__class__ else (cls, tz.__class__)
        self_cls = type(cls.__name__, base_classes, dict(tz.__class__.__dict__))
        try:
            self_cls.ms_id = cls.PYTZ_TO_MS_MAP[tz.zone][0]
        except KeyError:
            raise UnknownTimeZone('No Windows timezone name found for timezone "%s"' % tz.zone)

        # We don't need the Windows long-format timezone name in long format. It's used in timezone XML elements, but
        # EWS happily accepts empty strings. For a full list of timezones supported by the target server, including
        # long-format names, see output of services.GetServerTimeZones(account.protocol).call()
        self_cls.ms_name = ''

        self = self_cls()
        for k, v in tz.__dict__.items():
            setattr(self, k, v)
        return self

    @classmethod
    def localzone(cls):
        try:
            tz = tzlocal.get_localzone()
        except pytz.exceptions.UnknownTimeZoneError:
            raise UnknownTimeZone("Failed to guess local timezone")
        return cls.from_pytz(tz)

    @classmethod
    def timezone(cls, location):
        # Like pytz.timezone() but returning EWSTimeZone instances
        try:
            tz = pytz.timezone(location)
        except pytz.exceptions.UnknownTimeZoneError:
            raise UnknownTimeZone("Timezone '%s' is unknown by pytz" % location)
        return cls.from_pytz(tz)

    def normalize(self, dt, is_dst=False):
        return self._localize_or_normalize(func='normalize', dt=dt, is_dst=is_dst)

    def localize(self, dt, is_dst=False):
        return self._localize_or_normalize(func='localize', dt=dt, is_dst=is_dst)

    def _localize_or_normalize(self, func, dt, is_dst=False):
        """localize() and normalize() have common code paths
        """
        # super() returns a dt.tzinfo of class pytz.tzinfo.FooBar. We need to return type EWSTimeZone
        if is_dst is not False:
            # Not all pytz timezones support 'is_dst' argument. Only pass it on if it's set explicitly.
            try:
                res = getattr(super(EWSTimeZone, self), func)(dt, is_dst=is_dst)
            except pytz.exceptions.AmbiguousTimeError as exc:
                six.raise_from(AmbiguousTimeError(str(dt)), exc)
            except pytz.exceptions.NonExistentTimeError as exc:
                six.raise_from(NonExistentTimeError(str(dt)), exc)
        else:
            res = getattr(super(EWSTimeZone, self), func)(dt)
        if not isinstance(res.tzinfo, EWSTimeZone):
            return res.replace(tzinfo=self.from_pytz(res.tzinfo))
        return res

    def fromutc(self, dt):
        t = super(EWSTimeZone, self).fromutc(dt)
        if isinstance(t, EWSDateTime):
            return t
        return EWSDateTime.from_datetime(t)  # We want to return EWSDateTime objects


UTC = EWSTimeZone.timezone('UTC')
UTC_NOW = lambda: EWSDateTime.now(tz=UTC)  # noqa: E731
