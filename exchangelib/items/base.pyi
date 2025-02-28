from ..errors import InvalidTypeError as InvalidTypeError
from ..extended_properties import ExtendedProperty as ExtendedProperty
from ..fields import AttachmentField as AttachmentField, BodyField as BodyField, BooleanField as BooleanField, CharField as CharField, EWSElementField as EWSElementField, ExtendedPropertyField as ExtendedPropertyField, ExtendedPropertyListField as ExtendedPropertyListField, IdElementField as IdElementField, MailboxField as MailboxField, MailboxListField as MailboxListField
from ..properties import EWSElement as EWSElement, EWSMeta as EWSMeta, IdChangeKeyMixIn as IdChangeKeyMixIn, InvalidField as InvalidField, ItemId as ItemId, ReferenceItemId as ReferenceItemId
from ..util import require_account as require_account
from ..version import EXCHANGE_2007_SP1 as EXCHANGE_2007_SP1
from _typeshed import Incomplete

log: Incomplete
ID_ONLY: str
DEFAULT: str
ALL_PROPERTIES: str
SHAPE_CHOICES: Incomplete
SAVE_ONLY: str
SEND_ONLY: str
SEND_AND_SAVE_COPY: str
MESSAGE_DISPOSITION_CHOICES: Incomplete
SEND_TO_NONE: str
SEND_ONLY_TO_ALL: str
SEND_ONLY_TO_CHANGED: str
SEND_TO_ALL_AND_SAVE_COPY: str
SEND_TO_CHANGED_AND_SAVE_COPY: str
SEND_MEETING_INVITATIONS_CHOICES: Incomplete
SEND_MEETING_INVITATIONS_AND_CANCELLATIONS_CHOICES: Incomplete
SEND_MEETING_CANCELLATIONS_CHOICES: Incomplete
ALL_OCCURRENCES: str
SPECIFIED_OCCURRENCE_ONLY: str
AFFECTED_TASK_OCCURRENCES_CHOICES: Incomplete
NEVER_OVERWRITE: str
AUTO_RESOLVE: str
ALWAYS_OVERWRITE: str
CONFLICT_RESOLUTION_CHOICES: Incomplete
HARD_DELETE: str
SOFT_DELETE: str
MOVE_TO_DELETED_ITEMS: str
DELETE_TYPE_CHOICES: Incomplete

class RegisterMixIn(IdChangeKeyMixIn, metaclass=EWSMeta):
    INSERT_AFTER_FIELD: Incomplete
    @classmethod
    def register(cls, attr_name, attr_cls) -> None: ...
    @classmethod
    def deregister(cls, attr_name) -> None: ...

class BaseItem(RegisterMixIn, metaclass=EWSMeta):
    ID_ELEMENT_CLS = ItemId
    account: Incomplete
    folder: Incomplete
    def __init__(self, **kwargs) -> None: ...
    @classmethod
    def from_xml(cls, elem, account): ...

class BaseReplyItem(EWSElement, metaclass=EWSMeta):
    subject: Incomplete
    body: Incomplete
    to_recipients: Incomplete
    cc_recipients: Incomplete
    bcc_recipients: Incomplete
    is_read_receipt_requested: Incomplete
    is_delivery_receipt_requested: Incomplete
    author: Incomplete
    reference_item_id: Incomplete
    new_body: Incomplete
    received_by: Incomplete
    received_representing: Incomplete
    account: Incomplete
    def __init__(self, **kwargs) -> None: ...
    def send(self, save_copy: bool = True, copy_to_folder: Incomplete | None = None): ...
    def save(self, folder): ...

class BulkCreateResult(BaseItem):
    attachments: Incomplete
    def __init__(self, **kwargs) -> None: ...
