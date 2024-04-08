import datetime
import logging
from decimal import Decimal

from ..ewsdatetime import UTC, EWSDateTime
from ..fields import (
    BooleanField,
    CharField,
    Choice,
    ChoiceField,
    DateTimeBackedDateField,
    DateTimeField,
    DecimalField,
    IntegerField,
    TaskRecurrenceField,
    TextField,
    TextListField,
)
from .item import Item

log = logging.getLogger(__name__)


class Task(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/task"""

    ELEMENT_NAME = "Task"
    NOT_STARTED = "NotStarted"
    COMPLETED = "Completed"

    actual_work = IntegerField(field_uri="task:ActualWork", min=0)
    assigned_time = DateTimeField(field_uri="task:AssignedTime", is_read_only=True)
    billing_information = TextField(field_uri="task:BillingInformation")
    change_count = IntegerField(field_uri="task:ChangeCount", is_read_only=True, min=0)
    companies = TextListField(field_uri="task:Companies")
    # 'complete_date' can be set, but is ignored by the server, which sets it to now()
    complete_date = DateTimeField(field_uri="task:CompleteDate", is_read_only=True)
    contacts = TextListField(field_uri="task:Contacts")
    delegation_state = ChoiceField(
        field_uri="task:DelegationState",
        choices={
            Choice("NoMatch"),
            Choice("OwnNew"),
            Choice("Owned"),
            Choice("Accepted"),
            Choice("Declined"),
            Choice("Max"),
        },
        is_read_only=True,
    )
    delegator = CharField(field_uri="task:Delegator", is_read_only=True)
    due_date = DateTimeBackedDateField(field_uri="task:DueDate")
    is_editable = BooleanField(field_uri="task:IsAssignmentEditable", is_read_only=True)
    is_complete = BooleanField(field_uri="task:IsComplete", is_read_only=True)
    is_recurring = BooleanField(field_uri="task:IsRecurring", is_read_only=True)
    is_team_task = BooleanField(field_uri="task:IsTeamTask", is_read_only=True)
    mileage = TextField(field_uri="task:Mileage")
    owner = CharField(field_uri="task:Owner", is_read_only=True)
    percent_complete = DecimalField(
        field_uri="task:PercentComplete",
        is_required=True,
        default=Decimal(0.0),
        min=Decimal(0),
        max=Decimal(100),
        is_searchable=False,
    )
    recurrence = TaskRecurrenceField(field_uri="task:Recurrence", is_searchable=False)
    start_date = DateTimeBackedDateField(field_uri="task:StartDate")
    status = ChoiceField(
        field_uri="task:Status",
        choices={
            Choice(NOT_STARTED),
            Choice("InProgress"),
            Choice(COMPLETED),
            Choice("WaitingOnOthers"),
            Choice("Deferred"),
        },
        is_required=True,
        is_searchable=False,
        default=NOT_STARTED,
    )
    status_description = CharField(field_uri="task:StatusDescription", is_read_only=True)
    total_work = IntegerField(field_uri="task:TotalWork", min=0)

    # O365 throws ErrorInternalServerError "[0x004f0102] MapiReplyToBlob" if UniqueBody is requested
    unique_body_idx = Item.FIELDS.index_by_name("unique_body")
    FIELDS = Item.FIELDS[:unique_body_idx] + Item.FIELDS[unique_body_idx + 1 :]

    def clean(self, version=None):
        super().clean(version=version)
        if self.due_date and self.start_date and self.due_date < self.start_date:
            log.warning(
                "'due_date' must be greater than 'start_date' (%s vs %s). Resetting 'due_date'",
                self.due_date,
                self.start_date,
            )
            self.due_date = self.start_date
        if self.complete_date:
            if self.status != self.COMPLETED:
                log.warning(
                    "'status' must be '%s' when 'complete_date' is set (%s). Resetting", self.COMPLETED, self.status
                )
                self.status = self.COMPLETED
            now = datetime.datetime.now(tz=UTC)
            if (self.complete_date - now).total_seconds() > 120:
                # Reset complete_date values that are in the future
                # 'complete_date' can be set automatically by the server. Allow some grace between local and server time
                log.warning("'complete_date' must be in the past (%s vs %s). Resetting", self.complete_date, now)
                self.complete_date = now
            if self.start_date and self.complete_date.date() < self.start_date:
                log.warning(
                    "'complete_date' must be greater than 'start_date' (%s vs %s). Resetting",
                    self.complete_date,
                    self.start_date,
                )
                self.complete_date = EWSDateTime.combine(self.start_date, datetime.time(0, 0)).replace(tzinfo=UTC)
        if self.percent_complete is not None:
            if self.status == self.COMPLETED and self.percent_complete != Decimal(100):
                # percent_complete must be 100% if task is complete
                log.warning(
                    "'percent_complete' must be 100 when 'status' is '%s' (%s). Resetting",
                    self.COMPLETED,
                    self.percent_complete,
                )
                self.percent_complete = Decimal(100)
            elif self.status == self.NOT_STARTED and self.percent_complete != Decimal(0):
                # percent_complete must be 0% if task is not started
                log.warning(
                    "'percent_complete' must be 0 when 'status' is '%s' (%s). Resetting",
                    self.NOT_STARTED,
                    self.percent_complete,
                )
                self.percent_complete = Decimal(0)

    def complete(self):
        # A helper method to mark a task as complete on the server
        self.status = Task.COMPLETED
        self.percent_complete = Decimal(100)
        self.save()
