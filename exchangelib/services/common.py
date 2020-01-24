import abc
from itertools import chain
import logging
import traceback

from .. import errors
from ..errors import EWSWarning, TransportError, SOAPError, ErrorTimeoutExpired, ErrorBatchProcessingStopped, \
    ErrorQuotaExceeded, ErrorCannotDeleteObject, ErrorCreateItemAccessDenied, ErrorFolderNotFound, \
    ErrorNonExistentMailbox, ErrorMailboxStoreUnavailable, ErrorImpersonateUserDenied, ErrorInternalServerError, \
    ErrorInternalServerTransientError, ErrorNoRespondingCASInDestinationSite, ErrorImpersonationFailed, \
    ErrorMailboxMoveInProgress, ErrorAccessDenied, ErrorConnectionFailed, RateLimitError, ErrorServerBusy, \
    ErrorTooManyObjectsOpened, ErrorInvalidLicense, ErrorInvalidSchemaVersionForMailboxVersion, \
    ErrorInvalidServerVersion, ErrorItemNotFound, ErrorADUnavailable, ErrorInvalidChangeKey, \
    ErrorItemSave, ErrorInvalidIdMalformed, ErrorMessageSizeExceeded, UnauthorizedError, \
    ErrorCannotDeleteTaskOccurrence, ErrorMimeContentConversionFailed, ErrorRecurrenceHasNoOccurrence, \
    ErrorNoPublicFolderReplicaAvailable, MalformedResponseError, ErrorExceededConnectionCount, \
    SessionPoolMinSizeReached, ErrorIncorrectSchemaVersion, ErrorInvalidRequest
from ..transport import wrap, extra_headers
from ..util import chunkify, create_element, add_xml_child, get_xml_attr, to_xml, post_ratelimited, \
    xml_to_str, set_xml_value, SOAPNS, TNS, MNS, ENS, ParseError

log = logging.getLogger(__name__)

CHUNK_SIZE = 100  # A default chunk size for all services


class EWSService(metaclass=abc.ABCMeta):
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
    # Controls whether the HTTP request should be streaming or fetch everything at once
    streaming = False

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
        while True:
            try:
                # Send the request, get the response and do basic sanity checking on the SOAP XML
                response = self._get_response_xml(payload=payload)
                # Read the XML and throw any general EWS error messages. Return a generator over the result elements
                return self._get_elements_in_response(response=response)
            except ErrorServerBusy as e:
                self._handle_backoff(e)
                continue
            except (
                    ErrorAccessDenied,
                    ErrorADUnavailable,
                    ErrorBatchProcessingStopped,
                    ErrorCannotDeleteObject,
                    ErrorConnectionFailed,
                    ErrorCreateItemAccessDenied,
                    ErrorExceededConnectionCount,
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
                    RateLimitError,
                    UnauthorizedError,
            ):
                # These are known and understood, and don't require a backtrace.
                raise
            except Exception:
                # This may run from a thread pool, which obfuscates the stack trace. Print trace immediately.
                account = self.account if isinstance(self, EWSAccountService) else None
                log.warning('EWS %s, account %s: Exception in _get_elements: %s', self.protocol.service_endpoint,
                            account, traceback.format_exc(20))
                raise

    def _get_response_xml(self, payload, **parse_opts):
        # Takes an XML tree and returns SOAP payload as an XML tree
        # Microsoft really doesn't want to make our lives easy. The server may report one version in our initial version
        # guessing tango, but then the server may decide that any arbitrary legacy backend server may actually process
        # the request for an account. Prepare to handle ErrorInvalidSchemaVersionForMailboxVersion errors and set the
        # server version per-account.
        from ..version import API_VERSIONS
        if isinstance(self, EWSAccountService):
            account = self.account
            version_hint = self.account.version
        else:
            account = None
            # We may be here due to version guessing in Protocol.version, so we can't use the Protocol.version property
            version_hint = self.protocol.config.version
        api_versions = [version_hint.api_version] + [v for v in API_VERSIONS if v != version_hint.api_version]
        for api_version in api_versions:
            log.debug('Trying API version %s for account %s', api_version, account)
            r, session = post_ratelimited(
                protocol=self.protocol,
                session=self.protocol.get_session(),
                url=self.protocol.service_endpoint,
                headers=extra_headers(account=account),
                data=wrap(content=payload, api_version=api_version, account=account),
                allow_redirects=False,
                stream=self.streaming,
            )
            if self.streaming:
                # Let 'requests' decode raw data automatically
                r.raw.decode_content = True
            else:
                # If we're streaming, we want to wait to release the session until we have consumed the stream.
                self.protocol.release_session(session)
            try:
                header, body = self._get_soap_parts(response=r, **parse_opts)
            except ParseError as e:
                raise SOAPError('Bad SOAP response: %s' % e)
            # The body may contain error messages from Exchange, but we still want to collect version info
            if header is not None:
                try:
                    self._update_api_version(version_hint=version_hint, api_version=api_version, header=header,
                                             **parse_opts)
                except TransportError as te:
                    log.debug('Failed to update version info (%s)', te)
            try:
                res = self._get_soap_messages(body=body, **parse_opts)
            except (ErrorInvalidServerVersion, ErrorIncorrectSchemaVersion, ErrorInvalidRequest):
                # The guessed server version is wrong. Try the next version
                log.debug('API version %s was invalid', api_version)
                continue
            except ErrorInvalidSchemaVersionForMailboxVersion:
                if not account:
                    # This should never happen for non-account services
                    raise ValueError("'account' should not be None")
                # The guessed server version is wrong for this account. Try the next version
                log.debug('API version %s was invalid for account %s', api_version, account)
                continue
            except ErrorExceededConnectionCount as e:
                # ErrorExceededConnectionCount indicates that the connecting user has too many open TCP connections to
                # the server. Decrease our session pool size.
                if self.streaming:
                    # In streaming mode, we haven't released the session yet, so we can't discard the session
                    raise
                else:
                    try:
                        self.protocol.decrease_poolsize()
                        continue
                    except SessionPoolMinSizeReached:
                        # We're already as low as we can go. Let the user handle this.
                        raise e
            except (ErrorTooManyObjectsOpened, ErrorTimeoutExpired) as e:
                # ErrorTooManyObjectsOpened means there are too many connections to the Exchange database. This is very
                # often a symptom of sending too many requests.
                #
                # ErrorTimeoutExpired can be caused by a busy server, or by overly large requests. Start by lowering the
                # session count. This is done by downstream code.
                if isinstance(e, ErrorTimeoutExpired) and self.protocol.session_pool_size <= 1:
                    # We're already as low as we can go, so downstream cannot limit the session count to put less load
                    # on the server. We don't have a way of lowering the page size of requests from
                    # this part of the code yet. Let the user handle this.
                    raise e

                # Re-raise as an ErrorServerBusy with a default delay of 5 minutes
                raise ErrorServerBusy(msg='Reraised from %s(%s)' % (e.__class__.__name__, e), back_off=300)
            finally:
                if self.streaming:
                    # TODO: We shouldn't release the session yet if we still haven't fully consumed the stream. It seems
                    # a Session can handle multiple unfinished streaming requests, though.
                    self.protocol.release_session(session)
            return res
        if account:
            raise ErrorInvalidSchemaVersionForMailboxVersion('Tried versions %s but all were invalid for account %s' %
                                                             (api_versions, account))
        raise ErrorInvalidServerVersion('Tried versions %s but all were invalid' % api_versions)

    def _handle_backoff(self, e):
        log.debug('Got ErrorServerBusy (back off %s seconds)', e.back_off)
        # ErrorServerBusy is very often a symptom of sending too many requests. Scale back if possible.
        try:
            self.protocol.decrease_poolsize()
        except SessionPoolMinSizeReached:
            pass
        if self.protocol.retry_policy.fail_fast:
            raise e
        self.protocol.retry_policy.back_off(e.back_off)
        # We'll warn about this later if we actually need to sleep

    def _update_api_version(self, version_hint, api_version, header, **parse_opts):
        from ..version import Version
        head_version = Version.from_soap_header(requested_api_version=api_version, header=header)
        if version_hint == head_version:
            # Nothing to do
            return
        log.debug('Found new version (%s -> %s)', version_hint, head_version)
        # The api_version that worked was different than our hint, or we never got a build version. Set new
        # version for account.
        if isinstance(self, EWSAccountService):
            self.account.version = head_version
        else:
            self.protocol.config.version = head_version

    @classmethod
    def _response_tag(cls):
        return '{%s}%sResponse' % (MNS, cls.SERVICE_NAME)

    @staticmethod
    def _response_messages_tag():
        return '{%s}ResponseMessages' % MNS

    @classmethod
    def _response_message_tag(cls):
        return '{%s}%sResponseMessage' % (MNS, cls.SERVICE_NAME)

    @classmethod
    def _get_soap_parts(cls, response, **parse_opts):
        root = to_xml(response.iter_content())
        header = root.find('{%s}Header' % SOAPNS)
        if header is None:
            # This is normal when the response contains SOAP-level errors
            log.debug('No header in XML response')
        body = root.find('{%s}Body' % SOAPNS)
        if body is None:
            raise MalformedResponseError('No Body element in SOAP response')
        return header, body

    @classmethod
    def _get_soap_messages(cls, body, **parse_opts):
        response = body.find(cls._response_tag())
        if response is None:
            fault = body.find('{%s}Fault' % SOAPNS)
            if fault is None:
                raise SOAPError('Unknown SOAP response: %s' % xml_to_str(body))
            cls._raise_soap_errors(fault=fault)  # Will throw SOAPError or custom EWS error
        response_messages = response.find(cls._response_messages_tag())
        if response_messages is None:
            # Result isn't delivered in a list of FooResponseMessages, but directly in the FooResponse. Consumers expect
            # a list, so return a list
            return [response]
        return response_messages.findall(cls._response_message_tag())

    @classmethod
    def _raise_soap_errors(cls, fault):
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
            elif code == 'ErrorSchemaValidation' and msg_xml is not None:
                violation = get_xml_attr(msg_xml, '{%s}Violation' % TNS)
                if violation is not None:
                    msg = '%s %s' % (msg, violation)
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

    def _get_element_container(self, message, response_message=None, name=None):
        if response_message is None:
            response_message = message
        # ResponseClass: See
        # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/finditemresponsemessage
        response_class = response_message.get('ResponseClass')
        # ResponseCode, MessageText: See
        # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/responsecode
        response_code = get_xml_attr(response_message, '{%s}ResponseCode' % MNS)
        msg_text = get_xml_attr(response_message, '{%s}MessageText' % MNS)
        msg_xml = response_message.find('{%s}MessageXml' % MNS)
        if response_class == 'Success' and response_code == 'NoError':
            if not name:
                return True
            container = message.find(name)
            if container is None:
                connection_status = get_xml_attr(response_message, '{%s}ConnectionStatus' % MNS)
                if self.streaming and connection_status == 'OK':
                    log.debug('Keep alive streaming message.')
                    return True
                else:
                    raise MalformedResponseError('No %s elements in ResponseMessage (%s)' % (name, xml_to_str(message)))
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
                    raise MalformedResponseError('No %s elements in ResponseMessage (%s)' % (name, xml_to_str(message)))
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
            # If this is an ErrorInternalServerError error, the xml may contain a more specific error code
            inner_code, inner_text = None, None
            for value_elem in msg_xml.findall('{%s}Value' % TNS):
                name = value_elem.get('Name')
                if name == 'InnerErrorResponseCode':
                    inner_code = value_elem.text
                elif name == 'InnerErrorMessageText':
                    inner_text = value_elem.text
            if inner_code:
                try:
                    # Raise the error as the inner error code
                    return vars(errors)[inner_code]('%s (raised from: %s(%r))' % (inner_text, code, text))
                except KeyError:
                    # Inner code is unknown to us. Just append to the original text
                    text += ' (inner error: %s(%r))' % (inner_code, inner_text)
        try:
            # Raise the error corresponding to the ResponseCode
            return vars(errors)[code](text)
        except KeyError:
            # Should not happen
            return TransportError('Unknown ResponseCode in ResponseMessage: %s (MessageText: %s, MessageXml: %s)' % (
                    code, text, msg_xml))

    def _get_elements_in_response(self, response):
        for msg in response:
            container_or_exc = self._get_element_container(message=msg, name=self.element_container_name)
            if isinstance(container_or_exc, (bool, Exception)):
                yield container_or_exc
            else:
                for c in self._get_elements_in_container(container=container_or_exc):
                    yield c

    @staticmethod
    def _get_elements_in_container(container):
        return [elem for elem in container]


class EWSAccountService(EWSService):

    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop('account')
        kwargs['protocol'] = self.account.protocol
        super().__init__(*args, **kwargs)


class EWSFolderService(EWSAccountService):

    def __init__(self, *args, **kwargs):
        self.folders = kwargs.pop('folders')
        if not self.folders:
            raise ValueError('"folders" must not be empty')
        super().__init__(*args, **kwargs)


class PagingEWSMixIn(EWSService):
    def _paged_call(self, payload_func, max_items, **kwargs):
        if isinstance(self, EWSAccountService):
            log_prefix = 'EWS %s, account %s, service %s' % (
                self.protocol.service_endpoint, self.account, self.SERVICE_NAME)
        else:
            log_prefix = 'EWS %s, service %s' % (self.protocol.service_endpoint, self.SERVICE_NAME)
        if isinstance(self, EWSFolderService):
            expected_message_count = len(self.folders)
        else:
            expected_message_count = 1
        paging_infos = [dict(item_count=0, next_offset=None) for _ in range(expected_message_count)]
        common_next_offset = kwargs['offset']
        total_item_count = 0
        while True:
            log.debug('%s: Getting items at offset %s (max_items %s)', log_prefix, common_next_offset, max_items)
            kwargs['offset'] = common_next_offset
            payload = payload_func(**kwargs)
            try:
                response = self._get_response_xml(payload=payload)
            except ErrorServerBusy as e:
                self._handle_backoff(e)
                continue
            # Collect a tuple of (rootfolder, next_offset) tuples
            parsed_pages = [self._get_page(message) for message in response]
            if len(parsed_pages) != expected_message_count:
                raise MalformedResponseError(
                    "Expected %s items in 'response', got %s" % (expected_message_count, len(parsed_pages))
                )
            for (rootfolder, next_offset), paging_info in zip(parsed_pages, paging_infos):
                paging_info['next_offset'] = next_offset
                if isinstance(rootfolder, Exception):
                    yield rootfolder
                    continue
                if rootfolder is not None:
                    container = rootfolder.find(self.element_container_name)
                    if container is None:
                        raise MalformedResponseError('No %s elements in ResponseMessage (%s)' % (
                            self.element_container_name, xml_to_str(rootfolder)))
                    for elem in self._get_elements_in_container(container=container):
                        if max_items and total_item_count >= max_items:
                            # No need to continue. Break out of elements loop
                            log.debug("'max_items' count reached (elements)")
                            break
                        paging_info['item_count'] += 1
                        total_item_count += 1
                        yield elem
                    if max_items and total_item_count >= max_items:
                        # No need to continue. Break out of inner loop
                        log.debug("'max_items' count reached (inner)")
                        break
                if not paging_info['next_offset']:
                    # Paging is done for this message
                    continue
                # Check sanity of paging offsets, but don't fail. When we are iterating huge collections that take a
                # long time to complete, the collection may change while we are iterating. This can affect the
                # 'next_offset' value and make it inconsistent with the number of already collected items.
                # We may have a mismatch if we stopped early due to reaching 'max_items'.
                if paging_info['next_offset'] != paging_info['item_count'] and (
                    not max_items or total_item_count < max_items
                ):
                    log.warning('Unexpected next offset: %s -> %s. Maybe the server-side collection has changed?'
                                % (paging_info['item_count'], paging_info['next_offset']))
            # Also break out of outer loop
            if max_items and total_item_count >= max_items:
                log.debug("'max_items' count reached (outer)")
                break
            next_offsets = {p['next_offset'] for p in paging_infos if p['next_offset'] is not None}
            if not next_offsets:
                # Paging is done for all messages
                break
            # We cannot guarantee that all messages that have a next_offset also have the *same* next_offset. This is
            # because the collections that we are iterating may change while iterating. We'll do our best but we cannot
            # guarantee 100% consistency when large collections are simultaneously being changed on the server.
            #
            # It's not possible to supply a per-folder offset when iterating multiple folders, so we'll just have to
            # choose something that is most likely to work. Select the lowest of all the values to at least make sure
            # we don't miss any items, although we may then get duplicates ¯\_(ツ)_/¯
            if len(next_offsets) > 1:
                log.warning('Inconsistent next_offset values: %r. Using lowest value', next_offsets)
            common_next_offset = min(next_offsets)

    def _get_page(self, message):
        rootfolder = self._get_element_container(message=message, name='{%s}RootFolder' % MNS)
        if isinstance(rootfolder, Exception):
            return rootfolder, None
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


class EWSPooledMixIn(EWSService):
    def _pool_requests(self, payload_func, items, **kwargs):
        log.debug('Processing items in chunks of %s', self.chunk_size)
        # Chop items list into suitable pieces and let worker threads chew on the work. The order of the output result
        # list must be the same as the input id list, so the caller knows which status message belongs to which ID.
        # Yield results as they become available.
        results = []
        n = 0
        for chunk in chunkify(items, self.chunk_size):
            n += 1
            log.debug('Starting %s._get_elements worker %s for %s items', self.__class__.__name__, n, len(chunk))
            results.append((n, self.protocol.thread_pool.apply_async(
                lambda c: self._get_elements(payload=payload_func(c, **kwargs)),
                (chunk,)
            )))

            # Results will be available before iteration has finished if 'items' is a slow generator. Return early
            while True:
                if not results:
                    break
                i, r = results[0]
                if not r.ready():
                    # First non-yielded result isn't ready yet. Yielding other ready results would mess up ordering
                    break
                log.debug('%s._get_elements result %s is ready early', self.__class__.__name__, i)
                for elem in r.get():
                    yield elem
                # Results object has been processed. Remove from list.
                del results[0]

        # Yield remaining results in order, as they become available
        for i, r in results:
            log.debug('Waiting for %s._get_elements result %s of %s', self.__class__.__name__, i, n)
            elems = r.get()
            log.debug('%s._get_elements result %s of %s is ready', self.__class__.__name__, i, n)
            for elem in elems:
                yield elem


def to_item_id(item, item_cls):
    # Coerce a tuple, dict or object to an 'item_cls' instance. Used to create [Parent][Item|Folder]Id instances from a
    # variety of input.
    if isinstance(item, item_cls):
        return item
    if isinstance(item, (tuple, list)):
        return item_cls(*item)
    if isinstance(item, dict):
        return item_cls(**item)
    return item_cls(item.id, item.changekey)


def create_shape_element(tag, shape, additional_fields, version):
    shape_elem = create_element(tag)
    add_xml_child(shape_elem, 't:BaseShape', shape)
    if additional_fields:
        additional_properties = create_element('t:AdditionalProperties')
        expanded_fields = chain(*(f.expand(version=version) for f in additional_fields))
        set_xml_value(additional_properties, sorted(expanded_fields, key=lambda f: f.path), version=version)
        shape_elem.append(additional_properties)
    return shape_elem


def create_folder_ids_element(tag, folders, version):
    from ..folders import BaseFolder, FolderId, DistinguishedFolderId
    folder_ids = create_element(tag)
    for folder in folders:
        log.debug('Collecting folder %s', folder)
        if not isinstance(folder, (BaseFolder, FolderId, DistinguishedFolderId)):
            folder = to_item_id(folder, FolderId)
        set_xml_value(folder_ids, folder, version=version)
    if not len(folder_ids):
        raise ValueError('"folders" must not be empty')
    return folder_ids


def create_item_ids_element(items, version):
    from ..properties import ItemId
    item_ids = create_element('m:ItemIds')
    for item in items:
        log.debug('Collecting item %s', item)
        set_xml_value(item_ids, to_item_id(item, ItemId), version=version)
    if not len(item_ids):
        raise ValueError('"items" must not be empty')
    return item_ids


def create_attachment_ids_element(items, version):
    from ..attachments import AttachmentId
    attachment_ids = create_element('m:AttachmentIds')
    for item in items:
        attachment_id = item if isinstance(item, AttachmentId) else AttachmentId(id=item)
        set_xml_value(attachment_ids, attachment_id, version=version)
    if not len(attachment_ids):
        raise ValueError('"items" must not be empty')
    return attachment_ids


def parse_folder_elem(elem, folder, account):
    from ..folders import BaseFolder, Folder, DistinguishedFolderId, RootOfHierarchy
    if isinstance(elem, Exception):
        return elem
    if isinstance(folder, RootOfHierarchy):
        f = folder.from_xml(elem=elem, account=folder.account)
    elif isinstance(folder, Folder):
        f = folder.from_xml_with_root(elem=elem, root=folder.root)
    elif isinstance(folder, DistinguishedFolderId):
        # We don't know the root, so assume account.root.
        for folder_cls in account.root.WELLKNOWN_FOLDERS:
            if folder_cls.DISTINGUISHED_FOLDER_ID == folder.id:
                break
        else:
            raise ValueError('Unknown distinguished folder ID: %s', folder.id)
        f = folder_cls.from_xml_with_root(elem=elem, root=account.root)
    else:
        # 'folder' is a generic FolderId instance. We don't know the root so assume account.root.
        f = Folder.from_xml_with_root(elem=elem, root=account.root)
    if isinstance(folder, DistinguishedFolderId):
        f.is_distinguished = True
    elif isinstance(folder, BaseFolder) and folder.is_distinguished:
        f.is_distinguished = True
    return f
