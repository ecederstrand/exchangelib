import datetime
from decimal import Decimal

from exchangelib.ewsdatetime import UTC_NOW
from exchangelib.folders import Tasks
from exchangelib.items import Task
from exchangelib.recurrence import DailyPattern, DailyRegeneration, TaskRecurrence

from .test_basics import CommonItemTest


class TasksTest(CommonItemTest):
    """Test Task instances and the Tasks folder."""

    TEST_FOLDER = "tasks"
    FOLDER_CLASS = Tasks
    ITEM_CLASS = Task

    def test_task_validation(self):
        tz = self.account.default_timezone
        task = Task(due_date=datetime.date(2017, 1, 1), start_date=datetime.date(2017, 2, 1))
        task.clean()
        # We reset due date if it's before start date
        self.assertEqual(task.due_date, datetime.date(2017, 2, 1))
        self.assertEqual(task.due_date, task.start_date)

        task = Task(complete_date=datetime.datetime(2099, 1, 1, tzinfo=tz), status=Task.NOT_STARTED)
        task.clean()
        # We reset status if complete_date is set
        self.assertEqual(task.status, Task.COMPLETED)
        # We also reset complete date to now() if it's in the future
        self.assertEqual(task.complete_date.date(), datetime.datetime.utcnow().date())

        task = Task(complete_date=datetime.datetime(2017, 1, 1, tzinfo=tz), start_date=datetime.date(2017, 2, 1))
        task.clean()
        # We also reset complete date to start_date if it's before start_date
        self.assertEqual(task.complete_date.date(), task.start_date)

        task = Task(percent_complete=Decimal("50.0"), status=Task.COMPLETED)
        task.clean()
        # We reset percent_complete to 100.0 if state is completed
        self.assertEqual(task.percent_complete, Decimal(100))

        task = Task(percent_complete=Decimal("50.0"), status=Task.NOT_STARTED)
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

    def test_recurring_item(self):
        """Test that changes to an occurrence of a recurring task cause one-off tasks to be generated when the
        following updates are made:
        * The status property of a regenerating or nonregenerating recurrent task is set to Completed.
        * The start date or end date of a nonregenerating recurrent task is changed.
        """
        # Create a master non-regenerating item with 4 daily occurrences
        start = datetime.date(2016, 1, 1)
        recurrence = TaskRecurrence(pattern=DailyPattern(interval=1), start=start, number=4)
        nonregenerating_item = self.ITEM_CLASS(
            folder=self.test_folder,
            categories=self.categories,
            recurrence=recurrence,
        ).save()
        nonregenerating_item.refresh()
        master_item_id = nonregenerating_item.id
        self.assertEqual(nonregenerating_item.is_recurring, True)
        self.assertEqual(nonregenerating_item.change_count, 1)
        self.assertEqual(self.test_folder.filter(categories__contains=self.categories).count(), 1)

        # Change the start date. We should see a new task appear.
        master_item = self.get_item_by_id((master_item_id, None), folder=self.test_folder)
        master_item.recurrence.boundary.start = datetime.date(2016, 2, 1)
        occurrence_item = master_item.save()
        occurrence_item.refresh()
        self.assertEqual(occurrence_item.is_recurring, False)  # This is now the occurrence
        self.assertEqual(self.test_folder.filter(categories__contains=self.categories).count(), 2)

        # Check fields on the recurring item
        master_item = self.get_item_by_id((master_item_id, None), folder=self.test_folder)
        self.assertEqual(master_item.change_count, 2)
        self.assertEqual(master_item.due_date, datetime.date(2016, 1, 2))  # This is the next occurrence
        self.assertEqual(master_item.recurrence.boundary.number, 3)  # One less

        # Change the status to 'Completed'. We should see a new task appear.
        master_item.status = Task.COMPLETED
        occurrence_item = master_item.save()
        occurrence_item.refresh()
        self.assertEqual(occurrence_item.is_recurring, False)  # This is now the occurrence
        self.assertEqual(self.test_folder.filter(categories__contains=self.categories).count(), 3)

        # Check fields on the recurring item
        master_item = self.get_item_by_id((master_item_id, None), folder=self.test_folder)
        self.assertEqual(master_item.change_count, 3)
        self.assertEqual(master_item.due_date, datetime.date(2016, 2, 1))  # This is the next occurrence
        self.assertEqual(master_item.recurrence.boundary.number, 2)  # One less

        self.test_folder.filter(categories__contains=self.categories).delete()

        # Create a master regenerating item with 4 daily occurrences
        recurrence = TaskRecurrence(pattern=DailyRegeneration(interval=1), start=start, number=4)
        regenerating_item = self.ITEM_CLASS(
            folder=self.test_folder,
            categories=self.categories,
            recurrence=recurrence,
        ).save()
        regenerating_item.refresh()
        master_item_id = regenerating_item.id
        self.assertEqual(regenerating_item.is_recurring, True)
        self.assertEqual(regenerating_item.change_count, 1)
        self.assertEqual(self.test_folder.filter(categories__contains=self.categories).count(), 1)

        # Change the start date. We should *not* see a new task appear.
        master_item = self.get_item_by_id((master_item_id, None), folder=self.test_folder)
        master_item.recurrence.boundary.start = datetime.date(2016, 1, 2)
        occurrence_item = master_item.save()
        occurrence_item.refresh()
        self.assertEqual(occurrence_item.id, master_item.id)  # This is not an occurrence. No new task was created
        self.assertEqual(self.test_folder.filter(categories__contains=self.categories).count(), 1)

        # Change the status to 'Completed'. We should see a new task appear.
        master_item.status = Task.COMPLETED
        occurrence_item = master_item.save()
        occurrence_item.refresh()
        self.assertEqual(occurrence_item.is_recurring, False)  # This is now the occurrence
        self.assertEqual(self.test_folder.filter(categories__contains=self.categories).count(), 2)

        # Check fields on the recurring item
        master_item = self.get_item_by_id((master_item_id, None), folder=self.test_folder)
        self.assertEqual(master_item.change_count, 2)
        # The due date is the next occurrence after today. This is apparently calculated in UTC, which is incorrect.
        self.assertEqual(master_item.due_date, UTC_NOW().date() + datetime.timedelta(days=1))
        self.assertEqual(master_item.recurrence.boundary.number, 3)  # One less
