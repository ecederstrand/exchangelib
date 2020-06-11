from ..util import create_element, set_xml_value, MNS, TNS
from .common import EWSAccountService


class GetUserOofSettings(EWSAccountService):
    """Get automatic reply settings for the specified mailbox.
    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getuseroofsettings-operation

    """
    SERVICE_NAME = 'GetUserOofSettings'
    element_container_name = '{%s}OofSettings' % TNS

    def call(self, mailbox):
        return self._get_elements(payload=self.get_payload(mailbox=mailbox))

    def get_payload(self, mailbox):
        from ..properties import AvailabilityMailbox
        payload = create_element('m:%sRequest' % self.SERVICE_NAME)
        return set_xml_value(payload, AvailabilityMailbox.from_mailbox(mailbox), version=self.account.version)

    def _get_elements_in_response(self, response):
        # This service only returns one result, but 'response' is a list
        from ..settings import OofSettings
        response = list(response)
        if len(response) != 1:
            raise ValueError("Expected 'response' length 1, got %s" % response)
        msg = response[0]
        container_or_exc = self._get_element_container(message=msg, name=self.element_container_name)
        if isinstance(container_or_exc, (bool, Exception)):
            # pylint: disable=raising-bad-type
            raise container_or_exc
        return OofSettings.from_xml(container_or_exc, account=self.account)

    def _get_element_container(self, message, response_message=None, name=None):
        response_message = message.find('{%s}ResponseMessage' % MNS)
        return super()._get_element_container(
            message=message, response_message=response_message, name=name
        )
