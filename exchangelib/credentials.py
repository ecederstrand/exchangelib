# coding=utf-8
"""
Implements an Exchange user object and access types. Exchange provides two different ways of granting access for a
login to a specific account. Impersonation is used mainly for service accounts that connect via EWS. Delegate is used
for ad-hoc access e.g. granted manually by the user.
See http://blogs.msdn.com/b/exchangedev/archive/2009/06/15/exchange-impersonation-vs-delegate-access.aspx
"""
from __future__ import unicode_literals

import datetime
import logging
from multiprocessing import Lock

from future.utils import python_2_unicode_compatible

log = logging.getLogger(__name__)

IMPERSONATION = 'impersonation'
DELEGATE = 'delegate'
ACCESS_TYPES = (IMPERSONATION, DELEGATE)


@python_2_unicode_compatible
class Credentials(object):
    """
    Keeps login info the way Exchange likes it.

    :param username: Usernames for authentication are of one of these forms:
    * PrimarySMTPAddress
    * WINDOMAIN\\username
    * User Principal Name (UPN)

    :param password: Clear-text password
    """
    EMAIL = 'email'
    DOMAIN = 'domain'
    UPN = 'upn'

    def __init__(self, username, password):
        if username.count('@') == 1:
            self.type = self.EMAIL
        elif username.count('\\') == 1:
            self.type = self.DOMAIN
        else:
            self.type = self.UPN
        self.username = username
        self.password = password

    @property
    def fail_fast(self):
        # Used to choose the error handling policy. When True, a fault-tolerant policy is used. False, a fail-fast
        # policy is used.
        return True

    @property
    def back_off_until(self):
        return None

    @back_off_until.setter
    def back_off_until(self, value):
        raise NotImplementedError()

    def __eq__(self, other):
        return self.username == other.username and self.password == other.password

    def __hash__(self):
        return hash((self.username, self.password))

    def __repr__(self):
        return self.__class__.__name__ + repr((self.username, '********'))

    def __str__(self):
        return self.username


class ServiceAccount(Credentials):
    def __init__(self, username, password, max_wait=3600):
        """
        A Credentials class that enables fault-tolerance handling. Tells internal methods to do an exponential back off
        when requests start failing, and wait up to max_wait seconds before failing.
        """
        super(ServiceAccount, self).__init__(username, password)
        self.max_wait = max_wait
        self._back_off_until = None
        self._back_off_lock = Lock()

    def __getstate__(self):
        # Locks cannot be pickled
        state = self.__dict__.copy()
        del state['_back_off_lock']
        return state

    def __setstate__(self, state):
        # Restore the lock
        self.__dict__.update(state)
        self._back_off_lock = Lock()

    @property
    def fail_fast(self):
        return False

    @property
    def back_off_until(self):
        """Returns the back off value as a datetime. Resets the current back off value if it has expired."""
        if self._back_off_until is None:
            return None
        with self._back_off_lock:
            if self._back_off_until is None:
                return None
            if self._back_off_until < datetime.datetime.now():
                self._back_off_until = None  # The backoff value has expired. Reset
                return None
            return self._back_off_until

    @back_off_until.setter
    def back_off_until(self, value):
        with self._back_off_lock:
            self._back_off_until = value

    def back_off(self, seconds):
        seconds = seconds or 60  # Back off 60 seconds if we didn't get an explicit suggested value
        value = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        with self._back_off_lock:
            self._back_off_until = value
