import logging

from .common import EWSAccountService, add_xml_child
from ..properties import Notification
from ..util import create_element, get_xml_attr, get_xml_attrs, MNS, DocumentYielder, DummyResponse

log = logging.getLogger(__name__)
xml_log = logging.getLogger('%s.xml' % __name__)


class GetStreamingEvents(EWSAccountService):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getstreamingevents-operation
    """
    SERVICE_NAME = 'GetStreamingEvents'
    element_container_name = '{%s}Notifications' % MNS
    streaming = True
    prefer_affinity = True

    # Connection status values
    OK = 'OK'
    CLOSED = 'Closed'

    def __init__(self, *args, **kwargs):
        # These values are set each time call() is consumed
        self.connection_status = None
        self.error_subscription_ids = []
        super().__init__(*args, **kwargs)

    def call(self, subscription_ids, connection_timeout):
        if connection_timeout < 1:
            raise ValueError("'connection_timeout' must be a positive integer")
        for elem in self._get_elements(payload=self.get_payload(
                subscription_ids=subscription_ids, connection_timeout=connection_timeout,
        )):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield Notification.from_xml(elem=elem, account=None)

    @classmethod
    def _get_soap_parts(cls, response, **parse_opts):
        # Pass the response unaltered. We want to use our custom document yielder
        return None, response

    def _get_soap_messages(self, body, **parse_opts):
        # 'body' is actually the raw response passed on by '_get_soap_parts'. We want to continuously read the content,
        # looking for complete XML documents. When we have a full document, we want to parse it as if it was a normal
        # XML response.
        r = body
        for i, doc in enumerate(DocumentYielder(r.iter_content()), start=1):
            xml_log.debug('''Response XML (docs received: %(i)s): %(xml_response)s''', dict(i=i, xml_response=doc))
            response = DummyResponse(url=None, headers=None, request_headers=None, content=doc)
            try:
                _, body = super()._get_soap_parts(response=response, **parse_opts)
            except Exception:
                r.close()  # Release memory
                raise
            # TODO: We're skipping ._update_api_version() here because we don't have access to the 'api_version' used.
            # TODO: We should be doing a lot of error handling for ._get_soap_messages().
            yield from super()._get_soap_messages(body=body, **parse_opts)
            if self.connection_status == self.CLOSED:
                # Don't wait for the TCP connection to timeout
                break

    def _get_element_container(self, message, name=None):
        error_ids_elem = message.find('{%s}ErrorSubscriptionIds' % MNS)
        if error_ids_elem is not None:
            self.error_subscription_ids = get_xml_attrs(error_ids_elem, '{%s}ErrorSubscriptionId' % MNS)
            log.debug('These subscription IDs are invalid: %s', self.error_subscription_ids)
        self.connection_status = get_xml_attr(message, '{%s}ConnectionStatus' % MNS)  # Either 'OK' or 'Closed'
        log.debug('Connection status is: %s', self.connection_status)
        # Upstream expects to find a 'name' tag but our response does not always have it. Return an empty element.
        if message.find(name) is None:
            return []
        return super()._get_element_container(message=message, name=name)

    def get_payload(self, subscription_ids, connection_timeout):
        getstreamingevents = create_element('m:%s' % self.SERVICE_NAME)
        subscriptions_elem = create_element('m:SubscriptionIds')
        for subscription_id in subscription_ids:
            add_xml_child(subscriptions_elem, 't:SubscriptionId', subscription_id)
        if not subscriptions_elem:
            raise ValueError('"subscription_ids" must not be empty')

        getstreamingevents.append(subscriptions_elem)
        add_xml_child(getstreamingevents, 'm:ConnectionTimeout', connection_timeout)
        return getstreamingevents
