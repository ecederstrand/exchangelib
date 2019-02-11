# coding=utf-8
from __future__ import unicode_literals

import datetime
import logging

import dateutil.parser
import pytz
import pytz.exceptions
import tzlocal

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
        return self.from_date(dt)  # We want to return EWSDate objects

    def __iadd__(self, other):
        return self + other

    def __sub__(self, other):
        dt = super(EWSDate, self).__sub__(other)
        if isinstance(dt, datetime.timedelta):
            return dt
        return self.from_date(dt)  # We want to return EWSDate objects

    def __isub__(self, other):
        return self - other

    @classmethod
    def fromordinal(cls, n):
        dt = super(EWSDate, cls).fromordinal(n)
        return cls.from_date(dt)  # We want to return EWSDate objects

    @classmethod
    def from_date(cls, d):
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
        return cls.from_date(dt.date())


class EWSDateTime(datetime.datetime):
    """
    Extends the normal datetime implementation to satisfy EWS
    """

    __slots__ = '_year', '_month', '_day', '_hour', '_minute', '_second', '_microsecond', '_tzinfo', '_hashcode'

    def __new__(cls, *args, **kwargs):
        """
        Inherits datetime and adds extra formatting required by EWS.
        """
        if 'tzinfo' in kwargs:
            raise ValueError('Do not set tzinfo directly. Use EWSTimeZone.localize() instead')
        # Some internal methods still need to set tzinfo in the constructor. Use a magic kwarg for that.
        if 'ewstzinfo' in kwargs:
            kwargs['tzinfo'] = kwargs.pop('ewstzinfo')
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
        return cls(d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond, ewstzinfo=tz)

    def astimezone(self, tz=None):
        t = super(EWSDateTime, self).astimezone(tz=tz)
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __add__(self, other):
        t = super(EWSDateTime, self).__add__(other)
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __iadd__(self, other):
        return self + other

    def __sub__(self, other):
        t = super(EWSDateTime, self).__sub__(other)
        if isinstance(t, datetime.timedelta):
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
        return cls.from_datetime(aware_dt.astimezone(UTC))

    @classmethod
    def now(cls, tz=None):
        # We want to return EWSDateTime objects
        t = super(EWSDateTime, cls).now(tz=tz)
        if isinstance(t, cls):
            return t
        return cls.from_datetime(t)  # We want to return EWSDateTime objects

    def date(self):
        # We want to return EWSDate objects
        d = super(EWSDateTime, self).date()
        return EWSDate.from_date(d)


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
        if not isinstance(other, EWSTimeZone):
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
            self_cls.ms_id = cls.PYTZ_TO_MS_MAP[tz.zone]
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
        # super() returns a dt.tzinfo of class pytz.tzinfo.FooBar. We need to return type EWSTimeZone
        if is_dst is not False:
            # Not all pytz timezones support 'is_dst' argument. Only pass it on if it's set explicitly.
            try:
                res = super(EWSTimeZone, self).normalize(dt, is_dst=is_dst)
            except pytz.exceptions.AmbiguousTimeError:
                raise AmbiguousTimeError(str(dt))
            except pytz.exceptions.NonExistentTimeError:
                raise NonExistentTimeError(str(dt))
        else:
            res = super(EWSTimeZone, self).normalize(dt)
        if not isinstance(res.tzinfo, EWSTimeZone):
            return res.replace(tzinfo=self.from_pytz(res.tzinfo))
        return res

    def localize(self, dt, is_dst=False):
        # super() returns a dt.tzinfo of class pytz.tzinfo.FooBar. We need to return type EWSTimeZone
        if is_dst is not False:
            # Not all pytz timezones support 'is_dst' argument. Only pass it on if it's set explicitly.
            try:
                res = super(EWSTimeZone, self).localize(dt, is_dst=is_dst)
            except pytz.exceptions.AmbiguousTimeError:
                raise AmbiguousTimeError(str(dt))
            except pytz.exceptions.NonExistentTimeError:
                raise NonExistentTimeError(str(dt))
        else:
            res = super(EWSTimeZone, self).localize(dt)
        if not isinstance(res.tzinfo, EWSTimeZone):
            return res.replace(tzinfo=self.from_pytz(res.tzinfo))
        return res


UTC = EWSTimeZone.timezone('UTC')
UTC_NOW = lambda: EWSDateTime.now(tz=UTC)
