from .common import TimedTestCase as TimedTestCase

class TransportTest(TimedTestCase):
    def test_get_auth_method_from_response(self, m) -> None: ...
