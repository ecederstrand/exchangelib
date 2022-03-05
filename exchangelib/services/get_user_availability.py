from ..properties import FreeBusyView
from ..util import MNS, create_element, set_xml_value
from .common import EWSService


class GetUserAvailability(EWSService):
    """Get detailed availability information for a list of users.
    MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getuseravailability-operation
    """

    SERVICE_NAME = "GetUserAvailability"

    def call(self, timezone, mailbox_data, free_busy_view_options):
        # TODO: Also supports SuggestionsViewOptions, see
        #  https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/suggestionsviewoptions
        return self._elems_to_objs(
            self._get_elements(
                payload=self.get_payload(
                    timezone=timezone, mailbox_data=mailbox_data, free_busy_view_options=free_busy_view_options
                )
            )
        )

    def _elem_to_obj(self, elem):
        return FreeBusyView.from_xml(elem=elem, account=None)

    def get_payload(self, timezone, mailbox_data, free_busy_view_options):
        payload = create_element(f"m:{self.SERVICE_NAME}Request")
        set_xml_value(payload, timezone, version=self.protocol.version)
        mailbox_data_array = create_element("m:MailboxDataArray")
        set_xml_value(mailbox_data_array, mailbox_data, version=self.protocol.version)
        payload.append(mailbox_data_array)
        return set_xml_value(payload, free_busy_view_options, version=self.protocol.version)

    @staticmethod
    def _response_messages_tag():
        return f"{{{MNS}}}FreeBusyResponseArray"

    @classmethod
    def _response_message_tag(cls):
        return f"{{{MNS}}}FreeBusyResponse"

    def _get_elements_in_response(self, response):
        for msg in response:
            container_or_exc = self._get_element_container(message=msg.find(f"{{{MNS}}}ResponseMessage"))
            if isinstance(container_or_exc, Exception):
                yield container_or_exc
            else:
                yield from self._get_elements_in_container(container=msg)

    @classmethod
    def _get_elements_in_container(cls, container):
        return [container.find(f"{{{MNS}}}FreeBusyView")]
