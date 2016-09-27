#!/usr/bin/env python3
from datetime import datetime
import logging
import os

from yaml import load

from exchangelib import DELEGATE, services, Credentials, Configuration, Account, EWSDateTime, EWSTimeZone
from exchangelib.folders import CalendarItem

logging.basicConfig(level=logging.WARNING)

try:
    with open(os.path.join(os.path.dirname(__file__), 'settings.yml')) as f:
        settings = load(f)
except FileNotFoundError:
    print('Copy settings.yml.sample to settings.yml and enter values for your test server')
    raise

categories = ['foobar', 'perftest']
tz = EWSTimeZone.timezone('US/Pacific')

t0 = datetime.now()

config = Configuration(server=settings['server'],
                       credentials=Credentials(settings['username'], settings['password'], is_service_account=True),
                       verify_ssl=settings['verify_ssl'])
print(('Exchange server: %s' % config.protocol.server))

account = Account(config=config, primary_smtp_address=settings['account'], access_type=DELEGATE)
cal = account.calendar

t1 = datetime.now()
print(('Time to build ExchangeServer object: %s' % (t1 - t0)))

year = 2012
month = 3
day = 20

n = 1000

calitems = []
for i in range(0, n):
    start = tz.localize(EWSDateTime(year, month, day, 8, 30))
    end = tz.localize(EWSDateTime(year, month, day, 9, 15))
    calitems.append(CalendarItem(
        start=start,
        end=end,
        subject='Performance test %s' % i,
        body='Hi from PerfTest',
        location='devnull',
        categories=categories,
    ))

t2 = datetime.now()
delta = t2 - t1
print(('Time to build %s items: %s (%s / sec)' % (len(calitems), delta, (n / (delta.seconds or 1)))))


def avg(delta, n):
    d = (delta.seconds * 1000000 + delta.microseconds) / 1000000
    return n / (d if d else 1)


def perf_test(cbs, dbs, ps):
    t2 = datetime.now()

    services.CreateItem.CHUNKSIZE = cbs
    services.DeleteItem.CHUNKSIZE = dbs
    config.protocol.poolsize = ps
    print(('Config: batch %s/%s pool %s' % (cbs, dbs, ps)))

    ids = cal.bulk_create(items=calitems)

    t3 = datetime.now()
    delta = t3 - t2
    avg_create = avg(delta, n)
    print(('Time to create %s items: %s (%s / sec)' % (len(ids), delta, avg_create)))

    start = tz.localize(EWSDateTime(year, month, day, 0, 0, 0))
    end = tz.localize(EWSDateTime(year, month, day, 23, 59, 59))
    ids = cal.filter(start__le=end, end__gt=start, categories__contains=categories)
    t4 = datetime.now()
    delta = t4 - t3
    avg_fetch = avg(delta, n)
    print(('Time to fetch %s items: %s (%s / sec)' % (len(ids), delta, avg_fetch)))
    result = account.bulk_delete(ids)
    for stat, msg in result:
        if not stat:
            print(('ERROR: %s' % msg))

    t5 = datetime.now()
    delta = t5 - t4
    avg_delete = avg(delta, n)
    print(('Time to delete %s items: %s (%s / sec)' % (len(result), delta, avg_delete)))
    total = t5 - t0
    print(('Total time: %s' % total))
    return avg_create, avg_fetch, avg_delete, total


from datetime import timedelta
from time import sleep

best_c = 0
best_d = 0
best_t = timedelta.max
best_cbs = 0
best_dbs = 0
best_ps = 0


def check(c, d, t, cbs, dbs, ps):
    global best_c, best_d, best_t, best_cbs, best_dbs, best_ps
    if c < best_c:
        best_c, best_cbs, best_ps = c, cbs, ps
        print(('New best save time: %s' % c))
    if d < best_d:
        best_d, best_dbs, best_ps = d, dbs, ps
        print(('New best delete time: %s' % d))
    if t < best_t:
        best_t = t
        print(('New best total time: %s' % t))


def run(cbs, dbs, ps):
    c, f, d, t = perf_test(cbs, dbs, ps)
    check(c, d, t, cbs, dbs, ps)
    # Let server cool off a bit. Otherwise perf numbers deteriorate over time even though the same settings are used.
    sleep(60)


for poolsize in (2, 2, 2):
    for batchsize in (25, 25, 25):
        run(batchsize, batchsize, poolsize)

print(('Best batch/poolsize for create: %s / %s (%s / sec)' % (best_cbs, best_ps, best_c)))
print(('Best batch/poolsize for delete: %s / %s (%s / sec)' % (best_dbs, best_ps, best_d)))
print(('Best total time: %s' % best_t))
