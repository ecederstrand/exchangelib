Exchange Web Services client library
====================================
This module provides an well-performing, well-behaving, platform-independent and simple interface for communicating with
a Microsoft Exchange 2007-2016 Server or Office365 using Exchange Web Services (EWS). It currently implements
autodiscover, and functions for searching, creating, updating, deleting, exporting and uploading calendar, mailbox,
task, contact and distribution list items.


.. image:: https://img.shields.io/pypi/v/exchangelib.svg
    :target: https://pypi.python.org/pypi/exchangelib/

.. image:: https://img.shields.io/pypi/pyversions/exchangelib.svg
    :target: https://pypi.python.org/pypi/exchangelib/

.. image:: https://landscape.io/github/ecederstrand/exchangelib/master/landscape.png
   :target: https://landscape.io/github/ecederstrand/exchangelib/master

.. image:: https://secure.travis-ci.org/ecederstrand/exchangelib.png
    :target: http://travis-ci.org/ecederstrand/exchangelib

.. image:: https://coveralls.io/repos/github/ecederstrand/exchangelib/badge.svg?branch=master
    :target: https://coveralls.io/github/ecederstrand/exchangelib?branch=master


Usage
-----
Here are some examples of how `exchangelib` works:


Setup and connecting
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from datetime import timedelta
    from exchangelib import DELEGATE, IMPERSONATION, Account, Credentials, ServiceAccount, \
        EWSDateTime, EWSTimeZone, Configuration, NTLM, CalendarItem, Message, \
        Mailbox, Attendee, Q, ExtendedProperty, FileAttachment, ItemAttachment, \
        HTMLBody, Build, Version

    # Specify your credentials. Username is usually in WINDOMAIN\username format, where WINDOMAIN is
    # the name of the Windows Domain your username is connected to, but some servers also
    # accept usernames in PrimarySMTPAddress ('myusername@example.com') format (Office365 requires it).
    # UPN format is also supported, if your server expects that.
    credentials = Credentials(username='MYWINDOMAIN\\myusername', password='topsecret')

    # If you're running long-running jobs, you may want to enable fault-tolerance. Fault-tolerance
    # means that requests to the server do an exponential backoff and sleep for up to a certain
    # threshold before giving up, if the server is unavailable or responding with error messages.
    # This prevents automated scripts from overwhelming a failing or overloaded server, and hides
    # intermittent service outages that often happen in large Exchange installations.

    # If you want to enable the fault tolerance, create credentials as a service account instead:
    credentials = ServiceAccount(username='FOO\\bar', password='topsecret')

    # An Account is the account on the Exchange server that you want to connect to. This can be
    # the account associated with the credentials you connect with, or any other account on the
    # server that you have been granted access to.
    # 'primary_smtp_address' is the primary SMTP address assigned the account. If you enable
    # autodiscover, an alias address will work, too. In this case, 'Account.primary_smtp_address'
    # will be set to the primary SMTP address.
    my_account = Account(primary_smtp_address='myusername@example.com', credentials=credentials,
                         autodiscover=True, access_type=DELEGATE)
    johns_account = Account(primary_smtp_address='john@example.com', credentials=credentials,
                            autodiscover=True, access_type=DELEGATE)
    marys_account = Account(primary_smtp_address='mary@example.com', credentials=credentials,
                            autodiscover=True, access_type=DELEGATE)
    still_marys_account = Account(primary_smtp_address='alias_for_mary@example.com',
                                  credentials=credentials, autodiscover=True, access_type=DELEGATE)

    # Set up a target account and do an autodiscover lookup to find the target EWS endpoint.
    account = Account(primary_smtp_address='john@example.com', credentials=credentials,
                      autodiscover=True, access_type=DELEGATE)

    # If your credentials have been given impersonation access to the target account, set a
    # different 'access_type':
    account = Account(primary_smtp_address='john@example.com', credentials=credentials,
                      autodiscover=True, access_type=IMPERSONATION)

    # If the server doesn't support autodiscover, or you want to avoid the overhead of autodiscover,
    # use a Configuration object to set the server location instead:
    config = Configuration(server='mail.example.com', credentials=credentials)
    account = Account(primary_smtp_address='john@example.com', config=config,
                      autodiscover=False, access_type=DELEGATE)

    # 'exchangelib' will attempt to guess the server version and authentication method. If you
    # have a really bizarre or locked-down installation and the guessing fails, or you want to avoid
    # the extra network traffic, you can set the auth method and version explicitly instead:
    version = Version(build=Build(15, 0, 12, 34))
    config = Configuration(server='example.com', credentials=credentials, version=version, auth_type=NTLM)

    # If you're connecting to the same account very often, you can cache the autodiscover result for
    # later so you can skip the autodiscover lookup:
    ews_url = account.protocol.service_endpoint
    ews_auth_type = account.protocol.auth_type
    primary_smtp_address = account.primary_smtp_address

    # 5 minutes later, fetch the cached values and create the account without autodiscovering:
    config = Configuration(service_endpoint=ews_url, credentials=credentials, auth_type=ews_auth_type)
    account = Account(
        primary_smtp_address=primary_smtp_address, config=config, autodiscover=False, access_type=DELEGATE
    )

    # If you need proxy support or custom TLS validation, you can supply a custom 'requests' transport adapter, as
    # described in http://docs.python-requests.org/en/master/user/advanced/#transport-adapters
    # exchangelib provides a sample adapter which ignores SSL validation errors. Use at own risk.
    from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter


Folders
^^^^^^^

.. code-block:: python

    # The most common folders are available as account.calendar, account.trash, account.drafts, account.inbox,
    # account.outbox, account.sent, account.junk, account.tasks, and account.contacts.
    #
    # There are multiple ways of navigating the folder tree and searching for folders. Globbing and absolute path may
    # create unexpected results if your folder names contain slashes.
    some_folder.parent
    some_folder.parent.parent.parent
    some_folder.root  # Returns the root of the folder structure, at any level. Same as Account.root
    some_folder.children  # A generator of child folders
    some_folder.absolute  # Returns the absolute path, as a string
    some_folder.walk()  # A generator returning all subfolders at arbitrary depth this level
    # Globbing uses the normal UNIX globbing syntax
    some_folder.glob('foo*')  # Return child folders matching the pattern
    some_folder.glob('*/foo')  # Return subfolders named 'foo' in any child folder
    some_folder.glob('**/foo')  # Return subfolders named 'foo' at any depth
    some_folder / 'sub_folder' / 'even_deeper' / 'leaf'  # Works like pathlib.Path
    some_folder.parts  # returns some_folder, some_folder.parent, some_folder.parent.parent as Folder instances
    # tree() returns a string representation of the tree structure at the given level
    print(root.tree())
    '''
    root
    ├── inbox
    │   └── todos
    └── archive
        ├── Last Job
        ├── exchangelib issues
        └── Mom
    '''

    # Folders have some useful counters:
    account.inbox.total_count
    account.inbox.child_folder_count
    account.inbox.unread_count
    # Update the counters
    account.inbox.refresh()
    # The folder structure is cached after first access. To clear the cache, refresh the root folder
    account.root.refresh()


Dates, datetimes and timezones
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

EWS has some special requirements on datetimes and timezones. You need to use the special ``EWSDate``,
``EWSDateTime`` and ``EWSTimeZone`` classes when working with dates.

.. code-block:: python

    # EWSTimeZone works just like pytz.timezone()
    tz = EWSTimeZone.timezone('Europe/Copenhagen')
    # You can also get the local timezone defined in your operating system
    tz = EWSTimeZone.localzone()

    # EWSDate and EWSDateTime work just like datetime.datetime and datetime.date. Always create timezone-aware
    # datetimes with EWSTimeZone.localize():
    localized_dt = tz.localize(EWSDateTime(2017, 9, 5, 8, 30))
    right_now = tz.localize(EWSDateTime.now())

    # Datetime math works transparently
    two_hours_later = localized_dt + timedelta(hours=2)
    two_hours = two_hours_later - localized_dt

    # Dates
    my_date = EWSDate(2017, 9, 5)
    today = EWSDate.today()
    also_today = right_now.date()

    # UTC helpers. 'UTC' is the UTC timezone as an EWSTimeZone instance.
    # 'UTC_NOW' returns a timezone-aware UTC timestamp of current time.
    from exchangelib import UTC, UTC_NOW

    right_now_in_utc = UTC.localize(EWSDateTime.now())
    right_now_in_utc = UTC_NOW()


Creating, updating, deleting, sending and moving
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # Here's an example of creating a calendar item in the user's standard calendar.  If you want to
    # access a non-standard calendar, choose a different one from account.folders[Calendar].
    #
    # You can create, update and delete single items:
    from exchangelib.items import SEND_ONLY_TO_ALL, SEND_ONLY_TO_CHANGED
    item = CalendarItem(folder=account.calendar, subject='foo')
    item.save()  # This gives the item an 'item_id' and a 'changekey' value
    item.save(send_meeting_invitations=SEND_ONLY_TO_ALL)  # Send a meeting invitation to attendees
    # Update a field. All fields have a corresponding Python type that must be used.
    item.subject = 'bar'
    # Print all available fields on the 'CalendarItem' class. Beware that some fields are read-only, or
    # read-only after the item has been saved or sent, and some fields are not supported on old versions
    # of Exchange.
    print(CalendarItem.FIELDS)
    item.save()  # When the items has an item_id, this will update the item
    item.save(update_fields=['subject'])  # Only updates certain fields
    item.save(send_meeting_invitations=SEND_ONLY_TO_CHANGED)  # Send meeting invitation, but only to attendee changes
    item.delete()  # Hard deletinon
    item.delete(send_meeting_cancellations=SEND_ONLY_TO_ALL)  # Send meeting cancellations to all attendees
    item.soft_delete()  # Delete, but keep a copy in the recoverable items folder
    item.move_to_trash()  # Move to the trash folder
    item.move(account.trash)  # Also moves the item to the trash folder

    # You can also send emails. If you don't want a local copy:
    m = Message(
        account=a,
        subject='Daily motivation',
        body='All bodies are beautiful',
        to_recipients=[Mailbox(email_address='anne@example.com'), Mailbox(email_address='bob@example.com')],
        cc_recipients=['carl@example.com', 'denice@example.com'],  # Simple strings work, too
        bcc_recipients=[Mailbox(email_address='erik@example.com'), 'felicity@example.com'],  # Or a mix of both
    )
    m.send()

    # Or, if you want a copy in e.g. the 'Sent' folder
    m = Message(
        account=a,
        folder=a.sent,
        subject='Daily motivation',
        body='All bodies are beautiful',
        to_recipients=[Mailbox(email_address='anne@example.com')]
    )
    m.send_and_save()

    # EWS distinquishes between plain text and HTML body contents. If you want to send HTML body content, use
    # the HTMLBody helper. Clients will see this as HTML and display the body correctly:
    item.body = HTMLBody('<html><body>Hello happy <blink>OWA user!</blink></body></html>')


Bulk operations
^^^^^^^^^^^^^^^

.. code-block:: python

    # Build a list of calendar items
    tz = EWSTimeZone.timezone('Europe/Copenhagen')
    year, month, day = 2016, 3, 20
    calendar_items = []
    for hour in range(7, 17):
        calendar_items.append(CalendarItem(
            start=tz.localize(EWSDateTime(year, month, day, hour, 30)),
            end=tz.localize(EWSDateTime(year, month, day, hour + 1, 15)),
            subject='Test item',
            body='Hello from Python',
            location='devnull',
            categories=['foo', 'bar'],
            required_attendees = [Attendee(
                mailbox=Mailbox(email_address='user1@example.com'),
                response_type='Accept'
            )]
        ))

    # Create all items at once
    return_ids = account.bulk_create(folder=account.calendar, items=calendar_items)

    # Bulk fetch, when you have a list of item IDs and want the full objects. Returns a generator.
    calendar_ids = [(i.item_id, i.changekey) for i in calendar_items]
    items_iter = account.fetch(ids=calendar_ids)
    # If you only want some fields, use the 'only_fields' attribute
    items_iter = account.fetch(ids=calendar_ids, only_fields=['start', 'subject'])

    # Bulk update items. Each item must be accompanied by a list of attributes to update
    updated_ids = account.bulk_create(items=[(i, ('start', 'subject')) for i in calendar_items])

    # Move many items to a new folder
    new_ids = account.bulk_move(ids=calendar_ids, to_folder=account.other_calendar)

    # Send draft messages in bulk
    new_ids = account.bulk_send(ids=message_ids, save_copy=False)

    # Delete in bulk
    delete_results = account.bulk_delete(ids=calendar_ids)

    # Bulk delete items found as a queryset
    account.inbox.filter(subject__startswith='Invoice').delete()



Searching
^^^^^^^^^

Searching is modeled after the Django QuerySet API, and a large part of the API is supported. Like
in Django, the QuerySet is lazy and doesn't fetch anything before the QuerySet is iterated. QuerySets
support chaining, so you can build the final query in multiple steps, and you can re-use a base
QuerySet for multiple sub-searches. The QuerySet returns an iterator, and results are cached when the
QuerySet is fully iterated the first time.

Here are some examples of using the API:

.. code-block:: python

    # Let's get the calendar items we just created.
    all_items = my_folder.all()  # Get everything
    all_items_without_caching = my_folder.all().iterator()  # Get everything, but don't cache
    filtered_items = my_folder.filter(subject__contains='foo').exclude(categories__icontains='bar')  # Chaining
    status_report = my_folder.all().delete()  # Delete the items returned by the QuerySet
    items_for_2017 = my_calendar.filter(start__range=(
        tz.localize(EWSDateTime(2017, 1, 1)),
        tz.localize(EWSDateTime(2018, 1, 1))
    ))  # Filter by a date range
    # Same as filter() but throws an error if exactly one item isn't returned
    item = my_folder.get(subject='unique_string')

    # You can sort by a single or multiple fields. Prefix a field with '-' to reverse the sorting. Sorting is efficient
    # since it is done server-side.
    ordered_items = my_folder.all().order_by('subject')
    reverse_ordered_items = my_folder.all().order_by('-subject')
    sorted_by_home_street = my_contacts.all().order_by('physical_addresses__Home__street')  # Indexed properties
    dont_do_this = my_huge_folder.all().order_by('subject', 'categories')[:10]  # This is efficient

    # Counting and exists
    n = my_folder.all().count()  # Efficient counting
    folder_is_empty = not my_folder.all().exists()  # Efficient tasting

    # Restricting returned attributes
    sparse_items = my_folder.all().only('subject', 'start')
    # Dig deeper on indexed properties
    sparse_items = my_contacts.all().only('phone_numbers')
    sparse_items = my_contacts.all().only('phone_numbers__CarPhone')
    sparse_items = my_contacts.all().only('physical_addresses__Home__street')

    # Returning values instead of objects
    ids_as_dict = my_folder.all().values('item_id', 'changekey')  # Return values as dicts, not objects
    values_as_list = my_folder.all().values_list('subject', 'body')  # Return values as nested lists
    all_subjects = my_folder.all().values_list('physical_addresses__Home__street', flat=True)  # Return a flat list

    # A QuerySet can be sliced like a normal Python list. Slicing from the start of the QuerySet
    # is efficient (it only fetches the necessary items), but more exotic slicing requires many or all
    # items to be fetched from the server. Slicing from the end is also efficient, but then you might as
    # well just reverse the sorting.
    first_ten_emails = my_folder.all().order_by('-datetime_received')[:10]  # Efficient
    last_ten_emails = my_folder.all().order_by('-datetime_received')[:-10]  # Efficient, but convoluted
    next_ten_emails = my_folder.all().order_by('-datetime_received')[10:20]  # Still quite efficient
    eviction_warning = my_folder.all().order_by('-datetime_received')[34298]  # This is looking for trouble
    some_random_emails = my_folder.all().order_by('-datetime_received')[::3]  # This is just stupid

    # The syntax for filter() is modeled after Django QuerySet filters. The following filter lookup types
    # are supported. Some lookups only work with string attributes, some only with date or numerical
    # attributes, and some attributes are not searchable at all:
    qs = account.calendar.all()
    qs.filter(subject='foo')  # Returns items where subject is exactly 'foo'. Case-sensitive
    qs.filter(start__range=(dt1, dt2))  # Returns items starting within range. Only for date and numerical types
    qs.filter(subject__in=('foo', 'bar'))  # Return items where subject is either 'foo' or 'bar'
    qs.filter(subject__not='foo')  # Returns items where subject is not 'foo'
    qs.filter(start__gt=dt)  # Returns items starting after 'dt'.  Only for date and numerical types
    qs.filter(start__gte=dt)  # Returns items starting on or after 'dt'.  Only for date and numerical types
    qs.filter(start__lt=dt)  # Returns items starting before 'dt'.  Only for date and numerical types
    qs.filter(start__lte=dt)  # Returns items starting on or before 'dt'.  Only for date and numerical types
    qs.filter(subject__exact='foo')  #  Returns items where subject is 'foo'. Same as filter(subject='foo')
    qs.filter(subject__iexact='foo')  #  Returns items where subject is 'foo', 'FOO' or 'Foo'
    qs.filter(subject__contains='foo')  #  Returns items where subject contains 'foo'
    qs.filter(subject__icontains='foo')  # Returns items where subject contains 'foo', 'FOO' or 'Foo'
    qs.filter(subject__startswith='foo')  # Returns items where subject starts with 'foo'
    qs.filter(subject__istartswith='foo')  # Returns items where subject starts with 'foo', 'FOO' or 'Foo'
    # Returns items that have at least one category set, i.e. the field exists on the item on the server
    qs.filter(categories__exists=True)
    # Returns items that have no categories set, i.e. the field does not exist on the item on the server
    qs.filter(categories__exists=False)

    # filter() also supports EWS QueryStrings. Just pass the string to filter(). QueryStrings cannot be combined with
    # other filters. We make no attempt at validating the syntax of the QueryString - we just pass the string verbatim
    # to EWS.
    #
    # Read more about the QueryString syntax here: https://msdn.microsoft.com/en-us/library/ee693615.aspx
    items = my_folder.filter('subject:XXX')

    # filter() also supports Q objects that are modeled after Django Q objects, for building complex
    # boolean logic search expressions.
    q = (Q(subject__iexact='foo') | Q(subject__contains='bar')) & ~Q(subject__startswith='baz')
    items = my_folder.filter(q)

    # In this example, we filter by categories so we only get the items created by us.
    items = account.calendar.filter(
        start__lt=tz.localize(EWSDateTime(year, month, day + 1)),
        end__gt=tz.localize(EWSDateTime(year, month, day)),
        categories__contains=['foo', 'bar'],
    )
    for item in items:
        print(item.start, item.end, item.subject, item.body, item.location)

    # By default, EWS returns only the master recurring item. If you want recurring calendar
    # items to be expanded, use calendar.view(start=..., end=...) instead.
    items = account.calendar.view(
        start=tz.localize(EWSDateTime(year, month, day)),
        end=tz.localize(EWSDateTime(year, month, day)) + timedelta(days=1),
    )
    for item in items:
        print(item.start, item.end, item.subject, item.body, item.location)


Extended properties
^^^^^^^^^^^^^^^^^^^
Extended properties makes it possible to attach custom key-value pairs to items stored on the Exchange server. There are
multiple online resources that describe working with extended properties, and list many of the magic values that are
used by existing Exchange clients to store common and custom properties. The following is not a comprehensive
description of the possibilities, but we do intend to support all the possibilities provided by EWS.

.. code-block:: python

    # If folder items have extended properties, you need to register them before you can access them. Create
    # a subclass of ExtendedProperty and define a set of matching setup values:
    class LunchMenu(ExtendedProperty):
        property_set_id = '12345678-1234-1234-1234-123456781234'
        property_name = 'Catering from the cafeteria'
        property_type = 'String'

    # Register the property on the item type of your choice
    CalendarItem.register('lunch_menu', LunchMenu)
    # Now your property is available as the attribute 'lunch_menu', just like any other attribute
    item = CalendarItem(..., lunch_menu='Foie gras et consommé de légumes')
    item.save()
    for i in account.calendar.all():
        print(i.lunch_menu)
    # If you change your mind, jsut remove the property again
    CalendarItem.deregister('lunch_menu')

    # You can also create named properties (e.g. created from User Defined Fields in Outlook, see issue #137):
    class LunchMenu(ExtendedProperty):
        distinguished_property_set_id = 'PublicStrings'
        property_name = 'Catering from the cafeteria'
        property_type = 'String'

    # We support extended properties with tags. This is the definition for the 'completed' and 'followup' flag you can
    # add to items in Outlook (see also issue #85):
    class Flag(ExtendedProperty):
        property_tag = 0x1090
        property_type = 'Integer'

    # Or with property ID:
    class MyMeetingArray(ExtendedProperty):
        property_set_id = '00062004-0000-0000-C000-000000000046'
        property_type = 'BinaryArray'
        property_id = 32852

    # Or using distinguished property sets combined with property ID (here as a hex value to align with
    # the format usually mentioned in Microsoft docs). This is the definition for a response to an Outlook
    # Vote request (see issue #198):
    class VoteResponse(ExtendedProperty):
        distinguished_property_set_id = 'Common'
        property_id = 0x00008524
        property_type = 'String'


Attachments
^^^^^^^^^^^

.. code-block:: python

    # It's possible to create, delete and get attachments connected to any item type:
    # Process attachments on existing items. FileAttachments have a 'content' attribute
    # containing the binary content of the file, and ItemAttachments have an 'item' attribute
    # containing the item. The item can be a Message, CalendarItem, Task etc.
    for item in my_folder.all():
        for attachment in item.attachments:
            if isinstance(attachment, FileAttachment):
                local_path = os.path.join('/tmp', attachment.name)
                with open(local_path, 'wb') as f:
                    f.write(attachment.content)
                print('Saved attachment to', local_path)
            elif isinstance(attachment, ItemAttachment):
                if isinstance(attachment.item, Message):
                    print(attachment.item.subject, attachment.item.body)

    # Create a new item with an attachment
    item = Message(...)
    binary_file_content = 'Hello from unicode æøå'.encode('utf-8')  # Or read from file, BytesIO etc.
    my_file = FileAttachment(name='my_file.txt', content=binary_file_content)
    item.attach(my_file)
    my_calendar_item = CalendarItem(...)
    my_appointment = ItemAttachment(name='my_appointment', item=my_calendar_item)
    item.attach(my_appointment)
    item.save()

    # Add an attachment on an existing item
    my_other_file = FileAttachment(name='my_other_file.txt', content=binary_file_content)
    item.attach(my_other_file)

    # Remove the attachment again
    item.detach(my_file)

    # If you want to embed an image in the item body, you can link to the file in the HTML
    logo_filename = 'logo.png'
    with open(logo_filename, 'rb') as f:
        my_logo = FileAttachment(name=logo_filename, content=f.read())
    message.attach(my_logo)
    message.body = HTMLBody('<html><body>Hello logo: <img src="cid:%s"></body></html>' % logo_filename)

    # Attachments cannot be updated via EWS. In this case, you must to detach the attachment, update the
    # relevant fields, and attach the updated attachment.

    # Be aware that adding and deleting attachments from items that are already created in Exchange
    # (items that have an item_id) will update the changekey of the item.


Recurring calendar items
^^^^^^^^^^^^^^^^^^^^^^^^
There is full read-write support for creating recurring calendar items. You can create daily, weekly, monthly and
yearly recurrences (the latter two in relative and absolute versions).

Here's an example of creating 7 occurrences on Mondays and Wednesdays of every third week, starting September 1, 2017:

.. code-block:: python

    from exchangelib.recurrence import Recurrence, WeeklyPattern, MONDAY, WEDNESDAY

    start = tz.localize(EWSDateTime(2017, 9, 1, 11))
    item = CalendarItem(
        folder=a.calendar,
        start=start,
        end=start + timedelta(hours=2),
        subject='Hello Recurrence',
        recurrence=Recurrence(
            pattern=WeeklyPattern(interval=3, weekdays=[MONDAY, WEDNESDAY]),
            start=start.date(),
            number=7
        ),
    )

    # Occurrence data for the master item
    for i in a.calendar.filter(start__lt=end, end__gt=start):
        print(i.subject, i.start, i.end)
        print(i.recurrence)
        print(i.first_occurrence)
        print(i.last_occurrence)
        for o in i.modified_occurrences:
            print(o)
        for o in i.deleted_occurrences:
            print(o)

    # All occurrences expanded. The recurrence will span over 4 iterations of a 3-week period
    for i in a.calendar.view(start=start, end=start + timedelta(days=4*3*7)):
        print(i.subject, i.start, i.end)


Message timestamp fields
^^^^^^^^^^^^^^^^^^^^^^^^

Each ``Message`` item has four timestamp fields:

* ``datetime_created``
* ``datetime_sent``
* ``datetime_received``
* ``last_modified_time``

The values for these fields are set by the Exchange server and are not modifiable via EWS. All
values are timezone-aware ``EWSDateTime`` instances.

The ``datetime_sent`` value may be earlier than ``datetime_created``.


Troubleshooting
^^^^^^^^^^^^^^^
If you are having trouble using this library, the first thing to try is to enable debug logging. This will output a huge
amount of information about what is going on, most notable the actual XML documents that are doing over the wite. This
can be really handy to see which fields are being sent and received.

.. code-block:: python

    import logging
    # This handler will pretty-print and syntax highlight the request and response XML documents
    from exchangelib.util import PrettyXmlHandler

    logging.basicConfig(level=logging.DEBUG, handlers=[PrettyXmlHandler()])
    # Your code using exchangelib goes here


Most class definitions have a docstring containing at least a URL to the MSDN  page for the corresponding XML element.

.. code-block:: python

    from exchangelib import CalendarItem
    print(CalendarItem.__doc__)


Notes
^^^^^

Most, but not all, item attributes are supported. Adding more attributes is usually uncomplicated. Feel
free to open a PR or an issue.

Item export and upload is supported, for efficient backup, restore and migration.
