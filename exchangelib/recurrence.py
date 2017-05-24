from six import text_type

from .ewsdatetime import EWSDate, EWSDateTime
from .folders import EWSElement
from .util import create_element, set_xml_value, add_xml_child


# DayOfWeekIndex enum. See https://msdn.microsoft.com/en-us/library/office/aa581350(v=exchg.150).aspx
FIRST = 'First'
SECOND = 'Second'
THIRD = 'Third'
FOURTH = 'Fourth'
LAST = 'Last'
WEEK_NUMBERS = (FIRST, SECOND, THIRD, FOURTH, LAST)

# Month enum
JANUARY = 'January'
FEBRUARY = 'February'
MARCH = 'March'
APRIL = 'April'
MAY = 'May'
JUNE = 'June'
JULY = 'July'
AUGUST  ='August'
SEPTEMBER = 'September'
OCTOBER = 'October'
NOVEMBER  ='November'
DECEMBER = 'December'
MONTHS = (JANUARY, FEBRUARY, MARCH, APRIL, MAY, JUNE, JULY, AUGUST, SEPTEMBER, OCTOBER, NOVEMBER, DECEMBER)

# Weekday enum
MONDAY = 'Monday'
TUESDAY = 'Tuesday'
WEDNESDAY = 'Wednesday'
THURSDAY = 'Thursday'
FRIDAY = 'Friday'
SATURDAY = 'Saturday'
SUNDAY = 'Sunday'
WEEKDAY_NAMES = (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY)

# Used for weekday recurrences except weekly recurrences. E.g. for "First WeekendDay in March"
DAY = 'Day'
WEEK_DAY = 'Weekday'  # Non-weekend day
WEEKEND_DAY = 'WeekendDay'
EXTRA_WEEKDAY_OPTIONS = (DAY, WEEK_DAY, WEEKEND_DAY)

# DaysOfWeek enum: See https://msdn.microsoft.com/en-us/library/office/ee332417(v=exchg.150).aspx
WEEKDAYS = WEEKDAY_NAMES + EXTRA_WEEKDAY_OPTIONS


class Pattern(EWSElement):
    pass


class AbsoluteYearlyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564242(v=exchg.150).aspx
    ELEMENT_NAME = 'AbsoluteYearlyRecurrence'

    def __init__(self, month, day_of_month):
        """

        :param month: Month number, in range 1 -> 12
        :param day_of_month: The day of month of an occurrence, in range 1 -> 31. If a particular month has less days
        than the day_of_month value, the last day in the month is assumed
        """
        assert 1 <= month <= 12
        assert 1 <= day_of_month <= 31
        self.month = month
        self.day_of_month = day_of_month

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:DayOfMonth', self.day_of_month)
        add_xml_child(entry, 't:Month', MONTHS[self.month-1])
        return entry

    def __str__(self):
        return 'Occurs on the %s. day of the %s. month of the year' % (self.day_of_month, self.month)


class RelativeYearlyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/bb204113(v=exchg.150).aspx
    ELEMENT_NAME = 'RelativeYearlyRecurrence'

    def __init__(self, month, week_number, weekdays):
        """

        :param month: Month of the year, in range 1 -> 12
        :param week_number: Week number of the month, in range 1 -> 5. If 5 is specified, this assumes the last week of
        the month for months that have only 4 weeks
        :param weekdays: List of valid ISO 8601 weekdays, as list of numbers in range 1 -> 7 (1 being Monday)
        than the day_of_month value, the last day in the month is assumed. Alternatively, weekdays can be one of the
        DAY, WEEK_DAY or WEEKEND_DAY consts which is interpreted as the first day, weekday, or weekend day in the month,
        respectively.
        """
        assert 1 <= month <= 12
        assert 1 <= week_number <= 53
        if isinstance(weekdays, str):
            assert weekdays in EXTRA_WEEKDAY_OPTIONS
        else:
            assert len(weekdays) > 0
            for weekday in weekdays:
                assert 1 <= weekday <= 7
        self.month = month
        self.week_number = week_number
        self.weekdays = weekdays

    def to_xml(self, version):
        self.clean()
        if isinstance(self.weekdays, str):
            days_of_week = self.weekdays
        else:
            days_of_week = ' '.join(WEEKDAYS[i-1] for i in sorted(self.weekdays))
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:DaysOfWeek', days_of_week)
        add_xml_child(entry, 't:DayOfWeekIndex', WEEK_NUMBERS[self.week_number-1])
        add_xml_child(entry, 't:Month', MONTHS[self.month-1])
        return entry

    def __str__(self):
        return 'Occurs on weekdays %s in the %s. week of the %s. month of the year' % (
            self.weekdays, self.week_number, self.month
        )


class AbsoluteMonthlyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa493844(v=exchg.150).aspx
    ELEMENT_NAME = 'AbsoluteMonthlyRecurrence'

    def __init__(self, interval, day_of_month):
        """

        :param interval: Interval, in months, in range 1 -> 99
        :param day_of_month: The day of month of an occurrence, in range 1 -> 31. If a particular month has less days
        than the day_of_month value, the last day in the month is assumed
        """
        assert 1 <= interval <= 99
        assert 1 <= day_of_month <= 31
        self.interval = interval
        self.day_of_month = day_of_month

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:Interval', self.interval)
        add_xml_child(entry, 't:DayOfMonth', self.day_of_month)
        return entry

    def __str__(self):
        return 'Occurs on the %s. day of every %s. month' % (self.day_of_month, self.interval)


class RelativeMonthlyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564558(v=exchg.150).aspx
    ELEMENT_NAME = 'RelativeMonthlyRecurrence'

    def __init__(self, interval, week_number, weekdays):
        """

        :param interval: Interval, in months, in range 1 -> 99
        :param week_number: Week number of the month, in range 1 -> 5. If 5 is specified, this assumes the last week of
        the month for months that have only 4 weeks
        :param weekdays: List of valid ISO 8601 weekdays, as list of numbers in range 1-> 7 (1 being Monday)
        than the day_of_month value, the last day in the month is assumed. Alternatively, weekdays can be one of the
        DAY, WEEK_DAY or WEEKEND_DAY consts which is interpreted as the first day, weekday, or weekend day in the month,
        respectively.
        """
        assert 1 <= week_number <= 53
        assert len(weekdays) > 0
        if isinstance(weekdays, str):
            assert weekdays in EXTRA_WEEKDAY_OPTIONS
        else:
            assert len(weekdays) > 0
            for weekday in weekdays:
                assert 1 <= weekday <= 7
        self.interval = interval
        self.week_number = week_number
        self.weekdays = weekdays

    def to_xml(self, version):
        self.clean()
        if isinstance(self.weekdays, str):
            days_of_week = self.weekdays
        else:
            days_of_week = ' '.join(WEEKDAYS[i-1] for i in sorted(self.weekdays))
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:Interval', self.interval)
        add_xml_child(entry, 't:DaysOfWeek', days_of_week)
        add_xml_child(entry, 't:DayOfWeekIndex', WEEK_NUMBERS[self.week_number-1])
        return entry

    def __str__(self):
        return 'Occurs on weekdays %s in the %s. week of every %s. month' % (
            self.weekdays, self.week_number, self.interval
        )


class WeeklyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa563500(v=exchg.150).aspx
    ELEMENT_NAME = 'WeeklyRecurrence'

    def __init__(self, interval, weekdays):
        """

        :param interval: Interval, in weeks, in range 1 -> 99
        :param weekdays: List of valid ISO 8601 weekdays, as list of numbers in range 1-> 7 (1 being Monday)
        """
        assert 1 <= interval <= 99
        assert len(weekdays) > 0
        for weekday in weekdays:
            assert 1 <= weekday <= 7
        self.interval = interval
        self.weekdays = weekdays

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:Interval', self.interval)
        add_xml_child(entry, 't:DaysOfWeek', ' '.join(WEEKDAYS[i-1] for i in sorted(self.weekdays)))
        add_xml_child(entry, 't:FirstDayOfWeek', WEEKDAYS[0])  # TODO: forcing Monday may not be correct. Use account.locale?
        return entry

    def __str__(self):
        return 'Occurs on weekdays %s of every %s. week' % (self.weekdays, self.interval)


class DailyPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa563228(v=exchg.150).aspx
    ELEMENT_NAME = 'DailyRecurrence'

    def __init__(self, interval):
        """

        :param interval: Interval, in days, in range 1 -> 999
        """
        assert 1 <= interval <= 999
        self.interval = interval

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:Interval', self.interval)
        return entry

    def __str__(self):
        return 'Occurs every %s. day' % (self.interval)


class NoEndPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564699(v=exchg.150).aspx
    ELEMENT_NAME = 'NoEndRecurrence'

    def __init__(self, start):
        """

        :param start:  Start date, as EWSDate
        """
        assert isinstance(start, EWSDate)
        self.start = start

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:StartDate', self.start)
        return entry


class EndDatePattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa564536(v=exchg.150).aspx
    ELEMENT_NAME = 'NoEndRecurrence'

    def __init__(self, start, end):
        """

        :param start: Start date, as EWSDate
        :param end: End date, as EWSDate
        """
        assert isinstance(start, EWSDate)
        assert isinstance(end, EWSDate)
        self.start = start
        self.end = end

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:StartDate', self.start)
        add_xml_child(entry, 't:EndDate', self.end)
        return entry


class NumberedPattern(Pattern):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580960(v=exchg.150).aspx
    ELEMENT_NAME = 'NumberedRecurrence'

    def __init__(self, start, number):
        """

        :param start: Start date, as EWSDate
        :param number: The number of occurrences in this pattern
        """
        assert isinstance(start, EWSDate)
        assert isinstance(number, int)
        self.start = start
        self.number = number

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:StartDate', self.start)
        add_xml_child(entry, 't:NumberOfOccurrences', self.number)
        return entry


class Occurrence(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565603(v=exchg.150).aspx
    ELEMENT_NAME = 'Occurrence'

    def __init__(self, item, start, end, original_start):
        """

        :param item: The item_id and changekey of a modified item occurrence
        :param start: The modified start time of the item, as EWSDateTime
        :param end: The modified end time of the item, as EWSDateTime
        :param original_start: The original start time of the item, as EWSDateTime
        """
        assert isinstance(start, EWSDateTime)
        assert isinstance(end, EWSDateTime)
        assert isinstance(original_start, EWSDateTime)
        self.item = item
        self.start = start
        self.end = end
        self.original_start = original_start

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:Start', self.start)
        add_xml_child(entry, 't:End', self.end)
        add_xml_child(entry, 't:OriginalStart', self.original_start)
        return entry

# Container elements:
# 'ModifiedOccurrences'
# 'DeletedOccurrences'

class FirstOccurrence(Occurrence):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565661(v=exchg.150).aspx
    ELEMENT_NAME = 'FirstOccurrence'


class LastOccurrence(Occurrence):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565375(v=exchg.150).aspx
    ELEMENT_NAME = 'LastOccurrence'


class DeletedOccurrence(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa566477(v=exchg.150).aspx
    ELEMENT_NAME = 'DeletedOccurrence'

    def __init__(self, start):
        self.start = start

    def to_xml(self, version):
        self.clean()
        entry = create_element(self.request_tag())
        add_xml_child(entry, 't:Start', self.start)
        return entry


class Recurrence(EWSElement):
    # This is where the fun begins!
    pass
