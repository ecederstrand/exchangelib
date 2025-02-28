from ..ewsdatetime import EWSDateTime as EWSDateTime, UTC as UTC
from ..fields import BooleanField as BooleanField, CharField as CharField, Choice as Choice, ChoiceField as ChoiceField, DateTimeBackedDateField as DateTimeBackedDateField, DateTimeField as DateTimeField, DecimalField as DecimalField, IntegerField as IntegerField, TaskRecurrenceField as TaskRecurrenceField, TextField as TextField, TextListField as TextListField
from .item import Item as Item
from _typeshed import Incomplete

log: Incomplete

class Task(Item):
    ELEMENT_NAME: str
    NOT_STARTED: str
    COMPLETED: str
    actual_work: Incomplete
    assigned_time: Incomplete
    billing_information: Incomplete
    change_count: Incomplete
    companies: Incomplete
    complete_date: Incomplete
    contacts: Incomplete
    delegation_state: Incomplete
    delegator: Incomplete
    due_date: Incomplete
    is_editable: Incomplete
    is_complete: Incomplete
    is_recurring: Incomplete
    is_team_task: Incomplete
    mileage: Incomplete
    owner: Incomplete
    percent_complete: Incomplete
    recurrence: Incomplete
    start_date: Incomplete
    status: Incomplete
    status_description: Incomplete
    total_work: Incomplete
    unique_body_idx: Incomplete
    FIELDS: Incomplete
    def clean(self, version: Incomplete | None = None) -> None: ...
    def complete(self) -> None: ...
