"""
This script is an example of 'exchangelib' usage. It will give you email and appointment notifications from your 
Exchange account on your Ubuntu desktop.

Usage: notifier.py [notify_interval]

You need to install the `libxml2-dev` `libxslt1-dev` packages for 
'exchangelib' to work on Ubuntu.

Login and password is fetched from `~/.netrc`. Add an entry like this:

machine       office365
      login MY_INITIALS@example.com
      password MY_PASSWORD


You can keep the notifier running by adding this to your shell startup script:
     start-stop-daemon \
         --pid ~/office365-notifier/notify.pid \
         --make-pidfile --start --background \
         --startas ~/office365-notifier/notify.sh

Where `~/office365-notifier/notify.sh` contains this:

cd  ~/office365-notifier
if [ ! -d "office365_env" ]; then
    virtualenv -p python3 office365_env
fi
source office365_env/bin/activate
pip3 install sh bs4 exchangelib > /dev/null

sleep=${1:-600}
while true
do
    python3 notifier.py $sleep
    sleep $sleep
done

"""
from datetime import timedelta
from netrc import netrc
import sys
import warnings

from exchangelib import DELEGATE, Configuration, Credentials, Account
from exchangelib.ewsdatetime import UTC_NOW, EWSTimeZone
import sh
from bs4 import BeautifulSoup

# Disable insecure SSL warnings
warnings.filterwarnings("ignore")

# Use notify-send for email notifications and zenity for calendar notifications
notify = sh.Command('/usr/bin/notify-send')
zenity = sh.Command('/usr/bin/zenity')

# Get the local timezone
timedatectl = sh.Command('/usr/bin/timedatectl')
for l in timedatectl():
    if 'Timezone' in l:
        tz_name = l.split()[1]
        break
else:
    raise ValueError('Timezone not found')
tz = EWSTimeZone.timezone(tz_name)

sleep = int(sys.argv[1])  # 1st arg to this script is the number of seconds to look back in the inbox
now = UTC_NOW()
emails_since = now - timedelta(seconds=sleep)
cal_items_before = now + timedelta(seconds=sleep * 4)  # Longer notice of upcoming appointments than new emails
username, _, password = netrc().authenticators('office365')
c = Credentials(username, password, is_service_account=False)
a = Account(primary_smtp_address=c.username, credentials=c, access_type=DELEGATE, autodiscover=True, verify_ssl=False)

for msg in a.calendar.view(start=now, end=cal_items_before)\
        .only('start', 'end', 'subject', 'location')\
        .order_by('start', 'end'):
    if msg.start < now:
        continue
    minutes_to_appointment = int((msg.start - now).total_seconds() / 60)
    subj = 'You have a meeting in %s minutes' % minutes_to_appointment
    body = '%s-%s: %s\n%s' % (
        msg.start.astimezone(tz).strftime('%H:%M'),  
        msg.end.astimezone(tz).strftime('%H:%M'), 
        msg.subject[:150], 
        msg.location
    )
    zenity(**{'info': None, 'no-markup': None, 'title': subj, 'text': body})

for msg in a.inbox.filter(datetime_received__gt=emails_since, is_read=False)\
        .only('datetime_received', 'subject', 'body')\
        .order_by('datetime_received',):
    subj = 'New mail: %s' % msg.subject
    body = BeautifulSoup(msg.body)
    for s in body(['script', 'style']):
        s.extract()
    clean_body = '\n'.join(l for l in body.text.split('\n') if l)
    notify(subj, clean_body[:200])
