==========
Change Log
==========

1.7.3
-----
* Implement attachments support. It's now possible to create, delete and get attachments connected to any item type:

  .. code-block:: python

      from exchangelib.folders import FileAttachment, ItemAttachment

      # Process attachments on existing items
      for item in my_folder.all():
          for attachment in item.attachments:
              local_path = os.path.join('/tmp', attachment.name)
              with open(local_path, 'wb') as f:
                  f.write(attachment.content)
                  print('Saved attachment to', local_path)

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

  Be aware that adding and deleting attachments from items that are already created in Exchange (items that have an
  `item_id`) will update the `changekey` of the item.

* Implement `Item.headers` which contains custom Internet message headers. Primarily useful for `Message` objects.
  Read-only for now.


1.7.2
-----
* Implement the ``Contact.physical_addresses`` attribute. This is a list of ``exchangelib.folders.PhysicalAddress``
  items.
* Implement the ``CalendarItem.is_all_day`` boolean to create all-day appointments.
* Implement ``my_folder.export()`` and ``my_folder.upload()``. Thanks to @SamCB!
* Fixed ``Account.folders`` for non-distinguished folders
* Added ``Folder.get_folder_by_name()`` to make it easier to get sub-folders by name.
* Implement ``CalendarView`` searches as ``my_calendar.view(start=..., end=...)``. A view differs from a normal
  ``filter()`` in that a view expands recurring items and returns recurring item occurrences that are valid in the time
  span of the view.
* Persistent storage location for autodiscover cache is now platform independent
* Implemented custom extended properties. To add support for your own custom property, subclass
  ``exchangelib.folders.ExtendedProperty`` and call ``register()`` on the item class you want to use the extended
  property with. When you have registered your extended property, you can use it exactly like you would use any other
  attribute on this item type. If you change your mind, you can remove the extended property again with ``deregister()``:

  .. code-block:: python

      class LunchMenu(ExtendedProperty):
          property_id = '12345678-1234-1234-1234-123456781234'
          property_name = 'Catering from the cafeteria'
          property_type = 'String'

      CalendarItem.register('lunch_menu', LunchMenu)
      item = CalendarItem(..., lunch_menu='Foie gras et consommé de légumes')
      item.save()
      CalendarItem.deregister('lunch_menu')

* Fixed a bug on folder items where an existing HTML body would be converted to text when calling ``save()``. When
  creating or updating an item body, you can use the two new helper classes ``exchangelib.Body`` and
  ``exchangelib.HTMLBody`` to specify if your body should be saved as HTML or text. E.g.:

  .. code-block:: python

      item = CalendarItem(...)
      # Plain-text body
      item.body = Body('Hello UNIX-beard pine user!')
      # Also plain-text body, works as before
      item.body = 'Hello UNIX-beard pine user!'
      # Exchange will see this as an HTML body and display nicely in clients
      item.body = HTMLBody('<html><body>Hello happy <blink>OWA user!</blink></body></html>')
      item.save()

1.7.1
-----
* Fix bug where fetching items from a folder that can contain multiple item types (e.g. the Deleted Items folder) would
  only return one item type.
* Added ``Item.move(to_folder=...)`` that moves an item to another folder, and ``Item.refresh()`` that updates the
  Item with data from EWS.
* Support reverse sort on individual fields in ``order_by()``, e.g. ``my_folder.all().order_by('subject', '-start')``
* ``Account.bulk_create()`` was added to create items that don't need a folder, e.g. ``Message.send()``
* ``Account.fetch()`` was added to fetch items without knowing the containing folder.
* Implemented ``SendItem`` service to send existing messages.
* ``Folder.bulk_delete()`` was moved to ``Account.bulk_delete()``
* ``Folder.bulk_update()`` was moved to ``Account.bulk_update()`` and changed to expect a list of ``(Item, fieldnames)``
  tuples where Item is e.g. a ``Message`` instance and ``fieldnames`` is a list of attributes names that need updating.
  E.g.:

  .. code-block:: python

      items = []
      for i in range(4):
          item = Message(subject='Test %s' % i)
          items.append(item)
      account.sent.bulk_create(items=items)

      item_changes = []
      for i, item in enumerate(items):
          item.subject = 'Changed subject' % i
          item_changes.append(item, ['subject'])
      account.bulk_update(items=item_changes)


1.7.0
-----
* Added the ``is_service_account`` flag to ``Credentials``. ``is_service_account=False`` disables the fault-tolerant error
  handling policy and enables immediate failures.
* ``Configuration`` now expects a single ``credentials`` attribute instead of separate ``username`` and ``password``
  attributes.
* Added support for distinguished folders ``Account.trash``, ``Account.drafts``, ``Account.outbox``,
  ``Account.sent`` and ``Account.junk``.
* Renamed ``Folder.find_items()`` to ``Folder.filter()``
* Renamed ``Folder.add_items()`` to ``Folder.bulk_create()``
* Renamed ``Folder.update_items()`` to ``Folder.bulk_update()``
* Renamed ``Folder.delete_items()`` to ``Folder.bulk_delete()``
* Renamed ``Folder.get_items()`` to ``Folder.fetch()``
* Made various policies for message saving, meeting invitation sending, conflict resolution, task occurrences and
  deletion available on ``bulk_create()``, ``bulk_update()`` and ``bulk_delete()``.
* Added convenience methods ``Item.save()``, ``Item.delete()``, ``Item.soft_delete()``, ``Item.move_to_trash()``, and
  methods ``Message.send()`` and ``Message.send_and_save()`` that are specific to ``Message`` objects. These methods
  make it easier to create, update and delete single items.
* Removed ``fetch(.., with_extra=True)`` in favor of the more fine-grained ``fetch(.., only_fields=[...])``
* Added a ``QuerySet`` class that supports QuerySet-returning methods ``filter()``, ``exclude()``, ``only()``,
  ``order_by()``, ``reverse()````values()`` and ``values_list()`` that all allow for chaining. ``QuerySet`` also has
  methods ``iterator()``, ``get()``, ``count()``, ``exists()`` and ``delete()``. All these methods behave like their
  counterparts in Django.


1.6.2
-----
* Use of ``my_folder.with_extra_fields = True`` to get the extra fields in ``Item.EXTRA_ITEM_FIELDS`` is deprecated (it was
  a kludge anyway). Instead, use ``my_folder.get_items(ids, with_extra=[True, False])``. The default was also changed to
  ``True``, to avoid head-scratching with newcomers.


1.6.1
-----
* Simplify ``Q`` objects and ``Restriction.from_source()`` by using Item attribute names in expressions and kwargs
  instead of EWS FieldURI values. Change ``Folder.find_items()`` to accept either a search expression, or a list of
  ``Q`` objects just like Django ``filter()`` does. E.g.:

  .. code-block:: python

      ids = account.calendar.find_items(
            "start < '2016-01-02T03:04:05T' and end > '2016-01-01T03:04:05T' and categories in ('foo', 'bar')",
            shape=IdOnly
      )

      q1, q2 = (Q(subject__iexact='foo') | Q(subject__contains='bar')), ~Q(subject__startswith='baz')
      ids = account.calendar.find_items(q1, q2, shape=IdOnly)


1.6.0
-----
* Complete rewrite of ``Folder.find_items()``. The old ``start``, ``end``, ``subject`` and
  ``categories`` args are deprecated in favor of a Django QuerySet filter() syntax. The
  supported lookup types are ``__gt``, ``__lt``, ``__gte``, ``__lte``, ``__range``, ``__in``,
  ``__exact``, ``__iexact``, ``__contains``, ``__icontains``, ``__contains``, ``__icontains``,
  ``__startswith``, ``__istartswith``, plus an additional ``__not`` which translates to ``!=``.
  Additionally, *all* fields on the item are now supported in ``Folder.find_items()``.

  **WARNING**: This change is backwards-incompatible! Old uses of ``Folder.find_items()`` like this:

  .. code-block:: python

      ids = account.calendar.find_items(
          start=tz.localize(EWSDateTime(year, month, day)),
          end=tz.localize(EWSDateTime(year, month, day + 1)),
          categories=['foo', 'bar'],
      )

  must be rewritten like this:

  .. code-block:: python

      ids = account.calendar.find_items(
          start__lt=tz.localize(EWSDateTime(year, month, day + 1)),
          end__gt=tz.localize(EWSDateTime(year, month, day)),
          categories__contains=['foo', 'bar'],
      )

  failing to do so will most likely result in empty or wrong results.

* Added a ``exchangelib.restrictions.Q`` class much like Django Q objects that can be used to
  create even more complex filtering. Q objects must be passed directly to ``exchangelib.services.FindItem``.


1.3.6
-----
* Don't require sequence arguments to ``Folder.*_items()`` methods to support ``len()``
  (e.g. generators and ``map`` instances are now supported)
* Allow empty sequences as argument to ``Folder.*_items()`` methods


1.3.4
-----
* Add support for ``required_attendees``, ``optional_attendees`` and ``resources``
  attribute on ``folders.CalendarItem``. These are implemented with a new ``folders.Attendee``
  class.


1.3.3
-----
* Add support for ``organizer`` attribute on ``CalendarItem``.  Implemented with a
  new ``folders.Mailbox`` class.


1.2
---
* Initial import
