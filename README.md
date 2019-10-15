Exchange Web Services client library
====================================

This module provides an well-performing, well-behaving,
platform-independent and simple interface for communicating with a
Microsoft Exchange 2007-2016 Server or Office365 using Exchange Web
Services (EWS). It currently implements autodiscover, and functions for
searching, creating, updating, deleting, exporting and uploading
calendar, mailbox, task, contact and distribution list items.

[![image](https://img.shields.io/pypi/v/exchangelib.svg)](https://pypi.org/project/exchangelib/)
[![image](https://img.shields.io/pypi/pyversions/exchangelib.svg)](https://pypi.org/project/exchangelib/)
[![image](https://api.codacy.com/project/badge/Grade/5f805ad901054a889f4b99a82d6c1cb7)](https://www.codacy.com/app/ecederstrand/exchangelib?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=ecederstrand/exchangelib&amp;utm_campaign=Badge_Grade)
[![image](https://secure.travis-ci.org/ecederstrand/exchangelib.png)](http://travis-ci.org/ecederstrand/exchangelib)
[![image](https://coveralls.io/repos/github/ecederstrand/exchangelib/badge.svg?branch=master)](https://coveralls.io/github/ecederstrand/exchangelib?branch=master)

[![image](https://liberapay.com/assets/widgets/donate.svg)](https://en.liberapay.com/ecederstrand)

## Teaser

Here's a short example of how `exchangelib` works. Let's print the first
100 inbox messages in reverse order:

```python
from exchangelib import Credentials, Account

credentials = Credentials('john@example.com', 'topsecret')
account = Account('john@example.com', credentials=credentials, autodiscover=True)

for item in account.inbox.all().order_by('-datetime_received')[:100]:
    print(item.subject, item.sender, item.datetime_received)
```


## Installation
You can install this package from PyPI:

```bash
pip install exchangelib
```

The default installation does not support Kerberos or SSPI. For additional Kerberos or SSPI support,
install with the extra `kerberos` or `sspi` dependencies (please note that SSPI is only supported on
Windows):

```bash
pip install exchangelib[kerberos]
pip install exchangelib[sspi]
```

To get both, install as:

```bash
pip install exchangelib[complete]
```

To install the very latest code, install directly from GitHub instead:

```bash
pip install git+https://github.com/ecederstrand/exchangelib.git
```

`exchangelib` uses the `lxml` package, and `pykerberos` to support Kerberos authentication.
To be able to install these, you may need to install some additional operating system packages.

On Ubuntu:
```bash
apt-get install libxml2-dev libxslt1-dev

# For Kerberos support, also install these:
apt-get install libkrb5-dev build-essential libssl-dev libffi-dev python-dev
```

On CentOS:
```bash
# For Kerberos support, install these:
yum install gcc python-devel krb5-devel krb5-workstation python-devel
```

On FreeBSD, `pip` needs a little help:
```bash
pkg install libxml2 libxslt
CFLAGS=-I/usr/local/include pip install lxml

# For Kerberos support, also install these:
pkg install krb5
CFLAGS=-I/usr/local/include pip install kerberos pykerberos
```

For other operating systems, please consult the documentation for the Python package that
fails to install.


## Setup and connecting

```python
from exchangelib import DELEGATE, IMPERSONATION, Account, Credentials, OAuth2Credentials, \
    FaultTolerance, Configuration, NTLM, GSSAPI, SSPI, OAUTH2, Build, Version

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

# An Account is the account on the Exchange server that you want to connect to. This can be
# the account associated with the credentials you connect with, or any other account on the
# server that you have been granted access to. If, for example, you want to access a shared
# folder, create an Account instance using the email address of the account that the shared 
# folder belongs to, and access the shared folder through this account.

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
config = Configuration(
    server='example.com', credentials=credentials, version=version, auth_type=NTLM
)

# By default, we fail on all exceptions from the server. If you want to enable fault
# tolerance, add a retry policy to your configuration. We will then retry on certain
# transient errors. By default, we back off exponentially and retry for up to an hour.
# This is configurable:
config = Configuration(retry_policy=FaultTolerance(max_wait=3600), credentials=credentials)
account = Account(primary_smtp_address='john@example.com', config=config)

# Kerberos and SSPI authentication are supported via the GSSAPI and SSPI auth types.
config = Configuration(server='example.com', auth_type=GSSAPI)
config = Configuration(server='example.com', auth_type=SSPI)

# OAuth is supported via the OAUTH2 auth type and the OAuth2Credentials class.
credentials = OAuth2Credentials(client_id='MY_ID', client_secret='MY_SECRET', tenant_id='TENANT_ID')
config = Configuration(credentials=credentials, auth_type=OAUTH2)

# If you're connecting to the same account very often, you can cache the autodiscover result for
# later so you can skip the autodiscover lookup:
ews_url = account.protocol.service_endpoint
ews_auth_type = account.protocol.auth_type
primary_smtp_address = account.primary_smtp_address

# You can now create the Account without autodiscovering, using the cached values:
config = Configuration(service_endpoint=ews_url, credentials=credentials, auth_type=ews_auth_type)
account = Account(
    primary_smtp_address=primary_smtp_address, 
    config=config, autodiscover=False, 
    access_type=DELEGATE,
)

# Autodiscover can take a lot of time, specially the part that figures out the autodiscover 
# server to contact for a specific email domain. For this reason, we will create a persistent, 
# per-user, on-disk cache containing a map of previous, successful domain -> autodiscover server
# lookups. This cache is shared between processes and is not deleted when your program exits.

# A cache entry for a domain is removed automatically if autodiscovery fails for an email in that
# domain. It's possible to clear the entire cache completely if you want:
from exchangelib.autodiscover import _autodiscover_cache
_autodiscover_cache.clear()
```

## Proxies and custom TLS validation

If you need proxy support or custom TLS validation, you can supply a
custom 'requests' transport adapter class, as described in
<http://docs.python-requests.org/en/master/user/advanced/#transport-adapters>.

Here's an example using different custom root certificates depending on
the server to connect to:

```python
from urllib.parse import urlparse
import requests.adapters
from exchangelib.protocol import BaseProtocol

class RootCAAdapter(requests.adapters.HTTPAdapter):
    # An HTTP adapter that uses a custom root CA certificate at a hard coded location
    def cert_verify(self, conn, url, verify, cert):
        cert_file = {
            'example.com': '/path/to/example.com.crt',
            'mail.internal': '/path/to/mail.internal.crt',
        }[urlparse(url).hostname]
        super(RootCAAdapter, self).cert_verify(conn=conn, url=url, verify=cert_file, cert=cert)

# Tell exchangelib to use this adapter class instead of the default
BaseProtocol.HTTP_ADAPTER_CLS = RootCAAdapter
```

Here's an example of adding proxy support:

```python
import requests.adapters
from exchangelib.protocol import BaseProtocol

class ProxyAdapter(requests.adapters.HTTPAdapter):
    def send(self, *args, **kwargs):
        kwargs['proxies'] = {
            'http': 'http://10.0.0.1:1243',
            'https': 'http://10.0.0.1:4321',
        }
        return super(ProxyAdapter, self).send(*args, **kwargs)

# Tell exchangelib to use this adapter class instead of the default
BaseProtocol.HTTP_ADAPTER_CLS = ProxyAdapter
```

`exchangelib` provides a sample adapter which ignores TLS validation
errors. Use at own risk.

```python
from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter

# Tell exchangelib to use this adapter class instead of the default
BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
```

## User-Agent

You can supply a custom 'User-Agent' for your application.
By default, `exchangelib` will use: `exchangelib/<version> (python-requests/<version>)`

Here's an example using different User-Agent:

```python
from exchangelib.protocol import BaseProtocol

# Tell exchangelib to use this user-agent instead of the default
BaseProtocol.USERAGENT = "Auto-Reply/0.1.0"
```

## Folders
All wellknown folders are available as properties on the account, e.g. as `account.root`, `account.calendar`,
`account.trash`, `account.inbox`, `account.outbox`, `account.sent`, `account.junk`, `account.tasks` and
`account.contacts`.

```python
# There are multiple ways of navigating the folder tree and searching for folders. Globbing and 
# absolute path may create unexpected results if your folder names contain slashes.

# The folder structure is cached after first access to a folder hierarchy. This means that external
# changes to the folder structure will not show up until you clear the cache. Here's how to clear
# the cache of each of the currently supported folder hierarchies:
from exchangelib import Account, Folder

a = Account(...)
a.root.refresh()
a.public_folders_root.refresh()
a.archive_root.refresh()

some_folder = a.root / 'Some Folder'
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
# You can also drill down into the folder structure without using the cache. This works like
# the single slash syntax, but does not start by creating a cache the folder hierarchy. This is
# useful if your account contains a huge number of folders, and you already know where to go.
some_folder // 'sub_folder' // 'even_deeper' // 'leaf'
some_folder.parts  # returns some_folder and all its parents, as Folder instances
# tree() returns a string representation of the tree structure at the given level
print(a.root.tree())
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
a.inbox.total_count
a.inbox.child_folder_count
a.inbox.unread_count
# Update the counters
a.inbox.refresh()

# Folders can be created, updated and deleted:
f = Folder(parent=a.inbox, name='My New Folder')
f.save()

f.name = 'My New Subfolder'
f.save()
f.delete()

# Delete all items in a folder
f.empty()
# Also delete all subfolders in the folder
f.empty(delete_sub_folders=True)
# Recursively delete all items in a folder, and all subfolders and their content. This is
# like `empty(delete_sub_folders=True)` but attempts to protect distinguished folders from
# being deleted. Use with caution!
f.wipe()
```

## Dates, datetimes and timezones

EWS has some special requirements on datetimes and timezones. You need
to use the special `EWSDate`, `EWSDateTime` and `EWSTimeZone` classes
when working with dates.

```python
from datetime import datetime, timedelta
import pytz
from exchangelib import EWSTimeZone, EWSDateTime, EWSDate

# EWSTimeZone works just like pytz.timezone()
tz = EWSTimeZone.timezone('Europe/Copenhagen')
# You can also get the local timezone defined in your operating system
tz = EWSTimeZone.localzone()

# EWSDate and EWSDateTime work just like datetime.datetime and datetime.date. Always create
# timezone-aware datetimes with EWSTimeZone.localize():
localized_dt = tz.localize(EWSDateTime(2017, 9, 5, 8, 30))
right_now = tz.localize(EWSDateTime.now())

# Datetime math works transparently
two_hours_later = localized_dt + timedelta(hours=2)
two_hours = two_hours_later - localized_dt
two_hours_later += timedelta(hours=2)

# Dates
my_date = EWSDate(2017, 9, 5)
today = EWSDate.today()
also_today = right_now.date()
also_today += timedelta(days=10)

# UTC helpers. 'UTC' is the UTC timezone as an EWSTimeZone instance.
# 'UTC_NOW' returns a timezone-aware UTC timestamp of current time.
from exchangelib import UTC, UTC_NOW

right_now_in_utc = UTC.localize(EWSDateTime.now())
right_now_in_utc = UTC_NOW()

# Already have a Python datetime object you want to use? Make sure it's localized. Then pass 
# it to from_datetime().
pytz_tz = pytz.timezone('Europe/Copenhagen')
py_dt = pytz_tz.localize(datetime(2017, 12, 11, 10, 9, 8))
ews_now = EWSDateTime.from_datetime(py_dt)
```

## Creating, updating, deleting, sending, moving, archiving

```python
# Here's an example of creating a calendar item in the user's standard calendar.  If you want to
# access a non-standard calendar, choose a different one from account.folders[Calendar].
#
# You can create, update and delete single items:
from exchangelib import Account, CalendarItem, Message, Mailbox, FileAttachment, HTMLBody
from exchangelib.items import SEND_ONLY_TO_ALL, SEND_ONLY_TO_CHANGED
from exchangelib.properties import DistinguishedFolderId

a = Account(...)
item = CalendarItem(folder=a.calendar, subject='foo')
item.save()  # This gives the item an 'id' and a 'changekey' value
item.save(send_meeting_invitations=SEND_ONLY_TO_ALL)  # Send a meeting invitation to attendees
# Update a field. All fields have a corresponding Python type that must be used.
item.subject = 'bar'
# Print all available fields on the 'CalendarItem' class. Beware that some fields are read-only, or
# read-only after the item has been saved or sent, and some fields are not supported on old
# versions of Exchange.
print(CalendarItem.FIELDS)
item.save()  # When the items has an item_id, this will update the item
item.save(update_fields=['subject'])  # Only updates certain fields. Accepts a list of field names.
item.save(send_meeting_invitations=SEND_ONLY_TO_CHANGED)  # Send invites only to attendee changes
item.delete()  # Hard deletinon
item.delete(send_meeting_cancellations=SEND_ONLY_TO_ALL)  # Send cancellations to all attendees
item.soft_delete()  # Delete, but keep a copy in the recoverable items folder
item.move_to_trash()  # Move to the trash folder
item.move(a.trash)  # Also moves the item to the trash folder
item.copy(a.trash)  # Creates a copy of the item to the trash folder
item.archive(DistinguishedFolderId('inbox'))  # Archives the item to inbox of the the archive mailbox

# You can also send emails. If you don't want a local copy:
m = Message(
    account=a,
    subject='Daily motivation',
    body='All bodies are beautiful',
    to_recipients=[
        Mailbox(email_address='anne@example.com'),
        Mailbox(email_address='bob@example.com'),
    ],
    cc_recipients=['carl@example.com', 'denice@example.com'],  # Simple strings work, too
    bcc_recipients=[
        Mailbox(email_address='erik@example.com'),
        'felicity@example.com',
    ],  # Or a mix of both
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

# Likewise, you can reply to and forward messages that are stored in your mailbox (i.e. they
# have an item ID).
m = a.sent.get(subject='Daily motivation')
m.reply(
    subject='Re: Daily motivation',
    body='I agree',
    to_recipients=['carl@example.com', 'denice@example.com']
)
m.reply_all(subject='Re: Daily motivation', body='I agree')
m.forward(
    subject='Fwd: Daily motivation',
    body='Hey, look at this!', 
    to_recipients=['carl@example.com', 'denice@example.com']
)

# You can also edit a draft of a reply or forward
forward_draft = m.create_forward(
    subject='Fwd: Daily motivation',
    body='Hey, look at this!',
    to_recipients=['carl@example.com', 'denice@example.com']
).save(a.drafts) # gives you back the item
forward_draft.reply_to = ['erik@example.com']
forward_draft.attach(FileAttachment(name='my_file.txt', content='hello world'.encode('utf-8')))
forward_draft.send() # now our forward has an extra reply_to field and an extra attachment.

# EWS distinguishes between plain text and HTML body contents. If you want to send HTML body
# content, use the HTMLBody helper. Clients will see this as HTML and display the body correctly:
item.body = HTMLBody('<html><body>Hello happy <blink>OWA user!</blink></body></html>')
```

## Bulk operations

```python
# Build a list of calendar items
from exchangelib import Account, CalendarItem, EWSDateTime, EWSTimeZone, Attendee, Mailbox
from exchangelib.properties import DistinguishedFolderId

a = Account(...)
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
return_ids = a.bulk_create(folder=a.calendar, items=calendar_items)

# Bulk fetch, when you have a list of item IDs and want the full objects. Returns a generator.
calendar_ids = [(i.id, i.changekey) for i in calendar_items]
items_iter = a.fetch(ids=calendar_ids)
# If you only want some fields, use the 'only_fields' attribute
items_iter = a.fetch(ids=calendar_ids, only_fields=['start', 'subject'])

# Bulk update items. Each item must be accompanied by a list of attributes to update
updated_ids = a.bulk_update(items=[(i, ('start', 'subject')) for i in calendar_items])

# Move many items to a new folder
new_ids = a.bulk_move(ids=calendar_ids, to_folder=a.other_calendar)

# Send draft messages in bulk
message_ids = a.drafts.all().only('id', 'changekey')
new_ids = a.bulk_send(ids=message_ids, save_copy=False)

# Delete in bulk
delete_results = a.bulk_delete(ids=calendar_ids)

# Archive in bulk
delete_results = a.bulk_archive(ids=calendar_ids, to_folder=DistinguishedFolderId('inbox'))

# Bulk delete items found as a queryset
a.inbox.filter(subject__startswith='Invoice').delete()

# Likewise, you can bulk send, copy, move or archive items found in a QuerySet
a.drafts.filter(subject__startswith='Invoice').send()
# All kwargs are passed on to the equivalent bulk methods on the Account
a.drafts.filter(subject__startswith='Invoice').send(save_copy=False)
a.inbox.filter(subject__startswith='Invoice').copy(to_folder=a.inbox / 'Archive')
a.inbox.filter(subject__startswith='Invoice').move(to_folder=a.inbox / 'Archive')
a.inbox.filter(subject__startswith='Invoice').archive(to_folder=DistinguishedFolderId('inbox'))

# You can change the default page size of bulk operations if you have a slow or busy server
a.inbox.filter(subject__startswith='Invoice').delete(page_size=25)
```

## Searching

Searching is modeled after the Django QuerySet API, and a large part of
the API is supported. Like in Django, the QuerySet is lazy and doesn't
fetch anything before the QuerySet is iterated. QuerySets support
chaining, so you can build the final query in multiple steps, and you
can re-use a base QuerySet for multiple sub-searches. The QuerySet
returns an iterator, and results are cached when the QuerySet is fully
iterated the first time.

Here are some examples of using the API:

```python
from datetime import timedelta
from exchangelib import Account, EWSDateTime, FolderCollection, Q

a = Account(...)
all_items = a.inbox.all()  # Get everything
all_items_without_caching = a.inbox.all().iterator()  # Get everything, but don't cache
# Chain multiple modifiers ro refine the query
filtered_items = a.inbox.filter(subject__contains='foo').exclude(categories__icontains='bar')
status_report = a.inbox.all().delete()  # Delete the items returned by the QuerySet
start = a.default_timezone.localize(EWSDateTime(2017, 1, 1))
end = a.default_timezone.localize(EWSDateTime(2018, 1, 1))
items_for_2017 = a.calendar.filter(start__range=(start, end))  # Filter by a date range

# Same as filter() but throws an error if exactly one item isn't returned
item = a.inbox.get(subject='unique_string')

# If you only have the ID and possibly the changekey of an item, you can get the full item:
a.inbox.get(id='AAMkADQy=')
a.inbox.get(id='AAMkADQy=', changekey='FwAAABYA')

# You can sort by a single or multiple fields. Prefix a field with '-' to reverse the sorting. 
# Sorting is efficient since it is done server-side, except when a calendar view sorting on 
# multiple fields.
ordered_items = a.inbox.all().order_by('subject')
reverse_ordered_items = a.inbox.all().order_by('-subject')
 # Indexed properties can be ordered on their individual components
sorted_by_home_street = a.contacts.all().order_by('physical_addresses__Home__street')
# Beware that sorting is done client-side here
a.calendar.view(start=start, end=end).order_by('subject', 'categories')

# Counting and exists
n = a.inbox.all().count()  # Efficient counting
folder_is_empty = not a.inbox.all().exists()  # Efficient tasting

# Restricting returned attributes
sparse_items = a.inbox.all().only('subject', 'start')
# Dig deeper on indexed properties
sparse_items = a.contacts.all().only('phone_numbers')
sparse_items = a.contacts.all().only('phone_numbers__CarPhone')
sparse_items = a.contacts.all().only('physical_addresses__Home__street')

# Return values as dicts, not objects
ids_as_dict = a.inbox.all().values('id', 'changekey')
# Return values as nested lists
values_as_list = a.inbox.all().values_list('subject', 'body')
# Return values as a flat list
all_subjects = a.inbox.all().values_list('physical_addresses__Home__street', flat=True)

# A QuerySet can be indexed and sliced like a normal Python list. Slicing and indexing of the
# QuerySet is efficient because it only fetches the necessary items to perform the slicing.
# Slicing from the end is also efficient, but then you might as well reverse the sorting.
first_ten = a.inbox.all().order_by('-subject')[:10]  # Efficient. We only fetch 10 items
last_ten = a.inbox.all().order_by('-subject')[:-10]  # Efficient, but convoluted
next_ten = a.inbox.all().order_by('-subject')[10:20]  # Efficient. We only fetch 10 items
single_item = a.inbox.all().order_by('-subject')[34298]  # Efficient. We only fetch 1 item
ten_items = a.inbox.all().order_by('-subject')[3420:3430]  # Efficient. We only fetch 10 items
random_emails = a.inbox.all().order_by('-subject')[::3]  # This is just stupid, but works

# The syntax for filter() is modeled after Django QuerySet filters. The following filter lookup 
# types are supported. Some lookups only work with string attributes. Range and less/greater 
# operators only work for date or numerical attributes. Some attributes are not searchable at all 
# via EWS:
qs = a.calendar.all()
qs.filter(subject='foo')  # Returns items where subject is exactly 'foo'. Case-sensitive
qs.filter(start__range=(start, end))  # Returns items within range
qs.filter(subject__in=('foo', 'bar'))  # Return items where subject is either 'foo' or 'bar'
qs.filter(subject__not='foo')  # Returns items where subject is not 'foo'
qs.filter(start__gt=start)  # Returns items starting after 'dt'
qs.filter(start__gte=start)  # Returns items starting on or after 'dt'
qs.filter(start__lt=start)  # Returns items starting before 'dt'
qs.filter(start__lte=start)  # Returns items starting on or before 'dt'
qs.filter(subject__exact='foo')  # Same as filter(subject='foo')
qs.filter(subject__iexact='foo')  #  Returns items where subject is 'foo', 'FOO' or 'Foo'
qs.filter(subject__contains='foo')  # Returns items where subject contains 'foo'
qs.filter(subject__icontains='foo')  # Returns items where subject contains 'foo', 'FOO' or 'Foo'
qs.filter(subject__startswith='foo')  # Returns items where subject starts with 'foo'
# Returns items where subject starts with 'foo', 'FOO' or 'Foo'
qs.filter(subject__istartswith='foo')
# Returns items that have at least one category assigned, i.e. the field exists on the item on the 
# server.
qs.filter(categories__exists=True)
# Returns items that have no categories set, i.e. the field does not exist on the item on the 
# server.
qs.filter(categories__exists=False)

# WARNING: Filtering on the 'body' field is not fully supported by EWS. There seems to be a window
# before some internal search index is populated where case-sensitive or case-insensitive filtering
# for substrings in the body element incorrectly returns an empty result, and sometimes the result
# stays empty.

# filter() also supports EWS QueryStrings. Just pass the string to filter(). QueryStrings cannot
# be combined with other filters. We make no attempt at validating the syntax of the QueryString 
# - we just pass the string verbatim to EWS.
#
# Read more about the QueryString syntax here:
# https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/querystring-querystringtype
a.inbox.filter('subject:XXX')

# filter() also supports Q objects that are modeled after Django Q objects, for building complex
# boolean logic search expressions.
q = (Q(subject__iexact='foo') | Q(subject__contains='bar')) & ~Q(subject__startswith='baz')
a.inbox.filter(q)

# In this example, we filter by categories so we only get the items created by us.
a.calendar.filter(
    start__lt=a.default_timezone.localize(EWSDateTime(2019, 1, 1)),
    end__gt=a.default_timezone.localize(EWSDateTime(2019, 1, 31)),
    categories__contains=['foo', 'bar'],
)

# By default, EWS returns only the master recurring item. If you want recurring calendar
# items to be expanded, use calendar.view(start=..., end=...) instead.
items = a.calendar.view(
    start=a.default_timezone.localize(EWSDateTime(2019, 1, 31)),
    end=a.default_timezone.localize(EWSDateTime(2019, 1, 31)) + timedelta(days=1),
)
for item in items:
    print(item.start, item.end, item.subject, item.body, item.location)

# You can combine view() with other modifiers. For example, to check for conflicts before 
# adding a meeting from 8:00 to 10:00:
has_conflicts = a.calendar.view(
    start=a.default_timezone.localize(EWSDateTime(2019, 1, 31, 8)),
    end=a.default_timezone.localize(EWSDateTime(2019, 1, 31, 10)),
    max_items=1
).exists()

# The filtering syntax also works on collections of folders, so you can search multiple folders in 
# a single request.
a.inbox.children.filter(subject='foo')
a.inbox.walk().filter(subject='foo')
a.inbox.glob('foo*').filter(subject='foo')
# Or select the folders individually
FolderCollection(account=a, folders=[a.inbox, a.calendar]).filter(subject='foo')
```

## Paging

Paging EWS services, e.g. FindItem and, have a default page size of 100. You can
change this value globally if you want:

```python
import exchangelib.services
exchangelib.services.CHUNK_SIZE = 25
```

If you are working with very small or very large items, this may not be a reasonable
value. For example, if you want to retrieve and save emails with large attachments,
you can change this value on a per-queryset basis:

```python
from exchangelib import Account

a = Account(...)
qs = a.inbox.all().only('mime_content')
qs.page_size = 5
for msg in qs.iterator():
    with open('%s.eml' % msg.item_id, 'w') as f:
        f.write(msg.mime_content)
```

Finally, the bulk methods defined on the `Account` class have an optional `chunk_size`
argument that you can use to set a non-default page size when fetching, creating, updating
or deleting items.

```python
from exchangelib import Account, Message

a = Account(...)
huge_list_of_items = [Message(...) for i in range(10000)]
return_ids = a.bulk_create(folder=a.inbox, items=huge_list_of_items, chunk_size=5)
```

## Meetings

The `CalendarItem` class allows you send out requests for meetings that
you initiate or to cancel meetings that you already set out before. It
is also possible to process `MeetingRequest` messages that are received.
You can reply to these messages using the `AcceptItem`,
`TentativelyAcceptItem` and `DeclineItem` classes. If you receive a
cancellation for a meeting (class `MeetingCancellation`) that you
already accepted then you can also process these by removing the entry
from the calendar.

```python
from exchangelib import Account, CalendarItem, EWSDateTime
from exchangelib.items import MeetingRequest, MeetingCancellation, SEND_TO_ALL_AND_SAVE_COPY

a = Account(...)

# create a meeting request and send it out
item = CalendarItem(
    account=a,
    folder=a.calendar,
    start=a.default_timezone.localize(EWSDateTime(2019, 1, 31, 8, 15)),
    end=a.default_timezone.localize(EWSDateTime(2019, 1, 31, 8, 45)),
    subject="Subject of Meeting",
    body="Please come to my meeting",
    required_attendees=['anne@example.com', 'bob@example.com']
)
item.save(send_meeting_invitations=SEND_TO_ALL_AND_SAVE_COPY)

# cancel a meeting that was sent out using the CalendarItem class
for calendar_item in a.calendar.all().order_by('-datetime_received')[:5]:
    # only the organizer of a meeting can cancel it
    if calendar_item.organizer.email_address == a.primary_smtp_address:
        calendar_item.cancel()

# processing an incoming MeetingRequest
for item in a.inbox.all().order_by('-datetime_received')[:5]:
    if isinstance(item, MeetingRequest):
        item.accept(body="Sure, I'll come")
        # Or:
        item.decline(body="No way!")
        # Or:
        item.tentatively_accept(body="Maybe...")

# meeting requests can also be handled from the calendar - e.g. decline the meeting that was 
# received last.
for calendar_item in a.calendar.all().order_by('-datetime_received')[:1]:
    calendar_item.decline()

# processing an incoming MeetingCancellation (also delete from calendar)
for item in a.inbox.all().order_by('-datetime_received')[:5]:
    if isinstance(item, MeetingCancellation):
        if item.associated_calendar_item_id:
            calendar_item = a.inbox.get(
                id=item.associated_calendar_item_id.id,
                changekey=item.associated_calendar_item_id.changekey
            )
            calendar_item.delete()
        item.move_to_trash()
```

## Contacts

Fetching personas from a contact folder is supported using the same
syntax as folders. Just start your query with `.people()`:

```python
# Navigate to a contact folder and start the search
from exchangelib import Account, DistributionList
from exchangelib.indexed_properties import EmailAddress

a = Account(...)
folder = a.root / 'AllContacts'
for p in folder.people():
    print(p)
for p in folder.people().only('display_name').filter(display_name='john').order_by('display_name'):
    print(p)

# Getting a single contact in the GAL contact list
gal = a.contacts / 'GAL Contacts'
contact = gal.get(email_addresses=EmailAddress(email='lucas@example.com'))
# All contacts with a gmail address
gmail_contacts = list(gal.filter(email_addresses__contains=EmailAddress(email='gmail.com')))
# All Gmail email addresses
gmail_addresses = [e.email for c in
                   gal.filter(email_addresses__contains=EmailAddress(email='gmail.com'))
                   for e in c.email_addresses]
# All email addresses
all_addresses = [e.email for c in gal.all()
                 for e in c.email_addresses if not isinstance(c, DistributionList)]
```

Contact items have `photo` and `notes` fields, but they are apparently unused. Instead, you can
add a contact photo and notes like this:

```python
from exchangelib import Account, FileAttachment

a = Account(...)
contact = a.contacts.get(given_name='John')
contact.body = 'This is a note'
contact.save(update_fields=['body'])
att = FileAttachment(
    name='ContactPicture.jpg',
    content_type='image/png',
    is_inline=False,
    is_contact_photo=True,
    content=open('john_profile_picture.png', 'rb').read(),
)
contact.attach(att)
```


## Extended properties

Extended properties makes it possible to attach custom key-value pairs
to items and folders on the Exchange server. There are multiple online
resources that describe working with extended properties, and list many
of the magic values that are used by existing Exchange clients to store
common and custom properties. The following is not a comprehensive
description of the possibilities, but we do intend to support all the
possibilities provided by EWS.

```python
# If folder items have extended properties, you need to register them before you can access them. 
# Create a subclass of ExtendedProperty and define a set of matching setup values:
from exchangelib import Account, ExtendedProperty, CalendarItem, Folder, Message

a = Account(...)

class LunchMenu(ExtendedProperty):
    property_set_id = '12345678-1234-1234-1234-123456781234'
    property_name = 'Catering from the cafeteria'
    property_type = 'String'

# Register the property on the item type of your choice
CalendarItem.register('lunch_menu', LunchMenu)
# Now your property is available as the attribute 'lunch_menu', just like any other attribute
item = CalendarItem(..., lunch_menu='Foie gras et consommé de légumes')
item.save()
for i in a.calendar.all():
    print(i.lunch_menu)
# If you change your mind, jsut remove the property again
CalendarItem.deregister('lunch_menu')

# You can also create named properties (e.g. created from User Defined Fields in Outlook, see 
# issue #137):
class LunchMenu(ExtendedProperty):
    distinguished_property_set_id = 'PublicStrings'
    property_name = 'Catering from the cafeteria'
    property_type = 'String'

# We support extended properties with tags. This is the definition for the 'completed' and 
# 'followup' flag you can add to items in Outlook (see also issue #85):
class Flag(ExtendedProperty):
    property_tag = 0x1090
    property_type = 'Integer'

# Or with property ID:
class MyMeetingArray(ExtendedProperty):
    property_set_id = '00062004-0000-0000-C000-000000000046'
    property_type = 'BinaryArray'
    property_id = 32852

# Or using distinguished property sets combined with property ID (here as a hex value to align 
# with the format usually mentioned in Microsoft docs). This is the definition for a response to
# an Outlook Vote request (see issue #198):
class VoteResponse(ExtendedProperty):
    distinguished_property_set_id = 'Common'
    property_id = 0x00008524
    property_type = 'String'

# Extended properties also work with folders. Here's an example of getting the size (in bytes) of
# a folder:
class FolderSize(ExtendedProperty):
    property_tag = 0x0e08
    property_type = 'Integer'

Folder.register('size', FolderSize)
print(a.inbox.size)

# In general, here's how to work with any MAPI property as listed in e.g.
# https://docs.microsoft.com/en-us/office/client-developer/outlook/mapi/mapi-properties. Let's
# take `PidLidTaskDueDate` as an example. This is the due date for a message maked with the
# follow-up flag in Microsoft Outlook.
#
# PidLidTaskDueDate is documented at
# https://docs.microsoft.com/en-us/office/client-developer/outlook/mapi/pidlidtaskduedate-canonical-property.
# The property ID is `0x00008105` and the property set is `PSETID_Task`. But EWS wants the UUID for
# `PSETID_Task`, so we look that up in the MS-OXPROPS pdf:
# https://docs.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-oxprops/f6ab1613-aefe-447d-a49c-18217230b148
# The UUID is `00062003-0000-0000-C000-000000000046`. The property type is `PT_SYSTIME` which is also called
# `SystemTime` (see
# https://docs.microsoft.com/en-us/dotnet/api/microsoft.exchange.webservices.data.mapipropertytype )
#
# In conclusion, the definition for the due date becomes:

class FlagDue(ExtendedProperty):
    property_set_id = '00062003-0000-0000-C000-000000000046'
    property_id = 0x8105
    property_type = 'SystemTime'

Message.register('flag_due', FlagDue)
```

## Attachments

```python
# It's possible to create, delete and get attachments connected to any item type:
# Process attachments on existing items. FileAttachments have a 'content' attribute
# containing the binary content of the file, and ItemAttachments have an 'item' attribute
# containing the item. The item can be a Message, CalendarItem, Task etc.
import os.path
from exchangelib import Account, FileAttachment, ItemAttachment, Message, CalendarItem, HTMLBody

a = Account
for item in a.inbox.all():
    for attachment in item.attachments:
        if isinstance(attachment, FileAttachment):
            local_path = os.path.join('/tmp', attachment.name)
            with open(local_path, 'wb') as f:
                f.write(attachment.content)
            print('Saved attachment to', local_path)
        elif isinstance(attachment, ItemAttachment):
            if isinstance(attachment.item, Message):
                print(attachment.item.subject, attachment.item.body)

# Streaming downloads of file attachment is supported. This reduces memory consumption since we
# never store the full content of the file in-memory:
for item in a.inbox.all():
    for attachment in item.attachments:
        if isinstance(attachment, FileAttachment):
            local_path = os.path.join('/tmp', attachment.name)
            with open(local_path, 'wb') as f, attachment.fp as fp:
                buffer = fp.read(1024)
                while buffer:
                    f.write(buffer)
                    buffer = fp.read(1024)
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

# If you want to embed an image in the item body, you can link to the file in the HTML
message = Message(...)
logo_filename = 'logo.png'
with open(logo_filename, 'rb') as f:
    my_logo = FileAttachment(name=logo_filename, content=f.read(), is_inline=True, content_id=logo_filename)
message.attach(my_logo)
message.body = HTMLBody('<html><body>Hello logo: <img src="cid:%s"></body></html>' % logo_filename)

# Attachments cannot be updated via EWS. In this case, you must to detach the attachment, update
# the relevant fields, and attach the updated attachment.

# Be aware that adding and deleting attachments from items that are already created in Exchange
# (items that have an item_id) will update the changekey of the item.
```

## Recurring calendar items

There is full read-write support for creating recurring calendar items.
You can create daily, weekly, monthly and yearly recurrences (the latter
two in relative and absolute versions).

Here's an example of creating 7 occurrences on Mondays and Wednesdays of
every third week, starting September 1, 2017:

```python
from datetime import timedelta
from exchangelib import Account, CalendarItem, EWSDateTime
from exchangelib.fields import MONDAY, WEDNESDAY
from exchangelib.recurrence import Recurrence, WeeklyPattern

a = Account(...)
start = a.default_timezone.localize(EWSDateTime(2017, 9, 1, 11))
end = start + timedelta(hours=2)
item = CalendarItem(
    folder=a.calendar,
    start=start,
    end=end,
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

# 'modified_occurrences' and 'deleted_occurrences' of master items are read-only fields. To 
# delete or modify an occurrence, you must use 'view()' to fetch the occurrence and modify or 
# delete it:
for occurrence in a.calendar.view(start=start, end=start + timedelta(days=4*3*7)):
    # Delete or update random occurrences. This will affect 'modified_occurrences' and 
    # 'deleted_occurrences' of the master item.
    if occurrence.start.milliseconds % 2:
        # We receive timestamps as UTC but want to write them back as local timezone
        occurrence.start = occurrence.start.astimezone(a.default_timezone)
        occurrence.start += timedelta(minutes=30)
        occurrence.end = occurrence.end.astimezone(a.default_timezone)
        occurrence.end += timedelta(minutes=30)
        occurrence.subject = 'My new subject'
        occurrence.save()
    else:
        occurrence.delete()
```

## Message timestamp fields

Each `Message` item has four timestamp fields:

-   `datetime_created`
-   `datetime_sent`
-   `datetime_received`
-   `last_modified_time`

The values for these fields are set by the Exchange server and are not
modifiable via EWS. All values are timezone-aware `EWSDateTime`
instances.

The `datetime_sent` value may be earlier than `datetime_created`.

## Out of Facility

You can get and set OOF messages using the `Account.oof_settings`
property:

```python
from exchangelib import Account, OofSettings, EWSDateTime

a = Account(...)

# Get the current OOF settings
a.oof_settings
# Change the OOF settings to something else
a.oof_settings = OofSettings(
    state=OofSettings.SCHEDULED,
    external_audience='Known',
    internal_reply="I'm in the pub. See ya guys!",
    external_reply="I'm having a business dinner in town",
    start=a.default_timezone.localize(EWSDateTime(2017, 11, 1, 11)),
    end=a.default_timezone.localize(EWSDateTime(2017, 12, 1, 11)),
)
# Disable OOF messages
a.oof_settings = OofSettings(
    state=OofSettings.DISABLED,
    internal_reply='',
    external_reply='',
)
```


## Mail tips
Mail tips for an account contain some extra information about the account,
e.g. OOF information, max message size, whether the mailbox is full, messages
are moderated etc. Here's how to get mail tips for a single account:

```python
from exchangelib import Account

a = Account(...)
print(a.mail_tips)
```


## Export and upload

Exchange supports backup and restore of folder contents using special
export and upload services. They are available on the `Account` model:

```python
from exchangelib import Account

a = Account(...)
items = a.inbox.all().only('id', 'changekey')
data = a.export(items)  # Pass a list of Item instances or (item_id, changekey) tuples
a.upload((a.inbox, d) for d in data)  # Restore the items. Expects a list of (folder, data) tuples
```

## Non-account methods

```python
from exchangelib import Account, DLMailbox

a = Account(...)

# Get timezone information from the server
a.protocol.get_timezones()

# Get room lists defined on the server
a.protocol.get_roomlists()

# Get rooms belonging to a specific room list
for rl in a.protocol.get_roomlists():
    a.protocol.get_rooms(rl)

# Get account information for a list of names or email addresses
for mailbox in a.protocol.resolve_names(['ann@example.com', 'bart@example.com']):
    print(mailbox.email_address)
for mailbox, contact in a.protocol.resolve_names(['anne', 'bart'], return_full_contact_data=True):
    print(mailbox.email_address, contact.display_name)

# Get all mailboxes on a distribution list
for mailbox in a.protocol.expand_dl(DLMailbox(email_address='distro@example.com', mailbox_type='PublicDL')):
    print(mailbox.email_address)
# Or just pass a string containing the SMTP address
for mailbox in a.protocol.expand_dl('distro@example.com'):
    print(mailbox.email_address)

# Get searchable mailboxes. This method is only available to users who have been assigned
# the Discovery Management RBAC role. (This feature works on Exchange 2013 onwards)
for mailbox in a.protocol.get_searchable_mailboxes():
    print(mailbox)
```

EWS supports getting availability information for a set of users in a certain
timeframe. The server returns an object for each account containing free/busy
information, including a list of calendar events in the user's calendar, and
the working hours and timezone of the user.

```python
from datetime import timedelta
from exchangelib import Account, EWSDateTime

a = Account(...)
start = a.default_timezone.localize(EWSDateTime.now())
end = start + timedelta(hours=6)
accounts = [(a, 'Organizer', False)]
for busy_info in a.protocol.get_free_busy_info(accounts=accounts, start=start, end=end):
    print(busy_info)
```

The calendar events and working hours are returned as naive datetimes. To convert
to timezone-aware datetimes, a bit of extra work is needed if the users are not
known to be in the same timezone.

```python
# Get all server timezones. We need that to convert 'working_hours_timezone'
from datetime import timedelta
from exchangelib import Account, EWSDateTime, EWSTimeZone

a = Account(...)
timezones = list(a.protocol.get_timezones(return_full_timezone_data=True))

# Get availability information for a list of accounts
start = a.default_timezone.localize(EWSDateTime.now())
end = start + timedelta(hours=6)
# get_free_busy_info() expects a list of (account, attendee_type, exclude_conflicts) tuples
accounts = [(a, 'Organizer', False)]
for busy_info in a.protocol.get_free_busy_info(accounts=accounts, start=start, end=end):
    # Convert the TimeZone object to a Microsoft timezone ID
    ms_id = busy_info.working_hours_timezone.to_server_timezone(timezones, start.year)
    account_tz = EWSTimeZone.from_ms_id(ms_id)
    print(account_tz, busy_info.working_hours)
    for event in busy_info.calendar_events:
        print(account_tz.localize(event.start), account_tz.localize(event.end))
```


## Troubleshooting

If you are having trouble using this library, the first thing to try is
to enable debug logging. This will output a huge amount of information
about what is going on, most notable the actual XML documents that are
going over the wire. This can be really handy to see which fields are
being sent and received.

```python
import logging
# This handler will pretty-print and syntax highlight the request and response XML documents
from exchangelib.util import PrettyXmlHandler

logging.basicConfig(level=logging.DEBUG, handlers=[PrettyXmlHandler()])
# Your code using exchangelib goes here
```

Most class definitions have a docstring containing at least a URL to the
MSDN page for the corresponding XML element.

```python
from exchangelib import CalendarItem
print(CalendarItem.__doc__)
```


# Tests

The test suite is split into unit tests, and integration tests that require a real Exchange
server. If you want to run the full test suite, you must provide setup parameters for
a test account. Copy `settings.yml.sample` to `settings.yml` and change the default
parameters. If a `settings.yml` is available, we will run the entire test suite. Otherwise,
just the unit tests are run.

*WARNING*: The test account should not contain valuable data. The tests try hard to no touch
existing data in the account, but accidents happen.

You can run either the entire test suite or individual tests.

```bash
# Full test suite
python setup.py test

# Single test class or test case
python tests/__init__.py FolderTest.test_refresh
# Or, if you don't want extreme levels of debug output:
python tests/__init__.py FolderTest.test_refresh -q
```


# Notes

Almost all item fields are supported. The remaining ones are tracked in
<https://github.com/ecederstrand/exchangelib/issues/203>.
