#!/usr/bin/env python3

# Tries to get optimal values for concurrent sessions and payload size for deletes and creates
import copy
import logging
import os
from datetime import datetime

from yaml import load

from exchangelib import DELEGATE, services, Credentials, Configuration, Account, EWSDateTime, EWSTimeZone, CalendarItem

logging.basicConfig(level=logging.WARNING)

try:
    with open(os.path.join(os.path.dirname(__file__), 'settings.yml')) as f:
        settings = load(f)
except FileNotFoundError:
    print('Copy settings.yml.sample to settings.yml and enter values for your test server')
    raise

categories = ['perftest']
tz = EWSTimeZone.timezone('US/Pacific')

config = Configuration(server=settings['server'],
                       credentials=Credentials(settings['username'], settings['password'], is_service_account=True),
                       verify_ssl=settings['verify_ssl'])
print(('Exchange server: %s' % config.protocol.server))

account = Account(config=config, primary_smtp_address=settings['account'], access_type=DELEGATE)
cal = account.calendar


# Calendar item generator
def calitems():
    i = 0
    start = tz.localize(EWSDateTime(2000, 3, 1, 8, 30, 0))
    end = tz.localize(EWSDateTime(2000, 3, 1, 9, 15, 0))
    item = CalendarItem(
        subject='Performance optimization test %s by pyexchange' % i,
        start=start,
        end=end,
        body='This is a performance optimization test of server %s intended to find the optimal batch size and '
             'concurrent connection pool size of this server.' % config.protocol.server,
        location="It's safe to delete this",
        categories=categories,
    )
    while True:
        itm = copy.copy(item)
        itm.subject = 'Test %s' % i
        i += 1
        yield itm


# Worker
def test(calitems):
    t1 = datetime.now()
    ids = cal.bulk_create(items=calitems)
    t2 = datetime.now()
    account.bulk_delete(ids)
    t3 = datetime.now()

    delta1 = t2 - t1
    rate1 = len(ids) / (delta1.seconds if delta1.seconds != 0 else 1)
    delta2 = t3 - t2
    rate2 = len(ids) / (delta2.seconds if delta2.seconds != 0 else 1)
    print(('Time to process %s items (batchsize %s/%s, poolsize %s): %s / %s (%s / %s per sec)' % (
        len(ids), services.CreateItem.CHUNKSIZE, services.DeleteItem.CHUNKSIZE,
        config.protocol.poolsize, delta1, delta2, rate1, rate2)))


item_gen = calitems()

n = 1000
calitems = [next(item_gen) for i in range(n)]
print(('Generated %s calendar items for import' % len(calitems)))

print('\nTesting batch size')
for i in range(1, 11):
    services.CreateItem.CHUNKSIZE = 10 * i
    services.DeleteItem.CHUNKSIZE = 10 * i
    config.protocol.poolsize = 5
    test(calitems)

print('\nTesting pool size')
for i in range(1, 11):
    services.CreateItem.CHUNKSIZE = 50
    services.DeleteItem.CHUNKSIZE = 50
    config.protocol.poolsize = i
    test(calitems)
