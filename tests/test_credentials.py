import pickle

from exchangelib.account import Identity
from exchangelib.credentials import (
    Credentials,
    OAuth2AuthorizationCodeCredentials,
    OAuth2Credentials,
    OAuth2LegacyCredentials,
)

from .common import TimedTestCase


class CredentialsTest(TimedTestCase):
    def test_hash(self):
        # Test that we can use credentials as a dict key
        self.assertEqual(hash(Credentials("a", "b")), hash(Credentials("a", "b")))
        self.assertNotEqual(hash(Credentials("a", "b")), hash(Credentials("a", "a")))
        self.assertNotEqual(hash(Credentials("a", "b")), hash(Credentials("b", "b")))

    def test_equality(self):
        self.assertEqual(Credentials("a", "b"), Credentials("a", "b"))
        self.assertNotEqual(Credentials("a", "b"), Credentials("a", "a"))
        self.assertNotEqual(Credentials("a", "b"), Credentials("b", "b"))

    def test_type(self):
        self.assertEqual(Credentials("a", "b").type, Credentials.UPN)
        self.assertEqual(Credentials("a@example.com", "b").type, Credentials.EMAIL)
        self.assertEqual(Credentials("a\\n", "b").type, Credentials.DOMAIN)

    def test_pickle(self):
        # Test that we can pickle, hash, repr, str and compare various credentials types
        for o in (
            Identity("XXX", "YYY", "ZZZ", "WWW"),
            Credentials("XXX", "YYY"),
            OAuth2Credentials(client_id="XXX", client_secret="YYY", tenant_id="ZZZZ"),
            OAuth2Credentials(client_id="XXX", client_secret="YYY", tenant_id="ZZZZ", identity=Identity("AAA")),
            OAuth2LegacyCredentials(
                client_id="XXX", client_secret="YYY", tenant_id="ZZZZ", username="AAA", password="BBB"
            ),
            OAuth2AuthorizationCodeCredentials(client_id="WWW", client_secret="XXX", authorization_code="YYY"),
            OAuth2AuthorizationCodeCredentials(
                client_id="WWW", client_secret="XXX", access_token={"access_token": "ZZZ"}
            ),
            OAuth2AuthorizationCodeCredentials(access_token={"access_token": "ZZZ"}),
            OAuth2AuthorizationCodeCredentials(
                client_id="WWW",
                client_secret="XXX",
                authorization_code="YYY",
                access_token={"access_token": "ZZZ"},
                tenant_id="ZZZ",
                identity=Identity("AAA"),
            ),
        ):
            with self.subTest(o=o):
                pickled_o = pickle.dumps(o)
                unpickled_o = pickle.loads(pickled_o)
                self.assertIsInstance(unpickled_o, type(o))
                self.assertEqual(o, unpickled_o)
                self.assertEqual(hash(o), hash(unpickled_o))
                self.assertEqual(repr(o), repr(unpickled_o))
                self.assertEqual(str(o), str(unpickled_o))

    def test_plain(self):
        OAuth2Credentials("XXX", "YYY", "ZZZZ").refresh("XXX")  # No-op

    def test_oauth_validation(self):
        with self.assertRaises(TypeError) as e:
            OAuth2AuthorizationCodeCredentials(client_id="WWW", client_secret="XXX", access_token="XXX")
        self.assertEqual(
            e.exception.args[0],
            "'access_token' 'XXX' must be of type <class 'oauthlib.oauth2.rfc6749.tokens.OAuth2Token'>",
        )

        c = OAuth2Credentials("XXX", "YYY", "ZZZZ")
        c.refresh("XXX")  # No-op

        with self.assertRaises(TypeError) as e:
            c.on_token_auto_refreshed("XXX")
        self.assertEqual(
            e.exception.args[0],
            "'access_token' 'XXX' must be of type <class 'oauthlib.oauth2.rfc6749.tokens.OAuth2Token'>",
        )
        c.on_token_auto_refreshed(dict(access_token="XXX"))
        self.assertIsInstance(c.sig(), int)
