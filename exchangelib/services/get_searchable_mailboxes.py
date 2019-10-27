from ..errors import MalformedResponseError
from ..util import create_element, add_xml_child, MNS
from ..version import EXCHANGE_2013
from .common import EWSService


class GetSearchableMailboxes(EWSService):
    """MSDN:
    https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getsearchablemailboxes-operation
    """
    SERVICE_NAME = 'GetSearchableMailboxes'
    element_container_name = '{%s}SearchableMailboxes' % MNS
    failed_mailboxes_container_name = '{%s}FailedMailboxes' % MNS

    def call(self, search_filter, expand_group_membership):
        if self.protocol.version.build < EXCHANGE_2013:
            raise NotImplementedError('%s is only supported for Exchange 2013 servers and later' % self.SERVICE_NAME)
        from ..properties import SearchableMailbox, FailedMailbox
        for elem in self._get_elements(payload=self.get_payload(
                search_filter=search_filter,
                expand_group_membership=expand_group_membership,
        )):
            if isinstance(elem, Exception):
                yield elem
                continue
            if elem.tag == SearchableMailbox.response_tag():
                yield SearchableMailbox.from_xml(elem=elem, account=None)
            elif elem.tag == FailedMailbox.response_tag():
                yield FailedMailbox.from_xml(elem=elem, account=None)
            else:
                raise ValueError("Unknown element tag '%s': (%s)" % (elem.tag, elem))

    def get_payload(self, search_filter, expand_group_membership):
        payload = create_element('m:%s' % self.SERVICE_NAME)
        if search_filter:
            add_xml_child(payload, 'm:SearchFilter', search_filter)
        if expand_group_membership is not None:
            add_xml_child(payload, 'm:ExpandGroupMembership', 'true' if expand_group_membership else 'false')
        return payload

    def _get_elements_in_response(self, response):
        for msg in response:
            for container_name in (self.element_container_name, self.failed_mailboxes_container_name):
                try:
                    container_or_exc = self._get_element_container(message=msg, name=container_name)
                except MalformedResponseError:
                    # Responses bay contain no failed mailboxes. _get_element_container() does not accept this.
                    if container_name == self.failed_mailboxes_container_name:
                        continue
                    raise
                if isinstance(container_or_exc, (bool, Exception)):
                    yield container_or_exc
                else:
                    for c in self._get_elements_in_container(container=container_or_exc):
                        yield c
