# coding=utf-8
from __future__ import unicode_literals

import datetime
import logging
import shelve

import pytz
from future.utils import raise_from, PY2

from .errors import UnknownTimeZone
from .winzone import PYTZ_TO_MS_TIMEZONE_MAP

if PY2:
    from contextlib import contextmanager

    @contextmanager
    def shelve_open(*args, **kwargs):
        shelve_handle = shelve.open(*args, **kwargs)
        try:
            yield shelve_handle
        finally:
            shelve_handle.close()
else:
    shelve_open = shelve.open

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
        return self.strftime('%Y-%m-%d')


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
            # Creating
            raise ValueError('Do not set tzinfo directly. Use EWSTimeZone.localize() instead')
        self = super(EWSDateTime, cls).__new__(cls, *args, **kwargs)
        return self

    def ewsformat(self):
        """
        ISO 8601 format to satisfy xs:datetime as interpreted by EWS. Example: 2009-01-15T13:45:56Z
        """
        assert self.tzinfo  # EWS datetimes must always be timezone-aware
        if self.tzinfo.zone == 'UTC':
            return self.strftime('%Y-%m-%dT%H:%M:%SZ')
        return self.strftime('%Y-%m-%dT%H:%M:%S')

    @classmethod
    def from_datetime(cls, d):
        dt = cls(d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond)
        if d.tzinfo:
            if isinstance(d.tzinfo, EWSTimeZone):
                return d.tzinfo.localize(dt)
            return EWSTimeZone.from_pytz(d.tzinfo).localize(dt)
        return dt

    def astimezone(self, tz=None):
        t = super(EWSDateTime, self).astimezone(tz=tz)
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __add__(self, other):
        t = super(EWSDateTime, self).__add__(other)
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    def __sub__(self, other):
        t = super(EWSDateTime, self).__sub__(other)
        if isinstance(t, datetime.timedelta):
            return t
        return self.from_datetime(t)  # We want to return EWSDateTime objects

    @classmethod
    def from_string(cls, date_string):
        # Assume UTC and return timezone-aware EWSDateTime objects
        local_dt = super(EWSDateTime, cls).strptime(date_string, '%Y-%m-%dT%H:%M:%SZ')
        return EWSTimeZone.from_pytz(pytz.utc).localize(cls.from_datetime(local_dt))

    @classmethod
    def now(cls, tz=None):
        # We want to return EWSDateTime objects
        t = super(EWSDateTime, cls).now(tz=tz)
        return cls.from_datetime(t)


class EWSTimeZone(object):
    """
    Represents a timezone as expected by the EWS TimezoneContext / TimezoneDefinition XML element, and returned by
    services.GetServerTimeZones.
    """
    PYTZ_TO_MS_MAP = PYTZ_TO_MS_TIMEZONE_MAP

    @classmethod
    def from_pytz(cls, tz):
        # pytz timezones are dynamically generated. Subclass the tz.__class__ and add the extra Microsoft timezone
        # labels we need.
        self_cls = type(cls.__name__, (cls, tz.__class__), dict(tz.__class__.__dict__))
        try:
            self_cls.ms_id = cls.PYTZ_TO_MS_MAP[tz.zone]
        except KeyError as e:
            raise_from(ValueError('No Windows timezone name found for timezone "%s"' % tz.zone), e)

        # We don't need the Windows long-format timezone name in long format. It's used in timezone XML elements, but
        # EWS happily accepts empty strings. For a full list of timezones supported by the target server, including
        # long-format names, see output of services.GetServerTimeZones(account.protocol).call()
        self_cls.ms_name = ''

        self = self_cls()
        for k, v in tz.__dict__.items():
            setattr(self, k, v)
        return self

    @classmethod
    def timezone(cls, location):
        # Like pytz.timezone() but returning EWSTimeZone instances
        try:
            tz = pytz.timezone(location)
        except pytz.exceptions.UnknownTimeZoneError:
            raise UnknownTimeZone("Timezone '%s' is unknown by pytz" % location)
        return cls.from_pytz(tz)

    def normalize(self, dt):
        # super() returns a dt.tzinfo of class pytz.tzinfo.FooBar. We need to return type EWSTimeZone
        res = super(EWSTimeZone, self).normalize(dt)
        return res.replace(tzinfo=self.from_pytz(res.tzinfo))

    def localize(self, dt):
        # super() returns a dt.tzinfo of class pytz.tzinfo.FooBar. We need to return type EWSTimeZone
        res = super(EWSTimeZone, self).localize(dt)
        return res.replace(tzinfo=self.from_pytz(res.tzinfo))


UTC = EWSTimeZone.timezone('UTC')

UTC_NOW = lambda: EWSDateTime.now(tz=UTC)
