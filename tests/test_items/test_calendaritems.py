import datetime

from exchangelib.errors import ErrorInvalidOperation, ErrorItemNotFound
from exchangelib.ewsdatetime import EWSDateTime, EWSDate, UTC
from exchangelib.folders import Calendar
from exchangelib.items import CalendarItem, BulkCreateResult
from exchangelib.items.calendar_item import SINGLE, OCCURRENCE, EXCEPTION, RECURRING_MASTER
from exchangelib.recurrence import Recurrence, DailyPattern, Occurrence, FirstOccurrence, LastOccurrence, \
    DeletedOccurrence

from ..common import get_random_string, get_random_datetime_range, get_random_date
from .test_basics import CommonItemTest


class CalendarTest(CommonItemTest):
    TEST_FOLDER = 'calendar'
    FOLDER_CLASS = Calendar
    ITEM_CLASS = CalendarItem

    def match_cat(self, i):
        return set(i.categories or []) == set(self.categories)

    def test_cancel(self):
        item = self.get_test_item().save()
        res = item.cancel()  # Returns (id, changekey) of cancelled item
        self.assertIsInstance(res, BulkCreateResult)
        with self.assertRaises(ErrorItemNotFound):
            # Item is already cancelled
            item.cancel()

    def test_updating_timestamps(self):
        # Test that we can update an item without changing anything, and maintain the hidden timezone fields as local
        # timezones, and that returned timestamps are in UTC.
        item = self.get_test_item()
        item.reminder_is_set = True
        item.is_all_day = False
        item.recurrence = None
        item.save()
        item.refresh()
        self.assertEqual(item.type, SINGLE)
        for i in self.account.calendar.filter(categories__contains=self.categories).only('start', 'end', 'categories'):
            self.assertEqual(i.start, item.start)
            self.assertEqual(i.start.tzinfo, UTC)
            self.assertEqual(i.end, item.end)
            self.assertEqual(i.end.tzinfo, UTC)
            self.assertEqual(i._start_timezone, self.account.default_timezone)
            self.assertEqual(i._end_timezone, self.account.default_timezone)
            i.save(update_fields=['start', 'end'])
            self.assertEqual(i.start, item.start)
            self.assertEqual(i.start.tzinfo, UTC)
            self.assertEqual(i.end, item.end)
            self.assertEqual(i.end.tzinfo, UTC)
            self.assertEqual(i._start_timezone, self.account.default_timezone)
            self.assertEqual(i._end_timezone, self.account.default_timezone)
        for i in self.account.calendar.filter(categories__contains=self.categories).only('start', 'end', 'categories'):
            self.assertEqual(i.start, item.start)
            self.assertEqual(i.start.tzinfo, UTC)
            self.assertEqual(i.end, item.end)
            self.assertEqual(i.end.tzinfo, UTC)
            self.assertEqual(i._start_timezone, self.account.default_timezone)
            self.assertEqual(i._end_timezone, self.account.default_timezone)
            i.delete()

    def test_update_to_non_utc_datetime(self):
        # Test updating with non-UTC datetime values. This is a separate code path in UpdateItem code
        item = self.get_test_item()
        item.reminder_is_set = True
        item.is_all_day = False
        item.save()
        # Update start, end and recurrence with timezoned datetimes. For some reason, EWS throws
        # 'ErrorOccurrenceTimeSpanTooBig' is we go back in time.
        start = get_random_date(start_date=item.start.date() + datetime.timedelta(days=1))
        dt_start, dt_end = [
            dt.astimezone(self.account.default_timezone) for dt in
            get_random_datetime_range(start_date=start, end_date=start, tz=self.account.default_timezone)
        ]
        item.start, item.end = dt_start, dt_end
        item.recurrence.boundary.start = dt_start.date()
        item.save()
        item.refresh()
        self.assertEqual(item.start, dt_start)
        self.assertEqual(item.end, dt_end)

    def test_all_day_datetimes(self):
        # Test that we can use plain dates for start and end values for all-day items
        start = get_random_date()
        start_dt, end_dt = get_random_datetime_range(
            start_date=start,
            end_date=start + datetime.timedelta(days=365),
            tz=self.account.default_timezone
        )
        # Assign datetimes for start and end
        item = self.ITEM_CLASS(folder=self.test_folder, start=start_dt, end=end_dt, is_all_day=True,
                               categories=self.categories).save()

        # Returned item start and end values should be EWSDate instances
        item = self.test_folder.all().only('is_all_day', 'start', 'end').get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.is_all_day, True)
        self.assertEqual(item.start, start_dt.date())
        self.assertEqual(item.end, end_dt.date())
        item.save()  # Make sure we can update
        item.delete()

        # We are also allowed to assign plain dates as values for all-day items
        item = self.ITEM_CLASS(folder=self.test_folder, start=start_dt.date(), end=end_dt.date(), is_all_day=True,
                               categories=self.categories).save()

        # Returned item start and end values should be EWSDate instances
        item = self.test_folder.all().only('is_all_day', 'start', 'end').get(id=item.id, changekey=item.changekey)
        self.assertEqual(item.is_all_day, True)
        self.assertEqual(item.start, start_dt.date())
        self.assertEqual(item.end, end_dt.date())
        item.save()  # Make sure we can update

    def test_view(self):
        item1 = self.ITEM_CLASS(
            account=self.account,
            folder=self.test_folder,
            subject=get_random_string(16),
            start=EWSDateTime(2016, 1, 1, 8, tzinfo=self.account.default_timezone),
            end=EWSDateTime(2016, 1, 1, 10, tzinfo=self.account.default_timezone),
            categories=self.categories,
        )
        item2 = self.ITEM_CLASS(
            account=self.account,
            folder=self.test_folder,
            subject=get_random_string(16),
            start=EWSDateTime(2016, 2, 1, 8, tzinfo=self.account.default_timezone),
            end=EWSDateTime(2016, 2, 1, 10, tzinfo=self.account.default_timezone),
            categories=self.categories,
        )
        self.test_folder.bulk_create(items=[item1, item2])
        qs = self.test_folder.view(start=item1.start, end=item2.end)

        # Test missing args
        with self.assertRaises(TypeError):
            self.test_folder.view()
        # Test bad args
        with self.assertRaises(ValueError):
            list(self.test_folder.view(start=item1.end, end=item1.start))
        with self.assertRaises(TypeError):
            list(self.test_folder.view(start='xxx', end=item1.end))
        with self.assertRaises(ValueError):
            list(self.test_folder.view(start=item1.start, end=item1.end, max_items=0))

        # Test dates
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.start, end=item1.end) if self.match_cat(i)]),
            1
        )
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.start, end=item2.end) if self.match_cat(i)]),
            2
        )
        # Edge cases. Get view from end of item1 to start of item2. Should logically return 0 items, but Exchange wants
        # it differently and returns item1 even though there is no overlap.
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.end, end=item2.start) if self.match_cat(i)]),
            1
        )
        self.assertEqual(
            len([i for i in self.test_folder.view(start=item1.start, end=item2.start) if self.match_cat(i)]),
            1
        )

        # Test max_items
        self.assertEqual(
            len([
                i for i in self.test_folder.view(start=item1.start, end=item2.end, max_items=9999) if self.match_cat(i)
            ]),
            2
        )
        self.assertEqual(
            self.test_folder.view(start=item1.start, end=item2.end, max_items=1).count(),
            1
        )

        # Test client-side ordering
        self.assertListEqual(
            [i.subject for i in qs.order_by('subject') if self.match_cat(i)], sorted([item1.subject, item2.subject])
        )
        # Test client-side ordering on a field with no default value and no default value_cls value
        self.assertListEqual(
            [i.start for i in qs.order_by('-start') if self.match_cat(i)], [item2.start, item1.start]
        )
        # Test client-side ordering on multiple fields. Intentionally sort first on a field where values are equal,
        # to see that we can sort on the 2nd field.
        self.assertListEqual(
            [i.start for i in qs.order_by('categories', '-start') if self.match_cat(i)], [item2.start, item1.start]
        )

        # Test chaining
        self.assertTrue(qs.count() >= 2)
        with self.assertRaises(ErrorInvalidOperation):
            qs.filter(subject=item1.subject).count()  # EWS does not allow restrictions
        self.assertListEqual(
            [i for i in qs.order_by('subject').values('subject') if i['subject'] in (item1.subject, item2.subject)],
            [{'subject': s} for s in sorted([item1.subject, item2.subject])]
        )

    def test_client_side_ordering_on_mixed_all_day_and_normal(self):
        # Test that client-side ordering on start and end fields works for items that are a mix of normal an all-day
        # items. This requires us to compare EWSDateTime -> EWSDate values which is not allowed by default (EWSDate ->
        # EWSDateTime *is* allowed).
        start = EWSDateTime(2016, 1, 1, 8, tzinfo=self.account.default_timezone)
        end = EWSDateTime(2016, 1, 1, 10, tzinfo=self.account.default_timezone)
        all_day_date = (start - datetime.timedelta(days=1)).date()
        item1 = self.ITEM_CLASS(
            account=self.account,
            folder=self.test_folder,
            subject=get_random_string(16),
            start=all_day_date,
            end=all_day_date,
            is_all_day=True,
            categories=self.categories,
        )
        item2 = self.ITEM_CLASS(
            account=self.account,
            folder=self.test_folder,
            subject=get_random_string(16),
            start=start,
            end=end,
            categories=self.categories,
        )
        self.test_folder.bulk_create(items=[item1, item2])
        list(self.test_folder.view(start=start - datetime.timedelta(days=1), end=end).order_by('start'))
        list(self.test_folder.view(start=start - datetime.timedelta(days=1), end=end).order_by('-start'))

    def test_recurring_item(self):
        # Create a recurring calendar item. Test that occurrence fields are correct on the master item

        # Create a master item with 4 daily occurrences from 8:00 to 10:00. 'start' and 'end' are values for the first
        # occurrence.
        start = EWSDateTime(2016, 1, 1, 8, tzinfo=self.account.default_timezone)
        end = EWSDateTime(2016, 1, 1, 10, tzinfo=self.account.default_timezone)
        master_item = self.ITEM_CLASS(
            folder=self.test_folder,
            start=start,
            end=end,
            recurrence=Recurrence(pattern=DailyPattern(interval=1), start=start.date(), number=4),
            categories=self.categories,
        ).save()

        master_item.refresh()
        self.assertEqual(master_item.is_recurring, False)
        self.assertEqual(master_item.type, RECURRING_MASTER)
        self.assertIsInstance(master_item.first_occurrence, FirstOccurrence)
        self.assertEqual(master_item.first_occurrence.start, start)
        self.assertEqual(master_item.first_occurrence.end, end)
        self.assertIsInstance(master_item.last_occurrence, LastOccurrence)
        self.assertEqual(master_item.last_occurrence.start, start + datetime.timedelta(days=3))
        self.assertEqual(master_item.last_occurrence.end, end + datetime.timedelta(days=3))
        self.assertEqual(master_item.modified_occurrences, None)
        self.assertEqual(master_item.deleted_occurrences, None)

        # Test occurrences as full calendar items, unfolded from the master
        range_start, range_end = start, end + datetime.timedelta(days=3)
        unfolded = [i for i in self.test_folder.view(start=range_start, end=range_end) if self.match_cat(i)]
        self.assertEqual(len(unfolded), 4)
        for item in unfolded:
            self.assertEqual(item.type, OCCURRENCE)
            self.assertEqual(item.is_recurring, True)

        first_occurrence = unfolded[0]
        self.assertEqual(first_occurrence.id, master_item.first_occurrence.id)
        self.assertEqual(first_occurrence.start, master_item.first_occurrence.start)
        self.assertEqual(first_occurrence.end, master_item.first_occurrence.end)

        second_occurrence = unfolded[1]
        self.assertEqual(second_occurrence.start, master_item.start + datetime.timedelta(days=1))
        self.assertEqual(second_occurrence.end, master_item.end + datetime.timedelta(days=1))

        third_occurrence = unfolded[2]
        self.assertEqual(third_occurrence.start, master_item.start + datetime.timedelta(days=2))
        self.assertEqual(third_occurrence.end, master_item.end + datetime.timedelta(days=2))

        last_occurrence = unfolded[3]
        self.assertEqual(last_occurrence.id, master_item.last_occurrence.id)
        self.assertEqual(last_occurrence.start, master_item.last_occurrence.start)
        self.assertEqual(last_occurrence.end, master_item.last_occurrence.end)

    def test_change_occurrence(self):
        # Test that we can make changes to individual occurrences and see the effect on the master item.
        start = EWSDateTime(2016, 1, 1, 8, tzinfo=self.account.default_timezone)
        end = EWSDateTime(2016, 1, 1, 10, tzinfo=self.account.default_timezone)
        master_item = self.ITEM_CLASS(
            folder=self.test_folder,
            start=start,
            end=end,
            recurrence=Recurrence(pattern=DailyPattern(interval=1), start=start.date(), number=4),
            categories=self.categories,
        ).save()
        master_item.refresh()

        # Test occurrences as full calendar items, unfolded from the master
        range_start, range_end = start, end + datetime.timedelta(days=3)
        unfolded = [i for i in self.test_folder.view(start=range_start, end=range_end) if self.match_cat(i)]

        # Change the start and end of the second occurrence
        second_occurrence = unfolded[1]
        second_occurrence.start += datetime.timedelta(hours=1)
        second_occurrence.end += datetime.timedelta(hours=1)
        second_occurrence.save()

        # Test change on the master item
        master_item.refresh()
        self.assertEqual(len(master_item.modified_occurrences), 1)
        modified_occurrence = master_item.modified_occurrences[0]
        self.assertIsInstance(modified_occurrence, Occurrence)
        self.assertEqual(modified_occurrence.id, second_occurrence.id)
        self.assertEqual(modified_occurrence.start, second_occurrence.start)
        self.assertEqual(modified_occurrence.end, second_occurrence.end)
        self.assertEqual(modified_occurrence.original_start, second_occurrence.start - datetime.timedelta(hours=1))
        self.assertEqual(master_item.deleted_occurrences, None)

        # Test change on the unfolded item
        unfolded = [i for i in self.test_folder.view(start=range_start, end=range_end) if self.match_cat(i)]
        self.assertEqual(len(unfolded), 4)
        self.assertEqual(unfolded[1].type, EXCEPTION)
        self.assertEqual(unfolded[1].start, second_occurrence.start)
        self.assertEqual(unfolded[1].end, second_occurrence.end)
        self.assertEqual(unfolded[1].original_start, second_occurrence.start - datetime.timedelta(hours=1))

    def test_delete_occurrence(self):
        # Test that we can delete an occurrence and see the cange on the master item
        start = EWSDateTime(2016, 1, 1, 8, tzinfo=self.account.default_timezone)
        end = EWSDateTime(2016, 1, 1, 10, tzinfo=self.account.default_timezone)
        master_item = self.ITEM_CLASS(
            folder=self.test_folder,
            start=start,
            end=end,
            recurrence=Recurrence(pattern=DailyPattern(interval=1), start=start.date(), number=4),
            categories=self.categories,
        ).save()
        master_item.refresh()

        # Test occurrences as full calendar items, unfolded from the master
        range_start, range_end = start, end + datetime.timedelta(days=3)
        unfolded = [i for i in self.test_folder.view(start=range_start, end=range_end) if self.match_cat(i)]

        # Delete the third occurrence
        third_occurrence = unfolded[2]
        third_occurrence.delete()

        # Test change on the master item
        master_item.refresh()
        self.assertEqual(master_item.modified_occurrences, None)
        self.assertEqual(len(master_item.deleted_occurrences), 1)
        deleted_occurrence = master_item.deleted_occurrences[0]
        self.assertIsInstance(deleted_occurrence, DeletedOccurrence)
        self.assertEqual(deleted_occurrence.start, third_occurrence.start)

        # Test change on the unfolded items
        unfolded = [i for i in self.test_folder.view(start=range_start, end=range_end) if self.match_cat(i)]
        self.assertEqual(len(unfolded), 3)

    def test_change_occurrence_via_index(self):
        # Test updating occurrences via occurrence index without knowing the ID of the occurrence.
        start = EWSDateTime(2016, 1, 1, 8, tzinfo=self.account.default_timezone)
        end = EWSDateTime(2016, 1, 1, 10, tzinfo=self.account.default_timezone)
        master_item = self.ITEM_CLASS(
            folder=self.test_folder,
            start=start,
            end=end,
            subject=get_random_string(16),
            recurrence=Recurrence(pattern=DailyPattern(interval=1), start=start.date(), number=4),
            categories=self.categories,
        ).save()

        # Change the start and end of the second occurrence
        second_occurrence = master_item.occurrence(index=2)
        second_occurrence.start = start + datetime.timedelta(days=1, hours=1)
        second_occurrence.end = end + datetime.timedelta(days=1, hours=1)
        second_occurrence.save(update_fields=['start', 'end'])  # Test that UpdateItem works with only a few fields

        second_occurrence = master_item.occurrence(index=2)
        second_occurrence.refresh()
        self.assertEqual(second_occurrence.subject, master_item.subject)
        second_occurrence.start += datetime.timedelta(hours=1)
        second_occurrence.end += datetime.timedelta(hours=1)
        second_occurrence.save(update_fields=['start', 'end'])  # Test that UpdateItem works after refresh

        # Test change on the master item
        master_item.refresh()
        self.assertEqual(len(master_item.modified_occurrences), 1)
        modified_occurrence = master_item.modified_occurrences[0]
        self.assertIsInstance(modified_occurrence, Occurrence)
        self.assertEqual(modified_occurrence.id, second_occurrence.id)
        self.assertEqual(modified_occurrence.start, second_occurrence.start)
        self.assertEqual(modified_occurrence.end, second_occurrence.end)
        self.assertEqual(modified_occurrence.original_start, second_occurrence.start - datetime.timedelta(hours=2))
        self.assertEqual(master_item.deleted_occurrences, None)

    def test_delete_occurrence_via_index(self):
        # Test deleting occurrences via occurrence index without knowing the ID of the occurrence.
        start = EWSDateTime(2016, 1, 1, 8, tzinfo=self.account.default_timezone)
        end = EWSDateTime(2016, 1, 1, 10, tzinfo=self.account.default_timezone)
        master_item = self.ITEM_CLASS(
            folder=self.test_folder,
            start=start,
            end=end,
            subject=get_random_string(16),
            recurrence=Recurrence(pattern=DailyPattern(interval=1), start=start.date(), number=4),
            categories=self.categories,
        ).save()

        # Delete the third occurrence
        third_occurrence = master_item.occurrence(index=3)
        third_occurrence.refresh()  # Test that GetItem works

        third_occurrence = master_item.occurrence(index=3)
        third_occurrence.delete()  # Test that DeleteItem works

        # Test change on the master item
        master_item.refresh()
        self.assertEqual(master_item.modified_occurrences, None)
        self.assertEqual(len(master_item.deleted_occurrences), 1)
        deleted_occurrence = master_item.deleted_occurrences[0]
        self.assertIsInstance(deleted_occurrence, DeletedOccurrence)
        self.assertEqual(deleted_occurrence.start, start + datetime.timedelta(days=2))

    def test_get_master_recurrence(self):
        # Test getting the master recurrence via an occurrence
        start = EWSDateTime(2016, 1, 1, 8, tzinfo=self.account.default_timezone)
        end = EWSDateTime(2016, 1, 1, 10, tzinfo=self.account.default_timezone)
        master_item = self.ITEM_CLASS(
            folder=self.test_folder,
            start=start,
            end=end,
            subject=get_random_string(16),
            recurrence=Recurrence(pattern=DailyPattern(interval=1), start=start.date(), number=4),
            categories=self.categories,
        ).save()

        # Get the master from an occurrence
        range_start, range_end = start, end + datetime.timedelta(days=3)
        unfolded = [i for i in self.test_folder.view(start=range_start, end=range_end) if self.match_cat(i)]
        third_occurrence = unfolded[2]
        master_from_occurrence = third_occurrence.recurring_master()

        master_from_occurrence.refresh()  # Test that GetItem works
        self.assertEqual(master_from_occurrence.subject, master_item.subject)

        master_from_occurrence = third_occurrence.recurring_master()
        master_from_occurrence.subject = get_random_string(16)
        master_from_occurrence.save(update_fields=['subject'])  # Test that UpdateItem works
        master_from_occurrence.delete()  # Test that DeleteItem works

        with self.assertRaises(ErrorItemNotFound):
            master_item.delete()  # Item is gone from the server, so this should fail
