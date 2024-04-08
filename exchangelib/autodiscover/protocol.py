from ..properties import UserResponse
from ..protocol import BaseProtocol
from ..services import GetUserSettings
from ..transport import get_autodiscover_authtype
from ..version import Version


class AutodiscoverProtocol(BaseProtocol):
    """Protocol which implements the bare essentials for autodiscover."""

    TIMEOUT = 10  # Seconds

    def __init__(self, config):
        if not config.version:
            # Default to the latest supported version
            config.version = Version.all_versions()[0]
        super().__init__(config=config)

    def __str__(self):
        return f"""\
Autodiscover endpoint: {self.service_endpoint}
Auth type: {self.auth_type}"""

    @property
    def version(self):
        return self.config.version

    @property
    def auth_type(self):
        # Autodetect authentication type if necessary
        if self.config.auth_type is None:
            self.config.auth_type = self.get_auth_type()
        return self.config.auth_type

    def get_auth_type(self):
        # Autodetect authentication type.
        return get_autodiscover_authtype(protocol=self)

    def get_user_settings(self, user, settings=None):
        if not settings:
            settings = [
                "user_dn",
                "mailbox_dn",
                "user_display_name",
                "auto_discover_smtp_address",
                "external_ews_url",
                "ews_supported_schemas",
            ]
        for setting in settings:
            if setting not in UserResponse.SETTINGS_MAP:
                raise ValueError(
                    f"Setting {setting!r} is invalid. Valid options are: {sorted(UserResponse.SETTINGS_MAP.keys())}"
                )
        return GetUserSettings(protocol=self).get(users=[user], settings=settings)

    def dummy_xml(self):
        # Generate a valid EWS request for SOAP autodiscovery
        svc = GetUserSettings(protocol=self)
        return svc.wrap(
            content=svc.get_payload(
                users=["DUMMY@example.com"],
                settings=["auto_discover_smtp_address"],
            ),
            api_version=self.config.version.api_version,
        )
