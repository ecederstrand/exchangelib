Exchange Web Services client library
====================================

This module is an ORM for your Exchange mailbox, providing Django-style access to all your data. It is a
platform-independent, well-performing, well-behaving, well-documented, well-tested and simple interface for
communicating with an on-premise Microsoft Exchange 2007-2016 server or Office365 using Exchange Web Services
(EWS). Among other things, it implements autodiscover, and functions for searching, creating, updating, deleting,
exporting and uploading calendar, mailbox, task, contact and distribution list items.

[![image](https://img.shields.io/pypi/v/exchangelib.svg)](https://pypi.org/project/exchangelib/)
[![image](https://img.shields.io/pypi/pyversions/exchangelib.svg)](https://pypi.org/project/exchangelib/)
[![image](https://api.codacy.com/project/badge/Grade/5f805ad901054a889f4b99a82d6c1cb7)](https://app.codacy.com/gh/ecederstrand/exchangelib)
[![image](https://coveralls.io/repos/github/ecederstrand/exchangelib/badge.svg?branch=master)](https://coveralls.io/github/ecederstrand/exchangelib?branch=master)
[![xscode](https://img.shields.io/badge/Available%20on-xs%3Acode-blue)](https://xscode.com/ecederstrand/exchangelib)


## Teaser

Here's a short example of how `exchangelib` works. Let's print the first
100 inbox messages in reverse order:

```python
from exchangelib import Credentials, Account

credentials = Credentials("john@example.com", "topsecret")
account = Account("john@example.com", credentials=credentials, autodiscover=True)

for item in account.inbox.all().order_by("-datetime_received")[:100]:
    print(item.subject, item.sender, item.datetime_received)
```


## Documentation
Documentation is available at [https://ecederstrand.github.io/exchangelib/](https://ecederstrand.github.io/exchangelib/).
Source code documentation is available at [https://ecederstrand.github.io/exchangelib/exchangelib/](https://ecederstrand.github.io/exchangelib/exchangelib/).
