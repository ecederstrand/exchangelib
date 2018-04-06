import logging

from six import string_types

from .fields import IntegerField, IdField, EnumField, EnumListField, DateField, DateTimeField, EWSElementField, \
    WEEKDAY_NAMES, MONTHS, WEEK_NUMBERS, WEEKDAYS, EXTRA_WEEKDAY_OPTIONS
from .properties import EWSElement, ItemId

log = logging.getLogger(__name__)


class ExtraWeekdaysField(EnumListField):
    def __init__(self, *args, **kwargs):
        kwargs['enum'] = WEEKDAYS
        super(ExtraWeekdaysField, self).__init__(*args, **kwargs)

    def clean(self, value, version=None):
        # Pass EXTRA_WEEKDAY_OPTIONS as single string or integer value
        if isinstance(value, string_types):
            if value not in EXTRA_WEEKDAY_OPTIONS:
                raise ValueError(
                    "Single value '%s' on field '%s' must be one of %s" % (value, self.name, EXTRA_WEEKDAY_OPTIONS))
            value = [self.enum.index(value) + 1]
        elif isinstance(value, self.value_cls):
            value = [value]
        else:
            value = list(value)  # Convert to something we can index
            for i, v in enumerate(value):
                if isinstance(v, string_types):
                    if v not in WEEKDAY_NAMES:
                        raise ValueError(
                            "List value '%s' on field '%s' must be one of %s" % (v, self.name, WEEKDAY_NAMES))
                    value[i] = self.enum.index(v) + 1
                elif isinstance(v, self.value_cls) and not 1 <= v <= 7:
                    raise ValueError("List value '%s' on field '%s' must be in range 1 -> 7" % (v, self.name))
        return super(ExtraWeekdaysField, self).clean(value, version=version)


class Pattern(EWSElement):
    __slots__ = tuple()


class AbsoluteYearlyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564242(v=exchg.150).aspx
    ELEMENT_NAME = 'AbsoluteYearlyRecurrence'

    FIELDS = [
        # The month of the year, from 1 - 12
        EnumField('month', field_uri='t:Month', enum=MONTHS, is_required=True),
        # The day of month of an occurrence, in range 1 -> 31. If a particular month has less days than the day_of_month
        # value, the last day in the month is assumed
        IntegerField('day_of_month', field_uri='t:DayOfMonth', min=1, max=31, is_required=True),
    ]
    __slots__ = ('month', 'day_of_month')

    def __str__(self):
        month = MONTHS[self.month-1] if isinstance(self.month, int) else self.month
        return 'Occurs on day %s of %s' % (self.day_of_month, month)


class RelativeYearlyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/bb204113(v=exchg.150).aspx
    ELEMENT_NAME = 'RelativeYearlyRecurrence'

    FIELDS = [
        # List of valid ISO 8601 weekdays, as list of numbers in range 1 -> 7 (1 being Monday). Alternatively, weekdays
        # can be one of the DAY (or 8), WEEK_DAY (or 9) or WEEKEND_DAY (or 10) consts which is interpreted as the first
        # day, weekday, or weekend day in the month, respectively.
        ExtraWeekdaysField('weekdays', field_uri='t:DaysOfWeek', is_required=True),
        # Week number of the month, in range 1 -> 5. If 5 is specified, this assumes the last week of the month for
        # months that have only 4 weeks
        EnumField('week_number', field_uri='t:DayOfWeekIndex', enum=WEEK_NUMBERS, is_required=True),
        # The month of the year, from 1 - 12
        EnumField('month', field_uri='t:Month', enum=MONTHS, is_required=True),
    ]
    __slots__ = ('weekdays', 'week_number', 'month')

    def __str__(self):
        weekdays = [WEEKDAYS[i - 1] if isinstance(i, int) else i for i in self.weekdays]
        week_number = WEEK_NUMBERS[self.week_number-1] if isinstance(self.week_number, int) else self.week_number
        month = MONTHS[self.month-1] if isinstance(self.month, int) else self.month
        return 'Occurs on weekdays %s in the %s week of %s' % (', '.join(weekdays), week_number, month)


class AbsoluteMonthlyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa493844(v=exchg.150).aspx
    ELEMENT_NAME = 'AbsoluteMonthlyRecurrence'

    FIELDS = [
        # Interval, in months, in range 1 -> 99
        IntegerField('interval', field_uri='t:Interval', min=1, max=99, is_required=True),
        # The day of month of an occurrence, in range 1 -> 31. If a particular month has less days than the day_of_month
        # value, the last day in the month is assumed
        IntegerField('day_of_month', field_uri='t:DayOfMonth', min=1, max=31, is_required=True),
    ]
    __slots__ = ('interval', 'day_of_month')

    def __str__(self):
        return 'Occurs on day %s of every %s month(s)' % (self.day_of_month, self.interval)


class RelativeMonthlyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564558(v=exchg.150).aspx
    ELEMENT_NAME = 'RelativeMonthlyRecurrence'

    FIELDS = [
        # Interval, in months, in range 1 -> 99
        IntegerField('interval', field_uri='t:Interval', min=1, max=99, is_required=True),
        # List of valid ISO 8601 weekdays, as list of numbers in range 1 -> 7 (1 being Monday). Alternatively, weekdays
        # can be one of the DAY (or 8), WEEK_DAY (or 9) or WEEKEND_DAY (or 10) consts which is interpreted as the first
        # day, weekday, or weekend day in the month, respectively.
        ExtraWeekdaysField('weekdays', field_uri='t:DaysOfWeek', is_required=True),
        # Week number of the month, in range 1 -> 5. If 5 is specified, this assumes the last week of the month for
        # months that have only 4 weeks.
        EnumField('week_number', field_uri='t:DayOfWeekIndex', enum=WEEK_NUMBERS, is_required=True),
    ]
    __slots__ = ('interval', 'week_number', 'weekdays')

    def __str__(self):
        weekdays = [WEEKDAYS[i - 1] if isinstance(i, int) else i for i in self.weekdays]
        week_number = WEEK_NUMBERS[self.week_number-1] if isinstance(self.week_number, int) else self.week_number
        return 'Occurs on weekdays %s in the %s week of every %s month(s)' % (
            ', '.join(weekdays), week_number, self.interval
        )


class WeeklyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa563500(v=exchg.150).aspx
    ELEMENT_NAME = 'WeeklyRecurrence'

    FIELDS = [
        # Interval, in weeks, in range 1 -> 99
        IntegerField('interval', field_uri='t:Interval', min=1, max=99, is_required=True),
        # List of valid ISO 8601 weekdays, as list of numbers in range 1 -> 7 (1 being Monday)
        EnumListField('weekdays', field_uri='t:DaysOfWeek', enum=WEEKDAYS, is_required=True),
        # The first day of the week. Defaults to Monday
        EnumField('first_day_of_week', field_uri='t:FirstDayOfWeek', enum=WEEKDAYS, default=1, is_required=True),
    ]
    __slots__ = ('interval', 'weekdays', 'first_day_of_week')

    def __str__(self):
        if isinstance(self.weekdays, string_types):
            weekdays = [self.weekdays]
        elif isinstance(self.weekdays, int):
            weekdays = [WEEKDAYS[self.weekdays - 1]]
        else:
            weekdays = [WEEKDAYS[i - 1] if isinstance(i, int) else i for i in self.weekdays]
        first_day_of_week = WEEKDAYS[self.first_day_of_week - 1] if isinstance(self.first_day_of_week, int) \
            else self.first_day_of_week
        return 'Occurs on weekdays %s of every %s week(s) where the first day of the week is %s' % (
            ', '.join(weekdays), self.interval, first_day_of_week
        )


class DailyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa563228(v=exchg.150).aspx
    ELEMENT_NAME = 'DailyRecurrence'

    FIELDS = [
        # Interval, in days, in range 1 -> 999
        IntegerField('interval', field_uri='t:Interval', min=1, max=999, is_required=True),
    ]
    __slots__ = ('interval',)

    def __str__(self):
        return 'Occurs every %s day(s)' % self.interval


class Boundary(EWSElement):
    pass


class NoEndPattern(Boundary):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564699(v=exchg.150).aspx
    ELEMENT_NAME = 'NoEndRecurrence'

    FIELDS = [
        # Start date, as EWSDate
        DateField('start', field_uri='t:StartDate', is_required=True),
    ]
    __slots__ = ('start',)


class EndDatePattern(Boundary):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564536(v=exchg.150).aspx
    ELEMENT_NAME = 'EndDateRecurrence'

    FIELDS = [
        # Start date, as EWSDate
        DateField('start', field_uri='t:StartDate', is_required=True),
        # End date, as EWSDate
        DateField('end', field_uri='t:EndDate', is_required=True),
    ]
    __slots__ = ('start', 'end')


class NumberedPattern(Boundary):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580960(v=exchg.150).aspx
    ELEMENT_NAME = 'NumberedRecurrence'

    FIELDS = [
        # Start date, as EWSDate
        DateField('start', field_uri='t:StartDate', is_required=True),
        # The number of occurrences in this pattern, in range 1 -> 999
        IntegerField('number', field_uri='t:NumberOfOccurrences', min=1, max=999, is_required=True),
    ]
    __slots__ = ('start', 'number',)


class Occurrence(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565603(v=exchg.150).aspx
    ELEMENT_NAME = 'Occurrence'

    ID_ATTR = 'ItemId'
    CHANGEKEY_ATTR = 'ChangeKey'
    FIELDS = [
        IdField('item_id', field_uri=ID_ATTR),
        IdField('changekey', field_uri=CHANGEKEY_ATTR),
        # The modified start time of the item, as EWSDateTime
        DateTimeField('start', field_uri='t:Start'),
        # The modified end time of the item, as EWSDateTime
        DateTimeField('end', field_uri='t:End'),
        # The original start time of the item, as EWSDateTime
        DateTimeField('original_start', field_uri='t:OriginalStart'),
    ]
    __slots__ = ('item_id', 'changekey', 'start', 'end', 'original_start')

    @classmethod
    def id_from_xml(cls, elem):
        id_elem = elem.find(ItemId.response_tag())
        if id_elem is None:
            return None, None
        return id_elem.get(ItemId.ID_ATTR), id_elem.get(ItemId.CHANGEKEY_ATTR)

    @classmethod
    def from_xml(cls, elem, account):
        if elem.tag != cls.response_tag():
            raise ValueError('Unexpected element tag in class %s: %s vs %s' % (cls, elem.tag, cls.response_tag()))
        item_id, changekey = cls.id_from_xml(elem)
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.supported_fields()}
        elem.clear()
        return cls(item_id=item_id, changekey=changekey, **kwargs)


# Container elements:
# 'ModifiedOccurrences'
# 'DeletedOccurrences'


class FirstOccurrence(Occurrence):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565661(v=exchg.150).aspx
    ELEMENT_NAME = 'FirstOccurrence'
    __slots__ = Occurrence.__slots__


class LastOccurrence(Occurrence):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565375(v=exchg.150).aspx
    ELEMENT_NAME = 'LastOccurrence'
    __slots__ = Occurrence.__slots__


class DeletedOccurrence(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa566477(v=exchg.150).aspx
    ELEMENT_NAME = 'DeletedOccurrence'

    FIELDS = [
        # The modified start time of the item, as EWSDateTime
        DateTimeField('start', field_uri='t:Start'),
    ]
    __slots__ = ('start',)


PATTERN_CLASSES = AbsoluteYearlyPattern, RelativeYearlyPattern, AbsoluteMonthlyPattern, RelativeMonthlyPattern, \
                   WeeklyPattern, DailyPattern
BOUNDARY_CLASSES = NoEndPattern, EndDatePattern, NumberedPattern


class Recurrence(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580471(v=exchg.150).aspx
    ELEMENT_NAME = 'Recurrence'

    FIELDS = [
        EWSElementField('pattern', value_cls=Pattern),
        EWSElementField('boundary', value_cls=Boundary),
    ]

    __slots__ = ('pattern', 'boundary')

    def __init__(self, **kwargs):
        # Allow specifying a start, end and/or number as a shortcut to creating a boundary
        start = kwargs.pop('start', None)
        end = kwargs.pop('end', None)
        number = kwargs.pop('number', None)
        if any([start, end, number]):
            if 'boundary' in kwargs:
                raise ValueError("'boundary' is not allowed in combination with 'start', 'end' or 'number'")
            if start and not end and not number:
                kwargs['boundary'] = NoEndPattern(start=start)
            elif start and end and not number:
                kwargs['boundary'] = EndDatePattern(start=start, end=end)
            elif start and number and not end:
                kwargs['boundary'] = NumberedPattern(start=start, number=number)
            else:
                raise ValueError("Unsupported 'start', 'end', 'number' combination")
        super(Recurrence, self).__init__(**kwargs)

    @classmethod
    def from_xml(cls, elem, account):
        if elem is None:
            return None
        for pattern_cls in PATTERN_CLASSES:
            pattern_elem = elem.find(pattern_cls.response_tag())
            if pattern_elem is None:
                continue
            pattern = pattern_cls.from_xml(elem=pattern_elem, account=account)
            break
        else:
            pattern = None
        for boundary_cls in BOUNDARY_CLASSES:
            boundary_elem = elem.find(boundary_cls.response_tag())
            if boundary_elem is None:
                continue
            boundary = boundary_cls.from_xml(elem=boundary_elem, account=account)
            break
        else:
            boundary = None
        return cls(pattern=pattern, boundary=boundary)

    def __str__(self):
        return 'Pattern: %s, Boundary: %s' % (self.pattern, self.boundary)
