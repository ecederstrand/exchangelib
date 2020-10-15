import datetime
from decimal import Decimal

from exchangelib.ewsdatetime import EWSDate, EWSDateTime, EWSTimeZone, UTC_NOW
from exchangelib.folders import Tasks
from exchangelib.items import Task

from .test_basics import CommonItemTest


class TasksTest(CommonItemTest):
    TEST_FOLDER = 'tasks'
    FOLDER_CLASS = Tasks
    ITEM_CLASS = Task

    def test_task_validation(self):
        tz = EWSTimeZone('Europe/Copenhagen')
        task = Task(due_date=EWSDate(2017, 1, 1), start_date=EWSDate(2017, 2, 1))
        task.clean()
        # We reset due date if it's before start date
        self.assertEqual(task.due_date, EWSDate(2017, 2, 1))
        self.assertEqual(task.due_date, task.start_date)

        task = Task(complete_date=EWSDateTime(2099, 1, 1, tzinfo=tz), status=Task.NOT_STARTED)
        task.clean()
        # We reset status if complete_date is set
        self.assertEqual(task.status, Task.COMPLETED)
        # We also reset complete date to now() if it's in the future
        self.assertEqual(task.complete_date.date(), UTC_NOW().date())

        task = Task(complete_date=EWSDateTime(2017, 1, 1, tzinfo=tz), start_date=EWSDate(2017, 2, 1))
        task.clean()
        # We also reset complete date to start_date if it's before start_date
        self.assertEqual(task.complete_date.date(), task.start_date)

        task = Task(percent_complete=Decimal('50.0'), status=Task.COMPLETED)
        task.clean()
        # We reset percent_complete to 100.0 if state is completed
        self.assertEqual(task.percent_complete, Decimal(100))

        task = Task(percent_complete=Decimal('50.0'), status=Task.NOT_STARTED)
        task.clean()
        # We reset percent_complete to 0.0 if state is not_started
        self.assertEqual(task.percent_complete, Decimal(0))

    def test_complete(self):
        item = self.get_test_item().save()
        item.refresh()
        self.assertNotEqual(item.status, Task.COMPLETED)
        self.assertNotEqual(item.percent_complete, Decimal(100))
        item.complete()
        item.refresh()
        self.assertEqual(item.status, Task.COMPLETED)
        self.assertEqual(item.percent_complete, Decimal(100))
