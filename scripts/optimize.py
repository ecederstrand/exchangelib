#!/usr/bin/env python

# Measures bulk create and delete performance for different session pool sizes and payload chunksizes
import copy
import datetime
import logging
import time
from pathlib import Path

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from yaml import safe_load

from exchangelib import DELEGATE, Account, CalendarItem, Configuration, Credentials, FaultTolerance

logging.basicConfig(level=logging.WARNING)

try:
    settings = safe_load((Path(__file__).parent.parent / "settings.yml").read_text())
except FileNotFoundError:
    print("Copy settings.yml.sample to settings.yml and enter values for your test server")
    raise

categories = ["perftest"]
tz = zoneinfo.ZoneInfo("America/New_York")

verify_ssl = settings.get("verify_ssl", True)
if not verify_ssl:
    from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter

    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter

config = Configuration(
    server=settings["server"],
    credentials=Credentials(settings["username"], settings["password"]),
    retry_policy=FaultTolerance(),
)
print(f"Exchange server: {config.service_endpoint}")

account = Account(config=config, primary_smtp_address=settings["account"], access_type=DELEGATE)

# Remove leftovers from earlier tests
account.calendar.filter(categories__contains=categories).delete()


# Calendar item generator
def generate_items(count):
    start = datetime.datetime(2000, 3, 1, 8, 30, 0, tzinfo=tz)
    end = datetime.datetime(2000, 3, 1, 9, 15, 0, tzinfo=tz)
    tpl_item = CalendarItem(
        start=start,
        end=end,
        body=f"This is a performance optimization test of server {account.protocol.server} intended to find the "
        f"optimal batch size and concurrent connection pool size of this server.",
        location="It's safe to delete this",
        categories=categories,
    )
    for j in range(count):
        item = copy.copy(tpl_item)
        item.subject = (f"Performance optimization test {j} by exchangelib",)
        yield item


# Worker
def test(items, chunk_size):
    t1 = time.monotonic()
    ids = account.calendar.bulk_create(items=items, chunk_size=chunk_size)
    t2 = time.monotonic()
    account.bulk_delete(ids=ids, chunk_size=chunk_size)
    t3 = time.monotonic()

    delta1 = t2 - t1
    rate1 = len(ids) / delta1
    delta2 = t3 - t2
    rate2 = len(ids) / delta2
    print(
        f"Time to process {len(ids)} items (batchsize {chunk_size}, poolsize {account.protocol.poolsize}): "
        f"{delta1} / {delta2} ({rate1} / {rate2} per sec)"
    )


# Generate items
calitems = list(generate_items(500))

print("\nTesting batch size")
for i in range(1, 11):
    chunk_size = 25 * i
    account.protocol.poolsize = 5
    test(calitems, chunk_size)
    time.sleep(60)  # Sleep 1 minute. Performance will deteriorate over time if we give the server tie to recover

print("\nTesting pool size")
for i in range(1, 11):
    chunk_size = 10
    account.protocol.poolsize = i
    test(calitems, chunk_size)
    time.sleep(60)
