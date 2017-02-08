# Add noqa on top-level convenience imports
from .account import Account  # noqa
from .autodiscover import discover  # noqa
from .configuration import Configuration  # noqa
from .credentials import DELEGATE, IMPERSONATION, Credentials  # noqa
from .ewsdatetime import EWSDateTime, EWSTimeZone  # noqa
from .folders import CalendarItem, Contact, Message, Task, Mailbox, Attendee, Body, HTMLBody  # noqa
from .restriction import Q  # noqa
from .services import SHALLOW, DEEP  # noqa
from .transport import NTLM, DIGEST, BASIC  # noqa


def close_connections():
    from .autodiscover import close_connections as close_autodiscover_connections
    from .protocol import close_connections as close_protocol_connections
    close_autodiscover_connections()
    close_protocol_connections()
