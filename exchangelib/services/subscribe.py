"""The 'Subscribe' service has three different modes - pull, push and streaming - with different signatures. Implement
as three distinct classes.
"""

import abc

from ..util import MNS, create_element
from .common import EWSAccountService, add_xml_child, folder_ids_element


class Subscribe(EWSAccountService, metaclass=abc.ABCMeta):
    """Base class for subscription classes.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/subscribe-operation"""

    SERVICE_NAME = "Subscribe"
    EVENT_TYPES = (
        "CopiedEvent",
        "CreatedEvent",
        "DeletedEvent",
        "ModifiedEvent",
        "MovedEvent",
        "NewMailEvent",
        "FreeBusyChangedEvent",
    )
    subscription_request_elem_tag = None

    def _partial_call(self, payload_func, folders, event_types, **kwargs):
        if set(event_types) - set(self.EVENT_TYPES):
            raise ValueError(f"'event_types' values must consist of values in {self.EVENT_TYPES}")
        return self._elems_to_objs(
            self._get_elements(payload=payload_func(folders=folders, event_types=event_types, **kwargs))
        )

    def _elem_to_obj(self, elem):
        subscription_elem, watermark_elem = elem
        return subscription_elem.text, watermark_elem.text

    @classmethod
    def _get_elements_in_container(cls, container):
        return [(container.find(f"{{{MNS}}}SubscriptionId"), container.find(f"{{{MNS}}}Watermark"))]

    def _partial_payload(self, folders, event_types):
        if folders is None:
            # Interpret this as "all folders"
            request_elem = create_element(self.subscription_request_elem_tag, attrs=dict(SubscribeToAllFolders=True))
        else:
            request_elem = create_element(self.subscription_request_elem_tag)
            folder_ids = folder_ids_element(folders=folders, version=self.account.version, tag="t:FolderIds")
            request_elem.append(folder_ids)
        event_types_elem = create_element("t:EventTypes")
        for event_type in event_types:
            add_xml_child(event_types_elem, "t:EventType", event_type)
        if not len(event_types_elem):
            raise ValueError("'event_types' must not be empty")
        request_elem.append(event_types_elem)
        return request_elem


class SubscribeToPull(Subscribe):
    # https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/pullsubscriptionrequest
    subscription_request_elem_tag = "m:PullSubscriptionRequest"
    prefer_affinity = True

    def call(self, folders, event_types, watermark, timeout):
        yield from self._partial_call(
            payload_func=self.get_payload,
            folders=folders,
            event_types=event_types,
            timeout=timeout,
            watermark=watermark,
        )

    def get_payload(self, folders, event_types, watermark, timeout):
        payload = create_element(f"m:{self.SERVICE_NAME}")
        request_elem = self._partial_payload(folders=folders, event_types=event_types)
        if watermark:
            add_xml_child(request_elem, "m:Watermark", watermark)
        add_xml_child(request_elem, "t:Timeout", timeout)  # In minutes
        payload.append(request_elem)
        return payload


class SubscribeToPush(Subscribe):
    # https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/pushsubscriptionrequest
    subscription_request_elem_tag = "m:PushSubscriptionRequest"

    def call(self, folders, event_types, watermark, status_frequency, url):
        yield from self._partial_call(
            payload_func=self.get_payload,
            folders=folders,
            event_types=event_types,
            status_frequency=status_frequency,
            url=url,
            watermark=watermark,
        )

    def get_payload(self, folders, event_types, watermark, status_frequency, url):
        payload = create_element(f"m:{self.SERVICE_NAME}")
        request_elem = self._partial_payload(folders=folders, event_types=event_types)
        if watermark:
            add_xml_child(request_elem, "m:Watermark", watermark)
        add_xml_child(request_elem, "t:StatusFrequency", status_frequency)  # In minutes
        add_xml_child(request_elem, "t:URL", url)
        payload.append(request_elem)
        return payload


class SubscribeToStreaming(Subscribe):
    # https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/streamingsubscriptionrequest
    subscription_request_elem_tag = "m:StreamingSubscriptionRequest"
    prefer_affinity = True

    def call(self, folders, event_types):
        yield from self._partial_call(payload_func=self.get_payload, folders=folders, event_types=event_types)

    def _elem_to_obj(self, elem):
        return elem.text

    @classmethod
    def _get_elements_in_container(cls, container):
        return [container.find(f"{{{MNS}}}SubscriptionId")]

    def get_payload(self, folders, event_types):
        payload = create_element(f"m:{self.SERVICE_NAME}")
        payload.append(self._partial_payload(folders=folders, event_types=event_types))
        return payload
