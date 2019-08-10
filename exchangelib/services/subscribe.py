from ..util import add_xml_child, create_element, set_xml_value, MNS
from .common import EWSFolderService, EWSAccountService

NEW_MAIL_EVENT = 'NewMailEvent'
CREATED_EVENT = 'CreatedEvent'
DELETED_EVENT = 'DeletedEvent'
MODIFIED_EVENT = 'ModifiedEvent'
MOVED_EVENT = 'MovedEvent'
COPIED_EVENT = 'CopiedEvent'
EVENT_TYPES = (NEW_MAIL_EVENT, CREATED_EVENT, DELETED_EVENT, MODIFIED_EVENT, MOVED_EVENT, COPIED_EVENT)


class SubscribeStreamingFolder(EWSFolderService):
    """
    https://msdn.microsoft.com/en-us/library/office/dn458792(v=exchg.150).aspx
    """
    SERVICE_NAME = 'Subscribe'
    element_container_name = '{%s}SubscriptionId' % MNS

    def call(self, events):
        return self._get_elements(payload=self.get_payload(events))

    def get_payload(self, events):
        payload = create_element('m:%s' % self.SERVICE_NAME)
        streaming_request = create_element('m:StreamingSubscriptionRequest')
        folder_ids = create_element('t:FolderIds')
        set_xml_value(folder_ids, self.folders, version=self.account.version)
        streaming_request.append(folder_ids)
        event_types = create_element('t:EventTypes')
        for event in events:
            add_xml_child(event_types, 't:EventType', event)
        streaming_request.append(event_types)
        payload.append(streaming_request)
        return payload

    def _get_elements_in_container(self, container):
        return [container.text]


class SubscribePushFolder(EWSFolderService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa566188(v=exchg.150).aspx
    """
    SERVICE_NAME = 'Subscribe'
    element_container_name = '{%s}SubscriptionId' % MNS

    def call(self, events, callback_url):
        return self._get_elements(payload=self.get_payload(events, callback_url))

    def get_payload(self, events, callback_url):
        if not callback_url:
            raise ValueError('Call back url must be valid for push subscription')
        payload = create_element('m:%s' % self.SERVICE_NAME)
        streaming_request = create_element('m:PushSubscriptionRequest')
        folder_ids = create_element('t:FolderIds')
        set_xml_value(folder_ids, self.folders, version=self.account.version)
        streaming_request.append(folder_ids)
        event_types = create_element('t:EventTypes')
        for event in events:
            add_xml_child(event_types, 't:EventType', event)
        streaming_request.append(event_types)
        add_xml_child(streaming_request, 't:StatusFrequency', 1)
        add_xml_child(streaming_request, 't:URL', callback_url)
        payload.append(streaming_request)
        return payload

    def _get_elements_in_container(self, container):
        return [container.text]


class GetStreamingEvents(EWSAccountService):
    """
    https://msdn.microsoft.com/en-us/library/office/dn458792(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetStreamingEvents'
    element_container_name = '{%s}Notifications' % MNS

    def call(self, subscription_ids):
        return self._get_elements(payload=self.get_payload(subscription_ids))

    def get_payload(self, subscription_ids):
        if not subscription_ids:
            raise ValueError('Cannot get events without subscription ids')
        payload = create_element('m:%s' % self.SERVICE_NAME)
        ids_elem = create_element('m:SubscriptionIds')
        for subscription_id in subscription_ids:
            add_xml_child(ids_elem, 't:SubscriptionId', subscription_id)
        payload.append(ids_elem)
        add_xml_child(payload, 'm:ConnectionTimeout', 15)
        return payload
