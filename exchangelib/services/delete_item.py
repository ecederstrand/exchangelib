from collections import OrderedDict

from ..util import create_element
from ..version import EXCHANGE_2013_SP1
from .common import EWSAccountService, EWSPooledMixIn, create_item_ids_element


class DeleteItem(EWSAccountService, EWSPooledMixIn):
    """Takes a folder and a list of (id, changekey) tuples. Returns result of deletion as a list of tuples
    (success[True|False], errormessage), in the same order as the input list.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/deleteitem

    """
    SERVICE_NAME = 'DeleteItem'
    element_container_name = None  # DeleteItem doesn't return a response object, just status in XML attrs

    def call(self, items, delete_type, send_meeting_cancellations, affected_task_occurrences, suppress_read_receipts):
        from ..items import DELETE_TYPE_CHOICES, SEND_MEETING_CANCELLATIONS_CHOICES, AFFECTED_TASK_OCCURRENCES_CHOICES
        if delete_type not in DELETE_TYPE_CHOICES:
            raise ValueError("'delete_type' %s must be one of %s" % (
                delete_type, DELETE_TYPE_CHOICES
            ))
        if send_meeting_cancellations not in SEND_MEETING_CANCELLATIONS_CHOICES:
            raise ValueError("'send_meeting_cancellations' %s must be one of %s" % (
                send_meeting_cancellations, SEND_MEETING_CANCELLATIONS_CHOICES
            ))
        if affected_task_occurrences not in AFFECTED_TASK_OCCURRENCES_CHOICES:
            raise ValueError("'affected_task_occurrences' %s must be one of %s" % (
                affected_task_occurrences, AFFECTED_TASK_OCCURRENCES_CHOICES
            ))
        if suppress_read_receipts not in (True, False):
            raise ValueError("'suppress_read_receipts' %s must be True or False" % suppress_read_receipts)
        return self._pool_requests(payload_func=self.get_payload, **dict(
            items=items,
            delete_type=delete_type,
            send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences,
            suppress_read_receipts=suppress_read_receipts,
        ))

    def get_payload(self, items, delete_type, send_meeting_cancellations, affected_task_occurrences,
                    suppress_read_receipts):
        # Takes a list of (id, changekey) tuples or Item objects and returns the XML for a DeleteItem request.
        if self.account.version.build >= EXCHANGE_2013_SP1:
            deleteitem = create_element(
                'm:%s' % self.SERVICE_NAME,
                attrs=OrderedDict([
                    ('DeleteType', delete_type),
                    ('SendMeetingCancellations', send_meeting_cancellations),
                    ('AffectedTaskOccurrences', affected_task_occurrences),
                    ('SuppressReadReceipts', 'true' if suppress_read_receipts else 'false'),
                ])
            )
        else:
            deleteitem = create_element(
                'm:%s' % self.SERVICE_NAME,
                attrs=OrderedDict([
                    ('DeleteType', delete_type),
                    ('SendMeetingCancellations', send_meeting_cancellations),
                    ('AffectedTaskOccurrences', affected_task_occurrences),
                 ])
            )

        item_ids = create_item_ids_element(items=items, version=self.account.version)
        deleteitem.append(item_ids)
        return deleteitem
