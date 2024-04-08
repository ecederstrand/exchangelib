import logging

from ..errors import MalformedResponseError
from ..properties import UserResponse
from ..transport import DEFAULT_ENCODING
from ..util import ANS, add_xml_child, create_element, ns_translation, set_xml_value, xml_to_str
from ..version import EXCHANGE_2010
from .common import EWSService

log = logging.getLogger(__name__)


class GetUserSettings(EWSService):
    """Take a list of users and requested Autodiscover settings for these users. Returns the requested settings values.

    MSDN:
    https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/getusersettings-operation-soap
    """

    SERVICE_NAME = "GetUserSettings"
    NS_MAP = {k: v for k, v in ns_translation.items() if k in ("s", "t", "a", "wsa", "xsi")}
    element_container_name = f"{{{ANS}}}UserResponses"
    supported_from = EXCHANGE_2010

    def call(self, users, settings):
        return self._elems_to_objs(self._get_elements(self.get_payload(users=users, settings=settings)))

    def wrap(self, content, api_version=None):
        envelope = create_element("s:Envelope", nsmap=self.NS_MAP)
        header = create_element("s:Header")
        if api_version:
            add_xml_child(header, "a:RequestedServerVersion", api_version)
        action = f"http://schemas.microsoft.com/exchange/2010/Autodiscover/Autodiscover/{self.SERVICE_NAME}"
        add_xml_child(header, "wsa:Action", action)
        add_xml_child(header, "wsa:To", self.protocol.service_endpoint)
        identity = self._account_to_impersonate
        if identity:
            add_xml_child(header, "t:ExchangeImpersonation", identity)
        envelope.append(header)
        body = create_element("s:Body")
        body.append(content)
        envelope.append(body)
        return xml_to_str(envelope, encoding=DEFAULT_ENCODING, xml_declaration=True)

    def _elem_to_obj(self, elem):
        return UserResponse.from_xml(elem=elem, account=None)

    def get_payload(self, users, settings):
        payload = create_element(f"a:{self.SERVICE_NAME}RequestMessage")
        request = create_element("a:Request")
        users_elem = create_element("a:Users")
        for user in users:
            mailbox = create_element("a:Mailbox")
            set_xml_value(mailbox, user)
            add_xml_child(users_elem, "a:User", mailbox)
        if not len(users_elem):
            raise ValueError("'users' must not be empty")
        request.append(users_elem)
        requested_settings = create_element("a:RequestedSettings")
        for setting in settings:
            add_xml_child(requested_settings, "a:Setting", UserResponse.SETTINGS_MAP[setting])
        if not len(requested_settings):
            raise ValueError("'requested_settings' must not be empty")
        request.append(requested_settings)
        payload.append(request)
        return payload

    @classmethod
    def _response_tag(cls):
        """Return the name of the element containing the service response."""
        return f"{{{ANS}}}{cls.SERVICE_NAME}ResponseMessage"

    def _get_element_container(self, message, name=None):
        response = message.find(f"{{{ANS}}}Response")
        # ErrorCode: See
        # https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/errorcode-soap
        # There are two 'ErrorCode' elements in the response; one is a child of the 'Response' element, the other is a
        # child of the 'UserResponse' element. Let's handle both with the same code.
        res = UserResponse.parse_elem(response)
        if isinstance(res, Exception):
            raise res
        if res.error_code == "NoError":
            container = response.find(name)
            if container is None:
                raise MalformedResponseError(f"No {name} elements in ResponseMessage ({xml_to_str(response)})")
            return container
        # Raise any non-acceptable errors in the container, or return the acceptable exception instance
        try:
            raise self._get_exception(code=res.error_code, text=res.error_message, msg_xml=None)
        except self.ERRORS_TO_CATCH_IN_RESPONSE as e:
            return e
