from .fields import DateOrDateTimeField as DateOrDateTimeField, DateTimeField as DateTimeField, EWSElementField as EWSElementField, EnumField as EnumField, IdElementField as IdElementField, IntegerField as IntegerField, MONTHS as MONTHS, WEEKDAYS as WEEKDAYS, WEEKDAY_NAMES as WEEKDAY_NAMES, WEEK_NUMBERS as WEEK_NUMBERS, WeekdaysField as WeekdaysField
from .properties import EWSElement as EWSElement, EWSMeta as EWSMeta, IdChangeKeyMixIn as IdChangeKeyMixIn, ItemId as ItemId
from _typeshed import Incomplete

log: Incomplete

class Pattern(EWSElement, metaclass=EWSMeta): ...
class Regeneration(Pattern, metaclass=EWSMeta): ...

class AbsoluteYearlyPattern(Pattern):
    ELEMENT_NAME: str
    day_of_month: Incomplete
    month: Incomplete

class RelativeYearlyPattern(Pattern):
    ELEMENT_NAME: str
    weekday: Incomplete
    week_number: Incomplete
    month: Incomplete

class AbsoluteMonthlyPattern(Pattern):
    ELEMENT_NAME: str
    interval: Incomplete
    day_of_month: Incomplete

class RelativeMonthlyPattern(Pattern):
    ELEMENT_NAME: str
    interval: Incomplete
    weekday: Incomplete
    week_number: Incomplete

class WeeklyPattern(Pattern):
    ELEMENT_NAME: str
    interval: Incomplete
    weekdays: Incomplete
    first_day_of_week: Incomplete

class DailyPattern(Pattern):
    ELEMENT_NAME: str
    interval: Incomplete

class YearlyRegeneration(Regeneration):
    ELEMENT_NAME: str
    interval: Incomplete

class MonthlyRegeneration(Regeneration):
    ELEMENT_NAME: str
    interval: Incomplete

class WeeklyRegeneration(Regeneration):
    ELEMENT_NAME: str
    interval: Incomplete

class DailyRegeneration(Regeneration):
    ELEMENT_NAME: str
    interval: Incomplete

class Boundary(EWSElement, metaclass=EWSMeta): ...

class NoEndPattern(Boundary):
    ELEMENT_NAME: str
    start: Incomplete

class EndDatePattern(Boundary):
    ELEMENT_NAME: str
    start: Incomplete
    end: Incomplete

class NumberedPattern(Boundary):
    ELEMENT_NAME: str
    start: Incomplete
    number: Incomplete

class Occurrence(IdChangeKeyMixIn):
    ELEMENT_NAME: str
    ID_ELEMENT_CLS = ItemId
    start: Incomplete
    end: Incomplete
    original_start: Incomplete

class FirstOccurrence(Occurrence):
    ELEMENT_NAME: str

class LastOccurrence(Occurrence):
    ELEMENT_NAME: str

class DeletedOccurrence(EWSElement):
    ELEMENT_NAME: str
    start: Incomplete

PATTERN_CLASSES: Incomplete
REGENERATION_CLASSES: Incomplete
BOUNDARY_CLASSES: Incomplete

class Recurrence(EWSElement):
    ELEMENT_NAME: str
    PATTERN_CLASS_MAP: Incomplete
    BOUNDARY_CLASS_MAP: Incomplete
    pattern: Incomplete
    boundary: Incomplete
    def __init__(self, **kwargs) -> None: ...
    @classmethod
    def from_xml(cls, elem, account): ...

class TaskRecurrence(Recurrence):
    PATTERN_CLASS_MAP: Incomplete
