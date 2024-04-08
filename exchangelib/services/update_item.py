from ..errors import InvalidEnumValue
from ..ewsdatetime import EWSDate
from ..items import (
    CONFLICT_RESOLUTION_CHOICES,
    MESSAGE_DISPOSITION_CHOICES,
    SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES,
    SEND_ONLY,
    CalendarItem,
    Item,
)
from ..properties import ItemId
from ..util import MNS, create_element
from ..version import EXCHANGE_2013_SP1
from .common import to_item_id
from .update_folder import BaseUpdateService


class UpdateItem(BaseUpdateService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/updateitem-operation"""

    SERVICE_NAME = "UpdateItem"
    SET_FIELD_ELEMENT_NAME = "t:SetItemField"
    DELETE_FIELD_ELEMENT_NAME = "t:DeleteItemField"
    CHANGE_ELEMENT_NAME = "t:ItemChange"
    CHANGES_ELEMENT_NAME = "m:ItemChanges"
    element_container_name = f"{{{MNS}}}Items"

    def call(
        self,
        items,
        conflict_resolution,
        message_disposition,
        send_meeting_invitations_or_cancellations,
        suppress_read_receipts,
    ):
        if conflict_resolution not in CONFLICT_RESOLUTION_CHOICES:
            raise InvalidEnumValue("conflict_resolution", conflict_resolution, CONFLICT_RESOLUTION_CHOICES)
        if message_disposition not in MESSAGE_DISPOSITION_CHOICES:
            raise InvalidEnumValue("message_disposition", message_disposition, MESSAGE_DISPOSITION_CHOICES)
        if send_meeting_invitations_or_cancellations not in SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES:
            raise InvalidEnumValue(
                "send_meeting_invitations_or_cancellations",
                send_meeting_invitations_or_cancellations,
                SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES,
            )
        if message_disposition == SEND_ONLY:
            raise ValueError("Cannot send-only existing objects. Use SendItem service instead")
        return self._elems_to_objs(
            self._chunked_get_elements(
                self.get_payload,
                items=items,
                conflict_resolution=conflict_resolution,
                message_disposition=message_disposition,
                send_meeting_invitations_or_cancellations=send_meeting_invitations_or_cancellations,
                suppress_read_receipts=suppress_read_receipts,
            )
        )

    def _elem_to_obj(self, elem):
        return Item.id_from_xml(elem)

    def _update_elems(self, target, fieldnames):
        fieldnames_copy = list(fieldnames)

        if target.__class__ == CalendarItem:
            # For CalendarItem items where we update 'start' or 'end', we want to update internal timezone fields
            target.clean_timezone_fields(version=self.account.version)  # Possibly also sets timezone values
            for field_name in ("start", "end"):
                if field_name in fieldnames_copy:
                    tz_field_name = target.tz_field_for_field_name(field_name).name
                    if tz_field_name not in fieldnames_copy:
                        fieldnames_copy.append(tz_field_name)

        yield from super()._update_elems(target=target, fieldnames=fieldnames_copy)

    def _get_value(self, target, field):
        value = super()._get_value(target, field)

        if target.__class__ == CalendarItem:
            # For CalendarItem items where we update 'start' or 'end', we want to send values in the local timezone
            if field.name in ("start", "end"):
                if type(value) is EWSDate:
                    # EWS always expects a datetime
                    return target.date_to_datetime(field_name=field.name)
                tz_field_name = target.tz_field_for_field_name(field.name).name
                return value.astimezone(getattr(target, tz_field_name))

        return value

    @staticmethod
    def _target_elem(target):
        return to_item_id(target, ItemId)

    def get_payload(
        self,
        items,
        conflict_resolution,
        message_disposition,
        send_meeting_invitations_or_cancellations,
        suppress_read_receipts,
    ):
        # Takes a list of (Item, fieldnames) tuples where 'Item' is an instance of a subclass of Item and 'fieldnames'
        # are the attribute names that were updated.
        attrs = dict(
            ConflictResolution=conflict_resolution,
            MessageDisposition=message_disposition,
            SendMeetingInvitationsOrCancellations=send_meeting_invitations_or_cancellations,
        )
        if self.account.version.build >= EXCHANGE_2013_SP1:
            attrs["SuppressReadReceipts"] = suppress_read_receipts
        payload = create_element(f"m:{self.SERVICE_NAME}", attrs=attrs)
        payload.append(self._changes_elem(target_changes=items))
        return payload
