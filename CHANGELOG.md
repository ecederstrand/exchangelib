Change Log
==========

HEAD
----


5.5.1
-----
- `Account.version` is now lazy and merely creating an `Account` will not throw errors if the specified credentials
  have insufficient permissions to the account. This only happens if an attempt is made to access the mailbox.


5.5.0
-----
- Dropped support for Python 3.8 which is EOL per October 7, 2024.
- Fix setting OOF on servers that only accept UTC timestamps.


5.4.3
-----
- Fix access to shared folders


5.4.2
-----
- Remove timezone warnings in `GetUserAvailability`
- Update `NoVerifyHTTPAdapter` for newer requests versions


5.4.1
-----
- Fix traversal of public folders in `Account.public_folders_root`
- Mark certain distinguished folders as only supported on newer Exchange versions
- Fetch *all* autodiscover information by default


5.4.0
-----
- Add `O365InteractiveConfiguration` helper class to set up MSAL auth for O365.
- Add `exchangelib[msal]` installation flavor to match the above.
- Various bug fixes related to distinguished folders.


5.3.0
-----
- Fix various issues related to public folders and archive folders
- Support read-write for `Contact.im_addresses`
- Improve reporting of inbox rule validation errors


5.2.1
-----
- Fix `ErrorAccessDenied: Not allowed to access Non IPM folder` caused by recent changes in O365.
- Add more intuitive API for inbox rules
- Fix various bugs with inbox creation


5.2.0
-----
- Allow setting a custom `Configuration.max_conections` in autodiscover mode
- Add support for inbox rules. See documentation for examples.
- Fix shared folder access in delegate mode
- Support subscribing to all folders instead of specific folders


5.1.0
-----
- Fix QuerySet operations on shared folders
- Fix globbing on patterns with more than two folder levels
- Fix case sensitivity of "/" folder navigation
- Multiple improvements related to consistency and graceful error handling


5.0.3
-----
- Bugfix release


5.0.2
-----
- Fix bug where certain folders were being assigned the wrong Python class.


5.0.1
-----
- Fix PyPI package. No source code changes.


5.0.0
-----
- Make SOAP-based autodiscovery the default, and remove support for POX-based
  discovery. This also removes support for autodiscovery on Exchange 2007.
  Only `Account(..., autodiscover=True)` is supported again.
- Deprecated `RetryPolicy.may_retry_on_error`. Instead, add custom retry logic
  in `RetryPolicy.raise_response_errors`.
- Moved `exchangelib.util.RETRY_WAIT` to `BaseProtocol.RETRY_WAIT`.


4.9.0
-----
- Added support for SOAP-based autodiscovery, in addition to the existing POX
  (plain old XML) implementation. You can specify the autodiscover
  implementation explicitly using the `autodiscover` argument:
  `Account(..., autodiscover="soap")` or `Account(..., autodiscover="pox")`. POX
  is still the default.


4.8.0
-----
- Added new `OAuth2LegacyCredentials` class  to support username/password auth
  over OAuth.


4.7.6
-----
- Fixed token refresh bug with OAuth2 authentication, again


4.7.5
-----
- Fixed `Protocol.get_free_busy_info()` when called with +100 accounts.
- Allowed configuring DNS timeout for a single nameserver
  (`Autodiscovery.DNS_RESOLVER_ATTRS["timeout""]`) and the total query lifetime
  (`Autodiscovery.DNS_RESOLVER_LIFETIME`) separately.
- Fixed token refresh bug with OAuth2 authentication


4.7.4
-----
- Bugfix release


4.7.3
-----
- Bugfix release


4.7.2
-----
- Fixed field name to match API: `BaseReplyItem.received_by_representing` to
  `BaseReplyItem.received_representing`
- Added fields `received_by` and `received_representing` to `MeetingRequest`,
  `MeetingMessage` and `MeetingCancellation`
- Fixed `AppointmentStateField.CANCELLED` enum value.


4.7.1
-----
- Fixed issue where creating an Account with autodiscover and no config would
  never set a default retry policy.


4.7.0
-----
- Fixed some spelling mistakes:
  - `ALL_OCCURRENCIES` to `ALL_OCCURRENCES` in `exchangelib.items.base`
  - `Persona.orgnaization_main_phones` to `Persona.organization_main_phones`
- Removed deprecated methods `EWSTimeZone.localize()`, `EWSTimeZone.normalize()`,
  `EWSTimeZone.timezone()` and `QuerySet.iterator()`.
- Disambiguated `chunk_size` and `page_size` in querysets and services. Add a
  new `QuerySet.chunk_size` attribute and let it replace the task that
  `QuerySet.page_size` previously had. Chunk size is the number of items we send
  in e.g. a `GetItem` call, while `page_size` is the number of items we request
  per page in services like `FindItem` that support paging.
- Support creating a proper response when getting a notification request
  on the callback URL of a push subscription.
- `FolderCollection.subscribe_to_[pull|push|streaming]()` now return a single
  subscription instead of a 1-element generator.
- `FolderCollection` now has the same `[pull|push|streaming]_subscription()`
  context managers as folders.


4.6.2
-----

- Fix filtering on array-type extended properties.
- Exceptions in `GetStreamingEvents` responses are now raised.
- Support affinity cookies for pull and streaming subscriptions.


4.6.1
-----

- Support `tzlocal>=4.1`
- Bug fixes for paging in multi-folder requests.

4.6.0
-----

- Support microsecond precision in `EWSDateTime.ewsformat()`
- Remove usage of the `multiprocessing` module to allow running in AWS Lambda
- Support `tzlocal>=4`

4.5.2
-----

- Make `FileAttachment.fp` a proper `BytesIO` implementation
- Add missing `CalendarItem.recurrence_id` field
- Add `SingleFolderQuerySet.resolve()` to aid accessing a folder shared by a different account:

```python
from exchangelib import Account
from exchangelib.folders import Calendar, SingleFolderQuerySet
from exchangelib.properties import DistinguishedFolderId, Mailbox

account = Account(primary_smtp_address="some_user@example.com", ...)
shared_calendar = SingleFolderQuerySet(
    account=account,
    folder=DistinguishedFolderId(
        id=Calendar.DISTINGUISHED_FOLDER_ID,
        mailbox=Mailbox(email_address="other_user@example.com"),
    ),
).resolve()
```

- Minor bugfixes

4.5.1
-----

- Support updating items in `Account.upload()`. Previously, only insert was supported.
- Fixed types for `Contact.manager_mailbox` and `Contact.direct_reports`.
- Support getting `text_body` field on item attachments.

4.5.0
-----

- Fixed bug when updating indexed fields on `Contact` items.
- Fixed bug preventing parsing of `CalendarPermission` items in the `permission_set` field.
- Add support for parsing push notification POST requests sent from the Exchange server to the callback URL.

4.4.0
-----

- Add `Folder.move()` to move folders to a different parent folder.

4.3.0
-----

- Add context managers `Folder.pull_subscription()`, `Folder.push_subscription()` and
  `Folder.streaming_subscription()` that handle unsubscriptions automatically.

4.2.0
-----

- Move `util._may_retry_on_error` and and `util._raise_response_errors` to
  `RetryPolicy.may_retry_on_error` and `RetryPolicy.raise_response_errors`, respectively. This allows for easier
  customization of the retry logic.

4.1.0
-----

- Add support for synchronization, subscriptions and notifications. Both pull, push and streaming notifications are
  supported. See https://ecederstrand.github.io/exchangelib/#synchronization-subscriptions-and-notifications

4.0.0
-----

- Add a new `max_connections` option for the `Configuration` class, to increase the session pool size on a per-server,
  per-credentials basis. Useful when exchangelib is used with threads, where one may wish to increase the number of
  concurrent connections to the server.
- Add `Message.mark_as_junk()` and complementary `QuerySet.mark_as_junk()` methods to mark or un-mark messages as junk
  email, and optionally move them to the junk folder.
- Add support for Master Category Lists, also known as User Configurations. These are custom values that can be assigned
  to folders. Available via `Folder.get_user_configuration()`.
- `Persona` objects as returned by `QuerySet.people()` now support almost all documented fields.
- Improved `QuerySet.people()` to call the `GetPersona` service if at least one field is requested that is not supported
  by the `FindPeople` service.
- Removed the internal caching in `QuerySet`. It's not necessary in most use cases for exchangelib, and the memory
  overhead and complexity is not worth the extra effort. This means that `.iterator()`
  is now a no-op and marked as deprecated. ATTENTION: If you previously relied on caching of results in `QuerySet`, you
  need to do you own caching now.
- Allow plain `date`, `datetime` and `zoneinfo.ZoneInfo` objects as values for fields and methods. This lowers the
  barrier for using the library. We still use `EWSDate`, `EWSDateTime` and `EWSTimeZone` for all values returned from
  the server, but these classes are subclasses of `date`, `datetime` and
  `zoneinfo.ZoneInfo` objects and instances will behave just like instance of their parent class.

3.3.2
-----

- Change Kerberos dependency from `requests_kerberos` to `requests_gssapi`
- Let `EWSDateTime.from_datetime()` accept `datetime.datetime` objects with `tzinfo` objects that are `dateutil`
  , `zoneinfo` and `pytz` instances, in addition to `EWSTimeZone`.

3.3.1
-----

- Allow overriding `dns.resolver.Resolver` class attributes via `Autodiscovery.DNS_RESOLVER_ATTRS`.

3.3.0
-----

- Switch `EWSTimeZone` to be implemented on top of the new `zoneinfo` module in Python 3.9 instead of `pytz`
  . `backports.zoneinfo` is used for earlier versions of Python. This means that the
  `ÈWSTimeZone` methods `timezone()`, `normalize()` and `localize()` methods are now deprecated.
- Add `EWSTimeZone.from_dateutil()` to support converting `dateutil.tz` timezones to `EWSTimeZone`.
- Dropped support for Python 3.5 which is EOL per September 2020.
- Added support for `CalendaItem.appointment_state`, `CalendaItem.conflicting_meetings` and
  `CalendarItem.adjacent_meetings` fields.
- Added support for the `Message.reminder_message_data` field.
- Added support for `Contact.manager_mailbox`, `Contact.direct_reports` and `Contact.complete_name` fields.
- Added support for `Item.response_objects` field.
- Changed `Task.due_date` and `Tas.start_date` fields from datetime to date fields, since the time was being truncated
  anyway by the server.
- Added support for `Task.recurrence` field.
- Added read-only support for `Contact.user_smime_certificate` and `Contact.ms_exchange_certificate`. This means that
  all fields on all item types are now supported.

3.2.1
-----

- Fix bug leading to an exception in `CalendarItem.cancel()`.
- Improve stability of `.order_by()` in edge cases where sorting must be done client-side.
- Allow increasing the session pool-size dynamically.
- Change semantics of `.filter(foo__in=[])` to return an empty result. This was previously undefined behavior. Now we
  adopt the behaviour of Django in this case. This is still undefined behavior for list-type fields.
- Moved documentation to GitHub Pages and auto-documentation generated by `pdoc3`.

3.2.0
-----

- Remove use of `ThreadPool` objects. Threads were used to implement async HTTP requests, but were creating massive
  memory leaks. Async requests should be reimplemented using a real async HTTP request package, so this is just an
  emergency fix. This also lowers the default
  `Protocol.SESSION_POOLSIZE` to 1 because no internal code is running multi-threaded anymore.
- All-day calendar items (created as `CalendarItem(is_all_day=True, ...)`) now accept `EWSDate`
  instances for the `start` and `end` values. Similarly, all-day calendar items fetched from the server now
  return `start` and `end` values as `EWSDate` instances. In this case, start and end values are inclusive; a one-day
  event starts and ends on the same `EWSDate` value.
- Add support for `RecurringMasterItemId` and `OccurrenceItemId` elements that allow to request the master recurrence
  from a `CalendarItem` occurrence, and to request a specific occurrence from a `CalendarItem` master
  recurrence. `CalendarItem.master_recurrence()` and
  `CalendarItem.occurrence(some_occurrence_index)` methods were added to aid this traversal.
  `some_occurrence_index` in the last method specifies which item in the list of occurrences to
  target; `CalendarItem.occurrence(3)` gets the third occurrence in the recurrence.
- Change `Contact.birthday` and `Contact.wedding_anniversary` from `EWSDateTime` to `EWSDate`
  fields. EWS still expects and sends datetime values but has started to reset the time part to 11:59. Dates are a
  better match for these two fields anyway.
- Remove support for `len(some_queryset)`. It had the nasty side-effect of forcing
  `list(some_queryset)` to run the query twice, once for pre-allocating the list via the result of `len(some_queryset)`,
  and then once more to fetch the results. All occurrences of
  `len(some_queryset)` can be replaced with `some_queryset.count()`. Unfortunately, there is no way to keep
  backwards-compatibility for this feature.
- Added `Account.identity`, an attribute to contain extra information for impersonation. Setting
  `Account.identity.upn` or `Account.identity.sid` removes the need for an AD lookup on every request.
  `upn` will often be the same as `primary_smtp_address`, but it is not guaranteed. If you have access to your
  organization's AD servers, you can look up these values once and add them to your
  `Account` object to improve performance of the following requests.
- Added support for CBA authentication

3.1.1
-----

- The `max_wait` argument to `FaultTolerance` changed semantics. Previously, it triggered when the delay until the next
  attempt would exceed this value. It now triggers after the given timespan since the *first* request attempt.
- Fixed a bug when pagination is combined with `max_items` (#710)
- Other minor bug fixes

3.1.0
-----

- Removed the legacy autodiscover implementation.
- Added `QuerySet.depth()` to configure item traversal of querysets. Default is `Shallow` except for the `CommonViews`
  folder where default is `Associated`.
- Updating credentials on `Account.protocol` after getting an `UnauthorizedError` now works.

3.0.0
-----

- The new Autodiscover implementation added in 2.2.0 is now default. To switch back to the old implementation, set the
  environment variable `EXCHANGELIB_AUTODISCOVER_VERSION=legacy`.
- Removed support for Python 2

2.2.0
-----

- Added support for specifying a separate retry policy for the autodiscover service endpoint selection. Set via
  the `exchangelib.autodiscover.legacy.INITIAL_RETRY_POLICY` module variable for the the old autodiscover
  implementation, and via the
  `exchangelib.autodiscover.Autodiscovery.INITIAL_RETRY_POLICY` class variable for the new one.
- Support the authorization code OAuth 2.0 grant type (see issue #698)
- Removed the `RootOfHierarchy.permission_set` field. It was causing too many failures in the wild.
- The full autodiscover response containing all contents of the reponse is now available as `Account.ad_response`.
- Added a new Autodiscover implementation that is closer to the specification and easier to debug. To switch to the new
  implementation, set the environment variable `EXCHANGELIB_AUTODISCOVER_VERSION=new`. The old one is still the default
  if the variable is not set, or set to `EXCHANGELIB_AUTODISCOVER_VERSION=legacy`.
- The `Item.mime_content` field was switched back from a string type to a `bytes` type. It turns out trying to decode
  the data was an error (see issue #709).

2.1.1
-----

- Bugfix release.

2.1.0
-----

- Added support for OAuth 2.0 authentication
- Fixed a bug in `RelativeMonthlyPattern` and `RelativeYearlyPattern` where the `weekdays` field was thought to be a
  list, but is in fact a single value. Renamed the field to `weekday` to reflect the change.
- Added support for archiving items to the archive mailbox, if the account has one.
- Added support for getting delegate information on an Account, as `Account.delegates`.
- Added support for the `ConvertId` service. Available as `Protocol.convert_ids()`.

2.0.1
-----

- Fixed a bug where version 2.x could not open autodiscover cache files generated by version 1.x packages.

2.0.0
-----

- `Item.mime_content` is now a text field instead of a binary field. Encoding and decoding is done automatically.
- The `Item.item_id`, `Folder.folder_id` and `Occurrence.item_id` fields that were renamed to just `id` in 1.12.0, have
  now been removed.
- The `Persona.persona_id` field was replaced with `Persona.id` and `Persona.changekey`, to align with the `Item`
  and `Folder` classes.
- In addition to bulk deleting via a QuerySet (`qs.delete()`), it is now possible to also bulk send, move and copy items
  in a QuerySet (via `qs.send()`, `qs.move()` and `qs.copy()`, respectively).
- SSPI support was added but dependencies are not installed by default since it only works in Win32 environments.
  Install as `pip install exchangelib[sspi]` to get SSPI support. Install with `pip install exchangelib[complete]` to
  get both Kerberos and SSPI auth.
- The custom `extern_id` field is no longer registered by default. If you require this field, register it manually as
  part of your setup code on the item types you need:

    ```python
    from exchangelib import CalendarItem, Message, Contact, Task
    from exchangelib.extended_properties import ExternId

    CalendarItem.register("extern_id", ExternId)
    Message.register("extern_id", ExternId)
    Contact.register("extern_id", ExternId)
    Task.register("extern_id", ExternId)
    ```
- The `ServiceAccount` class has been removed. If you want fault tolerance, set it in a
  `Configuration` object:

    ```python
    from exchangelib import Configuration, Credentials, FaultTolerance

    c = Credentials("foo", "bar")
    config = Configuration(credentials=c, retry_policy=FaultTolerance())
    ```
- It is now possible to use Kerberos and SSPI auth without providing a dummy
  `Credentials('', '')` object.
- The `has_ssl` argument of `Configuration` was removed. If you want to connect to a plain HTTP endpoint, pass the full
  URL in the `service_endpoint` argument.
- We no longer look in `types.xsd` for a hint of which API version the server is running. Instead, we query the service
  directly, starting with the latest version first.

1.12.5
------

- Bugfix release.

1.12.4
------

- Fix bug that left out parts of the folder hierarchy when traversing `account.root`.
- Fix bug that did not properly find all attachments if an item has a mix of item and file attachments.

1.12.3
------

- Add support for reading and writing `PermissionSet` field on folders.
- Add support for Exchange 2019 build IDs.

1.12.2
------

- Add `Protocol.expand_dl()` to get members of a distribution list.

1.12.1
------

- Lower the session pool size automatically in response to ErrorServerBusy and ErrorTooManyObjectsOpened errors from the
  server.
- Unusual slicing and indexing (e.g. `inbox.all()[9000]` and `inbox.all()[9000:9001]`)
  is now efficient.
- Downloading large attachments is now more memory-efficient. We can now stream the file content without ever storing
  the full file content in memory, using the new
  `Attachment.fp` context manager.

1.12.0
------

- Add a MAINFEST.in to ensure the LICENSE file gets included + CHANGELOG.md and README.md to sdist tarball
- Renamed `Item.item_id`, `Folder.folder_id` and `Occurrence.item_id` to just
  `Item.id`, `Folder.id` and `Occurrence.id`, respectively. This removes redundancy in the naming and provides
  consistency. For all classes that have an ID, the ID can now be accessed using the `id` attribute. Backwards
  compatibility and deprecation warnings were added.
- Support folder traversal without creating a full cache of the folder hierarchy first, using
  the `some_folder // 'sub_folder' // 'leaf'`
  (double-slash) syntax.
- Fix a bug in traversal of public and archive folders. These folder hierarchies are now fully supported.
- Fix a bug where the timezone of a calendar item changed when the item was fetched and then saved.
- Kerberos support is now optional and Kerberos dependencies are not installed by default. Install
  as `pip install exchangelib[kerberos]` to get Kerberos support.

1.11.4
------

- Improve back off handling when receiving `ErrorServerBusy` error messages from the server
- Fixed bug where `Account.root` and its children would point to the root folder of the connecting account instead of
  the target account when connecting to other accounts.

1.11.3
------

- Add experimental Kerberos support. This adds the `pykerberos` package, which needs the following system packages to be
  installed on Ubuntu/Debian systems: `apt-get install build-essential libssl-dev libffi-dev python-dev libkrb5-dev`.

1.11.2
------

- Bugfix release

1.11.1
------

- Bugfix release

1.11.0
------

- Added `cancel` to `CalendarItem` and `CancelCalendarItem` class to allow cancelling meetings that were set up
- Added `accept`, `decline` and `tentatively_accept` to `CalendarItem`
  as wrapper methods
- Added `accept`, `decline` and `tentatively_accept` to
  `MeetingRequest` to respond to incoming invitations
- Added `BaseMeetingItem` (inheriting from `Item`) being used as base for MeetingCancellation, MeetingMessage,
  MeetingRequest and MeetingResponse
- Added `AssociatedCalendarItemId` (property),
  `AssociatedCalendarItemIdField` and `ReferenceItemIdField`
- Added `PostReplyItem`
- Removed `Folder.get_folder_by_name()` which has been deprecated since version `1.10.2`.
- Added `Item.copy(to_folder=some_folder)` method which copies an item to the given folder and returns the ID of the new
  item.
- We now respect the back off value of an `ErrorServerBusy`
  server error.
- Added support for fetching free/busy availability information ofr a list of accounts.
- Added `Message.reply()`, `Message.reply_all()`, and
  `Message.forward()` methods.
- The full search API now works on single folders *and* collections of folders, e.g. `some_folder.glob('foo*').filter()`
  ,
  `some_folder.children.filter()` and `some_folder.walk().filter()`.
- Deprecated `EWSService.CHUNKSIZE` in favor of a per-request chunk\_size available on `Account.bulk_foo()` methods.
- Support searching the GAL and other contact folders using
  `some_contact_folder.people()`.
- Deprecated the `page_size` argument for `QuerySet.iterator()` because it was inconsistent with other API methods. You
  can still set the page size of a queryset like this:

    ```python
    qs = a.inbox.filter(...).iterator()
    qs.page_size = 123
    for item in items:
        print(item)
    ```

1.10.7
------

- Added support for registering extended properties on folders.
- Added support for creating, updating, deleting and emptying folders.

1.10.6
------

- Added support for getting and setting `Account.oof_settings` using the new `OofSettings` class.
- Added snake\_case named shortcuts to all distinguished folders on the `Account` model. E.g. `Account.search_folders`.

1.10.5
------

- Bugfix release

1.10.4
------

- Added support for most item fields. The remaining ones are mentioned in issue \#203.

1.10.3
------

- Added an `exchangelib.util.PrettyXmlHandler` log handler which will pretty-print and highlight XML requests and
  responses.

1.10.2
------

- Greatly improved folder navigation. See the 'Folders' section in the README
- Added deprecation warnings for `Account.folders` and
  `Folder.get_folder_by_name()`

1.10.1
------

- Bugfix release

1.10.0
------

- Removed the `verify_ssl` argument to `Account`, `discover` and
  `Configuration`. If you need to disable TLS verification, register a custom `HTTPAdapter` class. A sample adapter
  class is provided for convenience:

    ```python
    from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter

    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
    ```

1.9.6
-----

- Support new Office365 build numbers

1.9.5
-----

- Added support for the `effective_rights`field on items and folders.
- Added support for custom `requests` transport adapters, to allow proxy support, custom TLS validation etc.
- Default value for the `affected_task_occurrences` argument to
  `Item.move_to_trash()`, `Item.soft_delete()` and `Item.delete()` was changed to `'AllOccurrences'` as a less
  surprising default when working with simple tasks.
- Added `Task.complete()` helper method to mark tasks as complete.

1.9.4
-----

- Added minimal support for the `PostItem` item type
- Added support for the `DistributionList` item type
- Added support for receiving naive datetimes from the server. They will be localized using the new `default_timezone`
  attribute on
  `Account`
- Added experimental support for recurring calendar items. See examples in issue \#37.

1.9.3
-----

- Improved support for `filter()`, `.only()`, `.order_by()` etc. on indexed properties. It is now possible to specify
  labels and subfields, e.g.
  `.filter(phone_numbers=PhoneNumber(label='CarPhone', phone_number='123'))`
  `.filter(phone_numbers__CarPhone='123')`,
  `.filter(physical_addresses__Home__street='Elm St. 123')`, .only('physical\_addresses\_\_Home\_\_street')\` etc.
- Improved performance of `.order_by()` when sorting on multiple fields.
- Implemented QueryString search. You can now filter using an EWS QueryString, e.g. `filter('subject:XXX')`

1.9.2
-----

- Added `EWSTimeZone.localzone()` to get the local timezone
- Support `some_folder.get(item_id=..., changekey=...)` as a shortcut to get a single item when you know the ID and
  changekey.
- Support attachments on Exchange 2007

1.9.1
-----

- Fixed XML generation for Exchange 2010 and other picky server versions
- Fixed timezone localization for `EWSTimeZone` created from a static timezone

1.9.0
-----

- Expand support for `ExtendedProperty` to include all possible attributes. This required renaming the `property_id`
  attribute to `property_set_id`.
- When using the `Credentials` class, `UnauthorizedError` is now raised if the credentials are wrong.
- Add a new `version` attribute to `Configuration`, to force the server version if version guessing does not work.
  Accepts a
  `exchangelib.version.Version` object.
- Rework bulk operations `Account.bulk_foo()` and `Account.fetch()` to return some exceptions unraised, if it is deemed
  the exception does not apply to all items. This means that e.g. `fetch()` can return a mix of `` `Item ``
  and `ErrorItemNotFound` instances, if only some of the requested `ItemId` were valid. Other exceptions will be raised
  immediately, e.g. `ErrorNonExistentMailbox` because the exception applies to all items. It is the responsibility of
  the caller to check the type of the returned values.
- The `Folder` class has new attributes `total_count`, `unread_count`
  and `child_folder_count`, and a `refresh()` method to update these values.
- The argument to `Account.upload()` was renamed from `upload_data` to just `data`
- Support for using a string search expression for `Folder.filter()`
  was removed. It was a cool idea but using QuerySet chaining and `Q`
  objects is even cooler and provides the same functionality, and more.
- Add support for `reminder_due_by` and
  `reminder_minutes_before_start` fields on `Item` objects. Submitted by `@vikipha`.
- Added a new `ServiceAccount` class which is like `Credentials` but does what `is_service_account` did before. If you
  need fault-tolerane and used `Credentials(..., is_service_account=True)`
  before, use `ServiceAccount` now. This also disables fault-tolerance for the `Credentials` class, which is in line
  with what most users expected.
- Added an optional `update_fields` attribute to `save()` to specify only some fields to be updated.
- Code in in `folders.py` has been split into multiple files, and some classes will have new import locaions. The most
  commonly used classes have a shortcut in \_\_init\_\_.py
- Added support for the `exists` lookup in filters, e.g.
  `my_folder.filter(categories__exists=True|False)` to filter on the existence of that field on items in the folder.
- When filtering, `foo__in=value` now requires the value to be a list, and `foo__contains` requires the value to be a
  list if the field itself is a list, e.g. `categories__contains=['a', 'b']`.
- Added support for fields and enum entries that are only supported in some EWS versions
- Added a new field `Item.text_body` which is a read-only version of HTML body content, where HTML tags are stripped by
  the server. Only supported from Exchange 2013 and up.
- Added a new choice `WorkingElsewhere` to the
  `CalendarItem.legacy_free_busy_status` enum. Only supported from Exchange 2013 and up.

1.8.1
-----

- Fix completely botched `Message.from` field renaming in 1.8.0
- Improve performance of QuerySet slicing and indexing. For example,
  `account.inbox.all()[10]` and `account.inbox.all()[:10]` now only fetch 10 items from the server even
  though `account.inbox.all()`
  could contain thousands of messages.

1.8.0
-----

- Renamed `Message.from` field to `Message.author`. `from` is a Python keyword so `from` could only be accessed as
  `Getattr(my_essage, 'from')` which is just stupid.
- Make `EWSTimeZone` Windows timezone name translation more robust
- Add read-only `Message.message_id` which holds the Internet Message Id
- Memory and speed improvements when sorting querysets using
  `order_by()` on a single field.
- Allow setting `Mailbox` and `Attendee`-type attributes as plain strings, e.g.:

    ```python
    calendar_item.organizer = "anne@example.com"
    calendar_item.required_attendees = ["john@example.com", "bill@example.com"]

    message.to_recipients = ["john@example.com", "anne@example.com"]
    ```

1.7.6
-----

- Bugfix release

1.7.5
-----

- `Account.fetch()` and `Folder.fetch()` are now generators. They will do nothing before being evaluated.
- Added optional `page_size` attribute to `QuerySet.iterator()` to specify the number of items to return per HTTP
  request for large query results. Default `page_size` is 100.
- Many minor changes to make queries less greedy and return earlier

1.7.4
-----

- Add Python2 support

1.7.3
-----

- Implement attachments support. It's now possible to create, delete and get attachments connected to any item type:

    ```python
    from exchangelib.folders import FileAttachment, ItemAttachment

    # Process attachments on existing items
    for item in my_folder.all():
        for attachment in item.attachments:
            local_path = os.path.join("/tmp", attachment.name)
            with open(local_path, "wb") as f:
                f.write(attachment.content)
                print("Saved attachment to", local_path)

    # Create a new item with an attachment
    item = Message(...)
    binary_file_content = "Hello from unicode æøå".encode(
        "utf-8"
    )  # Or read from file, BytesIO etc.
    my_file = FileAttachment(name="my_file.txt", content=binary_file_content)
    item.attach(my_file)
    my_calendar_item = CalendarItem(...)
    my_appointment = ItemAttachment(name="my_appointment", item=my_calendar_item)
    item.attach(my_appointment)
    item.save()

    # Add an attachment on an existing item
    my_other_file = FileAttachment(name="my_other_file.txt", content=binary_file_content)
    item.attach(my_other_file)

    # Remove the attachment again
    item.detach(my_file)
    ```

  Be aware that adding and deleting attachments from items that are already created in Exchange (items that have
  an `item_id`) will update the `changekey` of the item.

- Implement `Item.headers` which contains custom Internet message headers. Primarily useful for `Message` objects.
  Read-only for now.

1.7.2
-----

- Implement the `Contact.physical_addresses` attribute. This is a list of `exchangelib.folders.PhysicalAddress` items.
- Implement the `CalendarItem.is_all_day` boolean to create all-day appointments.
- Implement `my_folder.export()` and `my_folder.upload()`. Thanks to @SamCB!
- Fixed `Account.folders` for non-distinguished folders
- Added `Folder.get_folder_by_name()` to make it easier to get sub-folders by name.
- Implement `CalendarView` searches as
  `my_calendar.view(start=..., end=...)`. A view differs from a normal
  `filter()` in that a view expands recurring items and returns recurring item occurrences that are valid in the time
  span of the view.
- Persistent storage location for autodiscover cache is now platform independent
- Implemented custom extended properties. To add support for your own custom property,
  subclass `exchangelib.folders.ExtendedProperty` and call `register()` on the item class you want to use the extended
  property with. When you have registered your extended property, you can use it exactly like you would use any other
  attribute on this item type. If you change your mind, you can remove the extended property again with `deregister()`:

    ```python
    class LunchMenu(ExtendedProperty):
        property_id = "12345678-1234-1234-1234-123456781234"
        property_name = "Catering from the cafeteria"
        property_type = "String"


    CalendarItem.register("lunch_menu", LunchMenu)
    item = CalendarItem(..., lunch_menu="Foie gras et consommé de légumes")
    item.save()
    CalendarItem.deregister("lunch_menu")
    ```

- Fixed a bug on folder items where an existing HTML body would be converted to text when calling `save()`. When
  creating or updating an item body, you can use the two new helper classes
  `exchangelib.Body` and `exchangelib.HTMLBody` to specify if your body should be saved as HTML or text. E.g.:

    ```python
    item = CalendarItem(...)
    # Plain-text body
    item.body = Body("Hello UNIX-beard pine user!")
    # Also plain-text body, works as before
    item.body = "Hello UNIX-beard pine user!"
    # Exchange will see this as an HTML body and display nicely in clients
    item.body = HTMLBody("<html><body>Hello happy <blink>OWA user!</blink></body></html>")
    item.save()
    ```

1.7.1
-----

- Fix bug where fetching items from a folder that can contain multiple item types (e.g. the Deleted Items folder) would
  only return one item type.
- Added `Item.move(to_folder=...)` that moves an item to another folder, and `Item.refresh()` that updates the Item with
  data from EWS.
- Support reverse sort on individual fields in `order_by()`, e.g.
  `my_folder.all().order_by('subject', '-start')`
- `Account.bulk_create()` was added to create items that don't need a folder, e.g. `Message.send()`
- `Account.fetch()` was added to fetch items without knowing the containing folder.
- Implemented `SendItem` service to send existing messages.
- `Folder.bulk_delete()` was moved to `Account.bulk_delete()`
- `Folder.bulk_update()` was moved to `Account.bulk_update()` and changed to expect a list of `(Item, fieldnames)`
  tuples where Item is e.g. a `Message` instance and `fieldnames` is a list of attributes names that need updating.
  E.g.:

    ```python
    items = []
    for i in range(4):
        item = Message(subject="Test %s" % i)
        items.append(item)
    account.sent.bulk_create(items=items)

    item_changes = []
    for i, item in enumerate(items):
        item.subject = "Changed subject" % i
        item_changes.append(item, ["subject"])
    account.bulk_update(items=item_changes)
    ```

1.7.0
-----

- Added the `is_service_account` flag to `Credentials`.
  `is_service_account=False` disables the fault-tolerant error handling policy and enables immediate failures.
- `Configuration` now expects a single `credentials` attribute instead of separate `username` and `password` attributes.
- Added support for distinguished folders `Account.trash`,
  `Account.drafts`, `Account.outbox`, `Account.sent` and
  `Account.junk`.
- Renamed `Folder.find_items()` to `Folder.filter()`
- Renamed `Folder.add_items()` to `Folder.bulk_create()`
- Renamed `Folder.update_items()` to `Folder.bulk_update()`
- Renamed `Folder.delete_items()` to `Folder.bulk_delete()`
- Renamed `Folder.get_items()` to `Folder.fetch()`
- Made various policies for message saving, meeting invitation sending, conflict resolution, task occurrences and
  deletion available on `bulk_create()`, `bulk_update()` and `bulk_delete()`.
- Added convenience methods `Item.save()`, `Item.delete()`,
  `Item.soft_delete()`, `Item.move_to_trash()`, and methods
  `Message.send()` and `Message.send_and_save()` that are specific to
  `Message` objects. These methods make it easier to create, update and delete single items.
- Removed `fetch(.., with_extra=True)` in favor of the more fine-grained `fetch(.., only_fields=[...])`
- Added a `QuerySet` class that supports QuerySet-returning methods
  `filter()`, `exclude()`, `only()`, `order_by()`,
  `reverse()`, `values()` and `values_list()` that all allow for chaining. `QuerySet` also has methods `iterator()`
  , `get()`,
  `count()`, `exists()` and `delete()`. All these methods behave like their counterparts in Django.

1.6.2
-----

- Use of `my_folder.with_extra_fields = True` to get the extra fields in `Item.EXTRA_ITEM_FIELDS` is deprecated (it was
  a kludge anyway). Instead, use `my_folder.get_items(ids, with_extra=[True, False])`. The default was also changed
  to `True`, to avoid head-scratching with newcomers.

1.6.1
-----

- Simplify `Q` objects and `Restriction.from_source()` by using Item attribute names in expressions and kwargs instead
  of EWS FieldURI values. Change `Folder.find_items()` to accept either a search expression, or a list of `Q` objects
  just like Django
  `filter()` does. E.g.:

    ```python
    ids = account.calendar.find_items(
        "start < '2016-01-02T03:04:05T' and end > '2016-01-01T03:04:05T' and categories in ('foo', 'bar')",
        shape=IdOnly,
    )

    q1, q2 = (Q(subject__iexact="foo") | Q(subject__contains="bar")), ~Q(
        subject__startswith="baz"
    )
    ids = account.calendar.find_items(q1, q2, shape=IdOnly)
    ```

1.6.0
-----

- Complete rewrite of `Folder.find_items()`. The old `start`, `end`,
  `subject` and `categories` args are deprecated in favor of a Django QuerySet filter() syntax. The supported lookup
  types are `__gt`,
  `__lt`, `__gte`, `__lte`, `__range`, `__in`, `__exact`, `__iexact`,
  `__contains`, `__icontains`, `__contains`, `__icontains`,
  `__startswith`, `__istartswith`, plus an additional `__not` which translates to `!=`. Additionally, *all* fields on
  the item are now supported in `Folder.find_items()`.

  **WARNING**: This change is backwards-incompatible! Old uses of
  `Folder.find_items()` like this:

    ```python
    ids = account.calendar.find_items(
        start=tz.localize(EWSDateTime(year, month, day)),
        end=tz.localize(EWSDateTime(year, month, day + 1)),
        categories=["foo", "bar"],
    )
    ```

  must be rewritten like this:

    ```python
    ids = account.calendar.find_items(
        start__lt=tz.localize(EWSDateTime(year, month, day + 1)),
        end__gt=tz.localize(EWSDateTime(year, month, day)),
        categories__contains=["foo", "bar"],
    )
    ```

  failing to do so will most likely result in empty or wrong results.

- Added a `exchangelib.restrictions.Q` class much like Django Q objects that can be used to create even more complex
  filtering. Q objects must be passed directly to `exchangelib.services.FindItem`.

1.3.6
-----

- Don't require sequence arguments to `Folder.*_items()` methods to support `len()` (e.g. generators and `map` instances
  are now supported)
- Allow empty sequences as argument to `Folder.*_items()` methods

1.3.4
-----

- Add support for `required_attendees`, `optional_attendees` and
  `resources` attribute on `folders.CalendarItem`. These are implemented with a new `folders.Attendee` class.

1.3.3
-----

- Add support for `organizer` attribute on `CalendarItem`. Implemented with a new `folders.Mailbox` class.

1.2
---

- Initial import
