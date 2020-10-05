import logging

from ..fields import BooleanField, Base64Field, TextField, MailboxField, MailboxListField, CharField, EWSElementField
from ..properties import ReferenceItemId, ReminderMessageData, Fields
from ..services import SendItem
from ..util import require_account, require_id
from ..version import EXCHANGE_2013, EXCHANGE_2013_SP1
from .base import BaseReplyItem
from .item import Item, AUTO_RESOLVE, SEND_TO_NONE, SEND_ONLY, SEND_AND_SAVE_COPY

log = logging.getLogger(__name__)


class Message(Item):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/message-ex15websvcsotherref
    """
    ELEMENT_NAME = 'Message'
    LOCAL_FIELDS = Fields(
        MailboxField('sender', field_uri='message:Sender', is_read_only=True, is_read_only_after_send=True),
        MailboxListField('to_recipients', field_uri='message:ToRecipients', is_read_only_after_send=True,
                         is_searchable=False),
        MailboxListField('cc_recipients', field_uri='message:CcRecipients', is_read_only_after_send=True,
                         is_searchable=False),
        MailboxListField('bcc_recipients', field_uri='message:BccRecipients', is_read_only_after_send=True,
                         is_searchable=False),
        BooleanField('is_read_receipt_requested', field_uri='message:IsReadReceiptRequested',
                     is_required=True, default=False, is_read_only_after_send=True),
        BooleanField('is_delivery_receipt_requested', field_uri='message:IsDeliveryReceiptRequested',
                     is_required=True, default=False, is_read_only_after_send=True),
        Base64Field('conversation_index', field_uri='message:ConversationIndex', is_read_only=True),
        CharField('conversation_topic', field_uri='message:ConversationTopic', is_read_only=True),
        # Rename 'From' to 'author'. We can't use fieldname 'from' since it's a Python keyword.
        MailboxField('author', field_uri='message:From', is_read_only_after_send=True),
        CharField('message_id', field_uri='message:InternetMessageId', is_read_only_after_send=True),
        BooleanField('is_read', field_uri='message:IsRead', is_required=True, default=False),
        BooleanField('is_response_requested', field_uri='message:IsResponseRequested', default=False, is_required=True),
        TextField('references', field_uri='message:References'),
        MailboxListField('reply_to', field_uri='message:ReplyTo', is_read_only_after_send=True, is_searchable=False),
        MailboxField('received_by', field_uri='message:ReceivedBy', is_read_only=True),
        MailboxField('received_representing', field_uri='message:ReceivedRepresenting', is_read_only=True),
        EWSElementField('reminder_message_data', field_uri='message:ReminderMessageData',
                        value_cls=ReminderMessageData, supported_from=EXCHANGE_2013_SP1, is_read_only=True),
    )
    FIELDS = Item.FIELDS + LOCAL_FIELDS

    __slots__ = tuple(f.name for f in LOCAL_FIELDS)

    @require_account
    def send(self, save_copy=True, copy_to_folder=None, conflict_resolution=AUTO_RESOLVE,
             send_meeting_invitations=SEND_TO_NONE):
        # Only sends a message. The message can either be an existing draft stored in EWS or a new message that does
        # not yet exist in EWS.
        if copy_to_folder and not save_copy:
            raise AttributeError("'save_copy' must be True when 'copy_to_folder' is set")
        if save_copy and not copy_to_folder:
            copy_to_folder = self.account.sent  # 'Sent' is default EWS behaviour
        if self.id:
            SendItem(account=self.account).get(items=[self], saved_item_folder=copy_to_folder)
            # The item will be deleted from the original folder
            self._id = None
            self.folder = copy_to_folder
            return None

        # New message
        if copy_to_folder:
            # This would better be done via send_and_save() but lets just support it here
            self.folder = copy_to_folder
            return self.send_and_save(conflict_resolution=conflict_resolution,
                                      send_meeting_invitations=send_meeting_invitations)

        if self.account.version.build < EXCHANGE_2013 and self.attachments:
            # At least some versions prior to Exchange 2013 can't send attachments immediately. You need to first save,
            # then attach, then send. This is done in send_and_save(). send() will delete the item again.
            self.send_and_save(conflict_resolution=conflict_resolution,
                               send_meeting_invitations=send_meeting_invitations)
            return None

        self._create(message_disposition=SEND_ONLY, send_meeting_invitations=send_meeting_invitations)
        return None

    def send_and_save(self, update_fields=None, conflict_resolution=AUTO_RESOLVE,
                      send_meeting_invitations=SEND_TO_NONE):
        # Sends Message and saves a copy in the parent folder. Does not return an ItemId.
        if self.id:
            self._update(
                update_fieldnames=update_fields,
                message_disposition=SEND_AND_SAVE_COPY,
                conflict_resolution=conflict_resolution,
                send_meeting_invitations=send_meeting_invitations
            )
        else:
            if self.account.version.build < EXCHANGE_2013 and self.attachments:
                # At least some versions prior to Exchange 2013 can't send-and-save attachments immediately. You need
                # to first save, then attach, then send. This is done in save().
                self.save(update_fields=update_fields, conflict_resolution=conflict_resolution,
                          send_meeting_invitations=send_meeting_invitations)
                self.send(save_copy=False, conflict_resolution=conflict_resolution,
                          send_meeting_invitations=send_meeting_invitations)
            else:
                res = self._create(
                    message_disposition=SEND_AND_SAVE_COPY,
                    send_meeting_invitations=send_meeting_invitations
                )
                if res:
                    raise ValueError('Unexpected response in send-only mode')

    @require_id
    def create_reply(self, subject, body, to_recipients=None, cc_recipients=None, bcc_recipients=None):
        if to_recipients is None:
            if not self.author:
                raise ValueError("'to_recipients' must be set when message has no 'author'")
            to_recipients = [self.author]
        return ReplyToItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            subject=subject,
            new_body=body,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
            bcc_recipients=bcc_recipients,
        )

    def reply(self, subject, body, to_recipients=None, cc_recipients=None, bcc_recipients=None):
        self.create_reply(
            subject,
            body,
            to_recipients,
            cc_recipients,
            bcc_recipients
        ).send()

    @require_id
    def create_reply_all(self, subject, body):
        to_recipients = list(self.to_recipients) if self.to_recipients else []
        if self.author:
            to_recipients.append(self.author)
        return ReplyAllToItem(
            account=self.account,
            reference_item_id=ReferenceItemId(id=self.id, changekey=self.changekey),
            subject=subject,
            new_body=body,
            to_recipients=to_recipients,
            cc_recipients=self.cc_recipients,
            bcc_recipients=self.bcc_recipients,
        )

    def reply_all(self, subject, body):
        self.create_reply_all(subject, body).send()


class ReplyToItem(BaseReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/replytoitem"""
    ELEMENT_NAME = 'ReplyToItem'

    __slots__ = tuple()


class ReplyAllToItem(BaseReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/replyalltoitem"""
    ELEMENT_NAME = 'ReplyAllToItem'

    __slots__ = tuple()


class ForwardItem(BaseReplyItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/forwarditem"""
    ELEMENT_NAME = 'ForwardItem'

    __slots__ = tuple()
