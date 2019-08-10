from ..util import add_xml_child, create_element, MNS
from .common import EWSAccountService


class UnsubscribeStreamingFolder(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa564263(v=exchg.150).aspx
    Only works for unsubscribing streaming and pull notifications. You cannot unsubscribe from Push via EWS.
    """
    SERVICE_NAME = 'Unsubscribe'
    element_container_name = None

    def call(self, subscription_id):
        return self._get_elements(payload=self.get_payload(subscription_id))

    def get_payload(self, subscription_id):
        if not subscription_id:
            raise ValueError('Cannot unsubscribe empty subscription id')
        payload = create_element(self.SERVICE_NAME, attrs=dict(xmlns=MNS))
        add_xml_child(payload, 'SubscriptionId', subscription_id)
        return payload
