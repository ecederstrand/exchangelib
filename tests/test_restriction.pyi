from .common import TimedTestCase as TimedTestCase, mock_account as mock_account, mock_protocol as mock_protocol

class RestrictionTest(TimedTestCase):
    def test_magic(self) -> None: ...
    def test_q(self) -> None: ...
    def test_q_expr(self) -> None: ...
    def test_q_inversion(self) -> None: ...
    def test_q_boolean_ops(self) -> None: ...
    def test_q_failures(self) -> None: ...
    def test_q_never(self) -> None: ...
    def test_q_simplification(self) -> None: ...
    def test_q_querystring(self) -> None: ...
