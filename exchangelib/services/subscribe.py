"""The 'Subscribe' service has two different modes, pull and push, with different signatures. Implement as two classes.
"""
import abc

from .common import EWSAccountService, create_folder_ids_element, add_xml_child
from ..util import create_element, MNS


class Subscribe(EWSAccountService, metaclass=abc.ABCMeta):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/subscribe-operation"""
    SERVICE_NAME = 'Subscribe'
    EVENT_TYPES = (
        'CopiedEvent',
        'CreatedEvent',
        'DeletedEvent',
        'ModifiedEvent',
        'MovedEvent',
        'NewMailEvent',
        'FreeBusyChangedEvent',
    )
    subscription_request_elem_tag = None

    def _partial_call(self, payload_func, folders, event_types, **kwargs):
        if set(event_types) - set(self.EVENT_TYPES):
            raise ValueError("'event_types' values must consist of values in %r", self.EVENT_TYPES)
        for elem in self._get_elements(payload=payload_func(folders=folders, event_types=event_types, **kwargs)):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield elem

    @classmethod
    def _get_elements_in_container(cls, container):
        return[(container.find('{%s}SubscriptionId' % MNS).text, container.find('{%s}Watermark' % MNS).text)]

    def _partial_payload(self, folders, event_types):
        request_elem = create_element(self.subscription_request_elem_tag)
        folder_ids = create_folder_ids_element(tag='t:FolderIds', folders=folders, version=self.account.version)
        request_elem.append(folder_ids)
        event_types_elem = create_element('t:EventTypes')
        for event_type in event_types:
            add_xml_child(event_types_elem, 't:EventType', event_type)
        if not event_types_elem:
            raise ValueError('"event_types" must not be empty')
        request_elem.append(event_types_elem)
        return request_elem


class SubscribeToPull(Subscribe):
    subscription_request_elem_tag = 'm:PullSubscriptionRequest'

    def call(self, folders, event_types, watermark, timeout):
        yield from self._partial_call(
            payload_func=self.get_payload, folders=folders, event_types=event_types, timeout=timeout,
            watermark=watermark,
        )

    def get_payload(self, folders, event_types, watermark, timeout):
        subscribe = create_element('m:%s' % self.SERVICE_NAME)
        request_elem = self._partial_payload(folders=folders, event_types=event_types)
        if watermark:
            add_xml_child(request_elem, 'm:Watermark', watermark)
        add_xml_child(request_elem, 't:Timeout', timeout)  # In minutes
        subscribe.append(request_elem)
        return subscribe


class SubscribeToPush(Subscribe):
    subscription_request_elem_tag = 'm:PushSubscriptionRequest'

    def call(self, folders, event_types, watermark, status_frequency, url):
        yield from self._partial_call(
            payload_func=self.get_payload, folders=folders, event_types=event_types,
            status_frequency=status_frequency, url=url, watermark=watermark,
        )

    def get_payload(self, folders, event_types, watermark, status_frequency, url):
        subscribe = create_element('m:%s' % self.SERVICE_NAME)
        request_elem = self._partial_payload(folders=folders, event_types=event_types)
        if watermark:
            add_xml_child(request_elem, 'm:Watermark', watermark)
        add_xml_child(request_elem, 't:StatusFrequency', status_frequency)  # In minutes
        add_xml_child(request_elem, 't:URL', url)
        subscribe.append(request_elem)
        return subscribe


class SubscribeToStreaming(Subscribe):
    subscription_request_elem_tag = 'm:StreamingSubscriptionRequest'

    def call(self, folders, event_types):
        yield from self._partial_call(payload_func=self.get_payload, folders=folders, event_types=event_types)

    @classmethod
    def _get_elements_in_container(cls, container):
        return [container.find('{%s}SubscriptionId' % MNS).text]

    def get_payload(self, folders, event_types):
        subscribe = create_element('m:%s' % self.SERVICE_NAME)
        request_elem = self._partial_payload(folders=folders, event_types=event_types)
        subscribe.append(request_elem)
        return subscribe
