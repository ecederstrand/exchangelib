# coding=utf-8
from __future__ import unicode_literals

import datetime

import pytz
from future.utils import raise_from


class EWSDate(datetime.date):
    """
    Extends the normal date implementation to satisfy EWS
    """

    def ewsformat(self):
        """
        ISO 8601 format to satisfy xs:date as interpreted by EWS. Example: 2009-01-15
        """
        return self.strftime('%Y-%m-%d')


class EWSDateTime(datetime.datetime):
    """
    Extends the normal datetime implementation to satisfy EWS
    """

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

    @classmethod
    def from_pytz(cls, tz):
        # pytz timezones are dynamically generated. Subclass the tz.__class__ and add the extra Microsoft timezone
        # labels we need.
        self_cls = type(cls.__name__, (cls, tz.__class__), dict(tz.__class__.__dict__))
        try:
            self_cls.ms_id = cls.PYTZ_TO_MS_MAP[tz.zone]
        except KeyError as e:
            raise_from(ValueError('Please add an entry for "%s" in PYTZ_TO_MS_TZMAP' % tz.zone), e)
        self_cls.ms_name = cls.MS_TIMEZONE_DEFINITIONS[self_cls.ms_id]
        self = self_cls()
        for k, v in tz.__dict__.items():
            setattr(self, k, v)
        return self

    @classmethod
    def timezone(cls, location):
        # Like pytz.timezone() but returning EWSTimeZone instances
        tz = pytz.timezone(location)
        return cls.from_pytz(tz)

    def normalize(self, dt):
        # super() returns a dt.tzinfo of class pytz.tzinfo.FooBar. We need to return type EWSTimeZone
        res = super(EWSTimeZone, self).normalize(dt)
        return res.replace(tzinfo=self.from_pytz(res.tzinfo))

    def localize(self, dt):
        # super() returns a dt.tzinfo of class pytz.tzinfo.FooBar. We need to return type EWSTimeZone
        res = super(EWSTimeZone, self).localize(dt)
        return res.replace(tzinfo=self.from_pytz(res.tzinfo))

    # Manually maintained translation between pytz location / timezone name and MS timezone IDs
    PYTZ_TO_MS_MAP = {
        'UTC': 'UTC',
        'GMT': 'GMT Standard Time',
        'US/Pacific': 'Pacific Standard Time',
        'US/Eastern': 'Eastern Standard Time',
        'Europe/Copenhagen': 'Romance Standard Time',
    }

    # This is a somewhat authoritative list of the timezones available on an Exchange server. Format is (id, name).
    # For a full list supported by the target server, call services.GetServerTimeZones.
    MS_TIMEZONE_DEFINITIONS = dict([
        ('Dateline Standard Time', '(UTC-12:00) International Date Line West'),
        ('UTC-11', '(UTC-11:00) Coordinated Universal Time-11'),
        ('Samoa Standard Time', '(UTC-11:00) Midway Island, Samoa'),
        ('Hawaiian Standard Time', '(UTC-10:00) Hawaii'),
        ('Alaskan Standard Time', '(UTC-09:00) Alaska'),
        ('Pacific Standard Time', '(UTC-08:00) Pacific Time (US & Canada)'),
        ('Pacific Standard Time (Mexico)', '(UTC-08:00) Tijuana, Baja California'),
        ('US Mountain Standard Time', '(UTC-07:00) Arizona'),
        ('Mountain Standard Time (Mexico)', '(UTC-07:00) Chihuahua, La Paz, Mazatlan'),
        ('Mountain Standard Time', '(UTC-07:00) Mountain Time (US & Canada)'),
        ('Central America Standard Time', '(UTC-06:00) Central America'),
        ('Central Standard Time', '(UTC-06:00) Central Time (US & Canada)'),
        ('Central Standard Time (Mexico)', '(UTC-06:00) Guadalajara, Mexico City, Monterrey'),
        ('Canada Central Standard Time', '(UTC-06:00) Saskatchewan'),
        ('SA Pacific Standard Time', '(UTC-05:00) Bogota, Lima, Quito'),
        ('Eastern Standard Time', '(UTC-05:00) Eastern Time (US & Canada)'),
        ('US Eastern Standard Time', '(UTC-05:00) Indiana (East)'),
        ('Venezuela Standard Time', '(UTC-04:30) Caracas'),
        ('Paraguay Standard Time', '(UTC-04:00) Asuncion'),
        ('Atlantic Standard Time', '(UTC-04:00) Atlantic Time (Canada)'),
        ('SA Western Standard Time', '(UTC-04:00) Georgetown, La Paz, San Juan'),
        ('Central Brazilian Standard Time', '(UTC-04:00) Manaus'),
        ('Pacific SA Standard Time', '(UTC-04:00) Santiago'),
        ('Newfoundland Standard Time', '(UTC-03:30) Newfoundland'),
        ('E. South America Standard Time', '(UTC-03:00) Brasilia'),
        ('Argentina Standard Time', '(UTC-03:00) Buenos Aires'),
        ('SA Eastern Standard Time', '(UTC-03:00) Cayenne'),
        ('Greenland Standard Time', '(UTC-03:00) Greenland'),
        ('Montevideo Standard Time', '(UTC-03:00) Montevideo'),
        ('UTC-02', '(UTC-02:00) Coordinated Universal Time-02'),
        ('Mid-Atlantic Standard Time', '(UTC-02:00) Mid-Atlantic'),
        ('Azores Standard Time', '(UTC-01:00) Azores'),
        ('Cape Verde Standard Time', '(UTC-01:00) Cape Verde Is.'),
        ('Morocco Standard Time', '(UTC) Casablanca'),
        ('UTC', '(UTC) Coordinated Universal Time'),
        ('GMT Standard Time', '(UTC) Greenwich Mean Time : Dublin, Edinburgh, Lisbon, London'),
        ('Greenwich Standard Time', '(UTC) Monrovia, Reykjavik'),
        ('W. Europe Standard Time', '(UTC+01:00) Amsterdam, Berlin, Bern, Rome, Stockholm, Vienna'),
        ('Central Europe Standard Time', '(UTC+01:00) Belgrade, Bratislava, Budapest, Ljubljana, Prague'),
        ('Romance Standard Time', '(UTC+01:00) Brussels, Copenhagen, Madrid, Paris'),
        ('Central European Standard Time', '(UTC+01:00) Sarajevo, Skopje, Warsaw, Zagreb'),
        ('W. Central Africa Standard Time', '(UTC+01:00) West Central Africa'),
        ('Namibia Standard Time', '(UTC+02:00) Windhoek'),
        ('Jordan Standard Time', '(UTC+02:00) Amman'),
        ('GTB Standard Time', '(UTC+02:00) Athens, Bucharest, Istanbul'),
        ('Middle East Standard Time', '(UTC+02:00) Beirut'),
        ('Egypt Standard Time', '(UTC+02:00) Cairo'),
        ('Syria Standard Time', '(UTC+02:00) Damascus'),
        ('South Africa Standard Time', '(UTC+02:00) Harare, Pretoria'),
        ('FLE Standard Time', '(UTC+02:00) Helsinki, Kyiv, Riga, Sofia, Tallinn, Vilnius'),
        ('Israel Standard Time', '(UTC+02:00) Jerusalem'),
        ('E. Europe Standard Time', '(UTC+02:00) Minsk'),
        ('Arabic Standard Time', '(UTC+03:00) Baghdad'),
        ('Arab Standard Time', '(UTC+03:00) Kuwait, Riyadh'),
        ('Russian Standard Time', '(UTC+03:00) Moscow, St. Petersburg, Volgograd'),
        ('E. Africa Standard Time', '(UTC+03:00) Nairobi'),
        ('Iran Standard Time', '(UTC+03:30) Tehran'),
        ('Georgian Standard Time', '(UTC+03:00) Tbilisi'),
        ('Arabian Standard Time', '(UTC+04:00) Abu Dhabi, Muscat'),
        ('Azerbaijan Standard Time', '(UTC+04:00) Baku'),
        ('Mauritius Standard Time', '(UTC+04:00) Port Louis'),
        ('Caucasus Standard Time', '(UTC+04:00) Yerevan'),
        ('Afghanistan Standard Time', '(UTC+04:30) Kabul'),
        ('Ekaterinburg Standard Time', '(UTC+05:00) Ekaterinburg'),
        ('Pakistan Standard Time', '(UTC+05:00) Islamabad, Karachi'),
        ('West Asia Standard Time', '(UTC+05:00) Tashkent'),
        ('India Standard Time', '(UTC+05:30) Chennai, Kolkata, Mumbai, New Delhi'),
        ('Sri Lanka Standard Time', '(UTC+05:30) Sri Jayawardenepura'),
        ('Nepal Standard Time', '(UTC+05:45) Kathmandu'),
        ('N. Central Asia Standard Time', '(UTC+06:00) Almaty, Novosibirsk'),
        ('Central Asia Standard Time', '(UTC+06:00) Astana'),
        ('Bangladesh Standard Time', '(UTC+06:00) Dhaka'),
        ('Myanmar Standard Time', '(UTC+06:30) Yangon (Rangoon)'),
        ('SE Asia Standard Time', '(UTC+07:00) Bangkok, Hanoi, Jakarta'),
        ('North Asia Standard Time', '(UTC+07:00) Krasnoyarsk'),
        ('China Standard Time', '(UTC+08:00) Beijing, Chongqing, Hong Kong, Urumqi'),
        ('North Asia East Standard Time', '(UTC+08:00) Irkutsk, Ulaan Bataar'),
        ('Singapore Standard Time', '(UTC+08:00) Kuala Lumpur, Singapore'),
        ('W. Australia Standard Time', '(UTC+08:00) Perth'),
        ('Taipei Standard Time', '(UTC+08:00) Taipei'),
        ('Ulaanbaatar Standard Time', '(UTC+08:00) Ulaanbaatar'),
        ('Tokyo Standard Time', '(UTC+09:00) Osaka, Sapporo, Tokyo'),
        ('Korea Standard Time', '(UTC+09:00) Seoul'),
        ('Yakutsk Standard Time', '(UTC+09:00) Yakutsk'),
        ('Cen. Australia Standard Time', '(UTC+09:30) Adelaide'),
        ('AUS Central Standard Time', '(UTC+09:30) Darwin'),
        ('E. Australia Standard Time', '(UTC+10:00) Brisbane'),
        ('AUS Eastern Standard Time', '(UTC+10:00) Canberra, Melbourne, Sydney'),
        ('West Pacific Standard Time', '(UTC+10:00) Guam, Port Moresby'),
        ('Tasmania Standard Time', '(UTC+10:00) Hobart'),
        ('Vladivostok Standard Time', '(UTC+10:00) Vladivostok'),
        ('Magadan Standard Time', '(UTC+11:00) Magadan'),
        ('Central Pacific Standard Time', '(UTC+11:00) Magadan, Solomon Is., New Caledonia'),
        ('New Zealand Standard Time', '(UTC+12:00) Auckland, Wellington'),
        ('UTC+12', '(UTC+12:00) Coordinated Universal Time+12'),
        ('Fiji Standard Time', '(UTC+12:00) Fiji, Marshall Is.'),
        ('Kamchatka Standard Time', '(UTC+12:00) Petropavlovsk-Kamchatsky'),
        ('Tonga Standard Time', "(UTC+13:00) Nuku'alofa"),
    ])


UTC = EWSTimeZone.timezone('UTC')

UTC_NOW = lambda: EWSDateTime.now(tz=UTC)
