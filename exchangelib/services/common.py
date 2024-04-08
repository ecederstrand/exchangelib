import abc
import logging
from contextlib import suppress
from itertools import chain

from oauthlib.oauth2 import TokenExpiredError

from .. import errors
from ..attachments import AttachmentId
from ..credentials import IMPERSONATION, BaseOAuth2Credentials
from ..errors import (
    ErrorBatchProcessingStopped,
    ErrorCannotDeleteObject,
    ErrorCannotDeleteTaskOccurrence,
    ErrorCorruptData,
    ErrorExceededConnectionCount,
    ErrorIncorrectSchemaVersion,
    ErrorInternalServerTransientError,
    ErrorInvalidChangeKey,
    ErrorInvalidIdMalformed,
    ErrorInvalidRequest,
    ErrorInvalidSchemaVersionForMailboxVersion,
    ErrorInvalidServerVersion,
    ErrorItemCorrupt,
    ErrorItemNotFound,
    ErrorItemSave,
    ErrorMailRecipientNotFound,
    ErrorMessageSizeExceeded,
    ErrorMimeContentConversionFailed,
    ErrorRecurrenceHasNoOccurrence,
    ErrorServerBusy,
    ErrorTimeoutExpired,
    ErrorTooManyObjectsOpened,
    EWSWarning,
    InvalidTypeError,
    MalformedResponseError,
    SessionPoolMinSizeReached,
    SOAPError,
    TransportError,
)
from ..folders import ArchiveRoot, BaseFolder, Folder, PublicFoldersRoot, Root, RootOfHierarchy
from ..items import BaseItem
from ..properties import (
    BaseItemId,
    DistinguishedFolderId,
    ExceptionFieldURI,
    ExtendedFieldURI,
    FieldURI,
    FolderId,
    IndexedFieldURI,
    ItemId,
)
from ..transport import DEFAULT_ENCODING
from ..util import (
    ENS,
    MNS,
    SOAPNS,
    TNS,
    DummyResponse,
    ParseError,
    add_xml_child,
    chunkify,
    create_element,
    get_xml_attr,
    ns_translation,
    post_ratelimited,
    set_xml_value,
    to_xml,
    xml_to_str,
)
from ..version import SupportedVersionClassMixIn, Version

log = logging.getLogger(__name__)


class EWSService(SupportedVersionClassMixIn, metaclass=abc.ABCMeta):
    """Base class for all EWS services."""

    CHUNK_SIZE = 100  # A default chunk size for all services. This is the number of items we send in a single request

    SERVICE_NAME = None  # The name of the SOAP service
    element_container_name = None  # The name of the XML element wrapping the collection of returned items
    returns_elements = True  # If False, the service does not return response elements, just the ResponseCode status
    # Return exception instance instead of raising exceptions for the following errors when contained in an element
    ERRORS_TO_CATCH_IN_RESPONSE = (
        EWSWarning,
        ErrorCannotDeleteObject,
        ErrorInvalidChangeKey,
        ErrorItemNotFound,
        ErrorItemSave,
        ErrorInvalidIdMalformed,
        ErrorMessageSizeExceeded,
        ErrorCannotDeleteTaskOccurrence,
        ErrorMimeContentConversionFailed,
        ErrorRecurrenceHasNoOccurrence,
        ErrorCorruptData,
        ErrorItemCorrupt,
        ErrorMailRecipientNotFound,
    )
    # Similarly, define the warnings we want to return un-raised
    WARNINGS_TO_CATCH_IN_RESPONSE = ErrorBatchProcessingStopped
    # Define the warnings we want to ignore, to let response processing proceed
    WARNINGS_TO_IGNORE_IN_RESPONSE = ()
    # The exception type to raise when all attempted API versions failed
    NO_VALID_SERVER_VERSIONS = ErrorInvalidServerVersion

    NS_MAP = {k: v for k, v in ns_translation.items() if k in ("s", "m", "t")}

    def __init__(self, protocol, chunk_size=None, timeout=None):
        self.chunk_size = chunk_size or self.CHUNK_SIZE
        if not isinstance(self.chunk_size, int):
            raise InvalidTypeError("chunk_size", chunk_size, int)
        if self.chunk_size < 1:
            raise ValueError(f"'chunk_size' {self.chunk_size} must be a positive number")
        if self.supported_from and protocol.version.build < self.supported_from:
            raise NotImplementedError(
                f"Service {self.SERVICE_NAME!r} only supports server versions from {self.supported_from or '*'} to "
                f"{self.deprecated_from or '*'} (server has {protocol.version})"
            )
        self.protocol = protocol
        # Allow a service to override the default protocol timeout. Useful for streaming services
        self.timeout = timeout
        # Controls whether the HTTP request should be streaming or fetch everything at once
        self.streaming = False
        # Streaming connection variables
        self._streaming_session = None
        self._streaming_response = None

    def __del__(self):
        # pylint: disable=bare-except
        try:
            if self.streaming:
                # Make sure to clean up lingering resources
                self.stop_streaming()
        except Exception:  # nosec
            # __del__ should never fail
            pass

    # The following two methods are the minimum required to be implemented by subclasses, but the name and number of
    # kwargs differs between services. Therefore, we cannot make these methods abstract.

    # @abc.abstractmethod
    # def call(self, **kwargs):
    #     """Defines the arguments required by the service. Arguments are basic Python types or EWSElement objects.
    #     Returns either XML objects or EWSElement objects.
    #     """"
    #     pass

    # @abc.abstractmethod
    # def get_payload(self, **kwargs):
    #     """Using the arguments from .call(), return the payload expected by the service, as an XML object. The XML
    #     object should consist of a SERVICE_NAME element and everything within that.
    #     """
    #     pass

    def get(self, expect_result=True, **kwargs):
        """Like .call(), but expects exactly one result from the server, or zero when expect_result=False, or either
        zero or one when expect_result=None. Returns either one object or None.

        :param expect_result: None, True, or False
        :param kwargs: Same as arguments for .call()
        :return: Same as .call(), but returns either None or exactly one item
        """
        res = list(self.call(**kwargs))
        # Raise any errors
        for r in res:
            if isinstance(r, Exception):
                raise r
        if expect_result is None and not res:
            # Allow empty result
            return None
        if expect_result is False:
            if res:
                raise ValueError(f"Expected result length 0, but got {res}")
            return None
        if len(res) != 1:
            raise ValueError(f"Expected result length 1, but got {res}")
        return res[0]

    def parse(self, xml):
        """Used mostly for testing, when we want to parse static XML data."""
        resp = DummyResponse(content=xml, streaming=self.streaming)
        _, body = self._get_soap_parts(response=resp)
        return self._elems_to_objs(self._get_elements_in_response(response=self._get_soap_messages(body=body)))

    def wrap(self, content, api_version=None):
        """Generate the necessary boilerplate XML for a raw SOAP request. The XML is specific to the server version.
        ExchangeImpersonation allows to act as the user we want to impersonate.

        RequestServerVersion element on MSDN:
        https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/requestserverversion

        ExchangeImpersonation element on MSDN:
        https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/exchangeimpersonation

        TimeZoneContent element on MSDN:
        https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/timezonecontext

        :param content:
        :param api_version:
        """
        envelope = create_element("s:Envelope", nsmap=self.NS_MAP)
        header = create_element("s:Header")
        if api_version:
            request_server_version = create_element("t:RequestServerVersion", attrs=dict(Version=api_version))
            header.append(request_server_version)
        identity = self._account_to_impersonate
        if identity:
            add_xml_child(header, "t:ExchangeImpersonation", identity)
        timezone = self._timezone
        if timezone:
            timezone_context = create_element("t:TimeZoneContext")
            timezone_definition = create_element("t:TimeZoneDefinition", attrs=dict(Id=timezone.ms_id))
            timezone_context.append(timezone_definition)
            header.append(timezone_context)
        if len(header):
            envelope.append(header)
        body = create_element("s:Body")
        body.append(content)
        envelope.append(body)
        return xml_to_str(envelope, encoding=DEFAULT_ENCODING, xml_declaration=True)

    def _elems_to_objs(self, elems):
        """Takes a generator of XML elements and exceptions. Returns the equivalent Python objects (or exceptions)."""
        for elem in elems:
            # Allow None here. Some services don't return an ID if the target folder is outside the mailbox.
            if isinstance(elem, (Exception, type(None))):
                yield elem
                continue
            yield self._elem_to_obj(elem)

    def _elem_to_obj(self, elem):
        if not self.returns_elements:
            raise RuntimeError("Incorrect call to method when 'returns_elements' is False")
        raise NotImplementedError()

    @property
    def _version_hint(self):
        # We may be here due to version guessing in Protocol.version, so we can't use the self.protocol.version property
        return self.protocol.config.version

    @_version_hint.setter
    def _version_hint(self, value):
        self.protocol.config.version = value

    def _extra_headers(self):
        headers = {}
        identity = self._account_to_impersonate
        if identity and identity.primary_smtp_address:
            # See
            # https://blogs.msdn.microsoft.com/webdav_101/2015/05/11/best-practices-ews-authentication-and-access-issues/
            headers["X-AnchorMailbox"] = identity.primary_smtp_address
        return headers

    @property
    def _account_to_impersonate(self):
        if self.protocol and isinstance(self.protocol.credentials, BaseOAuth2Credentials):
            return self.protocol.credentials.identity
        return None

    @property
    def _timezone(self):
        return None

    def _response_generator(self, payload):
        """Send the payload to the server, and return the response.

        :param payload: payload as an XML object
        :return: the response, as XML objects
        """
        response = self._get_response_xml(payload=payload)
        return self._get_elements_in_response(response=response)

    def _chunked_get_elements(self, payload_func, items, **kwargs):
        """Yield elements in a response. Like ._get_elements(), but chop items into suitable chunks and send multiple
        requests.

        :param payload_func: A reference to .payload()
        :param items: An iterable of items (messages, folders, etc.) to process
        :param kwargs: Same as arguments for .call(), except for the 'items' argument
        :return: Same as ._get_elements()
        """
        # If the input for a service is a QuerySet, it can be difficult to remove exceptions before now
        filtered_items = filter(lambda item: not isinstance(item, Exception), items)
        for i, chunk in enumerate(chunkify(filtered_items, self.chunk_size), start=1):
            log.debug("Processing chunk %s containing %s items", i, len(chunk))
            yield from self._get_elements(payload=payload_func(chunk, **kwargs))

    def stop_streaming(self):
        if not self.streaming:
            raise RuntimeError("Attempt to stop a non-streaming service")
        if self._streaming_response:
            self._streaming_response.close()  # Release memory
            self._streaming_response = None
        if self._streaming_session:
            self.protocol.release_session(self._streaming_session)
            self._streaming_session = None

    def _get_elements(self, payload):
        """Send the payload to be sent and parsed. Handles and re-raise exceptions that are not meant to be returned
        to the caller as exception objects. Retry the request according to the retry policy.
        """
        wait = self.protocol.RETRY_WAIT
        while True:
            try:
                # Create a generator over the response elements so exceptions in response elements are also raised
                # here and can be handled.
                yield from self._response_generator(payload=payload)
                # TODO: Restore session pool size on succeeding request?
                return
            except TokenExpiredError:
                # Retry immediately
                continue
            except ErrorServerBusy as e:
                if not e.back_off:
                    e.back_off = wait
                self._handle_backoff(e)
            except ErrorExceededConnectionCount as e:
                # ErrorExceededConnectionCount indicates that the connecting user has too many open TCP connections to
                # the server. Decrease our session pool size and retry immediately.
                try:
                    self.protocol.decrease_poolsize()
                    continue
                except SessionPoolMinSizeReached:
                    # We're already as low as we can go. Let the user handle this.
                    raise e
            except ErrorTimeoutExpired as e:
                # ErrorTimeoutExpired can be caused by a busy server, or by an overly large request. If it's the latter,
                # we don't want to continue hammering the server with this request indefinitely. Instead, lower the
                # connection count, if possible, and retry the request.
                if self.protocol.session_pool_size <= 1:
                    # We're already as low as we can go. We can no longer use the session count to put less load
                    # on the server. If this is a chunked request we could lower the chunk size, but we don't have a
                    # way of doing that from this part of the code yet. Let the user handle this.
                    raise e
                self._handle_backoff(ErrorServerBusy(f"Reraised from {e.__class__.__name__}({e})", back_off=wait))
            except (ErrorTooManyObjectsOpened, ErrorInternalServerTransientError) as e:
                # ErrorTooManyObjectsOpened means there are too many connections to the Exchange database. This is very
                # often a symptom of sending too many requests.
                self._handle_backoff(ErrorServerBusy(f"Reraised from {e.__class__.__name__}({e})", back_off=wait))
            finally:
                wait *= 2  # Increase delay for every retry
                if self.streaming:
                    self.stop_streaming()

    def _handle_response_cookies(self, session):
        pass

    def _get_response(self, payload, api_version):
        """Send the actual HTTP request and get the response."""
        if self.streaming:
            # Make sure to clean up lingering resources
            self.stop_streaming()
        session = self.protocol.get_session()
        r, session = post_ratelimited(
            protocol=self.protocol,
            session=session,
            url=self.protocol.service_endpoint,
            headers=self._extra_headers(),
            data=self.wrap(
                content=payload,
                api_version=api_version,
            ),
            stream=self.streaming,
            timeout=self.timeout or self.protocol.TIMEOUT,
        )
        self._handle_response_cookies(session)
        if self.streaming:
            # We con only release the session when we have fully consumed the response. Save session and response
            # objects for later.
            self._streaming_session, self._streaming_response = session, r
        else:
            self.protocol.release_session(session)
        return r

    @classmethod
    def supported_api_versions(cls):
        """Return API versions supported by the service, sorted from newest to oldest"""
        return sorted({v.api_version for v in Version.all_versions() if cls.supports_version(v)}, reverse=True)

    def _api_versions_to_try(self):
        # Put the hint first in the list, and then all other versions except the hint, from newest to oldest
        return (self._version_hint.api_version,) + tuple(
            v for v in self.supported_api_versions() if v != self._version_hint.api_version
        )

    def _get_response_xml(self, payload, **parse_opts):
        """Send the payload to the server and return relevant elements from the result. Several things happen here:
          * The payload is wrapped in SOAP headers and sent to the server
          * The Exchange API version is negotiated and stored in the protocol object
          * Connection errors are handled and possibly reraised as ErrorServerBusy
          * SOAP errors are raised
          * EWS errors are raised, or passed on to the caller

        :param payload: The request payload, as an XML object
        :return: A generator of XML objects or None if the service does not return a result
        """
        # Microsoft really doesn't want to make our lives easy. The server may report one version in our initial version
        # guessing tango, but then the server may decide that any arbitrary legacy backend server may actually process
        # the request for an account. Prepare to handle version-related errors and set the server version per-account.
        log.debug("Calling service %s", self.SERVICE_NAME)
        for api_version in self._api_versions_to_try():
            log.debug("Trying API version %s", api_version)
            r = self._get_response(payload=payload, api_version=api_version)
            if self.streaming:
                # Let 'requests' decode raw data automatically
                r.raw.decode_content = True
            try:
                header, body = self._get_soap_parts(response=r, **parse_opts)
            except Exception:
                r.close()  # Release memory
                raise
            # The body may contain error messages from Exchange, but we still want to collect version info
            if header is not None:
                self._update_api_version(api_version=api_version, header=header, **parse_opts)
            try:
                return self._get_soap_messages(body=body, **parse_opts)
            except (
                ErrorInvalidServerVersion,
                ErrorIncorrectSchemaVersion,
                ErrorInvalidRequest,
                ErrorInvalidSchemaVersionForMailboxVersion,
            ):
                # The guessed server version is wrong. Try the next version
                log.debug("API version %s was invalid", api_version)
                continue
            finally:
                if not self.streaming:
                    # In streaming mode, we may not have accessed the raw stream yet. Caller must handle this.
                    r.close()  # Release memory

        raise self.NO_VALID_SERVER_VERSIONS(f"Tried versions {self._api_versions_to_try()} but all were invalid")

    def _handle_backoff(self, e):
        """Take a request from the server to back off and checks the retry policy for what to do. Re-raise the
        exception if conditions are not met.

        :param e: An ErrorServerBusy instance
        :return:
        """
        log.debug("Got ErrorServerBusy (back off %s seconds)", e.back_off)
        # ErrorServerBusy is very often a symptom of sending too many requests. Scale back connections if possible.
        with suppress(SessionPoolMinSizeReached):
            self.protocol.decrease_poolsize()
        if self.protocol.retry_policy.fail_fast:
            raise e
        self.protocol.retry_policy.back_off(e.back_off)
        # We'll warn about this later if we actually need to sleep

    def _update_api_version(self, api_version, header, **parse_opts):
        """Parse the server version contained in SOAP headers and update the version hint stored by the caller, if
        necessary.
        """
        try:
            head_version = Version.from_soap_header(requested_api_version=api_version, header=header)
        except TransportError as te:
            log.debug("Failed to update version info (%s)", te)
            return
        if self._version_hint == head_version:
            # Nothing to do
            return
        log.debug("Found new version (%s -> %s)", self._version_hint, head_version)
        # The api_version that worked was different from our hint, or we never got a build version. Store the working
        # version.
        self._version_hint = head_version

    @classmethod
    def _response_tag(cls):
        """Return the name of the element containing the service response."""
        return f"{{{MNS}}}{cls.SERVICE_NAME}Response"

    @staticmethod
    def _response_messages_tag():
        """Return the name of the element containing service response messages."""
        return f"{{{MNS}}}ResponseMessages"

    @classmethod
    def _response_message_tag(cls):
        """Return the name of the element of a single response message."""
        return f"{{{MNS}}}{cls.SERVICE_NAME}ResponseMessage"

    @classmethod
    def _get_soap_parts(cls, response, **parse_opts):
        """Split the SOAP response into its headers and body elements."""
        try:
            root = to_xml(response.iter_content())
        except ParseError as e:
            raise SOAPError(f"Bad SOAP response: {e}")
        header = root.find(f"{{{SOAPNS}}}Header")
        if header is None:
            # This is normal when the response contains SOAP-level errors
            log.debug("No header in XML response")
        body = root.find(f"{{{SOAPNS}}}Body")
        if body is None:
            raise MalformedResponseError("No Body element in SOAP response")
        return header, body

    def _get_soap_messages(self, body, **parse_opts):
        """Return the elements in the response containing the response messages. Raises any SOAP exceptions."""
        response = body.find(self._response_tag())
        if response is None:
            fault = body.find(f"{{{SOAPNS}}}Fault")
            if fault is None:
                raise SOAPError(f"Unknown SOAP response (expected {self._response_tag()} or Fault): {xml_to_str(body)}")
            self._raise_soap_errors(fault=fault)  # Will throw SOAPError or custom EWS error
        response_messages = response.find(self._response_messages_tag())
        if response_messages is None:
            # Result isn't delivered in a list of FooResponseMessages, but directly in the FooResponse. Consumers expect
            # a list, so return a list
            return [response]
        return response_messages.findall(self._response_message_tag())

    @classmethod
    def _raise_soap_errors(cls, fault):
        """Parse error messages contained in SOAP headers and raise as exceptions defined in this package."""
        # Fault: See http://www.w3.org/TR/2000/NOTE-SOAP-20000508/#_Toc478383507
        fault_code = get_xml_attr(fault, "faultcode")
        fault_string = get_xml_attr(fault, "faultstring")
        fault_actor = get_xml_attr(fault, "faultactor")
        detail = fault.find("detail")
        if detail is not None:
            code = get_xml_attr(detail, f"{{{ENS}}}ResponseCode")
            if code:
                code = code.strip()
            msg = get_xml_attr(detail, f"{{{ENS}}}Message")
            if msg:
                msg = msg.strip()
            msg_xml = detail.find(f"{{{TNS}}}MessageXml")  # Crazy. Here, it's in the TNS namespace
            if code == "ErrorServerBusy":
                back_off = None
                with suppress(TypeError, AttributeError):
                    value = msg_xml.find(f"{{{TNS}}}Value")
                    if value.get("Name") == "BackOffMilliseconds":
                        back_off = int(value.text) / 1000.0  # Convert to seconds
                raise ErrorServerBusy(msg, back_off=back_off)
            if code == "ErrorSchemaValidation" and msg_xml is not None:
                line_number = get_xml_attr(msg_xml, f"{{{TNS}}}LineNumber")
                line_position = get_xml_attr(msg_xml, f"{{{TNS}}}LinePosition")
                violation = get_xml_attr(msg_xml, f"{{{TNS}}}Violation")
                if violation:
                    msg = f"{msg} {violation}"
                if line_number or line_position:
                    msg = f"{msg} (line: {line_number} position: {line_position})"
            try:
                raise vars(errors)[code](msg)
            except KeyError:
                detail = f"{cls.SERVICE_NAME}: code: {code} msg: {msg} ({xml_to_str(detail)})"
        with suppress(KeyError):
            raise vars(errors)[fault_code](fault_string)
        raise SOAPError(f"SOAP error code: {fault_code} string: {fault_string} actor: {fault_actor} detail: {detail}")

    def _get_element_container(self, message, name=None):
        """Return the XML element in a response element that contains the elements we want the service to return. For
        example, in a GetFolder response, 'message' is the GetFolderResponseMessage element, and we return the 'Folders'
        element:

        <m:GetFolderResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:Folders>
            <t:Folder>
              <t:FolderId Id="AQApA=" ChangeKey="AQAAAB" />
              [...]
            </t:Folder>
          </m:Folders>
        </m:GetFolderResponseMessage>

        Some service responses don't have a containing element for the returned elements ('name' is None). In
        that case, we return the 'SomeServiceResponseMessage' element.

        If the response contains a warning or an error message, we raise the relevant exception, unless the error class
        is contained in WARNINGS_TO_CATCH_IN_RESPONSE or ERRORS_TO_CATCH_IN_RESPONSE, in which case we return the
        exception instance.
        """
        # ResponseClass is an XML attribute of various SomeServiceResponseMessage elements: Possible values are:
        # Success, Warning, Error. See e.g.
        # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/finditemresponsemessage
        response_class = message.get("ResponseClass")
        # ResponseCode, MessageText: See
        # https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/responsecode
        response_code = get_xml_attr(message, f"{{{MNS}}}ResponseCode")
        if response_class == "Success" and response_code == "NoError":
            if not name:
                return message
            container = message.find(name)
            if container is None:
                raise MalformedResponseError(f"No {name} elements in ResponseMessage ({xml_to_str(message)})")
            return container
        if response_code == "NoError":
            return True
        # Raise any non-acceptable errors in the container, or return the container or the acceptable exception instance
        msg_text = get_xml_attr(message, f"{{{MNS}}}MessageText")
        msg_xml = message.find(f"{{{MNS}}}MessageXml")
        if response_class == "Warning":
            try:
                raise self._get_exception(code=response_code, text=msg_text, msg_xml=msg_xml)
            except self.WARNINGS_TO_CATCH_IN_RESPONSE as e:
                return e
            except self.WARNINGS_TO_IGNORE_IN_RESPONSE as e:
                log.warning(str(e))
                container = message.find(name)
                if container is None:
                    raise MalformedResponseError(f"No {name} elements in ResponseMessage ({xml_to_str(message)})")
                return container
        # response_class == 'Error', or 'Success' and not 'NoError'
        try:
            raise self._get_exception(code=response_code, text=msg_text, msg_xml=msg_xml)
        except self.ERRORS_TO_CATCH_IN_RESPONSE as e:
            return e

    @staticmethod
    def _get_exception(code, text, msg_xml):
        """Parse error messages contained in EWS responses and raise as exceptions defined in this package."""
        if not code:
            return TransportError(f"Empty ResponseCode in ResponseMessage (MessageText: {text}, MessageXml: {msg_xml})")
        if msg_xml is not None:
            # If this is an ErrorInvalidPropertyRequest error, the xml may contain a specific FieldURI
            for elem_cls in (FieldURI, IndexedFieldURI, ExtendedFieldURI, ExceptionFieldURI):
                elem = msg_xml.find(elem_cls.response_tag())
                if elem is not None:
                    field_uri = elem_cls.from_xml(elem, account=None)
                    text += f" (field: {field_uri})"
                    break

            # If this is an ErrorInvalidValueForProperty error, the xml may contain the name and value of the property
            if code == "ErrorInvalidValueForProperty":
                msg_parts = {}
                for elem in msg_xml.findall(f"{{{TNS}}}Value"):
                    key, val = elem.get("Name"), elem.text
                    if key:
                        msg_parts[key] = val
                if msg_parts:
                    text += f" ({', '.join(f'{k}: {v}' for k, v in msg_parts.items())})"

            # If this is an ErrorInternalServerError error, the xml may contain a more specific error code
            inner_code, inner_text = None, None
            for value_elem in msg_xml.findall(f"{{{TNS}}}Value"):
                name = value_elem.get("Name")
                if name == "InnerErrorResponseCode":
                    inner_code = value_elem.text
                elif name == "InnerErrorMessageText":
                    inner_text = value_elem.text
            if inner_code:
                try:
                    # Raise the error as the inner error code
                    return vars(errors)[inner_code](f"{inner_text} (raised from: {code}({text!r}))")
                except KeyError:
                    # Inner code is unknown to us. Just append to the original text
                    text += f" (inner error: {inner_code}({inner_text!r}))"
        try:
            # Raise the error corresponding to the ResponseCode
            return vars(errors)[code](text)
        except KeyError:
            # Should not happen
            return TransportError(
                f"Unknown ResponseCode in ResponseMessage: {code} (MessageText: {text}, MessageXml: {msg_xml})"
            )

    def _get_elements_in_response(self, response):
        """Take a list of 'SomeServiceResponseMessage' elements and return the elements in each response message that
        we want the service to return. With e.g. 'CreateItem', we get a list of 'CreateItemResponseMessage' elements
        and return the 'Message' elements.

        <m:CreateItemResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:Items>
            <t:Message>
              <t:ItemId Id="AQApA=" ChangeKey="AQAAAB"/>
            </t:Message>
          </m:Items>
        </m:CreateItemResponseMessage>
        <m:CreateItemResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:Items>
            <t:Message>
              <t:ItemId Id="AQApB=" ChangeKey="AQAAAC"/>
            </t:Message>
          </m:Items>
        </m:CreateItemResponseMessage>

        :param response: a list of 'SomeServiceResponseMessage' XML objects
        :return: a generator of items as returned by '_get_elements_in_container()
        """
        for msg in response:
            container_or_exc = self._get_element_container(message=msg, name=self.element_container_name)
            if isinstance(container_or_exc, (bool, Exception)):
                yield container_or_exc
            else:
                for c in self._get_elements_in_container(container=container_or_exc):
                    yield c

    @classmethod
    def _get_elements_in_container(cls, container):
        """Return a list of response elements from an XML response element container. With e.g.
        'CreateItem', 'Items' is the container element, and we return the 'Message' child elements:

          <m:Items>
            <t:Message>
              <t:ItemId Id="AQApA=" ChangeKey="AQAAAB"/>
            </t:Message>
          </m:Items>

        If the service does not return response elements, return True to indicate the status. Errors have already been
        raised.
        """
        if cls.returns_elements:
            return list(container)
        return [True]


class EWSAccountService(EWSService, metaclass=abc.ABCMeta):
    """Base class for services that act on items concerning a single Mailbox on the server."""

    NO_VALID_SERVER_VERSIONS = ErrorInvalidSchemaVersionForMailboxVersion
    # Marks services that need affinity to the backend server
    prefer_affinity = False

    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop("account")
        kwargs["protocol"] = self.account.protocol
        super().__init__(*args, **kwargs)

    @property
    def _version_hint(self):
        return self.account.version

    @_version_hint.setter
    def _version_hint(self, value):
        self.account.version = value

    def _handle_response_cookies(self, session):
        super()._handle_response_cookies(session=session)

        # See self._extra_headers() for documentation on affinity
        if self.prefer_affinity:
            for cookie in session.cookies:
                if cookie.name == "X-BackEndOverrideCookie":
                    self.account.affinity_cookie = cookie.value
                    break

    def _extra_headers(self):
        headers = super()._extra_headers()
        # See
        # https://blogs.msdn.microsoft.com/webdav_101/2015/05/11/best-practices-ews-authentication-and-access-issues/
        headers["X-AnchorMailbox"] = self.account.primary_smtp_address

        # See
        # https://docs.microsoft.com/en-us/exchange/client-developer/exchange-web-services/how-to-maintain-affinity-between-group-of-subscriptions-and-mailbox-server
        if self.prefer_affinity:
            headers["X-PreferServerAffinity"] = "True"
            if self.account.affinity_cookie:
                headers["X-BackEndOverrideCookie"] = self.account.affinity_cookie
        return headers

    @property
    def _account_to_impersonate(self):
        if self.account.access_type == IMPERSONATION:
            return self.account.identity
        return super()._account_to_impersonate

    @property
    def _timezone(self):
        return self.account.default_timezone


class EWSPagingService(EWSAccountService):
    PAGE_SIZE = 100  # A default page size for all paging services. This is the number of items we request per page

    paging_container_name = None  # The name of the element that contains paging information and the paged results

    def __init__(self, *args, **kwargs):
        self.page_size = kwargs.pop("page_size", None) or self.PAGE_SIZE
        if not isinstance(self.page_size, int):
            raise InvalidTypeError("page_size", self.page_size, int)
        if self.page_size < 1:
            raise ValueError(f"'page_size' {self.page_size} must be a positive number")
        super().__init__(*args, **kwargs)

    def _response_generator(self, payload):
        """Send the payload to the server, and return the response.

        :param payload: payload as an XML object
        :return: the response, as XML objects
        """
        response = self._get_response_xml(payload=payload)
        return (self._get_page(message) for message in response)

    def _paged_call(self, payload_func, max_items, folders, **kwargs):
        """Call a service that supports paging requests. Return a generator over all response items. Keeps track of
        all paging-related counters.
        """
        paging_infos = {f: dict(item_count=0, next_offset=None) for f in folders}
        common_next_offset = kwargs["offset"]
        total_item_count = 0
        while True:
            if not paging_infos:
                # Paging is done for all folders
                break
            log.debug("Getting page at offset %s (max_items %s)", common_next_offset, max_items)
            kwargs["offset"] = common_next_offset
            kwargs["folders"] = paging_infos.keys()  # Only request the paging of the remaining folders.
            pages = self._get_pages(payload_func, kwargs, len(paging_infos))
            for (page, next_offset), (f, paging_info) in zip(pages, list(paging_infos.items())):
                paging_info["next_offset"] = next_offset
                if isinstance(page, Exception):
                    # Assume this folder no longer works. Don't attempt to page it again.
                    log.debug("Exception occurred for folder %s. Removing.", f)
                    del paging_infos[f]
                    yield page
                    continue
                if page is not None:
                    for elem in self._get_elems_from_page(page, max_items, total_item_count):
                        paging_info["item_count"] += 1
                        total_item_count += 1
                        yield elem
                    if max_items and total_item_count >= max_items:
                        # No need to continue. Break out of inner loop
                        log.debug("'max_items' count reached (inner)")
                        break
                if not paging_info["next_offset"]:
                    # Paging is done for this folder. Don't attempt to page it again.
                    log.debug("Paging has completed for folder %s. Removing.", f)
                    del paging_infos[f]
                    continue
                log.debug("Folder %s still has items", f)
                # Check sanity of paging offsets, but don't fail. When we are iterating huge collections that take a
                # long time to complete, the collection may change while we are iterating. This can affect the
                # 'next_offset' value and make it inconsistent with the number of already collected items.
                # We may have a mismatch if we stopped early due to reaching 'max_items'.
                if paging_info["next_offset"] != paging_info["item_count"] and (
                    not max_items or total_item_count < max_items
                ):
                    log.warning(
                        "Unexpected next offset: %s -> %s. Maybe the server-side collection has changed?",
                        paging_info["item_count"],
                        paging_info["next_offset"],
                    )
            # Also break out of outer loop
            if max_items and total_item_count >= max_items:
                log.debug("'max_items' count reached (outer)")
                break
            common_next_offset = self._get_next_offset(paging_infos.values())
            if common_next_offset is None:
                # Paging is done for all folders
                break

    @staticmethod
    def _get_paging_values(elem):
        """Read paging information from the paging container element."""
        offset_attr = elem.get("IndexedPagingOffset")
        next_offset = None if offset_attr is None else int(offset_attr)
        item_count = int(elem.get("TotalItemsInView"))
        is_last_page = elem.get("IncludesLastItemInRange").lower() in ("true", "0")
        log.debug("Got page with offset %s, item_count %s, last_page %s", next_offset, item_count, is_last_page)
        # Clean up contradictory paging values
        if next_offset is None and not is_last_page:
            log.debug("Not last page in range, but server didn't send a page offset. Assuming first page")
            next_offset = 1
        if next_offset is not None and is_last_page:
            if next_offset != item_count:
                log.debug("Last page in range, but we still got an offset. Assuming paging has completed")
            next_offset = None
        if not item_count and not is_last_page:
            log.debug("Not last page in range, but also no items left. Assuming paging has completed")
            next_offset = None
        if item_count and next_offset == 0:
            log.debug("Non-zero offset, but also no items left. Assuming paging has completed")
            next_offset = None
        return item_count, next_offset

    def _get_page(self, message):
        """Get a single page from a request message, and return the container and next offset."""
        paging_elem = self._get_element_container(message=message, name=self.paging_container_name)
        if isinstance(paging_elem, Exception):
            return paging_elem, None
        item_count, next_offset = self._get_paging_values(paging_elem)
        if not item_count:
            paging_elem = None
        return paging_elem, next_offset

    def _get_elems_from_page(self, elem, max_items, total_item_count):
        container = elem.find(self.element_container_name)
        if container is None:
            raise MalformedResponseError(
                f"No {self.element_container_name} elements in ResponseMessage ({xml_to_str(elem)})"
            )
        for e in self._get_elements_in_container(container=container):
            if max_items and total_item_count >= max_items:
                # No need to continue. Break out of elements loop
                log.debug("'max_items' count reached (elements)")
                break
            yield e

    def _get_pages(self, payload_func, kwargs, expected_message_count):
        """Request a page, or a list of pages if multiple collections are pages in a single request. Return each
        page.
        """
        payload = payload_func(**kwargs)
        page_elems = list(self._get_elements(payload=payload))
        if len(page_elems) != expected_message_count:
            raise MalformedResponseError(
                f"Expected {expected_message_count} items in 'response', got {len(page_elems)}"
            )
        return page_elems

    @staticmethod
    def _get_next_offset(paging_infos):
        next_offsets = {p["next_offset"] for p in paging_infos if p["next_offset"] is not None}
        if not next_offsets:
            # Paging is done for all messages
            return None
        # We cannot guarantee that all messages that have a next_offset also have the *same* next_offset. This is
        # because the collections that we are iterating may change while iterating. We'll do our best, but we cannot
        # guarantee 100% consistency when large collections are simultaneously being changed on the server.
        #
        # It's not possible to supply a per-folder offset when iterating multiple folders, so we'll just have to
        # choose something that is most likely to work. Select the lowest of all the values to at least make sure
        # we don't miss any items, although we may then get duplicates ¯\_(ツ)_/¯
        if len(next_offsets) > 1:
            log.warning("Inconsistent next_offset values: %r. Using lowest value", next_offsets)
        return min(next_offsets)


def to_item_id(item, item_cls):
    # Coerce a tuple, dict or object to an 'item_cls' instance. Used to create [Parent][Item|Folder]Id instances from a
    # variety of input.
    if isinstance(item, (BaseItemId, AttachmentId)):
        # Allow any BaseItemId subclass to pass unaltered
        return item
    if isinstance(item, (BaseFolder, BaseItem)):
        return item.to_id()
    if isinstance(item, (str, tuple, list)):
        return item_cls(*item)
    return item_cls(item.id, item.changekey)


def shape_element(tag, shape, additional_fields, version):
    shape_elem = create_element(tag)
    add_xml_child(shape_elem, "t:BaseShape", shape)
    if additional_fields:
        additional_properties = create_element("t:AdditionalProperties")
        expanded_fields = chain(*(f.expand(version=version) for f in additional_fields))
        # 'path' is insufficient to consistently sort additional properties. For example, we have both
        # 'contacts:Companies' and 'task:Companies' with path 'companies'. Sort by both 'field_uri' and 'path'.
        # Extended properties do not have a 'field_uri' value.
        set_xml_value(
            additional_properties,
            sorted(expanded_fields, key=lambda f: (getattr(f.field, "field_uri", ""), f.path)),
            version=version,
        )
        shape_elem.append(additional_properties)
    return shape_elem


def _ids_element(items, item_cls, version, tag):
    item_ids = create_element(tag)
    for item in items:
        set_xml_value(item_ids, to_item_id(item, item_cls), version=version)
    return item_ids


def folder_ids_element(folders, version, tag="m:FolderIds"):
    return _ids_element(folders, FolderId, version, tag)


def item_ids_element(items, version, tag="m:ItemIds"):
    return _ids_element(items, ItemId, version, tag)


def attachment_ids_element(items, version, tag="m:AttachmentIds"):
    return _ids_element(items, AttachmentId, version, tag)


def parse_folder_elem(elem, folder, account):
    if isinstance(folder, RootOfHierarchy):
        f = folder.from_xml(elem=elem, account=folder.account)
    elif isinstance(folder, Folder):
        f = folder.from_xml_with_root(elem=elem, root=folder.root)
    elif isinstance(folder, DistinguishedFolderId):
        # We don't know the root or even account, but we need to attach the folder to something if we want to make
        # future requests with this folder. Use 'account' but make sure to always use the distinguished folder ID going
        # forward, instead of referencing anything connected to 'account'.
        roots = (Root, ArchiveRoot, PublicFoldersRoot)
        for cls in roots + tuple(chain(*(r.WELLKNOWN_FOLDERS for r in roots))):
            if cls.DISTINGUISHED_FOLDER_ID == folder.id:
                folder_cls = cls
                break
        else:
            raise ValueError(f"Unknown distinguished folder ID: {folder.id}")
        if folder_cls in roots:
            f = folder_cls.from_xml(elem=elem, account=account)
        else:
            f = folder_cls.from_xml_with_root(elem=elem, root=account.root)
    else:
        # 'folder' is a generic FolderId instance. We don't know the root so assume account.root.
        f = Folder.from_xml_with_root(elem=elem, root=account.root)
    return f
