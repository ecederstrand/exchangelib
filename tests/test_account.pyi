from .common import EWSTest as EWSTest, get_random_choice as get_random_choice, get_random_email as get_random_email, get_random_int as get_random_int, get_random_string as get_random_string

class AccountTest(EWSTest):
    def test_magic(self) -> None: ...
    def test_validation(self) -> None: ...
    def test_getlocale_failure(self, m) -> None: ...
    def test_tzlocal_failure(self, m) -> None: ...
    def test_get_default_folder(self) -> None: ...
    def test_pickle(self) -> None: ...
    def test_mail_tips(self) -> None: ...
    def test_delegate(self) -> None: ...
    def test_login_failure_and_credentials_update(self): ...
    def test_protocol_default_values(self) -> None: ...
    def test_basic_inbox_rule(self) -> None: ...
    def test_disabled_inbox_rule(self) -> None: ...
    def test_all_inbox_rule_actions(self) -> None: ...
