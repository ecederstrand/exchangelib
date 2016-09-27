Exchange Web Services client library
====================================
This module provides an well-performing, well-behaving, platform-independent and simple interface for communicating with
a Microsoft Exchange 2007-2016 Server or Office365 using Exchange Web Services (EWS). It currently implements
autodiscover, and functions for searching, creating, updating and deleting calendar, mailbox, task and contact items.


.. image:: https://badge.fury.io/py/exchangelib.svg
    :target: https://badge.fury.io/py/exchangelib

.. image:: https://landscape.io/github/ecederstrand/exchangelib/master/landscape.png
   :target: https://landscape.io/github/ecederstrand/exchangelib/master

.. image:: https://secure.travis-ci.org/ecederstrand/exchangelib.png
    :target: http://travis-ci.org/ecederstrand/exchangelib

.. image:: https://coveralls.io/repos/github/ecederstrand/exchangelib/badge.svg?branch=
    :target: https://coveralls.io/github/ecederstrand/exchangelib?branch=


Usage
~~~~~

Here is a simple example that inserts, retrieves and deletes calendar items in an Exchange calendar:

.. code-block:: python

    from exchangelib import DELEGATE, IMPERSONATION, Account, Credentials, \
        EWSDateTime, EWSTimeZone, Configuration, NTLM, CalendarItem, Q
    from exchangelib.folders import Calendar

    year, month, day = 2016, 3, 20
    tz = EWSTimeZone.timezone('Europe/Copenhagen')

    # Build a list of calendar items
    calendar_items = []
    for hour in range(7, 17):
        calendar_items.append(CalendarItem(
            start=tz.localize(EWSDateTime(year, month, day, hour, 30)),
            end=tz.localize(EWSDateTime(year, month, day, hour + 1, 15)),
            subject='Test item',
            body='Hello from Python',
            location='devnull',
            categories=['foo', 'bar'],
        ))

    # Username in WINDOMAIN\username format. Office365 wants usernames in PrimarySMTPAddress
    # ('myusername@example.com') format. UPN format is also supported.
    #
    # By default, fault-tolerant error handling is used. This means that calls may block for a long time
    # if the server is unavailable. If you need immediate failures, add 'is_service_account=False' to
    # Credentials.
    credentials = Credentials(username='MYWINDOMAIN\\myusername', password='topsecret')

    # If your credentials have been given impersonation access to the target account, use
    # access_type=IMPERSONATION
    account = Account(primary_smtp_address='john@example.com', credentials=credentials,
                      autodiscover=True, access_type=DELEGATE)

    # If the server doesn't support autodiscover, use a Configuration object to set the
    # server location:
    # config = Configuration(
    #     server='mail.example.com',
    #     credentials=Credentials(username='MYWINDOMAIN\\myusername', password='topsecret'),
    #     auth_type=NTLM
    # )
    # account = Account(primary_smtp_address='john@example.com', config=config,
    #                   access_type=DELEGATE)


    # Create the calendar items in the user's standard calendar.  If you want to access a
    # non-standard calendar, choose a different one from account.folders[Calendar]
    #
    # bulk_update() and bulk_delete() methods are also supported.
    res = account.calendar.bulk_create(calendar_items)
    print(res)

    # Get the calendar items we just created. We filter by categories so we only get the items created by
    # us. The syntax for filter() is modeled after Django QuerySet filters.
    #
    # If you need more complex filtering, filter() also accepts a Python-like search expression:
    #
    # items = my_folder.filter(
    #       "start < '2016-01-02T03:04:05T' and end > '2016-01-01T03:04:05T' and categories in ('foo', 'bar')"
    # )
    #
    # filter() also support Q objects that are modeled after Django Q objects
    #
    # q = (Q(subject__iexact='foo') | Q(subject__contains='bar')) & ~Q(subject__startswith='baz')
    # items = my_folder.filter(q)
    #
    # A large part of the Django QuerySet API is supported:
    #
    # all_items = my_folder.all()
    # filtered_items = my_folder.filter(subject__contains='foo').exclude(categories__contains='bar')
    # sparse_items = my_folder.all().only('subject', 'start')
    # status_report = my_folder.all().delete()
    # items_for_2017 = my_calendar.filter(start__range=(EWSDateTime(2016, 1, 1), EWSDateTime(2017, 1, 1)))
    # item = my_folder.get(subject='unique_string')
    # ordered_items = my_folder.all().order_by('subject')
    # n = my_folder.all().count()
    # folder_is_empty = not my_folder.all().exists()
    # ids_as_dict = my_folder.all().values('item_id', 'changekey')
    # ids_as_list = my_folder.all().values_list('item_id', 'changekey')
    # subjects = my_folder.all().values_list('subject', flat=True)
    #
    items = account.calendar.filter(
        start__lt=tz.localize(EWSDateTime(year, month, day + 1)),
        end__gt=tz.localize(EWSDateTime(year, month, day)),
        categories__contains=['foo', 'bar'],
    )
    for item in items:
        print(item.start, item.end, item.subject, items.body, item.location)

    # Delete the calendar items we found
    res = items.delete()
    print(res)

    # You can also create, update and delete single items
    item = CalendarItem(folder=account.calendar, subject='foo')
    item.save()
    item.subject = 'bar'
    item.save()
    item.delete()
