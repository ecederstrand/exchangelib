# coding=utf-8
"""
Implement Mailbox services

"""
from __future__ import unicode_literals

import logging


from .transport import wrap, SOAPNS, TNS, MNS, ENS
from .services import EWSService
from .version import EXCHANGE_2010, EXCHANGE_2013
from .util import chunkify, create_element, add_xml_child, get_xml_attr, to_xml, post_ratelimited, ElementType
from .properties import EWSElement
from .fields import TextField, BooleanField

log = logging.getLogger(__name__)



# class Attendee(EWSElement):
#     # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580339(v=exchg.150).aspx
#     ELEMENT_NAME = 'Attendee'
#
#     FIELDS = [
#         MailboxField('mailbox', is_required=True),
#         ChoiceField('response_type', field_uri='ResponseType', choices={
#             Choice('Unknown'), Choice('Organizer'), Choice('Tentative'), Choice('Accept'), Choice('Decline'),
#             Choice('NoResponseReceived')
#         }, default='Unknown'),
#         DateTimeField('last_response_time', field_uri='LastResponseTime'),
#     ]
#
#     __slots__ = ('mailbox', 'response_type', 'last_response_time')
#
#     def __hash__(self):
#         # TODO: maybe take 'response_type' and 'last_response_time' into account?
#         return hash(self.mailbox)
#

class SearchableMailbox(EWSElement):
        """
        MSDN: https://msdn.microsoft.com/en-us/library/office/jj191013(v=exchg.150).aspx
        """

        ELEMENT_NAME = 'SearchableMailbox'

        #__slots__ = ('guid','primary_smtp_addres','display_name')

        FIELDS = [
                TextField('guid', field_uri='Guid'),
                TextField('primary_smtp_address',field_uri='PrimarySmtpAddress',is_required=False),
                BooleanField('is_external',field_uri='IsExternalMailbox',is_required=False),
                TextField('external_email',field_uri='ExternalEmailAddress',is_required=False),
                TextField('display_name',field_uri='DisplayName',is_required=False),
                BooleanField('is_membership_group',field_uri='IsMembershipGroup',is_required=False),
                TextField('reference_id',field_uri='ReferenceId',is_required=False)
        ]




class GetSearchableMailboxes(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/jj900497(v=exchg.150).aspx


<GetSearchableMailboxesResponse>
   <MessageText/>
   <ResponseCode/>
   <DescriptiveLinkKey/>
   <MessageXml/>
   <SearchableMailboxes/>
   <FailedMailboxes/>
</GetSearchableMailboxesResponse>



<SearchableMailboxes>
   <SearchableMailbox/>
</SearchableMailboxes>

<SearchableMailbox>
   <Guid/>
   <PrimarySmtpAddress/>
   <IsExternalMailbox/>
   <ExternalEmailAddress/>
   <DisplayName/>
   <IsMembershipGroup/>
   <ReferenceId/>
</SearchableMailbox>


<FailedMailboxes>
    <FailedMailbox/>
<FailedMailboxes>

<FailedMailbox>
    <Mailbox/>
    <ErrorCode/>
    <ErrorMessage/>
    <IsArchive/>
</FailedMailbox>


    """
    SERVICE_NAME = 'GetSearchableMailboxes'
    element_container_name = '{%s}SearchableMailboxes' % MNS

    def call(self,account):
        elements = self._get_elements(payload=self.get_payload())
        #return SearchableMailbox.from_xml(elements,account)
        #return elements
        # from .properties import RoomList
        return [SearchableMailbox.from_xml(elem=elem, account=account) for elem in elements]
        #return [elem for elem in elements]

    def get_payload(self):
        return create_element('m:%s' % self.SERVICE_NAME)
