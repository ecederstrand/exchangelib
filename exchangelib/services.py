# coding=utf-8
"""
Implement a selection of EWS services.

Exchange is very picky about things like the order of XML elements in SOAP requests, so we need to generate XML
automatically instead of taking advantage of Python SOAP libraries and the WSDL file.

Exchange EWS references:
    - 2007: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.80).aspx
    - 2010: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.140).aspx
    - 2013: http://msdn.microsoft.com/en-us/library/bb409286(v=exchg.150).aspx
"""
from __future__ import unicode_literals

import abc
import datetime
from itertools import chain
import logging
import time
import traceback

from defusedxml.ElementTree import ParseError
from six import text_type

from . import errors
from .errors import EWSWarning, TransportError, SOAPError, ErrorTimeoutExpired, ErrorBatchProcessingStopped, \
    ErrorQuotaExceeded, ErrorCannotDeleteObject, ErrorCreateItemAccessDenied, ErrorFolderNotFound, \
    ErrorNonExistentMailbox, ErrorMailboxStoreUnavailable, ErrorImpersonateUserDenied, ErrorInternalServerError, \
    ErrorInternalServerTransientError, ErrorNoRespondingCASInDestinationSite, ErrorImpersonationFailed, \
    ErrorMailboxMoveInProgress, ErrorAccessDenied, ErrorConnectionFailed, RateLimitError, ErrorServerBusy, \
    ErrorTooManyObjectsOpened, ErrorInvalidLicense, ErrorInvalidSchemaVersionForMailboxVersion, \
    ErrorInvalidServerVersion, ErrorItemNotFound, ErrorADUnavailable, ResponseMessageError, ErrorInvalidChangeKey, \
    ErrorItemSave, ErrorInvalidIdMalformed, ErrorMessageSizeExceeded, UnauthorizedError, \
    ErrorCannotDeleteTaskOccurrence, ErrorMimeContentConversionFailed, ErrorRecurrenceHasNoOccurrence, \
    ErrorNameResolutionMultipleResults, ErrorNameResolutionNoResults, ErrorNoPublicFolderReplicaAvailable, \
    ErrorInvalidOperation
from .ewsdatetime import EWSDateTime, NaiveDateTimeNotAllowed
from .transport import wrap, extra_headers, SOAPNS, TNS, MNS, ENS
from .util import chunkify, create_element, add_xml_child, get_xml_attr, to_xml, post_ratelimited, ElementType, \
    xml_to_str, set_xml_value, peek, xml_text_to_value, redact_email
from .version import EXCHANGE_2010, EXCHANGE_2010_SP2, EXCHANGE_2013, EXCHANGE_2013_SP1

log = logging.getLogger(__name__)

CHUNK_SIZE = 100  # A default chunk size for all services


class EWSService(object):
    __metaclass__ = abc.ABCMeta

    SERVICE_NAME = None  # The name of the SOAP service
    element_container_name = None  # The name of the XML element wrapping the collection of returned items
    # Return exception instance instead of raising exceptions for the following errors when contained in an element
    ERRORS_TO_CATCH_IN_RESPONSE = (
        EWSWarning, ErrorCannotDeleteObject, ErrorInvalidChangeKey, ErrorItemNotFound, ErrorItemSave,
        ErrorInvalidIdMalformed, ErrorMessageSizeExceeded, ErrorCannotDeleteTaskOccurrence,
        ErrorMimeContentConversionFailed, ErrorRecurrenceHasNoOccurrence,
    )
    # Similarly, define the warnings we want to return unraised
    WARNINGS_TO_CATCH_IN_RESPONSE = ErrorBatchProcessingStopped
    # Define the warnings we want to ignore, to let response processing proceed
    WARNINGS_TO_IGNORE_IN_RESPONSE = ()

    def __init__(self, protocol, chunk_size=None):
        self.chunk_size = chunk_size or CHUNK_SIZE  # The number of items to send in a single request
        if not isinstance(self.chunk_size, int):
            raise ValueError("'chunk_size' %r must be an integer" % chunk_size)
        if self.chunk_size < 1:
            raise ValueError("'chunk_size' must be a positive number")
        self.protocol = protocol

    # The following two methods are the minimum required to be implemented by subclasses, but the name and number of
    # kwargs differs between services. Therefore, we cannot make these methods abstract.

    # @abc.abstractmethod
    # def call(self, **kwargs):
    #     raise NotImplementedError()

    # @abc.abstractmethod
    # def get_payload(self, **kwargs):
    #     raise NotImplementedError()

    def _get_elements(self, payload):
        if not isinstance(payload, ElementType):
            raise ValueError("'payload' %r must be an ElementType" % payload)
        while True:
            try:
                # Send the request, get the response and do basic sanity checking on the SOAP XML
                response = self._get_response_xml(payload=payload)
                # Read the XML and throw any general EWS error messages. Return a generator over the result elements
                return self._get_elements_in_response(response=response)
            except ErrorServerBusy as e:
                if self.protocol.credentials.fail_fast:
                    raise
                back_off = e.back_off or 60  # Back off 60 seconds if we didn't get an explicit suggested value
                back_off_until = datetime.datetime.now() + datetime.timedelta(seconds=back_off)
                self.protocol.credentials.back_off_until = back_off_until
                # We'll warn about this if we actually need to sleep
                continue
            except (
                    ErrorAccessDenied,
                    ErrorADUnavailable,
                    ErrorBatchProcessingStopped,
                    ErrorCannotDeleteObject,
                    ErrorConnectionFailed,
                    ErrorCreateItemAccessDenied,
                    ErrorFolderNotFound,
                    ErrorImpersonateUserDenied,
                    ErrorImpersonationFailed,
                    ErrorInternalServerError,
                    ErrorInternalServerTransientError,
                    ErrorInvalidChangeKey,
                    ErrorInvalidLicense,
                    ErrorItemNotFound,
                    ErrorMailboxMoveInProgress,
                    ErrorMailboxStoreUnavailable,
                    ErrorNonExistentMailbox,
                    ErrorNoPublicFolderReplicaAvailable,
                    ErrorNoRespondingCASInDestinationSite,
                    ErrorQuotaExceeded,
                    ErrorTimeoutExpired,
                    ErrorTooManyObjectsOpened,
                    RateLimitError,
                    UnauthorizedError,
            ):
                # These are known and understood, and don't require a backtrace
                # TODO: ErrorTooManyObjectsOpened means there are too many connections to the database. We should be
                # able to act on this by lowering the self.protocol connection pool size.
                raise
            except Exception:
                # This may run from a thread pool, which obfuscates the stack trace. Print trace immediately.
                account = self.account if isinstance(self, EWSAccountService) else None
                log.warning('EWS %s, account %s: Exception in _get_elements: %s', self.protocol.service_endpoint,
                            redact_email(account), traceback.format_exc(20))
                raise

    def _get_response_xml(self, payload):
        # Takes an XML tree and returns SOAP payload as an XML tree
        if not isinstance(payload, ElementType):
            raise ValueError("'payload' %r must be an ElementType" % payload)
        # Microsoft really doesn't want to make our lives easy. The server may report one version in our initial version
        # guessing tango, but then the server may decide that any arbitrary legacy backend server may actually process
        # the request for an account. Prepare to handle ErrorInvalidSchemaVersionForMailboxVersion errors and set the
        # server version per-account.
        from .version import API_VERSIONS
        if isinstance(self, EWSAccountService):
            account = self.account
            hint = self.account.version
        else:
            account = None
            hint = self.protocol.version
        api_versions = [hint.api_version] + [v for v in API_VERSIONS if v != hint.api_version]
        for api_version in api_versions:
            session = self.protocol.get_session()
            soap_payload = wrap(content=payload, version=api_version, account=account)
            http_headers = extra_headers(account=account)
            r, session = post_ratelimited(
                protocol=self.protocol,
                session=session,
                url=self.protocol.service_endpoint,
                headers=http_headers,
                data=soap_payload,
                allow_redirects=False)
            self.protocol.release_session(session)
            log.debug('Trying API version %s for account %s', api_version, redact_email(account))
            try:
                soap_response_payload = to_xml(r.text)
            except ParseError as e:
                raise SOAPError('Bad SOAP response: %s' % e)
            try:
                res = self._get_soap_payload(soap_response=soap_response_payload)
            except ErrorInvalidServerVersion:
                # The guessed server version is wrong. Try the next version
                log.debug('API version %s was invalid', api_version)
                continue
            except ErrorInvalidSchemaVersionForMailboxVersion:
                if not account:
                    # This should never happen for non-account services
                    raise ValueError("'account' should not be None")
                # The guessed server version is wrong for this account. Try the next version
                log.debug('API version %s was invalid for account %s', api_version, redact_email(account))
                continue
            except ResponseMessageError:
                # We got an error message from Exchange, but we still want to get any new version info from the response
                try:
                    self._update_api_version(hint=hint, api_version=api_version, response=r)
                except TransportError as e:
                    log.debug('Failed to update version info (%s)', e)
                raise
            else:
                self._update_api_version(hint=hint, api_version=api_version, response=r)
            return res
        if account:
            raise ErrorInvalidSchemaVersionForMailboxVersion('Tried versions %s but all were invalid for account %s' %
                                                             (api_versions, redact_email(account)))
        raise ErrorInvalidServerVersion('Tried versions %s but all were invalid' % api_versions)

    def _update_api_version(self, hint, api_version, response):
        if api_version == hint.api_version and hint.build is not None:
            # Nothing to do
            return
        # The api_version that worked was different than our hint, or we never got a build version. Set new
        # version for account.
        from .version import Version
        if api_version != hint.api_version:
            log.debug('Found new API version (%s -> %s)', hint.api_version, api_version)
        else:
            log.debug('Adding missing build number %s', api_version)
        new_version = Version.from_response(requested_api_version=api_version, response=response.text)
        if isinstance(self, EWSAccountService):
            self.account.version = new_version
        else:
            self.protocol.version = new_version

    @classmethod
    def _get_soap_payload(cls, soap_response):
        if not isinstance(soap_response, ElementType):
            raise ValueError("'soap_response' %r must be an ElementType" % soap_response)
        body = soap_response.find('{%s}Body' % SOAPNS)
        if body is None:
            raise TransportError('No Body element in SOAP response')
        response = body.find('{%s}%sResponse' % (MNS, cls.SERVICE_NAME))
        if response is None:
            fault = body.find('{%s}Fault' % SOAPNS)
            if fault is None:
                raise SOAPError('Unknown SOAP response: %s' % xml_to_str(body))
            cls._raise_soap_errors(fault=fault)  # Will throw SOAPError or custom EWS error
        response_messages = response.find('{%s}ResponseMessages' % MNS)
        if response_messages is None:
            # Result isn't delivered in a list of FooResponseMessages, but directly in the FooResponse. Consumers expect
            # a list, so return a list
            return [response]
        return response_messages.findall('{%s}%sResponseMessage' % (MNS, cls.SERVICE_NAME))

    @classmethod
    def _raise_soap_errors(cls, fault):
        if not isinstance(fault, ElementType):
            raise ValueError("'fault' %r must be an ElementType" % fault)
        # Fault: See http://www.w3.org/TR/2000/NOTE-SOAP-20000508/#_Toc478383507
        faultcode = get_xml_attr(fault, 'faultcode')
        faultstring = get_xml_attr(fault, 'faultstring')
        faultactor = get_xml_attr(fault, 'faultactor')
        detail = fault.find('detail')
        if detail is not None:
            code, msg = None, ''
            if detail.find('{%s}ResponseCode' % ENS) is not None:
                code = get_xml_attr(detail, '{%s}ResponseCode' % ENS)
            if detail.find('{%s}Message' % ENS) is not None:
                msg = get_xml_attr(detail, '{%s}Message' % ENS)
            msg_xml = detail.find('{%s}MessageXml' % TNS)  # Crazy. Here, it's in the TNS namespace
            if code == 'ErrorServerBusy':
                back_off = None
                try:
                    value = msg_xml.find('{%s}Value' % TNS)
                    if value.get('Name') == 'BackOffMilliseconds':
                        back_off = int(value.text) / 1000.0  # Convert to seconds
                except (TypeError, AttributeError):
                    pass
                raise ErrorServerBusy(msg, back_off=back_off)
            try:
                raise vars(errors)[code](msg)
            except KeyError:
                detail = '%s: code: %s msg: %s (%s)' % (cls.SERVICE_NAME, code, msg, xml_to_str(detail))
        try:
            raise vars(errors)[faultcode](faultstring)
        except KeyError:
            pass
        raise SOAPError('SOAP error code: %s string: %s actor: %s detail: %s' % (
            faultcode, faultstring, faultactor, detail))

    def _get_element_container(self, message, name=None):
        if not isinstance(message, ElementType):
            raise ValueError("'message' %r must be an ElementType" % message)
        # ResponseClass: See http://msdn.microsoft.com/en-us/library/aa566424(v=EXCHG.140).aspx
        response_class = message.get('ResponseClass')
        # ResponseCode, MessageText: See http://msdn.microsoft.com/en-us/library/aa580757(v=EXCHG.140).aspx
        response_code = get_xml_attr(message, '{%s}ResponseCode' % MNS)
        msg_text = get_xml_attr(message, '{%s}MessageText' % MNS)
        msg_xml = message.find('{%s}MessageXml' % MNS)
        if response_class == 'Success' and response_code == 'NoError':
            if not name:
                return True
            container = message.find(name)
            if container is None:
                raise TransportError('No %s elements in ResponseMessage (%s)' % (name, xml_to_str(message)))
            return container
        if response_code == 'NoError':
            return True
        # Raise any non-acceptable errors in the container, or return the container or the acceptable exception instance
        if response_class == 'Warning':
            try:
                raise self._get_exception(code=response_code, text=msg_text, msg_xml=msg_xml)
            except self.WARNINGS_TO_CATCH_IN_RESPONSE as e:
                return e
            except self.WARNINGS_TO_IGNORE_IN_RESPONSE as e:
                log.warning(str(e))
                container = message.find(name)
                if container is None:
                    raise TransportError('No %s elements in ResponseMessage (%s)' % (name, xml_to_str(message)))
                return container
        # rspclass == 'Error', or 'Success' and not 'NoError'
        try:
            raise self._get_exception(code=response_code, text=msg_text, msg_xml=msg_xml)
        except self.ERRORS_TO_CATCH_IN_RESPONSE as e:
            return e

    @classmethod
    def _get_exception(cls, code, text, msg_xml):
        if not code:
            return TransportError('Empty ResponseCode in ResponseMessage (MessageText: %s, MessageXml: %s)' % (
                text, msg_xml))
        if msg_xml is not None:
            # If this is an ErrorInvalidPropertyRequest error, the xml may contain a specific FieldURI
            for tag_name in ('FieldURI', 'IndexedFieldURI', 'ExtendedFieldURI', 'ExceptionFieldURI'):
                field_uri_elem = msg_xml.find('{%s}%s' % (TNS, tag_name))
                if field_uri_elem is not None:
                    text += ' (field: %s)' % xml_to_str(field_uri_elem)
        try:
            # Raise the error corresponding to the ResponseCode
            return vars(errors)[code](text)
        except KeyError:
            # Should not happen
            return TransportError('Unknown ResponseCode in ResponseMessage: %s (MessageText: %s, MessageXml: %s)' % (
                    code, text, msg_xml))

    def _get_elements_in_response(self, response):
        for msg in response:
            if not isinstance(msg, ElementType):
                raise ValueError("'msg' %r must be an ElementType" % msg)
            container_or_exc = self._get_element_container(message=msg, name=self.element_container_name)
            if isinstance(container_or_exc, ElementType):
                for c in self._get_elements_in_container(container=container_or_exc):
                    yield c
            else:
                yield container_or_exc

    @staticmethod
    def _get_elements_in_container(container):
        return [elem for elem in container]


class EWSAccountService(EWSService):

    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop('account')
        kwargs['protocol'] = self.account.protocol
        super(EWSAccountService, self).__init__(*args, **kwargs)


class EWSFolderService(EWSAccountService):

    def __init__(self, *args, **kwargs):
        self.folders = kwargs.pop('folders')
        if not self.folders:
            raise ValueError('"folders" must not be empty')
        super(EWSFolderService, self).__init__(*args, **kwargs)


class PagingEWSMixIn(EWSService):
    def _paged_call(self, payload_func, max_items, **kwargs):
        service_endpoint = self.protocol.service_endpoint
        account = self.account if isinstance(self, EWSAccountService) else None
        redacted_account = redact_email(account)
        log_prefix = 'EWS %s, account %s, service %s' % (service_endpoint, redacted_account, self.SERVICE_NAME)
        if isinstance(self, EWSFolderService):
            expected_message_count = len(self.folders)
        else:
            expected_message_count = 1
        paging_infos = [dict(item_count=0, next_offset=None) for _ in range(expected_message_count)]
        common_next_offset = 0
        total_item_count = 0
        while True:
            log.debug('%s: Getting items at offset %s (max_items %s)', log_prefix, common_next_offset, max_items)
            kwargs['offset'] = common_next_offset
            payload = payload_func(**kwargs)
            try:
                response = self._get_response_xml(payload=payload)
            except ErrorServerBusy as e:
                if self.protocol.credentials.fail_fast:
                    raise
                back_off = e.back_off or 60  # Back off 60 seconds if we didn't get an explicit suggested value
                back_off_until = datetime.datetime.now() + datetime.timedelta(seconds=back_off)
                self.protocol.credentials.back_off_until = back_off_until
                # We'll warn about this if we actually need to sleep
                continue
            if len(response) != expected_message_count:
                raise TransportError(
                    "Expected %s items in 'response', got %s (%s)" % (
                        expected_message_count, len(response), response)
                )
            # Collect a tuple of (rootfolder, next_offset) tuples
            parsed_pages = [self._get_page(message) for message in response]
            for (rootfolder, next_offset), paging_info in zip(parsed_pages, paging_infos):
                paging_info['next_offset'] = next_offset
                if isinstance(rootfolder, ElementType):
                    container = rootfolder.find(self.element_container_name)
                    if container is None:
                        raise TransportError('No %s elements in ResponseMessage (%s)' % (self.element_container_name,
                                                                                         xml_to_str(rootfolder)))
                    for elem in self._get_elements_in_container(container=container):
                        paging_info['item_count'] += 1
                        yield elem
                    total_item_count += paging_info['item_count']
                    if max_items and total_item_count >= max_items:
                        # No need to continue. Break out of inner loop
                        log.debug("'max_items' count reached (inner)")
                        break
                if not paging_info['next_offset']:
                    # Paging is done for this message
                    continue
                if paging_info['next_offset'] != paging_info['item_count']:
                    # Check paging offsets
                    raise TransportError(
                        'Unexpected next offset: %s -> %s' % (paging_info['item_count'], paging_info['next_offset'])
                    )
            # Also break out of outer loop
            if max_items and total_item_count >= max_items:
                log.debug("'max_items' count reached (outer)")
                break
            # Make sure all messages that have a next_offset also have the *same* next_offset
            unique_item_counts = {p['next_offset'] for p in paging_infos if p['next_offset'] is not None}
            if not unique_item_counts:
                # Paging is done for all messages
                break
            if len(unique_item_counts) > 1:
                raise TransportError('Inconsistent next offsets: %s' % unique_item_counts)
            common_next_offset = unique_item_counts.pop()

    def _get_page(self, message):
        rootfolder = self._get_element_container(message=message, name='{%s}RootFolder' % MNS)
        is_last_page = rootfolder.get('IncludesLastItemInRange').lower() in ('true', '0')
        offset = rootfolder.get('IndexedPagingOffset')
        if offset is None and not is_last_page:
            log.debug("Not last page in range, but Exchange didn't send a page offset. Assuming first page")
            offset = '1'
        next_offset = None if is_last_page else int(offset)
        item_count = int(rootfolder.get('TotalItemsInView'))
        if not item_count:
            if next_offset is not None:
                raise ValueError("Expected empty 'next_offset' when 'item_count' is 0")
            rootfolder = None
        log.debug('%s: Got page with next offset %s (last_page %s)', self.SERVICE_NAME, next_offset, is_last_page)
        return rootfolder, next_offset


class GetServerTimeZones(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/dd899371(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetServerTimeZones'
    element_container_name = '{%s}TimeZoneDefinitions' % MNS

    def call(self, timezones=None, return_full_timezone_data=False):
        if self.protocol.version.build < EXCHANGE_2010:
            raise NotImplementedError('%s is only supported for Exchange 2010 servers and later' % self.SERVICE_NAME)
        return self._get_elements(payload=self.get_payload(
            timezones=timezones,
            return_full_timezone_data=return_full_timezone_data
        ))

    def get_payload(self, timezones, return_full_timezone_data):
        payload = create_element(
            'm:%s' % self.SERVICE_NAME,
            ReturnFullTimeZoneData='true' if return_full_timezone_data else 'false',
        )
        if timezones is not None:
            is_empty, timezones = peek(timezones)
            if not is_empty:
                tz_ids = create_element('m:Ids')
                for timezone in timezones:
                    tz_id = set_xml_value(create_element('t:Id'), timezone.ms_id, version=self.protocol.version)
                    tz_ids.append(tz_id)
                payload.append(tz_ids)
        return payload

    def _get_elements_in_container(self, container):
        from .recurrence import WEEKDAY_NAMES
        for timezonedef in container:
            tz_id = timezonedef.get('Id')
            tz_name = timezonedef.get('Name')
            periods = timezonedef.find('{%s}Periods' % TNS)
            tz_periods = {}
            for period in periods.findall('{%s}Period' % TNS):
                # Convert e.g. "trule:Microsoft/Registry/W. Europe Standard Time/2006-Daylight" to (2006, 'Daylight')
                p_year, p_type = period.get('Id').rsplit('/', 1)[1].split('-')
                tz_periods[(int(p_year), p_type)] = dict(
                    name=period.get('Name'),
                    bias=xml_text_to_value(period.get('Bias'), datetime.timedelta)
                )
            tz_transitions_groups = {}
            transitiongroups = timezonedef.find('{%s}TransitionsGroups' % TNS)
            if transitiongroups is not None:
                for transitiongroup in transitiongroups.findall('{%s}TransitionsGroup' % TNS):
                    tg_id = int(transitiongroup.get('Id'))
                    tz_transitions_groups[tg_id] = []
                    for transition in transitiongroup.findall('{%s}Transition' % TNS):
                        # Apply same conversion to To as for period IDs
                        to_year, to_type = transition.find('{%s}To' % TNS).text.rsplit('/', 1)[1].split('-')
                        tz_transitions_groups[tg_id].append(dict(
                            to=(int(to_year), to_type),
                        ))
                    for transition in transitiongroup.findall('{%s}RecurringDayTransition' % TNS):
                        # Apply same conversion to To as for period IDs
                        to_year, to_type = transition.find('{%s}To' % TNS).text.rsplit('/', 1)[1].split('-')
                        tz_transitions_groups[tg_id].append(dict(
                            to=(int(to_year), to_type),
                            offset=xml_text_to_value(transition.find('{%s}TimeOffset' % TNS).text, datetime.timedelta),
                            iso_month=xml_text_to_value(transition.find('{%s}Month' % TNS).text, int),
                            iso_weekday=WEEKDAY_NAMES.index(transition.find('{%s}DayOfWeek' % TNS).text) + 1,
                            occurrence=xml_text_to_value(transition.find('{%s}Occurrence' % TNS).text, int),
                        ))
            tz_transitions = {}
            transitions = timezonedef.find('{%s}Transitions' % TNS)
            if transitions is not None:
                for transition in transitions.findall('{%s}Transition' % TNS):
                    to = transition.find('{%s}To' % TNS)
                    if to.get('Kind') != 'Group':
                        raise ValueError('Unexpected "Kind" XML attr: %s' % to.get('Kind'))
                    tg_id = xml_text_to_value(to.text, int)
                    tz_transitions[tg_id] = None
                for transition in transitions.findall('{%s}AbsoluteDateTransition' % TNS):
                    to = transition.find('{%s}To' % TNS)
                    if to.get('Kind') != 'Group':
                        raise ValueError('Unexpected "Kind" XML attr: %s' % to.get('Kind'))
                    tg_id = xml_text_to_value(to.text, int)
                    try:
                        t_date = xml_text_to_value(transition.find('{%s}DateTime' % TNS).text, EWSDateTime).date()
                    except NaiveDateTimeNotAllowed as e:
                        # We encountered a naive datetime. Don't worry. we just need the date
                        t_date = e.args[0].date()
                    tz_transitions[tg_id] = t_date

            yield (tz_id, tz_name, tz_periods, tz_transitions, tz_transitions_groups)


class GetRoomLists(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/dd899486(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetRoomLists'
    element_container_name = '{%s}RoomLists' % MNS

    def call(self):
        from .properties import RoomList

        if self.protocol.version.build < EXCHANGE_2010:
            raise NotImplementedError('%s is only supported for Exchange 2010 servers and later' % self.SERVICE_NAME)
        elements = self._get_elements(payload=self.get_payload())
        return [RoomList.from_xml(elem=elem, account=None) for elem in elements]

    def get_payload(self):
        return create_element('m:%s' % self.SERVICE_NAME)


class GetRooms(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/dd899454(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetRooms'
    element_container_name = '{%s}Rooms' % MNS

    def call(self, roomlist):
        from .properties import Room
        if self.protocol.version.build < EXCHANGE_2010:
            raise NotImplementedError('%s is only supported for Exchange 2010 servers and later' % self.SERVICE_NAME)
        elements = self._get_elements(payload=self.get_payload(roomlist=roomlist))
        return [Room.from_xml(elem=elem, account=None) for elem in elements]

    def get_payload(self, roomlist):
        getrooms = create_element('m:%s' % self.SERVICE_NAME)
        set_xml_value(getrooms, roomlist, version=self.protocol.version)
        return getrooms


class EWSPooledMixIn(EWSService):
    def _pool_requests(self, payload_func, items, **kwargs):
        log.debug('Processing items in chunks of %s', self.chunk_size)
        # Chop items list into suitable pieces and let worker threads chew on the work. The order of the output result
        # list must be the same as the input id list, so the caller knows which status message belongs to which ID.
        # Yield results as they become available.
        results = []
        n = 1
        for chunk in chunkify(items, self.chunk_size):
            log.debug('Starting %s._get_elements worker %s for %s items', self.__class__.__name__, n, len(chunk))
            n += 1
            results.append(self.protocol.thread_pool.apply_async(
                lambda c: self._get_elements(payload=payload_func(c, **kwargs)),
                (chunk,)
            ))
            # Results will be available before iteration has finished if 'items' is a slow generator. Return early
            for i, r in enumerate(results, 1):
                if r is None:
                    continue
                if not r.ready():
                    # First non-yielded result isn't ready yet. Yielding other ready results would mess up ordering
                    break
                log.debug('%s._get_elements result %s is ready early', self.__class__.__name__, i)
                for elem in r.get():
                    yield elem
                results[i-1] = None
        # Yield remaining results in order, as they become available
        for i, r in enumerate(results, 1):
            if r is None:
                log.debug('%s._get_elements result %s of %s already sent', self.__class__.__name__, i, len(results))
                continue
            log.debug('Waiting for %s._get_elements result %s of %s', self.__class__.__name__, i, len(results))
            elems = r.get()
            log.debug('%s._get_elements result %s of %s is ready', self.__class__.__name__, i, len(results))
            for elem in elems:
                yield elem


class GetItem(EWSAccountService, EWSPooledMixIn):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa563775(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, items, additional_fields, shape):
        """
        Returns all items in an account that correspond to a list of ID's, in stable order.

        :param items: a list of (id, changekey) tuples or Item objects
        :param additional_fields: the extra fields that should be returned with the item, as FieldPath objects
        :param shape: The shape of returned objects
        :return: XML elements for the items, in stable order
        """
        return self._pool_requests(payload_func=self.get_payload, **dict(
            items=items,
            additional_fields=additional_fields,
            shape=shape,
        ))

    def get_payload(self, items, additional_fields, shape):
        from .properties import ItemId
        getitem = create_element('m:%s' % self.SERVICE_NAME)
        itemshape = create_element('m:ItemShape')
        add_xml_child(itemshape, 't:BaseShape', shape)
        if additional_fields:
            additional_properties = create_element('t:AdditionalProperties')
            expanded_fields = chain(*(f.expand(version=self.account.version) for f in additional_fields))
            set_xml_value(additional_properties, sorted(expanded_fields, key=lambda f: f.path),
                          version=self.account.version)
            itemshape.append(additional_properties)
        getitem.append(itemshape)
        item_ids = create_element('m:ItemIds')
        is_empty = True
        for item in items:
            is_empty = False
            item_id = ItemId(*(item if isinstance(item, tuple) else (item.item_id, item.changekey)))
            log.debug('Getting item %s', item)
            set_xml_value(item_ids, item_id, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        getitem.append(item_ids)
        return getitem


class CreateItem(EWSAccountService, EWSPooledMixIn):
    """
    Takes folder and a list of items. Returns result of creation as a list of tuples (success[True|False],
    errormessage), in the same order as the input list.

    MSDN: https://msdn.microsoft.com/en-us/library/office/aa565209(v=exchg.150).aspx
    """
    SERVICE_NAME = 'CreateItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, items, folder, message_disposition, send_meeting_invitations):
        return self._pool_requests(payload_func=self.get_payload, **dict(
            items=items,
            folder=folder,
            message_disposition=message_disposition,
            send_meeting_invitations=send_meeting_invitations,
        ))

    def get_payload(self, items, folder, message_disposition, send_meeting_invitations):
        # Takes a list of Item objects (CalendarItem, Message etc) and returns the XML for a CreateItem request.
        # convert items to XML Elements
        #
        # MessageDisposition is only applicable to email messages, where it is required.
        #
        # SendMeetingInvitations is required for calendar items. It is also applicable to tasks, meeting request
        # responses (see https://msdn.microsoft.com/en-us/library/office/aa566464(v=exchg.150).aspx) and sharing
        # invitation accepts (see https://msdn.microsoft.com/en-us/library/office/ee693280(v=exchg.150).aspx). The
        # last two are not supported yet.
        createitem = create_element(
            'm:%s' % self.SERVICE_NAME,
            MessageDisposition=message_disposition,
            SendMeetingInvitations=send_meeting_invitations,
        )
        if folder:
            saveditemfolderid = create_element('m:SavedItemFolderId')
            set_xml_value(saveditemfolderid, folder, version=self.account.version)
            createitem.append(saveditemfolderid)
        item_elems = create_element('m:Items')
        is_empty = True
        for item in items:
            is_empty = False
            log.debug('Adding item %s', item)
            set_xml_value(item_elems, item, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        createitem.append(item_elems)
        return createitem


class UpdateItem(EWSAccountService, EWSPooledMixIn):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa580254(v=exchg.150).aspx
    """
    SERVICE_NAME = 'UpdateItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, items, conflict_resolution, message_disposition, send_meeting_invitations_or_cancellations,
             suppress_read_receipts):
        return self._pool_requests(payload_func=self.get_payload, **dict(
            items=items,
            conflict_resolution=conflict_resolution,
            message_disposition=message_disposition,
            send_meeting_invitations_or_cancellations=send_meeting_invitations_or_cancellations,
            suppress_read_receipts=suppress_read_receipts,
        ))

    def _delete_item_elem(self, field_path):
        deleteitemfield = create_element('t:DeleteItemField')
        return set_xml_value(deleteitemfield, field_path, version=self.account.version)

    def _set_item_elem(self, item_model, field_path, value):
        setitemfield = create_element('t:SetItemField')
        set_xml_value(setitemfield, field_path, version=self.account.version)
        folderitem = create_element(item_model.request_tag())
        field_elem = field_path.field.to_xml(value, version=self.account.version)
        set_xml_value(folderitem, field_elem, version=self.account.version)
        setitemfield.append(folderitem)
        return setitemfield

    @staticmethod
    def _sort_fieldnames(item_model, fieldnames):
        # Take a list of fieldnames and return the fields in the order they are mentioned in item_class.FIELDS.
        for f in item_model.FIELDS:
            if f.name in fieldnames:
                yield f.name

    def _get_timezone_fieldnames(self, item, fieldnames):
        # For CalendarItem items where we update 'start' or 'end', we want to update internal timezone fields
        from .items import CalendarItem
        timezone_fieldnames = set()

        if item.__class__ == CalendarItem:
            has_start = 'start' in fieldnames
            has_end = 'end' in fieldnames
            item.clean_timezone_fields(version=self.account.version)
            meeting_tz_field, start_tz_field, end_tz_field = CalendarItem.timezone_fields()
            if self.account.version.build < EXCHANGE_2010:
                if has_start or has_end:
                    timezone_fieldnames.add(meeting_tz_field.name)
            else:
                if has_start:
                    timezone_fieldnames.add(start_tz_field.name)
                if has_end:
                    timezone_fieldnames.add(end_tz_field.name)
        return timezone_fieldnames

    def _get_item_update_elems(self, item, fieldnames):
        from .fields import FieldPath, IndexedField
        from .indexed_properties import MultiFieldIndexedElement
        item_model = item.__class__
        fieldnames_set = set(fieldnames)
        timezone_fieldnames = self._get_timezone_fieldnames(item=item, fieldnames=fieldnames_set)
        fieldnames_set.update(timezone_fieldnames)

        for fieldname in self._sort_fieldnames(item_model=item_model, fieldnames=fieldnames_set):
            field = item_model.get_field_by_fieldname(fieldname)
            if field.is_read_only and field.name not in timezone_fieldnames:
                # Timezone fields are ok, even though they are marked read-only
                raise ValueError('%s is a read-only field' % field.name)
            value = field.clean(getattr(item, field.name), version=self.account.version)  # Make sure the value is OK

            if value is None or (field.is_list and not value):
                # A value of None or [] means we want to remove this field from the item
                if field.is_required or field.is_required_after_save:
                    raise ValueError('%s is a required field and may not be deleted' % field.name)
                for field_path in FieldPath(field=field).expand(version=self.account.version):
                    yield self._delete_item_elem(field_path=field_path)
                continue

            if isinstance(field, IndexedField):
                # TODO: Maybe the set/delete logic should extend into subfields, not just overwrite the whole item.
                for v in value:
                    # TODO: We should also delete the labels that no longer exist in the list
                    if issubclass(field.value_cls, MultiFieldIndexedElement):
                        # We have subfields. Generate SetItem XML for each subfield. SetItem only accepts items that
                        # have the one value set that we want to change. Create a new IndexedField object that has
                        # only that value set.
                        for subfield in field.value_cls.supported_fields(version=self.account.version):
                            yield self._set_item_elem(
                                item_model=item_model,
                                field_path=FieldPath(field=field, label=v.label, subfield=subfield),
                                value=field.value_cls(**{'label': v.label, subfield.name: getattr(v, subfield.name)}),
                            )
                    else:
                        # The simpler IndexedFields with only one subfield
                        subfield = field.value_cls.value_field(version=self.account.version)
                        yield self._set_item_elem(
                            item_model=item_model,
                            field_path=FieldPath(field=field, label=v.label, subfield=subfield),
                            value=v,
                        )
                continue

            yield self._set_item_elem(item_model=item_model, field_path=FieldPath(field=field), value=value)

    def get_payload(self, items, conflict_resolution, message_disposition, send_meeting_invitations_or_cancellations,
                    suppress_read_receipts):
        # Takes a list of (Item, fieldnames) tuples where 'Item' is a instance of a subclass of Item and 'fieldnames'
        # are the attribute names that were updated. Returns the XML for an UpdateItem call.
        # an UpdateItem request.
        from .properties import ItemId
        if self.account.version.build >= EXCHANGE_2013_SP1:
            updateitem = create_element(
                'm:%s' % self.SERVICE_NAME,
                ConflictResolution=conflict_resolution,
                MessageDisposition=message_disposition,
                SendMeetingInvitationsOrCancellations=send_meeting_invitations_or_cancellations,
                SuppressReadReceipts='true' if suppress_read_receipts else 'false',
            )
        else:
            updateitem = create_element(
                'm:%s' % self.SERVICE_NAME,
                ConflictResolution=conflict_resolution,
                MessageDisposition=message_disposition,
                SendMeetingInvitationsOrCancellations=send_meeting_invitations_or_cancellations,
            )
        itemchanges = create_element('m:ItemChanges')
        is_empty = True
        for item, fieldnames in items:
            is_empty = False
            if not fieldnames:
                raise ValueError('"fieldnames" must not be empty')
            itemchange = create_element('t:ItemChange')
            log.debug('Updating item %s values %s', item.item_id, fieldnames)
            set_xml_value(itemchange, ItemId(item.item_id, item.changekey), version=self.account.version)
            updates = create_element('t:Updates')
            for elem in self._get_item_update_elems(item=item, fieldnames=fieldnames):
                updates.append(elem)
            itemchange.append(updates)
            itemchanges.append(itemchange)
        if is_empty:
            raise ValueError('"items" must not be empty')
        updateitem.append(itemchanges)
        return updateitem


class DeleteItem(EWSAccountService, EWSPooledMixIn):
    """
    Takes a folder and a list of (id, changekey) tuples. Returns result of deletion as a list of tuples
    (success[True|False], errormessage), in the same order as the input list.

    MSDN: https://msdn.microsoft.com/en-us/library/office/aa562961(v=exchg.150).aspx

    """
    SERVICE_NAME = 'DeleteItem'
    element_container_name = None  # DeleteItem doesn't return a response object, just status in XML attrs

    def call(self, items, delete_type, send_meeting_cancellations, affected_task_occurrences, suppress_read_receipts):
        return self._pool_requests(payload_func=self.get_payload, **dict(
            items=items,
            delete_type=delete_type,
            send_meeting_cancellations=send_meeting_cancellations,
            affected_task_occurrences=affected_task_occurrences,
            suppress_read_receipts=suppress_read_receipts,
        ))

    def get_payload(self, items, delete_type, send_meeting_cancellations, affected_task_occurrences,
                    suppress_read_receipts):
        # Takes a list of (item_id, changekey) tuples or Item objects and returns the XML for a DeleteItem request.
        from .properties import ItemId
        if self.account.version.build >= EXCHANGE_2013_SP1:
            deleteitem = create_element(
                'm:%s' % self.SERVICE_NAME,
                DeleteType=delete_type,
                SendMeetingCancellations=send_meeting_cancellations,
                AffectedTaskOccurrences=affected_task_occurrences,
                SuppressReadReceipts='true' if suppress_read_receipts else 'false',
            )
        else:
            deleteitem = create_element(
                'm:%s' % self.SERVICE_NAME,
                DeleteType=delete_type,
                SendMeetingCancellations=send_meeting_cancellations,
                AffectedTaskOccurrences=affected_task_occurrences,
            )

        item_ids = create_element('m:ItemIds')
        is_empty = True
        for item in items:
            is_empty = False
            item_id = ItemId(*(item if isinstance(item, tuple) else (item.item_id, item.changekey)))
            log.debug('Deleting item %s', item)
            set_xml_value(item_ids, item_id, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        deleteitem.append(item_ids)
        return deleteitem


class FindItem(EWSFolderService, PagingEWSMixIn):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa566370(v=exchg.150).aspx
    """
    SERVICE_NAME = 'FindItem'
    element_container_name = '{%s}Items' % TNS

    def call(self, additional_fields, restriction, order_fields, shape, query_string, depth, calendar_view, max_items):
        """
        Find items in an account.

        :param additional_fields: the extra fields that should be returned with the item, as FieldPath objects
        :param restriction: a Restriction object for
        :param order_fields: the fields to sort the results by
        :param shape: The set of attributes to return
        :param query_string: a QueryString object
        :param depth: How deep in the folder structure to search for items
        :param calendar_view: If set, returns recurring calendar items unfolded
        :param max_items: the max number of items to return
        :return: XML elements for the matching items
        """
        return self._paged_call(payload_func=self.get_payload, max_items=max_items, **dict(
            additional_fields=additional_fields,
            restriction=restriction,
            order_fields=order_fields,
            query_string=query_string,
            shape=shape,
            depth=depth,
            calendar_view=calendar_view,
            page_size=self.chunk_size,
        ))

    def get_payload(self, additional_fields, restriction, order_fields, query_string, shape, depth, calendar_view,
                    page_size, offset=0):
        finditem = create_element('m:%s' % self.SERVICE_NAME, Traversal=depth)
        itemshape = create_element('m:ItemShape')
        add_xml_child(itemshape, 't:BaseShape', shape)
        if additional_fields:
            additional_properties = create_element('t:AdditionalProperties')
            expanded_fields = chain(*(f.expand(version=self.account.version) for f in additional_fields))
            set_xml_value(additional_properties, sorted(expanded_fields, key=lambda f: f.path),
                          version=self.account.version)
            itemshape.append(additional_properties)
        finditem.append(itemshape)
        if calendar_view is None:
            view_type = create_element('m:IndexedPageItemView',
                                       MaxEntriesReturned=text_type(page_size),
                                       Offset=text_type(offset),
                                       BasePoint='Beginning')
        else:
            view_type = calendar_view.to_xml(version=self.account.version)
        finditem.append(view_type)
        if restriction:
            finditem.append(restriction.to_xml(version=self.account.version))
        if order_fields:
            sort_order = create_element('m:SortOrder')
            set_xml_value(sort_order, order_fields, version=self.account.version)
            finditem.append(sort_order)
        parentfolderids = create_element('m:ParentFolderIds')
        set_xml_value(parentfolderids, self.folders, version=self.account.version)
        finditem.append(parentfolderids)
        if query_string:
            finditem.append(query_string.to_xml(version=self.account.version))
        return finditem


class FindFolder(EWSFolderService, PagingEWSMixIn):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa564962(v=exchg.150).aspx
    """
    SERVICE_NAME = 'FindFolder'
    element_container_name = '{%s}Folders' % TNS

    def call(self, additional_fields, shape, depth, max_items):
        """
        Find subfolders of a folder.

        :param additional_fields: the extra fields that should be returned with the folder, as FieldPath objects
        :param shape: The set of attributes to return
        :param depth: How deep in the folder structure to search for folders
        :param max_items: The maximum number of items to return
        :return: XML elements for the matching folders
        """
        from .folders import Folder
        for elem in self._paged_call(payload_func=self.get_payload, max_items=max_items, **dict(
            additional_fields=additional_fields,
            shape=shape,
            depth=depth,
            page_size=self.chunk_size,
        )):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield Folder.from_xml(elem=elem, account=self.account)

    def get_payload(self, additional_fields, shape, depth, page_size, offset=0):
        findfolder = create_element('m:%s' % self.SERVICE_NAME, Traversal=depth)
        foldershape = create_element('m:FolderShape')
        add_xml_child(foldershape, 't:BaseShape', shape)
        if additional_fields:
            additional_properties = create_element('t:AdditionalProperties')
            expanded_fields = chain(*(f.expand(version=self.account.version) for f in additional_fields))
            set_xml_value(additional_properties, sorted(expanded_fields, key=lambda f: f.path),
                          version=self.account.version)
            foldershape.append(additional_properties)
        findfolder.append(foldershape)
        if self.account.version.build >= EXCHANGE_2010:
            indexedpageviewitem = create_element('m:IndexedPageFolderView', MaxEntriesReturned=text_type(page_size),
                                                 Offset=text_type(offset), BasePoint='Beginning')
            findfolder.append(indexedpageviewitem)
        else:
            if offset != 0:
                raise ValueError('Offsets are only supported from Exchange 2010')
        parentfolderids = create_element('m:ParentFolderIds')
        set_xml_value(parentfolderids, self.folders, version=self.account.version)
        findfolder.append(parentfolderids)
        return findfolder


class GetFolder(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa580263(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetFolder'
    element_container_name = '{%s}Folders' % MNS
    ERRORS_TO_CATCH_IN_RESPONSE = EWSAccountService.ERRORS_TO_CATCH_IN_RESPONSE + (
        ErrorFolderNotFound, ErrorNoPublicFolderReplicaAvailable, ErrorInvalidOperation,
    )

    def call(self, folders, additional_fields, shape):
        """
        Takes a folder ID and returns the full information for that folder.

        :param folders: a list of Folder objects
        :param additional_fields: the extra fields that should be returned with the folder, as FieldPath objects
        :param shape: The set of attributes to return
        :return: XML elements for the folders, in stable order
        """
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        from .folders import Folder, DistinguishedFolderId
        folders_list = list(folders)  # Convert to a list, in case 'folders' is a generator
        for folder, elem in zip(folders_list, self._get_elements(payload=self.get_payload(
            folders=folders,
            additional_fields=additional_fields,
            shape=shape,
        ))):
            if isinstance(elem, Exception):
                yield elem
                continue
            if isinstance(folder, Folder):
                f = folder.from_xml(elem=elem, account=self.account)
                if folder.is_distinguished or (not folder.folder_id and folder.has_distinguished_name):
                    f.is_distinguished = True
            else:
                # 'folder' may be a FolderId/DistinguishedFolderId instance
                f = Folder.from_xml(elem=elem, account=self.account)
                if isinstance(folder, DistinguishedFolderId):
                    f.is_distinguished = True
            yield f

    def get_payload(self, folders, additional_fields, shape):
        from .folders import FolderId
        getfolder = create_element('m:%s' % self.SERVICE_NAME)
        foldershape = create_element('m:FolderShape')
        add_xml_child(foldershape, 't:BaseShape', shape)
        if additional_fields:
            additional_properties = create_element('t:AdditionalProperties')
            expanded_fields = chain(*(f.expand(version=self.account.version) for f in additional_fields))
            set_xml_value(additional_properties, sorted(expanded_fields, key=lambda f: f.path),
                          version=self.account.version)
            foldershape.append(additional_properties)
        getfolder.append(foldershape)
        folder_ids = create_element('m:FolderIds')
        is_empty = True
        for folder in folders:
            is_empty = False
            log.debug('Getting folder %s', folder)
            if isinstance(folder, tuple):
                set_xml_value(folder_ids, FolderId(*folder), version=self.account.version)
                continue
            set_xml_value(folder_ids, folder, version=self.account.version)
        if is_empty:
            raise ValueError('"folders" must not be empty')
        getfolder.append(folder_ids)
        return getfolder


class CreateFolder(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa563574(v=exchg.150).aspx
    """
    SERVICE_NAME = 'CreateFolder'
    element_container_name = '{%s}Folders' % MNS

    def call(self, parent_folder, folders):
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        folders_list = list(folders)  # Convert to a list, in case 'folders' is a generator
        for folder, elem in zip(folders_list, self._get_elements(payload=self.get_payload(
                parent_folder=parent_folder, folders=folders
        ))):
            if isinstance(elem, Exception):
                yield elem
                continue
            f = folder.from_xml(elem=elem, account=self.account)
            if folder.is_distinguished or (not folder.folder_id and folder.has_distinguished_name):
                f.is_distinguished = True
            yield f

    def get_payload(self, parent_folder, folders):
        create_folder = create_element('m:%s' % self.SERVICE_NAME)
        parentfolderid = create_element('m:ParentFolderId')
        set_xml_value(parentfolderid, parent_folder, version=self.account.version)
        set_xml_value(create_folder, parentfolderid, version=self.account.version)
        folders_elem = create_element('m:Folders')
        is_empty = True
        for folder in folders:
            is_empty = False
            log.debug('Creating folder %s', folder)
            set_xml_value(folders_elem, folder, version=self.account.version)
        if is_empty:
            raise ValueError('"folders" must not be empty')
        create_folder.append(folders_elem)
        return create_folder


class UpdateFolder(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa580257(v=exchg.150).aspx
    """
    SERVICE_NAME = 'UpdateFolder'
    element_container_name = '{%s}Folders' % MNS

    def call(self, folders):
        # We can't easily find the correct folder class from the returned XML. Instead, return objects with the same
        # class as the folder instance it was requested with.
        folders_list = list(f[0] for f in folders)  # Convert to a list, in case 'folders' is a generator
        for folder, elem in zip(folders_list, self._get_elements(payload=self.get_payload(folders=folders))):
            if isinstance(elem, Exception):
                yield elem
                continue
            f = folder.from_xml(elem=elem, account=self.account)
            if folder.is_distinguished or (not folder.folder_id and folder.has_distinguished_name):
                f.is_distinguished = True
            yield f

    @staticmethod
    def _sort_fieldnames(folder_model, fieldnames):
        # Take a list of fieldnames and return the fields in the order they are mentioned in folder_model.FIELDS.
        for f in folder_model.FIELDS:
            if f.name in fieldnames:
                yield f.name

    def _set_folder_elem(self, folder_model, field_path, value):
        setfolderfield = create_element('t:SetFolderField')
        set_xml_value(setfolderfield, field_path, version=self.account.version)
        folder = create_element(folder_model.request_tag())
        field_elem = field_path.field.to_xml(value, version=self.account.version)
        set_xml_value(folder, field_elem, version=self.account.version)
        setfolderfield.append(folder)
        return setfolderfield

    def _delete_folder_elem(self, field_path):
        deletefolderfield = create_element('t:DeleteFolderField')
        return set_xml_value(deletefolderfield, field_path, version=self.account.version)

    def _get_folder_update_elems(self, folder, fieldnames):
        from .fields import FieldPath
        folder_model = folder.__class__
        fieldnames_set = set(fieldnames)

        for fieldname in self._sort_fieldnames(folder_model=folder_model, fieldnames=fieldnames_set):
            field = folder_model.get_field_by_fieldname(fieldname)
            if field.is_read_only:
                raise ValueError('%s is a read-only field' % field.name)
            value = field.clean(getattr(folder, field.name), version=self.account.version)  # Make sure the value is OK

            if value is None or (field.is_list and not value):
                # A value of None or [] means we want to remove this field from the item
                if field.is_required or field.is_required_after_save:
                    raise ValueError('%s is a required field and may not be deleted' % field.name)
                for field_path in FieldPath(field=field).expand(version=self.account.version):
                    yield self._delete_folder_elem(field_path=field_path)
                continue

            yield self._set_folder_elem(folder_model=folder_model, field_path=FieldPath(field=field), value=value)

    def get_payload(self, folders):
        updatefolder = create_element('m:%s' % self.SERVICE_NAME)
        folderchanges = create_element('m:FolderChanges')
        is_empty = True
        for folder, fieldnames in folders:
            is_empty = False
            log.debug('Updating folder %s', folder)
            folderchange = create_element('t:FolderChange')
            set_xml_value(folderchange, folder, version=self.account.version)
            updates = create_element('t:Updates')
            for elem in self._get_folder_update_elems(folder=folder, fieldnames=fieldnames):
                updates.append(elem)
            folderchange.append(updates)
            folderchanges.append(folderchange)
        if is_empty:
            raise ValueError('"folders" must not be empty')
        updatefolder.append(folderchanges)
        return updatefolder


class DeleteFolder(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa564767(v=exchg.150).aspx
    """
    SERVICE_NAME = 'DeleteFolder'
    element_container_name = None  # DeleteFolder doesn't return a response object, just status in XML attrs

    def call(self, folders, delete_type):
        return self._get_elements(payload=self.get_payload(folders=folders, delete_type=delete_type))

    def get_payload(self, folders, delete_type):
        from .folders import FolderId
        deletefolder = create_element('m:%s' % self.SERVICE_NAME, DeleteType=delete_type)
        folder_ids = create_element('m:FolderIds')
        is_empty = True
        for folder in folders:
            is_empty = False
            log.debug('Deleting folder %s', folder)
            if isinstance(folder, tuple):
                set_xml_value(folder_ids, FolderId(*folder) if isinstance(folder, tuple) else folder,
                              version=self.account.version)
                continue
            set_xml_value(folder_ids, folder, version=self.account.version)
        if is_empty:
            raise ValueError('"folders" must not be empty')
        deletefolder.append(folder_ids)
        return deletefolder


class EmptyFolder(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/ff709454(v=exchg.150).aspx
    """
    SERVICE_NAME = 'EmptyFolder'
    element_container_name = None  # EmptyFolder doesn't return a response object, just status in XML attrs

    def call(self, folders, delete_type, delete_sub_folders):
        return self._get_elements(payload=self.get_payload(folders=folders, delete_type=delete_type,
                                                           delete_sub_folders=delete_sub_folders))

    def get_payload(self, folders, delete_type, delete_sub_folders):
        from .folders import FolderId
        emptyfolder = create_element('m:%s' % self.SERVICE_NAME, DeleteType=delete_type,
                                     DeleteSubFolders='true' if delete_sub_folders else 'false')
        folder_ids = create_element('m:FolderIds')
        is_empty = True
        for folder in folders:
            is_empty = False
            log.debug('Emptying folder %s', folder)
            if isinstance(folder, tuple):
                set_xml_value(folder_ids, FolderId(*folder) if isinstance(folder, tuple) else folder,
                              version=self.account.version)
                continue
            set_xml_value(folder_ids, folder, version=self.account.version)
        if is_empty:
            raise ValueError('"folders" must not be empty')
        emptyfolder.append(folder_ids)
        return emptyfolder


class SendItem(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa580238(v=exchg.150).aspx
    """
    SERVICE_NAME = 'SendItem'
    element_container_name = None  # SendItem doesn't return a response object, just status in XML attrs

    def call(self, items, saved_item_folder):
        return self._get_elements(payload=self.get_payload(items=items, saved_item_folder=saved_item_folder))

    def get_payload(self, items, saved_item_folder):
        from .properties import ItemId
        senditem = create_element(
            'm:%s' % self.SERVICE_NAME,
            SaveItemToFolder='true' if saved_item_folder else 'false',
        )
        item_ids = create_element('m:ItemIds')
        is_empty = True
        for item in items:
            is_empty = False
            item_id = ItemId(*(item if isinstance(item, tuple) else (item.item_id, item.changekey)))
            log.debug('Sending item %s', item)
            set_xml_value(item_ids, item_id, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        senditem.append(item_ids)
        if saved_item_folder:
            saveditemfolderid = create_element('m:SavedItemFolderId')
            set_xml_value(saveditemfolderid, saved_item_folder, version=self.account.version)
            senditem.append(saveditemfolderid)
        return senditem


class MoveItem(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa565781(v=exchg.150).aspx
    """
    SERVICE_NAME = 'MoveItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, items, to_folder):
        return self._get_elements(payload=self.get_payload(
            items=items,
            to_folder=to_folder,
        ))

    def get_payload(self, items, to_folder):
        # Takes a list of items and returns their new item IDs
        from .properties import ItemId
        moveeitem = create_element('m:%s' % self.SERVICE_NAME)

        tofolderid = create_element('m:ToFolderId')
        set_xml_value(tofolderid, to_folder, version=self.account.version)
        moveeitem.append(tofolderid)
        item_ids = create_element('m:ItemIds')
        is_empty = True
        for item in items:
            is_empty = False
            item_id = ItemId(*(item if isinstance(item, tuple) else (item.item_id, item.changekey)))
            log.debug('Moving item %s to %s', item, to_folder)
            set_xml_value(item_ids, item_id, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        moveeitem.append(item_ids)
        return moveeitem


class CopyItem(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa565012(v=exchg.150).aspx
    """
    SERVICE_NAME = 'CopyItem'
    element_container_name = '{%s}Items' % MNS

    def call(self, items, to_folder):
        return self._get_elements(payload=self.get_payload(
            items=items,
            to_folder=to_folder,
        ))

    def get_payload(self, items, to_folder):
        from .properties import ItemId
        copyitem = create_element('m:%s' % self.SERVICE_NAME)

        tofolderid = create_element('m:ToFolderId')
        set_xml_value(tofolderid, to_folder, version=self.account.version)
        copyitem.append(tofolderid)
        item_ids = create_element('m:ItemIds')
        is_empty = True
        for item in items:
            is_empty = False
            item_id = ItemId(*(item if isinstance(item, tuple) else (item.item_id, None)))
            log.debug('Copying item %s to %s', item, to_folder)
            set_xml_value(item_ids, item_id, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        copyitem.append(item_ids)
        return copyitem


class FindPeople(EWSAccountService, PagingEWSMixIn):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/jj191039(v=exchg.150).aspx
    """
    SERVICE_NAME = 'FindPeople'
    element_container_name = '{%s}People' % MNS

    def call(self, folder, additional_fields, restriction, order_fields, shape, query_string, depth, max_items):
        """
        Find items in an account.

        :param folder: the Folder object to query
        :param additional_fields: the extra fields that should be returned with the item, as FieldPath objects
        :param restriction: a Restriction object for
        :param order_fields: the fields to sort the results by
        :param shape: The set of attributes to return
        :param query_string: a QueryString object
        :param depth: How deep in the folder structure to search for items
        :param max_items: the max number of items to return
        :return: XML elements for the matching items
        """
        from .items import Persona, IdOnly
        personas = self._paged_call(payload_func=self.get_payload, max_items=max_items, **dict(
            folder=folder,
            additional_fields=additional_fields,
            restriction=restriction,
            order_fields=order_fields,
            query_string=query_string,
            shape=shape,
            depth=depth,
            page_size=self.chunk_size,
        ))
        if shape == IdOnly and additional_fields is None:
            for p in personas:
                yield p if isinstance(p, Exception) else Persona.id_from_xml(p)
        else:
            for p in personas:
                yield p if isinstance(p, Exception) else Persona.from_xml(p, account=self.account)

    def get_payload(self, folder, additional_fields, restriction, order_fields, query_string, shape, depth, page_size,
                    offset=0):
        findpeople = create_element('m:%s' % self.SERVICE_NAME, Traversal=depth)
        personashape = create_element('m:PersonaShape')
        add_xml_child(personashape, 't:BaseShape', shape)
        if additional_fields:
            additional_properties = create_element('t:AdditionalProperties')
            expanded_fields = chain(*(f.expand(version=self.account.version) for f in additional_fields))
            set_xml_value(additional_properties, sorted(expanded_fields, key=lambda f: f.path),
                          version=self.account.version)
            personashape.append(additional_properties)
        findpeople.append(personashape)
        view_type = create_element('m:IndexedPageItemView',
                                   MaxEntriesReturned=text_type(page_size),
                                   Offset=text_type(offset),
                                   BasePoint='Beginning')
        findpeople.append(view_type)
        if restriction:
            findpeople.append(restriction.to_xml(version=self.account.version))
        if order_fields:
            sort_order = create_element('m:SortOrder')
            set_xml_value(sort_order, order_fields, version=self.account.version)
            findpeople.append(sort_order)
        parentfolderid = create_element('m:ParentFolderId')
        set_xml_value(parentfolderid, folder, version=self.account.version)
        findpeople.append(parentfolderid)
        if query_string:
            findpeople.append(query_string.to_xml(version=self.account.version))
        return findpeople

    def _paged_call(self, payload_func, max_items, **kwargs):
        service_endpoint = self.protocol.service_endpoint
        account = self.account if isinstance(self, EWSAccountService) else None
        redacted_account = redact_email(account)
        log_prefix = 'EWS %s, account %s, service %s' % (service_endpoint, redacted_account, self.SERVICE_NAME)
        item_count = 0
        while True:
            log.debug('%s: Getting items at offset %s', log_prefix, item_count)
            kwargs['offset'] = item_count
            payload = payload_func(**kwargs)
            try:
                response = self._get_response_xml(payload=payload)
            except ErrorServerBusy as e:
                if self.protocol.credentials.fail_fast:
                    raise
                back_off = e.back_off or 60  # Back off 60 seconds if we didn't get an explicit suggested value
                back_off_until = datetime.datetime.now() + datetime.timedelta(seconds=back_off)
                self.protocol.credentials.back_off_until = back_off_until
                # We'll warn about this if we actually need to sleep
                continue
            if len(response) != 1:
                # We can only query one folder, so there should only be one element in response
                raise TransportError("Expected single item in 'response', got %s" % response)
            rootfolder, total_items = self._get_page(response[0])
            if isinstance(rootfolder, ElementType):
                container = rootfolder.find(self.element_container_name)
                if container is None:
                    raise TransportError('No %s elements in ResponseMessage (%s)' % (self.element_container_name,
                                                                                     xml_to_str(rootfolder)))
                for elem in self._get_elements_in_container(container=container):
                    item_count += 1
                    yield elem
                if max_items and item_count >= max_items:
                    log.debug("'max_items' count reached")
                    break
            if total_items <= 0 or item_count >= total_items:
                log.debug('Got all items in view')
                break

    def _get_page(self, message):
        self._get_element_container(message=message)  # Just raise exceptions
        total_items = int(message.find('{%s}TotalNumberOfPeopleInView' % MNS).text)
        first_matching = int(message.find('{%s}FirstMatchingRowIndex' % MNS).text)
        first_loaded = int(message.find('{%s}FirstLoadedRowIndex' % MNS).text)
        # TODO: Implement paging when we know how it works for this service
        log.debug('%s: Got page with total items %s, first matching %s, first loaded %s ', self.SERVICE_NAME,
                  total_items, first_matching, first_loaded)
        return message, total_items


class GetPersona(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/jj191408(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetPersona'

    def call(self, persona):
        from .items import Persona
        elements = list(self._get_elements(payload=self.get_payload(persona=persona)))
        if len(elements) != 1:
            raise ValueError('Expected exactly one element in response')
        elem = elements[0]
        if isinstance(elem, Exception):
            raise elem
        return Persona.from_xml(elem=elem.find(Persona.response_tag()), account=None)

    def get_payload(self, persona):
        from .items import Persona
        from .properties import PersonaId
        payload = create_element('m:%s' % self.SERVICE_NAME)
        if isinstance(persona, PersonaId):
            set_xml_value(payload, persona, version=self.protocol.version)
        elif isinstance(persona, Persona):
            set_xml_value(payload, persona.persona_id, version=self.protocol.version)
        else:
            set_xml_value(payload, PersonaId(*persona), version=self.protocol.version)
        return payload

    @classmethod
    def _get_soap_payload(cls, soap_response):
        if not isinstance(soap_response, ElementType):
            raise ValueError("'soap_response' %r must be an ElementType" % soap_response)
        body = soap_response.find('{%s}Body' % SOAPNS)
        if body is None:
            raise TransportError('No Body element in SOAP response')
        response = body.find('{%s}%sResponseMessage' % (MNS, cls.SERVICE_NAME))
        if response is None:
            fault = body.find('{%s}Fault' % SOAPNS)
            if fault is None:
                raise SOAPError('Unknown SOAP response: %s' % xml_to_str(body))
            cls._raise_soap_errors(fault=fault)  # Will throw SOAPError or custom EWS error
        return [response]


class ResolveNames(EWSService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa565329(v=exchg.150).aspx
    """
    # TODO: Does not support paged responses yet. See example in issue #205
    SERVICE_NAME = 'ResolveNames'
    element_container_name = '{%s}ResolutionSet' % MNS
    ERRORS_TO_CATCH_IN_RESPONSE = ErrorNameResolutionNoResults
    WARNINGS_TO_IGNORE_IN_RESPONSE = ErrorNameResolutionMultipleResults

    def call(self, unresolved_entries, parent_folders=None, return_full_contact_data=False, search_scope=None,
             contact_data_shape=None):
        from .items import Contact
        from .properties import Mailbox
        elements = self._get_elements(payload=self.get_payload(
            unresolved_entries=unresolved_entries,
            parent_folders=parent_folders,
            return_full_contact_data=return_full_contact_data,
            search_scope=search_scope,
            contact_data_shape=contact_data_shape,
        ))
        for elem in elements:
            if isinstance(elem, ErrorNameResolutionNoResults):
                continue
            if isinstance(elem, Exception):
                raise elem
            if return_full_contact_data:
                yield (
                    Mailbox.from_xml(elem=elem.find(Mailbox.response_tag()), account=None),
                    Contact.from_xml(elem=elem.find(Contact.response_tag()), account=None),
                )
            else:
                yield Mailbox.from_xml(elem=elem.find(Mailbox.response_tag()), account=None)

    def get_payload(self, unresolved_entries, parent_folders, return_full_contact_data, search_scope,
                    contact_data_shape):
        payload = create_element(
            'm:%s' % self.SERVICE_NAME,
            ReturnFullContactData='true' if return_full_contact_data else 'false',
        )
        if search_scope:
            payload.set('SearchScope', search_scope)
        if contact_data_shape:
            if self.protocol.version.build < EXCHANGE_2010_SP2:
                raise NotImplementedError(
                    "'contact_data_shape' is only supported for Exchange 2010 SP2 servers and later")
            payload.set('ContactDataShape', contact_data_shape)
        if parent_folders:
            parentfolderids = create_element('m:ParentFolderIds')
            set_xml_value(parentfolderids, parent_folders, version=self.protocol.version)
        is_empty = True
        for entry in unresolved_entries:
            is_empty = False
            add_xml_child(payload, 'm:UnresolvedEntry', entry)
        if is_empty:
            raise ValueError('"unresolved_entries" must not be empty')
        return payload


class GetAttachment(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa494316(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetAttachment'
    element_container_name = '{%s}Attachments' % MNS

    def call(self, items, include_mime_content):
        return self._get_elements(payload=self.get_payload(
            items=items,
            include_mime_content=include_mime_content,
        ))

    def get_payload(self, items, include_mime_content):
        from .attachments import AttachmentId
        payload = create_element('m:%s' % self.SERVICE_NAME)
        # TODO: Support additional properties of AttachmentShape. See
        # https://msdn.microsoft.com/en-us/library/office/aa563727(v=exchg.150).aspx
        if include_mime_content:
            attachment_shape = create_element('m:AttachmentShape')
            add_xml_child(attachment_shape, 't:IncludeMimeContent', 'true')
            payload.append(attachment_shape)
        attachment_ids = create_element('m:AttachmentIds')
        is_empty = True
        for item in items:
            is_empty = False
            attachment_id = item if isinstance(item, AttachmentId) else AttachmentId(id=item)
            set_xml_value(attachment_ids, attachment_id, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        payload.append(attachment_ids)
        return payload


class CreateAttachment(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa565877(v=exchg.150).aspx
    """
    SERVICE_NAME = 'CreateAttachment'
    element_container_name = '{%s}Attachments' % MNS

    def call(self, parent_item, items):
        return self._get_elements(payload=self.get_payload(
            parent_item=parent_item,
            items=items,
        ))

    def get_payload(self, parent_item, items):
        from .properties import ParentItemId
        payload = create_element('m:%s' % self.SERVICE_NAME)
        parent_id = ParentItemId(*(parent_item if isinstance(parent_item, tuple)
                                   else (parent_item.item_id, parent_item.changekey)))
        payload.append(parent_id.to_xml(version=self.account.version))
        attachments = create_element('m:Attachments')
        is_empty = True
        for item in items:
            is_empty = False
            set_xml_value(attachments, item, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        payload.append(attachments)
        return payload


class DeleteAttachment(EWSAccountService):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/aa580782(v=exchg.150).aspx
    """
    SERVICE_NAME = 'DeleteAttachment'

    def call(self, items):
        return self._get_elements(payload=self.get_payload(
            items=items,
        ))

    def _get_element_container(self, message, name=None):
        # DeleteAttachment returns RootItemIds directly beneath DeleteAttachmentResponseMessage. Collect the elements
        # and make our own fake container.
        from .properties import RootItemId
        res = super(DeleteAttachment, self)._get_element_container(message=message, name=name)
        if not res:
            return res
        fake_elem = create_element('FakeContainer')
        for elem in message.findall(RootItemId.response_tag()):
            fake_elem.append(elem)
        return fake_elem

    def get_payload(self, items):
        from .attachments import AttachmentId
        payload = create_element('m:%s' % self.SERVICE_NAME)
        attachment_ids = create_element('m:AttachmentIds')
        is_empty = True
        for item in items:
            is_empty = False
            attachment_id = item if isinstance(item, AttachmentId) else AttachmentId(id=item)
            set_xml_value(attachment_ids, attachment_id, version=self.account.version)
        if is_empty:
            raise ValueError('"items" must not be empty')
        payload.append(attachment_ids)
        return payload


class ExportItems(EWSAccountService, EWSPooledMixIn):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/ff709523(v=exchg.150).aspx
    """
    ERRORS_TO_CATCH_IN_RESPONSE = ResponseMessageError
    SERVICE_NAME = 'ExportItems'
    element_container_name = '{%s}Data' % MNS

    def call(self, items):
        return self._pool_requests(payload_func=self.get_payload, **dict(items=items))

    def get_payload(self, items):
        from .properties import ItemId
        exportitems = create_element('m:%s' % self.SERVICE_NAME)
        itemids = create_element('m:ItemIds')
        exportitems.append(itemids)
        for item in items:
            item_id = ItemId(*(item if isinstance(item, tuple) else (item.item_id, item.changekey)))
            set_xml_value(itemids, item_id, version=self.account.version)

        return exportitems

    # We need to override this since ExportItemsResponseMessage is formatted a
    #  little bit differently. Namely, all we want is the 64bit string in the
    #  Data tag.
    def _get_elements_in_container(self, container):
        return [container.text]


class UploadItems(EWSAccountService, EWSPooledMixIn):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/office/ff709490(v=exchg.150).aspx

    This currently has the existing limitation of only being able to upload
    items that do not yet exist in the database. The full spec also allows
    actions "Update" and "UpdateOrCreate".
    """
    SERVICE_NAME = 'UploadItems'
    element_container_name = '{%s}ItemId' % MNS

    def call(self, data):
        # _pool_requests expects 'items', not 'data'
        return self._pool_requests(payload_func=self.get_payload, **dict(items=data))

    def get_payload(self, items):
        """Upload given items to given account

        data is an iterable of tuples where the first element is a Folder
        instance representing the ParentFolder that the item will be placed in
        and the second element is a Data string returned from an ExportItems
        call.
        """
        from .properties import ParentFolderId
        uploaditems = create_element('m:%s' % self.SERVICE_NAME)
        itemselement = create_element('m:Items')
        uploaditems.append(itemselement)
        for parent_folder, data_str in items:
            item = create_element('t:Item', CreateAction='CreateNew')
            parentfolderid = ParentFolderId(parent_folder.folder_id, parent_folder.changekey)
            set_xml_value(item, parentfolderid, version=self.account.version)
            add_xml_child(item, 't:Data', data_str)
            itemselement.append(item)
        return uploaditems

    def _get_elements_in_container(self, container):
        from .properties import ItemId
        return [(container.get(ItemId.ID_ATTR), container.get(ItemId.CHANGEKEY_ATTR))]


class BaseUserOofSettings(EWSAccountService):
    # Common response parsing for non-standard OOF services
    def _get_element_container(self, message, name=None):
        if not isinstance(message, ElementType):
            raise ValueError("'message' %r must be an ElementType" % message)
        # ResponseClass: See http://msdn.microsoft.com/en-us/library/aa566424(v=EXCHG.140).aspx
        response_message = message.find('{%s}ResponseMessage' % MNS)
        response_class = response_message.get('ResponseClass')
        # ResponseCode, MessageText: See http://msdn.microsoft.com/en-us/library/aa580757(v=EXCHG.140).aspx
        response_code = get_xml_attr(response_message, '{%s}ResponseCode' % MNS)
        msg_text = get_xml_attr(response_message, '{%s}MessageText' % MNS)
        msg_xml = response_message.find('{%s}MessageXml' % MNS)
        if response_class == 'Success' and response_code == 'NoError':
            if not name:
                return True
            container = message.find(name)
            if container is None:
                raise TransportError('No %s elements in ResponseMessage (%s)' % (name, xml_to_str(message)))
            return container
        if response_code == 'NoError':
            return True
        # Raise any non-acceptable errors in the container, or return the container or the acceptable exception instance
        if response_class == 'Warning':
            try:
                raise self._get_exception(code=response_code, text=msg_text, msg_xml=msg_xml)
            except self.WARNINGS_TO_CATCH_IN_RESPONSE as e:
                return e
            except self.WARNINGS_TO_IGNORE_IN_RESPONSE as e:
                log.warning(str(e))
                container = message.find(name)
                if container is None:
                    raise TransportError('No %s elements in ResponseMessage (%s)' % (name, xml_to_str(message)))
                return container
        # rspclass == 'Error', or 'Success' and not 'NoError'
        try:
            raise self._get_exception(code=response_code, text=msg_text, msg_xml=msg_xml)
        except self.ERRORS_TO_CATCH_IN_RESPONSE as e:
            return e


class GetUserOofSettings(BaseUserOofSettings):
    """
    MSDN: https://msdn.microsoft.com/en-us/library/aa563465(v=exchg.140).aspx
    """
    SERVICE_NAME = 'GetUserOofSettings'
    element_container_name = '{%s}OofSettings' % TNS

    def call(self, mailbox):
        return self._get_elements(payload=self.get_payload(mailbox=mailbox))

    def get_payload(self, mailbox):
        from .properties import AvailabilityMailbox
        payload = create_element('m:%sRequest' % self.SERVICE_NAME)
        return set_xml_value(payload, AvailabilityMailbox.from_mailbox(mailbox), version=self.account.version)

    def _get_elements_in_response(self, response):
        # This service only returns one result, but 'response' is a list
        from .settings import OofSettings
        if len(response) != 1:
            raise ValueError("Expected 'response' length 1, got %s" % response)
        response = response[0]
        if not isinstance(response, ElementType):
            raise ValueError("'response' %r must be an ElementType" % response)
        container_or_exc = self._get_element_container(message=response, name=self.element_container_name)
        if isinstance(container_or_exc, Exception):
            # pylint: disable=raising-bad-type
            raise container_or_exc
        return OofSettings.from_xml(container_or_exc, account=self.account)


class SetUserOofSettings(BaseUserOofSettings):
    """
    Set automatic replies for the specified mailbox.
    MSDN: https://msdn.microsoft.com/en-us/library/aa580294(v=exchg.140).aspx
    """
    SERVICE_NAME = 'SetUserOofSettings'

    def call(self, oof_settings, mailbox):
        res = list(self._get_elements(payload=self.get_payload(oof_settings=oof_settings, mailbox=mailbox)))
        if len(res) != 1:
            raise ValueError("Expected 'res' length 1, got %s" % res)
        return res[0]

    def get_payload(self, oof_settings, mailbox):
        from .properties import AvailabilityMailbox
        payload = create_element('m:%sRequest' % self.SERVICE_NAME)
        set_xml_value(payload, AvailabilityMailbox.from_mailbox(mailbox), version=self.account.version)
        set_xml_value(payload, oof_settings, version=self.account.version)
        return payload


class GetUserAvailability(EWSService):
    """
     Get detailed availability information for a list of users
     MSDN: https://msdn.microsoft.com/en-us/library/office/aa564001(v=exchg.150).aspx
    """
    SERVICE_NAME = 'GetUserAvailability'

    def call(self, timezone, mailbox_data, free_busy_view_options):
        # TODO: Also supports SuggestionsViewOptions, see
        # https://msdn.microsoft.com/en-us/library/office/aa564990(v=exchg.150).aspx
        from .properties import FreeBusyView
        for elem in self._get_elements(payload=self.get_payload(
            timezone=timezone,
            mailbox_data=mailbox_data,
            free_busy_view_options=free_busy_view_options
        )):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield FreeBusyView.from_xml(elem=elem, account=None)

    def get_payload(self, timezone, mailbox_data, free_busy_view_options):
        payload = create_element('m:%sRequest' % self.SERVICE_NAME)
        set_xml_value(payload, timezone, version=self.protocol.version)
        mailbox_data_array = create_element('m:MailboxDataArray')
        set_xml_value(mailbox_data_array, mailbox_data, version=self.protocol.version)
        payload.append(mailbox_data_array)
        set_xml_value(payload, free_busy_view_options, version=self.protocol.version)
        return payload

    @classmethod
    def _get_soap_payload(cls, soap_response):
        if not isinstance(soap_response, ElementType):
            raise ValueError("'soap_response' %r must be an ElementType" % soap_response)
        body = soap_response.find('{%s}Body' % SOAPNS)
        if body is None:
            raise TransportError('No Body element in SOAP response')
        response = body.find('{%s}%sResponse' % (MNS, cls.SERVICE_NAME))
        if response is None:
            fault = body.find('{%s}Fault' % SOAPNS)
            if fault is None:
                raise SOAPError('Unknown SOAP response: %s' % xml_to_str(body))
            cls._raise_soap_errors(fault=fault)  # Will throw SOAPError or custom EWS error
        response_messages = response.find('{%s}FreeBusyResponseArray' % MNS)
        return response_messages.findall('{%s}FreeBusyResponse' % MNS)

    def _get_elements_in_response(self, response):
        for msg in response:
            if not isinstance(msg, ElementType):
                raise ValueError("'msg' %r must be an ElementType" % msg)
            # Just check the response code and raise errors
            self._get_element_container(message=msg.find('{%s}ResponseMessage' % MNS))
            if isinstance(msg, ElementType):
                for c in self._get_elements_in_container(container=msg):
                    yield c
            else:
                yield msg

    def _get_elements_in_container(self, container):
        return [container.find('{%s}FreeBusyView' % MNS)]


class GetSearchableMailboxes(EWSService):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj900497(v=exchg.150).aspx
    SERVICE_NAME = 'GetSearchableMailboxes'
    element_container_name = '{%s}SearchableMailboxes' % MNS
    failed_mailboxes_container_name = '{%s}FailedMailboxes' % MNS

    def call(self, search_filter, expand_group_membership):
        if self.protocol.version.build < EXCHANGE_2013:
            raise NotImplementedError('%s is only supported for Exchange 2013 servers and later' % self.SERVICE_NAME)
        from .properties import SearchableMailbox, FailedMailbox
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
            if not isinstance(msg, ElementType):
                raise ValueError("'msg' %r must be an ElementType" % msg)
            for container_name in (self.element_container_name, self.failed_mailboxes_container_name):
                container_or_exc = self._get_element_container(message=msg, name=container_name)
                if isinstance(container_or_exc, ElementType):
                    for c in self._get_elements_in_container(container=container_or_exc):
                        yield c
                else:
                    yield container_or_exc
