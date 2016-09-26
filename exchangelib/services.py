"""
Implement a selection of EWS services.

Exchange is very picky about things like the order of XML elements in SOAP requests, so we need to generate XML
automatically instead of taking advantage of Python SOAP libraries and the WSDL file.

Exchange EWS references:
    - 2007: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.80).aspx
    - 2010: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.140).aspx
    - 2013: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.150).aspx
"""

import logging
import itertools
from xml.parsers.expat import ExpatError
import traceback

from . import errors
from .errors import EWSWarning, TransportError, SOAPError, ErrorTimeoutExpired, ErrorBatchProcessingStopped, \
    ErrorQuotaExceeded, ErrorCannotDeleteObject, ErrorCreateItemAccessDenied, ErrorFolderNotFound, \
    ErrorNonExistentMailbox, ErrorMailboxStoreUnavailable, ErrorImpersonateUserDenied, ErrorInternalServerError, \
    ErrorInternalServerTransientError, ErrorNoRespondingCASInDestinationSite, ErrorImpersonationFailed, \
    ErrorMailboxMoveInProgress, ErrorAccessDenied, ErrorConnectionFailed, RateLimitError, ErrorServerBusy, \
    ErrorTooManyObjectsOpened, ErrorInvalidLicense, ErrorInvalidSchemaVersionForMailboxVersion, \
    ErrorInvalidServerVersion, ErrorItemNotFound
from .ewsdatetime import EWSDateTime
from .transport import wrap, SOAPNS, TNS, MNS, ENS
from .util import chunkify, create_element, add_xml_child, get_xml_attr, to_xml, post_ratelimited, ElementType, \
    xml_to_str, set_xml_value
from .version import EXCHANGE_2010, EXCHANGE_2013

log = logging.getLogger(__name__)


# Shape enums
IdOnly = 'IdOnly'
# AllProperties doesn't actually get all properties in FindItem, just the "first-class" ones. See
#    http://msdn.microsoft.com/en-us/library/office/dn600367(v=exchg.150).aspx
AllProperties = 'AllProperties'
SHAPE_CHOICES = (IdOnly, AllProperties)

# Traversal enums
SHALLOW = 'Shallow'
SOFT_DELETED = 'SoftDeleted'
DEEP = 'Deep'
ASSOCIATED = 'Associated'
ITEM_TRAVERSAL_CHOICES = (SHALLOW, SOFT_DELETED, ASSOCIATED)
FOLDER_TRAVERSAL_CHOICES = (SHALLOW, DEEP, SOFT_DELETED)


class EWSService:
    SERVICE_NAME = None  # The name of the SOAP service
    element_container_name = None  # The name of the XML element wrapping the collection of returned items
    extra_element_names = []  # Some services may return multiple item types. List them here.

    def __init__(self, protocol):
        self.protocol = protocol
        self.element_name = None

    def payload(self, version, account, *args, **kwargs):
        return wrap(content=self._get_payload(*args, **kwargs), version=version, account=account)

    def _get_payload(self, *args, **kwargs):
        raise NotImplementedError()

    def _get_elements(self, payload, account=None):
        assert isinstance(payload, ElementType)
        try:
            response = self._get_response_xml(payload=payload, account=account)
            return self._get_elements_in_response(response=response)
        except (ErrorQuotaExceeded, ErrorCannotDeleteObject, ErrorCreateItemAccessDenied, ErrorTimeoutExpired,
                ErrorFolderNotFound, ErrorNonExistentMailbox, ErrorMailboxStoreUnavailable, ErrorImpersonateUserDenied,
                ErrorInternalServerError, ErrorInternalServerTransientError, ErrorNoRespondingCASInDestinationSite,
                ErrorImpersonationFailed, ErrorMailboxMoveInProgress, ErrorAccessDenied, ErrorConnectionFailed,
                RateLimitError, ErrorServerBusy, ErrorTooManyObjectsOpened, ErrorInvalidLicense, ErrorItemNotFound):
            # These are known and understood, and don't require a backtrace
            # TODO: ErrorTooManyObjectsOpened means there are too many connections to the database. We should be able to
            # act on this by lowering the self.protocol connection pool size.
            raise
        except Exception:
            # This may run from a thread pool, which obfuscates the stack trace. Print trace immediately.
            log.warning('EWS %s, account %s: Exception in _get_elements: %s', self.protocol.service_endpoint, account,
                        traceback.format_exc(20))
            raise

    def _get_response_xml(self, payload, account=None):
        # Takes an XML tree and returns SOAP payload as an XML tree
        assert isinstance(payload, ElementType)
        # Microsoft really doesn't want to make our lives easy. The server may report one version in our initial version
        # guessing tango, but then the server may decide that any arbitrary legacy backend server may actually process
        # the request for an account. Prepare to handle ErrorInvalidSchemaVersionForMailboxVersion errors and set the
        # server version per-account.
        from .version import API_VERSIONS, Version
        hint = account.version.api_version if account else self.protocol.version.api_version
        api_versions = [hint] + [v for v in API_VERSIONS if v != hint]
        for api_version in api_versions:
            session = self.protocol.get_session()
            soap_payload = wrap(content=payload, version=api_version, account=account)
            r, session = post_ratelimited(
                protocol=self.protocol,
                session=session,
                url=self.protocol.service_endpoint,
                headers=None,
                data=soap_payload,
                timeout=self.protocol.TIMEOUT,
                verify=self.protocol.verify_ssl,
                allow_redirects=False)
            self.protocol.release_session(session)
            log.debug('Trying API version %s for account %s', api_version, account)
            try:
                soap_response_payload = to_xml(r.text, encoding=r.encoding or 'utf-8')
            except ExpatError as e:
                raise SOAPError('SOAP response is not XML: %s' % e) from e
            try:
                res = self._get_soap_payload(soap_response=soap_response_payload)
            except (ErrorInvalidSchemaVersionForMailboxVersion, ErrorInvalidServerVersion):
                assert account  # This should never happen for non-account services
                # The guessed server version is wrong for this account. Try the next version
                log.debug('API version %s was invalid for account %s', api_version, account)
                continue
            if account and account.version.api_version != api_version:
                # The api_version that worked was different than our hint. Set new version for account
                log.info('New API version for account %s (%s -> %s)', account, account.version.api_version, api_version)
                account.version = Version.from_response(requested_api_version=api_version, response=r)
            return res
        raise ErrorInvalidSchemaVersionForMailboxVersion('Tried versions %s but all were invalid for account %s' %
                                                         (api_versions, account))

    def _get_soap_payload(self, soap_response):
        assert isinstance(soap_response, ElementType)
        body = soap_response.find('{%s}Body' % SOAPNS)
        if body is None:
            raise TransportError('No Body element in SOAP response')
        response = body.find('{%s}%sResponse' % (MNS, self.SERVICE_NAME))
        if response is None:
            fault = body.find('{%s}Fault' % SOAPNS)
            if fault is None:
                raise SOAPError('Unknown SOAP response: %s' % xml_to_str(body))
            self._raise_soap_errors(fault=fault)  # Will throw SOAPError
        response_messages = response.find('{%s}ResponseMessages' % MNS)
        if response_messages is None:
            return response.findall('{%s}%sResponse' % (MNS, self.SERVICE_NAME))
        return response_messages.findall('{%s}%sResponseMessage' % (MNS, self.SERVICE_NAME))

    def _raise_soap_errors(self, fault):
        assert isinstance(fault, ElementType)
        log_prefix = 'EWS %s, service %s' % (self.protocol.service_endpoint, self.SERVICE_NAME)
        # Fault: See http://www.w3.org/TR/2000/NOTE-SOAP-20000508/#_Toc478383507
        faultcode = get_xml_attr(fault, 'faultcode')
        faultstring = get_xml_attr(fault, 'faultstring')
        faultactor = get_xml_attr(fault, 'faultactor')
        detail = fault.find('detail')
        if detail is not None:
            code, msg = None, None
            if detail.find('{%s}ResponseCode' % ENS) is not None:
                code = get_xml_attr(detail, '{%s}ResponseCode' % ENS)
            if detail.find('{%s}Message' % ENS) is not None:
                msg = get_xml_attr(detail, '{%s}Message' % ENS)
            try:
                raise vars(errors)[code](msg)
            except KeyError:
                detail = '%s: code: %s msg: %s (%s)' % (log_prefix, code, msg, xml_to_str(detail))
        try:
            raise vars(errors)[faultcode](faultstring)
        except KeyError:
            pass
        raise SOAPError('SOAP error code: %s string: %s actor: %s detail: %s' % (
            faultcode, faultstring, faultactor, detail))

    def _get_element_container(self, message, name=None):
        assert isinstance(message, ElementType)
        # ResponseClass: See http://msdn.microsoft.com/en-us/library/aa566424(v=EXCHG.140).aspx
        response_class = message.get('ResponseClass')
        # ResponseCode, MessageText: See http://msdn.microsoft.com/en-us/library/aa580757(v=EXCHG.140).aspx
        response_code = get_xml_attr(message, '{%s}ResponseCode' % MNS)
        msg_text = get_xml_attr(message, '{%s}MessageText' % MNS)
        msg_xml = get_xml_attr(message, '{%s}MessageXml' % MNS)
        if response_class == 'Success' and response_code == 'NoError':
            if not name:
                return True
            container = message.find(name)
            if container is None:
                raise TransportError('No %s elements in ResponseMessage (%s)' % (name, xml_to_str(message)))
            return container
        if response_class == 'Warning':
            return self._raise_warnings(code=response_code, text=msg_text, xml=msg_xml)
        # rspclass == 'Error', or 'Success' and not 'NoError'
        return self._raise_errors(code=response_code, text=msg_text, xml=msg_xml)

    def _raise_warnings(self, code, text, xml):
        try:
            return self._raise_errors(code=code, text=text, xml=xml)
        except ErrorBatchProcessingStopped as e:
            raise EWSWarning(e.value) from e

    @staticmethod
    def _raise_errors(code, text, xml):
        if code == 'NoError':
            return True
        if not code:
            raise TransportError('Empty ResponseCode in ResponseMessage (MessageText: %s, MessageXml: %s)' % (
                text, xml))
        try:
            # Raise the error corresponding to the ResponseCode
            raise vars(errors)[code](text)
        except KeyError as e:
            # Should not happen
            raise TransportError('Unknown ResponseCode in ResponseMessage: %s (MessageText: %s, MessageXml: %s)' % (
                code, text, xml)) from e

    def _get_elements_in_response(self, response):
        assert isinstance(response, list)
        elements = []
        for msg in response:
            assert isinstance(msg, ElementType)
            try:
                container = self._get_element_container(message=msg, name=self.element_container_name)
                if isinstance(container, ElementType):
                    elements.extend(self._get_elements_in_container(container=container))
                else:
                    elements.append((container, None))
            except (ErrorTimeoutExpired, ErrorBatchProcessingStopped):
                raise
            except EWSWarning as e:
                elements.append((False, '%s' % e.value))
                continue
        return elements

    def _get_elements_in_container(self, container):
        assert self.element_name
        elems = container.findall(self.element_name)
        for element_name in self.extra_element_names:
            elems.extend(container.findall(element_name))
        return elems


class EWSAccountService(EWSService):
    def call(self, account, **kwargs):
        raise NotImplementedError()


class EWSFolderService(EWSService):
    def call(self, folder, **kwargs):
        raise NotImplementedError()


class PagingEWSService(EWSService):
    def _paged_call(self, **kwargs):
        # TODO This is awkward. The function must work with _get_payload() of both folder- and account-based services
        account = kwargs['folder'].account if 'folder' in kwargs else kwargs['account']
        log_prefix = 'EWS %s, account %s, service %s' % (self.protocol.service_endpoint, account, self.SERVICE_NAME)
        elements = []
        offset = 0
        while True:
            log.debug('%s: Getting %s at offset %s', log_prefix, self.element_name, offset)
            kwargs['offset'] = offset
            payload = self._get_payload(**kwargs)
            response = self._get_response_xml(payload=payload, account=account)
            page, offset = self._get_page(response)
            if isinstance(page, ElementType):
                container = page.find(self.element_container_name)
                if container is None:
                    raise TransportError('No %s elements in ResponseMessage (%s)' % (self.element_container_name,
                                                                                     xml_to_str(page)))
                elements.extend(self._get_elements_in_container(container=container))
            if not offset:
                break
        return elements

    def _get_page(self, response):
        assert len(response) == 1
        log_prefix = 'EWS %s, service %s' % (self.protocol.service_endpoint, self.SERVICE_NAME)
        rootfolder = self._get_element_container(message=response[0], name='{%s}RootFolder' % MNS)
        is_last_page = rootfolder.get('IncludesLastItemInRange').lower() in ('true', '0')
        offset = rootfolder.get('IndexedPagingOffset')
        if offset is None and not is_last_page:
            log.warning("Not last page in range, but Exchange didn't send a page offset. Assuming first page")
            offset = '1'
        next_offset = 0 if is_last_page else int(offset)
        if not int(rootfolder.get('TotalItemsInView')):
            assert next_offset == 0
            rootfolder = None
        log.debug('%s: Got page with next offset %s (last_page %s)', log_prefix, next_offset, is_last_page)
        return rootfolder, next_offset


class GetServerTimeZones(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/dd899371(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetServerTimeZones'
    element_container_name = '{%s}TimeZoneDefinitions' % MNS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.element_name = '{%s}TimeZoneDefinition' % TNS

    def call(self, **kwargs):
        if self.protocol.version.build < EXCHANGE_2010:
            raise NotImplementedError('%s is only supported for Exchange 2010 servers and later' % self.SERVICE_NAME)
        return self._get_elements(payload=self._get_payload(**kwargs))

    def _get_payload(self, returnfulltimezonedata=False):
        return create_element('m:%s' % self.SERVICE_NAME, ReturnFullTimeZoneData=(
            'true' if returnfulltimezonedata else 'false'))

    def _get_elements_in_container(self, container):
        timezones = []
        timezonedefs = container.findall(self.element_name)
        for timezonedef in timezonedefs:
            tz_id = timezonedef.get('Id')
            name = timezonedef.get('Name')
            timezones.append((tz_id, name))
        return timezones


class GetRoomLists(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/dd899486(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetRoomLists'
    element_container_name = '{%s}RoomLists' % MNS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .folders import RoomList
        self.element_name = RoomList.response_tag()

    def call(self, **kwargs):
        if self.protocol.version.build < EXCHANGE_2010:
            raise NotImplementedError('%s is only supported for Exchange 2010 servers and later' % self.SERVICE_NAME)
        elements = self._get_elements(payload=self._get_payload(**kwargs))
        from .folders import RoomList
        return [RoomList.from_xml(elem) for elem in elements]

    def _get_payload(self, *args, **kwargs):
        return create_element('m:%s' % self.SERVICE_NAME)


class GetRooms(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/dd899454(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetRooms'
    element_container_name = '{%s}Rooms' % MNS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .folders import Room
        self.element_name = Room.response_tag()

    def call(self, roomlist, **kwargs):
        if self.protocol.version.build < EXCHANGE_2010:
            raise NotImplementedError('%s is only supported for Exchange 2010 servers and later' % self.SERVICE_NAME)
        elements = self._get_elements(payload=self._get_payload(roomlist, **kwargs))
        from .folders import Room
        return [Room.from_xml(elem) for elem in elements]

    def _get_payload(self, roomlist, *args, **kwargs):
        getrooms = create_element('m:%s' % self.SERVICE_NAME)
        set_xml_value(getrooms, roomlist, self.protocol.version)
        return getrooms


class EWSPooledService(EWSService):
    CHUNKSIZE = None

    def _pool_requests(self, account, payload_func, items, **kwargs):
        log.debug('Processing items in chunks of %s', self.CHUNKSIZE)
        # Chop items list into suitable pieces and let worker threads chew on the work. The order of the output result
        # list must be the same as the input id list, so the caller knows which status message belongs to which ID.
        func = lambda n: self._get_elements(account=account, payload=payload_func(n, **kwargs))
        return list(itertools.chain(*self.protocol.thread_pool.map(func, chunkify(items, self.CHUNKSIZE))))


class GetItem(EWSPooledService):
    """
    Take a list of (id, changekey) tuples and returns all items in 'account', optionally expanded with
    'additional_fields' fields, in stable order.

    MSDN: https://msdn.microsoft.com/en-us/library/office/aa563775(v=exchg.150).aspx
    """
    CHUNKSIZE = 100
    SERVICE_NAME = 'GetItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, folder, **kwargs):
        self.element_name = folder.item_model.response_tag()
        return self._pool_requests(account=folder.account, payload_func=self._get_payload, items=kwargs['ids'],
                                   folder=folder, additional_fields=kwargs['additional_fields'])

    def _get_payload(self, items, folder, additional_fields):
        # Takes a list of (item_id, changekey) tuples or Item objects and returns the XML for a GetItem request.
        #
        # We start with an IdOnly request. 'additional_properties' defines the additional fields we want. Supported
        # fields are available in self.item_model.fieldnames().
        from .folders import ItemId
        getitem = create_element('m:%s' % self.SERVICE_NAME)
        itemshape = create_element('m:ItemShape')
        add_xml_child(itemshape, 't:BaseShape', IdOnly)
        if additional_fields:
            add_xml_child(itemshape, 't:AdditionalProperties',
                          folder.item_model.additional_property_elems(additional_fields))
        getitem.append(itemshape)
        item_ids = create_element('m:ItemIds')
        n = 0
        for item in items:
            n += 1
            item_id = ItemId(*item) if isinstance(item, tuple) else ItemId(item.item_id, item.changekey)
            set_xml_value(item_ids, item_id, folder.account.version)
        if not n:
            raise AttributeError('"ids" must not be empty')
        getitem.append(item_ids)
        return getitem


class CreateItem(EWSPooledService):
    """
    Takes folder and a list of items. Returns result of creation as a list of tuples (success[True|False],
    errormessage), in the same order as the input list.

    MSDN: https://msdn.microsoft.com/en-us/library/office/aa565209(v=exchg.150).aspx
    """
    CHUNKSIZE = 25
    SERVICE_NAME = 'CreateItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, folder, **kwargs):
        self.element_name = folder.item_model.response_tag()
        return self._pool_requests(
            account=folder.account, payload_func=self._get_payload, items=kwargs['items'],
            folder=folder,
            message_disposition=kwargs['message_disposition'],
            send_meeting_invitations=kwargs['send_meeting_invitations'],
        )

    def _get_payload(self, items, folder, message_disposition, send_meeting_invitations):
        # Takes a list of Item obejcts (CalendarItem, Message etc) and returns the XML for a CreateItem request.
        # convert items to XML Elements
        from .folders import Calendar, Messages
        if isinstance(folder, Calendar):
            # SendMeetingInvitations is required for calendar items. It is also applicable to tasks, meeting request
            # responses (see https://msdn.microsoft.com/en-us/library/office/aa566464(v=exchg.150).aspx) and sharing
            # invitation accepts (see https://msdn.microsoft.com/en-us/library/office/ee693280(v=exchg.150).aspx). The
            # last two are not supported yet.
            createitem = create_element('m:%s' % self.SERVICE_NAME,
                                        SendMeetingInvitations=send_meeting_invitations)
        elif isinstance(folder, Messages):
            # MessageDisposition is only applicable to email messages, where it is required.
            createitem = create_element('m:%s' % self.SERVICE_NAME, MessageDisposition=message_disposition)
        else:
            createitem = create_element('m:%s' % self.SERVICE_NAME)
        add_xml_child(createitem, 'm:SavedItemFolderId', folder.folderid_xml())
        item_elems = []
        for item in items:
            log.debug('Adding item %s', item)
            item_elems.append(item.to_xml(folder.account.version))
        if not item_elems:
            raise AttributeError('"items" must not be empty')
        add_xml_child(createitem, 'm:Items', item_elems)
        return createitem


class DeleteItem(EWSPooledService):
    """
    Takes a folder and a list of (id, changekey) tuples. Returns result of deletion as a list of tuples
    (success[True|False], errormessage), in the same order as the input list.

    MSDN: https://msdn.microsoft.com/en-us/library/office/aa562961(v=exchg.150).aspx

    """
    CHUNKSIZE = 25
    SERVICE_NAME = 'DeleteItem'
    element_container_name = None  # DeleteItem doesn't return a response object, just status in XML attrs

    def call(self, folder, **kwargs):
        return self._pool_requests(
            account=folder.account, payload_func=self._get_payload, items=kwargs['ids'], folder=folder,
            delete_type=kwargs['delete_type'], send_meeting_cancellations=kwargs['send_meeting_cancellations'],
            affected_task_occurrences=kwargs['affected_task_occurrences'],
        )

    def _get_payload(self, items, folder, delete_type, send_meeting_cancellations, affected_task_occurrences):
        # Takes a list of (item_id, changekey) tuples or Item objects and returns the XML for a DeleteItem request.
        from .folders import Calendar, Tasks, ItemId
        if isinstance(folder, Calendar):
            deleteitem = create_element(
                'm:%s' % self.SERVICE_NAME, DeleteType=delete_type,
                SendMeetingCancellations=send_meeting_cancellations)
        elif isinstance(folder, Tasks):
            deleteitem = create_element(
                'm:%s' % self.SERVICE_NAME, DeleteType=delete_type,
                AffectedTaskOccurrences=affected_task_occurrences)
        else:
            deleteitem = create_element('m:%s' % self.SERVICE_NAME, DeleteType=delete_type)
        if folder.account.version.build >= EXCHANGE_2013:
            deleteitem.set('SuppressReadReceipts', 'true')

        item_ids = create_element('m:ItemIds')
        n = 0
        for item in items:
            n += 1
            item_id = ItemId(*item) if isinstance(item, tuple) else ItemId(item.item_id, item.changekey)
            log.debug('Deleting item %s', item_id)
            set_xml_value(item_ids, item_id, folder.account.version)
        if not n:
            raise AttributeError('"ids" must not be empty')
        deleteitem.append(item_ids)
        return deleteitem


class UpdateItem(EWSPooledService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa580254(v=exchg.150).aspx
    """
    CHUNKSIZE = 25
    SERVICE_NAME = 'UpdateItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, folder, **kwargs):
        self.element_name = folder.item_model.response_tag()
        return self._pool_requests(
            account=folder.account, payload_func=self._get_payload, items=kwargs['items'], folder=folder,
            conflict_resolution=kwargs['conflict_resolution'], message_disposition=kwargs['message_disposition'],
            send_meeting_invitations_or_cancellations=kwargs['send_meeting_invitations_or_cancellations'],
        )

    def _get_payload(self, items, folder, conflict_resolution, message_disposition,
                     send_meeting_invitations_or_cancellations):
        # Takes a dict with an (item_id, changekey) tuple or Item object as the key, and a dict of
        # field_name -> new_value as values. Returns the XML for a DeleteItem request.
        from .folders import Calendar, Messages, ItemId, IndexedField, ExtendedProperty, ExternId, EWSElement
        if isinstance(folder, Calendar):
            updateitem = create_element('m:%s' % self.SERVICE_NAME, ConflictResolution=conflict_resolution,
                                        SendMeetingInvitationsOrCancellations=send_meeting_invitations_or_cancellations)
        elif isinstance(folder, Messages):
            updateitem = create_element('m:%s' % self.SERVICE_NAME, ConflictResolution=conflict_resolution,
                                        MessageDisposition=message_disposition)
        else:
            updateitem = create_element('m:%s' % self.SERVICE_NAME, ConflictResolution=conflict_resolution)
        if folder.account.version.build >= EXCHANGE_2013:
            updateitem.set('SuppressReadReceipts', 'true')

        itemchanges = create_element('m:ItemChanges')
        n = 0
        for item, update_dict in items:
            n += 1
            if not update_dict:
                raise AttributeError('"update_dict" must not be empty')
            itemchange = create_element('t:ItemChange')
            item_id = ItemId(*item) if isinstance(item, tuple) else ItemId(item.item_id, item.changekey)
            log.debug('Updating item %s values %s', item_id, update_dict)
            set_xml_value(itemchange, item_id, folder.account.version)
            updates = create_element('t:Updates')
            meeting_timezone_added = False
            for fieldname, val in update_dict.items():
                if fieldname in folder.item_model.readonly_fields():
                    log.warning('%s is a read-only field. Skipping', fieldname)
                    continue
                if fieldname == 'extern_id' and val is not None:
                    val = ExternId(val)
                field_uri = folder.attr_to_fielduri(fieldname)
                if isinstance(field_uri, str):
                    fielduri = create_element('t:FieldURI', FieldURI=field_uri)
                elif issubclass(field_uri, IndexedField):
                    log.warning("Skipping update on fieldname '%s' (not supported yet)", fieldname)
                    continue
                    # TODO: we need to create a SetItemField for every item in the list, and possibly DeleteItemField
                    # for every label not on the list
                    # fielduri = field_uri.field_uri_xml(label=val.label)
                elif issubclass(field_uri, ExtendedProperty):
                    fielduri = field_uri.field_uri_xml()
                else:
                    assert False, 'Unknown field_uri type: %s' % field_uri
                if val is None:
                    # A value of None means we want to remove this field from the item
                    if fieldname in folder.item_model.required_fields():
                        log.warning('%s is a required field and may not be deleted. Skipping', fieldname)
                        continue
                    add_xml_child(updates, 't:DeleteItemField', fielduri)
                    continue
                setitemfield = create_element('t:SetItemField')
                setitemfield.append(fielduri)
                folderitem = create_element(folder.item_model.request_tag())

                if isinstance(val, EWSElement):
                    set_xml_value(folderitem, val, folder.account.version)
                else:
                    folderitem.append(
                        set_xml_value(folder.item_model.elem_for_field(fieldname), val, folder.account.version)
                    )
                setitemfield.append(folderitem)
                updates.append(setitemfield)

                if isinstance(val, EWSDateTime):
                    # Always set timezone explicitly when updating date fields. Exchange 2007 wants "MeetingTimeZone"
                    # instead of explicit timezone on each datetime field.
                    setitemfield_tz = create_element('t:SetItemField')
                    folderitem_tz = create_element(folder.item_model.request_tag())
                    if folder.account.version.build < EXCHANGE_2010:
                        if meeting_timezone_added:
                            # Let's hope that we're not changing timezone, or that both 'start' and 'end' are supplied.
                            # Exchange 2007 doesn't support different timezone on start and end.
                            continue
                        fielduri_tz = create_element('t:FieldURI', FieldURI='calendar:MeetingTimeZone')
                        timezone = create_element('t:MeetingTimeZone', TimeZoneName=val.tzinfo.ms_id)
                        meeting_timezone_added = True
                    else:
                        if fieldname == 'start':
                            fielduri_tz = create_element('t:FieldURI', FieldURI='calendar:StartTimeZone')
                            timezone = create_element('t:StartTimeZone', Id=val.tzinfo.ms_id, Name=val.tzinfo.ms_name)
                        elif fieldname == 'end':
                            fielduri_tz = create_element('t:FieldURI', FieldURI='calendar:EndTimeZone')
                            timezone = create_element('t:EndTimeZone', Id=val.tzinfo.ms_id, Name=val.tzinfo.ms_name)
                        else:
                            log.warning("Skipping timezone for field '%s'", fieldname)
                            continue
                    setitemfield_tz.append(fielduri_tz)
                    folderitem_tz.append(timezone)
                    setitemfield_tz.append(folderitem_tz)
                    updates.append(setitemfield_tz)
            itemchange.append(updates)
            itemchanges.append(itemchange)
        if not n:
            raise AttributeError('"items" must not be empty')
        updateitem.append(itemchanges)
        return updateitem


class FindItem(PagingEWSService, EWSFolderService):
    """
    Gets all items for 'account' in folder 'folder_id', optionally expanded with 'additional_fields' fields,
    optionally restricted by a Restriction definition.

    MSDN: https://msdn.microsoft.com/en-us/library/office/aa566370(v=exchg.150).aspx
    """
    SERVICE_NAME = 'FindItem'
    element_container_name = '{%s}Items' % TNS

    def call(self, folder, **kwargs):
        self.element_name = folder.item_model.response_tag()
        return self._paged_call(folder=folder, **kwargs)

    def _get_payload(self, folder, additional_fields, restriction, shape, depth, offset=0):
        finditem = create_element('m:%s' % self.SERVICE_NAME, Traversal=depth)
        itemshape = create_element('m:ItemShape')
        add_xml_child(itemshape, 't:BaseShape', shape)
        if additional_fields:
            add_xml_child(itemshape, 't:AdditionalProperties',
                          folder.item_model.additional_property_elems(additional_fields))
        finditem.append(itemshape)
        indexedpageviewitem = create_element('m:IndexedPageItemView', Offset=str(offset), BasePoint='Beginning')
        finditem.append(indexedpageviewitem)
        if restriction:
            finditem.append(restriction.xml)
        parentfolderids = create_element('m:ParentFolderIds')
        parentfolderids.append(folder.folderid_xml())
        finditem.append(parentfolderids)
        return finditem


class FindFolder(PagingEWSService, EWSFolderService):
    """
    Gets a list of folders belonging to an account.

    MSDN: https://msdn.microsoft.com/en-us/library/office/aa564962(v=exchg.150).aspx
    """
    SERVICE_NAME = 'FindFolder'
    element_container_name = '{%s}Folders' % TNS
    # See http://msdn.microsoft.com/en-us/library/aa564009(v=exchg.150).aspx
    extra_element_names = [
        '{%s}CalendarFolder' % TNS,
        '{%s}ContactsFolder' % TNS,
        '{%s}SearchFolder' % TNS,
        '{%s}TasksFolder' % TNS,
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.element_name = '{%s}Folder' % TNS

    def call(self, folder, **kwargs):
        return self._paged_call(folder=folder, **kwargs)

    def _get_payload(self, folder, additional_fields, shape, depth, offset=0):
        findfolder = create_element('m:%s' % self.SERVICE_NAME, Traversal=depth)
        foldershape = create_element('m:FolderShape')
        add_xml_child(foldershape, 't:BaseShape', shape)
        if additional_fields:
            additionalproperties = create_element('t:AdditionalProperties')
            for field_uri in additional_fields:
                additionalproperties.append(create_element('t:FieldURI', FieldURI=field_uri))
            foldershape.append(additionalproperties)
        findfolder.append(foldershape)
        if folder.account.version.build >= EXCHANGE_2010:
            indexedpageviewitem = create_element('m:IndexedPageFolderView', Offset=str(offset), BasePoint='Beginning')
            findfolder.append(indexedpageviewitem)
        else:
            assert offset == 0, 'Offset is %s' % offset
        parentfolderids = create_element('m:ParentFolderIds')
        parentfolderids.append(folder.folderid_xml())
        findfolder.append(parentfolderids)
        return findfolder


class GetFolder(EWSFolderService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa580263(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetFolder'
    element_container_name = '{%s}Folders' % MNS
    # See http://msdn.microsoft.com/en-us/library/aa564009(v=exchg.150).aspx
    extra_element_names = [
        '{%s}CalendarFolder' % TNS,
        '{%s}ContactsFolder' % TNS,
        '{%s}SearchFolder' % TNS,
        '{%s}TasksFolder' % TNS,
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.element_name = '{%s}Folder' % TNS

    def call(self, account, **kwargs):
        return self._get_elements(payload=self._get_payload(account, **kwargs), account=account)

    def _get_payload(self, account, distinguished_folder_id, additional_fields, shape):
        from .credentials import DELEGATE
        from .folders import Mailbox
        getfolder = create_element('m:%s' % self.SERVICE_NAME)
        foldershape = create_element('m:FolderShape')
        add_xml_child(foldershape, 't:BaseShape', shape)
        if additional_fields:
            additionalproperties = create_element('t:AdditionalProperties')
            for field_uri in additional_fields:
                additionalproperties.append(create_element('t:FieldURI', FieldURI=field_uri))
            foldershape.append(additionalproperties)
        getfolder.append(foldershape)
        folderids = create_element('m:FolderIds')
        distinguishedfolderid = create_element('t:DistinguishedFolderId', Id=distinguished_folder_id)
        if account.access_type == DELEGATE:
            mailbox = Mailbox(email_address=account.primary_smtp_address)
            set_xml_value(distinguishedfolderid, mailbox, account.version)
        folderids.append(distinguishedfolderid)
        getfolder.append(folderids)
        return getfolder


class ResolveNames(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa565329(v=exchg.150).aspx
    """
    SERVICE_NAME = 'ResolveNames'
    element_container_name = '{%s}ResolutionSet' % MNS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.element_name = '{%s}Resolution' % TNS

    def call(self, **kwargs):
        return self._get_elements(payload=self._get_payload(**kwargs))

    def _get_payload(self, unresolvedentries, returnfullcontactdata=False):
        payload = create_element('m:%s' % self.SERVICE_NAME, ReturnFullContactData=(
            'true' if returnfullcontactdata else 'false'))
        n = 0
        for entry in unresolvedentries:
            n += 1
            add_xml_child(payload, 'm:UnresolvedEntry', entry)
        if not n:
            raise AttributeError('"unresolvedentries" must not be empty')
        return payload

class ExportItems(EWSPooledService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/ff709523(v=exchg.150).aspx
    """
    CHUNKSIZE = 100
    SERVICE_NAME = 'ExportItems'
    element_container_name = "{%s}Data" % MNS

    def call(self, account, item_ids):
        return self._pool_requests(
            account=account, payload_func=self._get_payload, items=item_ids,
            version=account.version
        )

    def _get_payload(self, items, version):
        exportitems = create_element('m:%s' % self.SERVICE_NAME)
        itemids = create_element('m:ItemIds')
        exportitems.append(itemids)
        for item_id in items:
            itemids.append(item_id.to_xml(version))
        return exportitems

    # We need to override this since ExportItemsResponseMessage is formated a
    #  little bit differently. Namely, all we want is the 64bit string in the
    #  Data tag.
    def _get_elements_in_container(self, container):
        return [container.text]

class UploadItems(EWSPooledService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/ff709490(v=exchg.150).aspx
    """
    CHUNKSIZE = 100
    SERVICE_NAME = 'UploadItems'
    element_container_name = '{%s}ItemId' % MNS

    def call(self, account, data):
        """Upload given items to given account

        data is an iterable of tuples where the first element is a Folder
        instance representing the ParentFolder that the item will be placed in
        and the second element is a Data string returned from an ExportItems
        call.
        """
        return self._pool_requests(
            account=account, payload_func=self._get_payload, items=data
        )

    def _get_payload(self, items):
        uploaditems = create_element('m:%s' % self.SERVICE_NAME)
        itemselement = create_element('m:Items')
        uploaditems.append(itemselement)
        for parent_folder, data_str in items:
            item = create_element("t:Item", CreateAction="CreateNew")
            parentfolderid = create_element('t:ParentFolderId')
            parentfolderid.attrib['Id'] = parent_folder.folder_id
            parentfolderid.attrib['ChangeKey'] = parent_folder.changekey
            item.append(parentfolderid)
            add_xml_child(item, 't:Data', data_str)
            itemselement.append(item)
        return uploaditems

    def _get_elements_in_container(self, container):
        return [(container.attrib['Id'], container.attrib['ChangeKey'])]
