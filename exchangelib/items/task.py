from decimal import Decimal
import logging

from ..ewsdatetime import UTC_NOW
from ..fields import BooleanField, IntegerField, DecimalField, TextField, ChoiceField, DateTimeField, Choice, \
    CharField, TextListField
from ..properties import Fields
from .item import Item

log = logging.getLogger(__name__)


class Task(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/task"""
    ELEMENT_NAME = 'Task'
    NOT_STARTED = 'NotStarted'
    COMPLETED = 'Completed'
    LOCAL_FIELDS = Fields(
        IntegerField('actual_work', field_uri='task:ActualWork', min=0),
        DateTimeField('assigned_time', field_uri='task:AssignedTime', is_read_only=True),
        TextField('billing_information', field_uri='task:BillingInformation'),
        IntegerField('change_count', field_uri='task:ChangeCount', is_read_only=True, min=0),
        TextListField('companies', field_uri='task:Companies'),
        # 'complete_date' can be set, but is ignored by the server, which sets it to now()
        DateTimeField('complete_date', field_uri='task:CompleteDate', is_read_only=True),
        TextListField('contacts', field_uri='task:Contacts'),
        ChoiceField('delegation_state', field_uri='task:DelegationState', choices={
            Choice('NoMatch'), Choice('OwnNew'), Choice('Owned'), Choice('Accepted'), Choice('Declined'), Choice('Max')
        }, is_read_only=True),
        CharField('delegator', field_uri='task:Delegator', is_read_only=True),
        DateTimeField('due_date', field_uri='task:DueDate'),
        BooleanField('is_editable', field_uri='task:IsAssignmentEditable', is_read_only=True),
        BooleanField('is_complete', field_uri='task:IsComplete', is_read_only=True),
        BooleanField('is_recurring', field_uri='task:IsRecurring', is_read_only=True),
        BooleanField('is_team_task', field_uri='task:IsTeamTask', is_read_only=True),
        TextField('mileage', field_uri='task:Mileage'),
        CharField('owner', field_uri='task:Owner', is_read_only=True),
        DecimalField('percent_complete', field_uri='task:PercentComplete', is_required=True, default=Decimal(0.0),
                     min=Decimal(0), max=Decimal(100), is_searchable=False),
        # Placeholder for Recurrence
        DateTimeField('start_date', field_uri='task:StartDate'),
        ChoiceField('status', field_uri='task:Status', choices={
            Choice(NOT_STARTED), Choice('InProgress'), Choice(COMPLETED), Choice('WaitingOnOthers'), Choice('Deferred')
        }, is_required=True, is_searchable=False, default=NOT_STARTED),
        CharField('status_description', field_uri='task:StatusDescription', is_read_only=True),
        IntegerField('total_work', field_uri='task:TotalWork', min=0),
    )
    FIELDS = Item.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)

    def clean(self, version=None):
        # pylint: disable=access-member-before-definition
        super().clean(version=version)
        if self.due_date and self.start_date and self.due_date < self.start_date:
            log.warning("'due_date' must be greater than 'start_date' (%s vs %s). Resetting 'due_date'",
                        self.due_date, self.start_date)
            self.due_date = self.start_date
        if self.complete_date:
            if self.status != self.COMPLETED:
                log.warning("'status' must be '%s' when 'complete_date' is set (%s). Resetting",
                            self.COMPLETED, self.status)
                self.status = self.COMPLETED
            now = UTC_NOW()
            if (self.complete_date - now).total_seconds() > 120:
                # Reset complete_date values that are in the future
                # 'complete_date' can be set automatically by the server. Allow some grace between local and server time
                log.warning("'complete_date' must be in the past (%s vs %s). Resetting", self.complete_date, now)
                self.complete_date = now
            if self.start_date and self.complete_date < self.start_date:
                log.warning("'complete_date' must be greater than 'start_date' (%s vs %s). Resetting",
                            self.complete_date, self.start_date)
                self.complete_date = self.start_date
        if self.percent_complete is not None:
            if self.status == self.COMPLETED and self.percent_complete != Decimal(100):
                # percent_complete must be 100% if task is complete
                log.warning("'percent_complete' must be 100 when 'status' is '%s' (%s). Resetting",
                            self.COMPLETED, self.percent_complete)
                self.percent_complete = Decimal(100)
            elif self.status == self.NOT_STARTED and self.percent_complete != Decimal(0):
                # percent_complete must be 0% if task is not started
                log.warning("'percent_complete' must be 0 when 'status' is '%s' (%s). Resetting",
                            self.NOT_STARTED, self.percent_complete)
                self.percent_complete = Decimal(0)

    def complete(self):
        # pylint: disable=access-member-before-definition
        # A helper method to mark a task as complete on the server
        self.status = Task.COMPLETED
        self.percent_complete = Decimal(100)
        self.save()
