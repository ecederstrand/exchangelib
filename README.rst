Exchange Web Services client library
====================================
This module provides an well-performing, well-behaving, platform-independent and simple interface for communicating with
a Microsoft Exchange 2007-2016 Server or Office365 using Exchange Web Services (EWS). It currently implements
autodiscover, and functions for searching, creating, updating, deleting, exporting and uploading calendar, mailbox, task
and contact items.


.. image:: https://badge.fury.io/py/exchangelib.svg
    :target: https://badge.fury.io/py/exchangelib

.. image:: https://landscape.io/github/ecederstrand/exchangelib/master/landscape.png
   :target: https://landscape.io/github/ecederstrand/exchangelib/master

.. image:: https://secure.travis-ci.org/ecederstrand/exchangelib.png
    :target: http://travis-ci.org/ecederstrand/exchangelib

.. image:: https://coveralls.io/repos/github/ecederstrand/exchangelib/badge.svg?branch=master
    :target: https://coveralls.io/github/ecederstrand/exchangelib?branch=master


Usage
~~~~~

Here are some examples of how `exchangelib` works:

.. code-block:: python

    from exchangelib import DELEGATE, IMPERSONATION, Account, Credentials, \
        EWSDateTime, EWSTimeZone, Configuration, NTLM, CalendarItem, Message, \
        Mailbox, Attendee, Q
    from exchangelib.folders import Calendar, ExtendedProperty, FileAttachment, ItemAttachment, \
        HTMLBody

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
            required_attendees = [Attendee(
                mailbox=Mailbox(email_address='user1@example.com'),
                response_type='Accept'
            )]
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
    res = account.calendar.bulk_create(items=calendar_items)
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
    # filter() also support Q objects that are modeled after Django Q objects.
    #
    # q = (Q(subject__iexact='foo') | Q(subject__contains='bar')) & ~Q(subject__startswith='baz')
    # items = my_folder.filter(q)
    #
    # A large part of the Django QuerySet API is supported. The QuerySet doesn't fetch anything before the 
    # QuerySet is iterated. The QuerySet returns an iterator, and results are cached when the QuerySet is 
    # iterated the first time.
    # Examples:
    #
    # all_items = my_folder.all()
    # all_items_without_caching = my_folder.all().iterator()
    # filtered_items = my_folder.filter(subject__contains='foo').exclude(categories__contains='bar')
    # sparse_items = my_folder.all().only('subject', 'start')
    # status_report = my_folder.all().delete()
    # items_for_2017 = my_calendar.filter(start__range=(
    #     tz.localize(EWSDateTime(2017, 1, 1)), 
    #     tz.localize(EWSDateTime(2018, 1, 1))
    # ))
    # item = my_folder.get(subject='unique_string')
    # ordered_items = my_folder.all().order_by('subject')
    # n = my_folder.all().count()
    # folder_is_empty = not my_folder.all().exists()
    # ids_as_dict = my_folder.all().values('item_id', 'changekey')
    # ids_as_list = my_folder.all().values_list('item_id', 'changekey')
    # all_subjects = my_folder.all().values_list('subject', flat=True)
    #
    # If you want recurring calendar items to be expanded, use calendar.view(start=..., end=...) instead
    items = account.calendar.filter(
        start__lt=tz.localize(EWSDateTime(year, month, day + 1)),
        end__gt=tz.localize(EWSDateTime(year, month, day)),
        categories__contains=['foo', 'bar'],
    )
    for item in items:
        print(item.start, item.end, item.subject, item.body, item.location)

    # Delete the calendar items we found
    res = items.delete()
    print(res)

    # You can also create, update and delete single items
    item = CalendarItem(folder=account.calendar, subject='foo')
    item.save()
    item.subject = 'bar'
    item.save()
    item.delete()

    # You can also send emails

    # If you don't want a local copy
    m = Message(
        account=a,
        subject='Daily motivation',
        body='All bodies are beautiful',
        to_recipients=[Mailbox(email_address='anne@example.com')]
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
    
    # The most common folders are available as account.calendar, account.trash, account.drafts, account.inbox,
    # account.outbox, account.sent, account.junk, account.tasks, and account.contacts.
    #
    # If you want to access other folders, you can either traverse the account.folders dictionary, or find 
    # the folder by name, starting at a direct or indirect parent of the folder you want to find. To search 
    # the full folder hirarchy, start the search from account.root:
    python_dev_mail_folder = account.root.get_folder_by_name('python-dev')
    # If you have multiple folders with the same name in your folder hierarchy, start your search further down 
    # the hierarchy:
    foo1_folder = account.inbox.get_folder_by_name('foo')
    foo2_folder = python_dev_mail_folder.get_folder_by_name('foo')
    # For more advanced folder traversing, use some_folder.get_folders()

    # If folder items have extended properties, you need to register them before you can access them. Create
    # a subclass of ExtendedProperty and set your custom property_id: 
    class LunchMenu(ExtendedProperty):
        property_id = '12345678-1234-1234-1234-123456781234'
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

    # Be aware that adding and deleting attachments from items that are already created in Exchange 
    # (items that have an item_id) will update the changekey of the item.

    
    # 'exchangelib' has support for most (but not all) item attributes, and also item export and upload.
