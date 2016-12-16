# coding=utf-8
"""
Stores errors specific to exchangelib, and mirrors all the possible errors that EWS can return.
"""
from __future__ import unicode_literals

from future.moves.urllib.parse import urlparse
from future.utils import python_2_unicode_compatible
from six import text_type


@python_2_unicode_compatible
class EWSError(Exception):
    """
    Global error type within this module.

    """

    def __init__(self, value):
        super(EWSError, self).__init__(value)
        self.value = value

    def __str__(self):
        return text_type(self.value)


# Warnings
class EWSWarning(EWSError):
    pass


# Misc errors
class TransportError(EWSError):
    pass


class RateLimitError(TransportError):
    pass


class SOAPError(TransportError):
    pass


class UnauthorizedError(EWSError):
    pass


@python_2_unicode_compatible
class RedirectError(TransportError):
    def __init__(self, url):
        parsed_url = urlparse(url)
        self.url = url
        self.server = parsed_url.hostname.lower()
        self.has_ssl = parsed_url.scheme == 'https'
        super(RedirectError, self).__init__(text_type(self))

    def __str__(self):
        return 'We were redirected to %s' % self.url


class RelativeRedirect(TransportError):
    pass


class AutoDiscoverError(TransportError):
    pass


class AutoDiscoverFailed(AutoDiscoverError):
    pass


class AutoDiscoverCircularRedirect(AutoDiscoverError):
    pass


@python_2_unicode_compatible
class AutoDiscoverRedirect(AutoDiscoverError):
    def __init__(self, redirect_email):
        self.redirect_email = redirect_email
        super(AutoDiscoverRedirect, self).__init__(text_type(self))

    def __str__(self):
        return 'AutoDiscover redirects to %s' % self.redirect_email


class ResponseMessageError(TransportError):
    pass


# Somewhat-authoritative list of possible response message error types from EWS. See full list at
# https://msdn.microsoft.com/en-us/library/office/aa580757(v=exchg.150).aspx
#
class ErrorAccessDenied(ResponseMessageError): pass
class ErrorAccessModeSpecified(ResponseMessageError): pass
class ErrorAccountDisabled(ResponseMessageError): pass
class ErrorAddDelegatesFailed(ResponseMessageError): pass
class ErrorAddressSpaceNotFound(ResponseMessageError): pass
class ErrorADOperation(ResponseMessageError): pass
class ErrorADSessionFilter(ResponseMessageError): pass
class ErrorADUnavailable(ResponseMessageError): pass
class ErrorAffectedTaskOccurrencesRequired(ResponseMessageError): pass
class ErrorApplyConversationActionFailed(ResponseMessageError): pass
class ErrorAttachmentSizeLimitExceeded(ResponseMessageError): pass
class ErrorAutoDiscoverFailed(ResponseMessageError): pass
class ErrorAvailabilityConfigNotFound(ResponseMessageError): pass
class ErrorBatchProcessingStopped(ResponseMessageError): pass
class ErrorCalendarCannotMoveOrCopyOccurrence(ResponseMessageError): pass
class ErrorCalendarCannotUpdateDeletedItem(ResponseMessageError): pass
class ErrorCalendarCannotUseIdForOccurrenceId(ResponseMessageError): pass
class ErrorCalendarCannotUseIdForRecurringMasterId(ResponseMessageError): pass
class ErrorCalendarDurationIsTooLong(ResponseMessageError): pass
class ErrorCalendarEndDateIsEarlierThanStartDate(ResponseMessageError): pass
class ErrorCalendarFolderIsInvalidForCalendarView(ResponseMessageError): pass
class ErrorCalendarInvalidAttributeValue(ResponseMessageError): pass
class ErrorCalendarInvalidDayForTimeChangePattern(ResponseMessageError): pass
class ErrorCalendarInvalidDayForWeeklyRecurrence(ResponseMessageError): pass
class ErrorCalendarInvalidPropertyState(ResponseMessageError): pass
class ErrorCalendarInvalidPropertyValue(ResponseMessageError): pass
class ErrorCalendarInvalidRecurrence(ResponseMessageError): pass
class ErrorCalendarInvalidTimeZone(ResponseMessageError): pass
class ErrorCalendarIsCancelledForAccept(ResponseMessageError): pass
class ErrorCalendarIsCancelledForDecline(ResponseMessageError): pass
class ErrorCalendarIsCancelledForRemove(ResponseMessageError): pass
class ErrorCalendarIsCancelledForTentative(ResponseMessageError): pass
class ErrorCalendarIsDelegatedForAccept(ResponseMessageError): pass
class ErrorCalendarIsDelegatedForDecline(ResponseMessageError): pass
class ErrorCalendarIsDelegatedForRemove(ResponseMessageError): pass
class ErrorCalendarIsDelegatedForTentative(ResponseMessageError): pass
class ErrorCalendarIsNotOrganizer(ResponseMessageError): pass
class ErrorCalendarIsOrganizerForAccept(ResponseMessageError): pass
class ErrorCalendarIsOrganizerForDecline(ResponseMessageError): pass
class ErrorCalendarIsOrganizerForRemove(ResponseMessageError): pass
class ErrorCalendarIsOrganizerForTentative(ResponseMessageError): pass
class ErrorCalendarMeetingRequestIsOutOfDate(ResponseMessageError): pass
class ErrorCalendarOccurrenceIndexIsOutOfRecurrenceRange(ResponseMessageError): pass
class ErrorCalendarOccurrenceIsDeletedFromRecurrence(ResponseMessageError): pass
class ErrorCalendarOutOfRange(ResponseMessageError): pass
class ErrorCalendarViewRangeTooBig(ResponseMessageError): pass
class ErrorCallerIsInvalidADAccount(ResponseMessageError): pass
class ErrorCannotCreateCalendarItemInNonCalendarFolder(ResponseMessageError): pass
class ErrorCannotCreateContactInNonContactFolder(ResponseMessageError): pass
class ErrorCannotCreatePostItemInNonMailFolder(ResponseMessageError): pass
class ErrorCannotCreateTaskInNonTaskFolder(ResponseMessageError): pass
class ErrorCannotDeleteObject(ResponseMessageError): pass
class ErrorCannotDeleteTaskOccurrence(ResponseMessageError): pass
class ErrorCannotEmptyFolder(ResponseMessageError): pass
class ErrorCannotOpenFileAttachment(ResponseMessageError): pass
class ErrorCannotSetCalendarPermissionOnNonCalendarFolder(ResponseMessageError): pass
class ErrorCannotSetNonCalendarPermissionOnCalendarFolder(ResponseMessageError): pass
class ErrorCannotSetPermissionUnknownEntries(ResponseMessageError): pass
class ErrorCannotUseFolderIdForItemId(ResponseMessageError): pass
class ErrorCannotUseItemIdForFolderId(ResponseMessageError): pass
class ErrorChangeKeyRequired(ResponseMessageError): pass
class ErrorChangeKeyRequiredForWriteOperations(ResponseMessageError): pass
class ErrorClientDisconnected(ResponseMessageError): pass
class ErrorConnectionFailed(ResponseMessageError): pass
class ErrorContainsFilterWrongType(ResponseMessageError): pass
class ErrorContentConversionFailed(ResponseMessageError): pass
class ErrorCorruptData(ResponseMessageError): pass
class ErrorCreateItemAccessDenied(ResponseMessageError): pass
class ErrorCreateManagedFolderPartialCompletion(ResponseMessageError): pass
class ErrorCreateSubfolderAccessDenied(ResponseMessageError): pass
class ErrorCrossMailboxMoveCopy(ResponseMessageError): pass
class ErrorCrossSiteRequest(ResponseMessageError): pass
class ErrorDataSizeLimitExceeded(ResponseMessageError): pass
class ErrorDataSourceOperation(ResponseMessageError): pass
class ErrorDelegateAlreadyExists(ResponseMessageError): pass
class ErrorDelegateCannotAddOwner(ResponseMessageError): pass
class ErrorDelegateMissingConfiguration(ResponseMessageError): pass
class ErrorDelegateNoUser(ResponseMessageError): pass
class ErrorDelegateValidationFailed(ResponseMessageError): pass
class ErrorDeleteDistinguishedFolder(ResponseMessageError): pass
class ErrorDeleteItemsFailed(ResponseMessageError): pass
class ErrorDistinguishedUserNotSupported(ResponseMessageError): pass
class ErrorDistributionListMemberNotExist(ResponseMessageError): pass
class ErrorDuplicateInputFolderNames(ResponseMessageError): pass
class ErrorDuplicateSOAPHeader(ResponseMessageError): pass
class ErrorDuplicateUserIdsSpecified(ResponseMessageError): pass
class ErrorEmailAddressMismatch(ResponseMessageError): pass
class ErrorEventNotFound(ResponseMessageError): pass
class ErrorExceededConnectionCount(ResponseMessageError): pass
class ErrorExceededFindCountLimit(ResponseMessageError): pass
class ErrorExceededSubscriptionCount(ResponseMessageError): pass
class ErrorExpiredSubscription(ResponseMessageError): pass
class ErrorFolderCorrupt(ResponseMessageError): pass
class ErrorFolderExists(ResponseMessageError): pass
class ErrorFolderNotFound(ResponseMessageError): pass
class ErrorFolderPropertyRequestFailed(ResponseMessageError): pass
class ErrorFolderSave(ResponseMessageError): pass
class ErrorFolderSaveFailed(ResponseMessageError): pass
class ErrorFolderSavePropertyError(ResponseMessageError): pass
class ErrorFreeBusyDLLimitReached(ResponseMessageError): pass
class ErrorFreeBusyGenerationFailed(ResponseMessageError): pass
class ErrorGetServerSecurityDescriptorFailed(ResponseMessageError): pass
class ErrorImpersonateUserDenied(ResponseMessageError): pass
class ErrorImpersonationDenied(ResponseMessageError): pass
class ErrorImpersonationFailed(ResponseMessageError): pass
class ErrorInboxRulesValidationError(ResponseMessageError): pass
class ErrorIncorrectSchemaVersion(ResponseMessageError): pass
class ErrorIncorrectUpdatePropertyCount(ResponseMessageError): pass
class ErrorIndividualMailboxLimitReached(ResponseMessageError): pass
class ErrorInsufficientResources(ResponseMessageError): pass
class ErrorInternalServerError(ResponseMessageError): pass
class ErrorInternalServerTransientError(ResponseMessageError): pass
class ErrorInvalidAccessLevel(ResponseMessageError): pass
class ErrorInvalidArgument(ResponseMessageError): pass
class ErrorInvalidAttachmentId(ResponseMessageError): pass
class ErrorInvalidAttachmentSubfilter(ResponseMessageError): pass
class ErrorInvalidAttachmentSubfilterTextFilter(ResponseMessageError): pass
class ErrorInvalidAuthorizationContext(ResponseMessageError): pass
class ErrorInvalidChangeKey(ResponseMessageError): pass
class ErrorInvalidClientSecurityContext(ResponseMessageError): pass
class ErrorInvalidCompleteDate(ResponseMessageError): pass
class ErrorInvalidContactEmailAddress(ResponseMessageError): pass
class ErrorInvalidContactEmailIndex(ResponseMessageError): pass
class ErrorInvalidCrossForestCredentials(ResponseMessageError): pass
class ErrorInvalidDelegatePermission(ResponseMessageError): pass
class ErrorInvalidDelegateUserId(ResponseMessageError): pass
class ErrorInvalidExchangeImpersonationHeaderData(ResponseMessageError): pass
class ErrorInvalidExcludesRestriction(ResponseMessageError): pass
class ErrorInvalidExpressionTypeForSubFilter(ResponseMessageError): pass
class ErrorInvalidExtendedProperty(ResponseMessageError): pass
class ErrorInvalidExtendedPropertyValue(ResponseMessageError): pass
class ErrorInvalidExternalSharingInitiator(ResponseMessageError): pass
class ErrorInvalidExternalSharingSubscriber(ResponseMessageError): pass
class ErrorInvalidFederatedOrganizationId(ResponseMessageError): pass
class ErrorInvalidFolderId(ResponseMessageError): pass
class ErrorInvalidFolderTypeForOperation(ResponseMessageError): pass
class ErrorInvalidFractionalPagingParameters(ResponseMessageError): pass
class ErrorInvalidFreeBusyViewType(ResponseMessageError): pass
class ErrorInvalidGetSharingFolderRequest(ResponseMessageError): pass
class ErrorInvalidId(ResponseMessageError): pass
class ErrorInvalidIdEmpty(ResponseMessageError): pass
class ErrorInvalidIdMalformed(ResponseMessageError): pass
class ErrorInvalidIdMalformedEwsLegacyIdFormat(ResponseMessageError): pass
class ErrorInvalidIdMonikerTooLong(ResponseMessageError): pass
class ErrorInvalidIdNotAnItemAttachmentId(ResponseMessageError): pass
class ErrorInvalidIdReturnedByResolveNames(ResponseMessageError): pass
class ErrorInvalidIdStoreObjectIdTooLong(ResponseMessageError): pass
class ErrorInvalidIdTooManyAttachmentLevels(ResponseMessageError): pass
class ErrorInvalidIdXml(ResponseMessageError): pass
class ErrorInvalidIndexedPagingParameters(ResponseMessageError): pass
class ErrorInvalidInternetHeaderChildNodes(ResponseMessageError): pass
class ErrorInvalidItemForOperationAcceptItem(ResponseMessageError): pass
class ErrorInvalidItemForOperationCancelItem(ResponseMessageError): pass
class ErrorInvalidItemForOperationCreateItem(ResponseMessageError): pass
class ErrorInvalidItemForOperationCreateItemAttachment(ResponseMessageError): pass
class ErrorInvalidItemForOperationDeclineItem(ResponseMessageError): pass
class ErrorInvalidItemForOperationExpandDL(ResponseMessageError): pass
class ErrorInvalidItemForOperationRemoveItem(ResponseMessageError): pass
class ErrorInvalidItemForOperationSendItem(ResponseMessageError): pass
class ErrorInvalidItemForOperationTentative(ResponseMessageError): pass
class ErrorInvalidLicense(ResponseMessageError): pass
class ErrorInvalidLogonType(ResponseMessageError): pass
class ErrorInvalidMailbox(ResponseMessageError): pass
class ErrorInvalidManagedFolderProperty(ResponseMessageError): pass
class ErrorInvalidManagedFolderQuota(ResponseMessageError): pass
class ErrorInvalidManagedFolderSize(ResponseMessageError): pass
class ErrorInvalidMergedFreeBusyInterval(ResponseMessageError): pass
class ErrorInvalidNameForNameResolution(ResponseMessageError): pass
class ErrorInvalidNetworkServiceContext(ResponseMessageError): pass
class ErrorInvalidOofParameter(ResponseMessageError): pass
class ErrorInvalidOperation(ResponseMessageError): pass
class ErrorInvalidOrganizationRelationshipForFreeBusy(ResponseMessageError): pass
class ErrorInvalidPagingMaxRows(ResponseMessageError): pass
class ErrorInvalidParentFolder(ResponseMessageError): pass
class ErrorInvalidPercentCompleteValue(ResponseMessageError): pass
class ErrorInvalidPermissionSettings(ResponseMessageError): pass
class ErrorInvalidPhoneCallId(ResponseMessageError): pass
class ErrorInvalidPhoneNumber(ResponseMessageError): pass
class ErrorInvalidPropertyAppend(ResponseMessageError): pass
class ErrorInvalidPropertyDelete(ResponseMessageError): pass
class ErrorInvalidPropertyForExists(ResponseMessageError): pass
class ErrorInvalidPropertyForOperation(ResponseMessageError): pass
class ErrorInvalidPropertyRequest(ResponseMessageError): pass
class ErrorInvalidPropertySet(ResponseMessageError): pass
class ErrorInvalidPropertyUpdateSentMessage(ResponseMessageError): pass
class ErrorInvalidProxySecurityContext(ResponseMessageError): pass
class ErrorInvalidPullSubscriptionId(ResponseMessageError): pass
class ErrorInvalidPushSubscriptionUrl(ResponseMessageError): pass
class ErrorInvalidRecipients(ResponseMessageError): pass
class ErrorInvalidRecipientSubfilter(ResponseMessageError): pass
class ErrorInvalidRecipientSubfilterComparison(ResponseMessageError): pass
class ErrorInvalidRecipientSubfilterOrder(ResponseMessageError): pass
class ErrorInvalidRecipientSubfilterTextFilter(ResponseMessageError): pass
class ErrorInvalidReferenceItem(ResponseMessageError): pass
class ErrorInvalidRequest(ResponseMessageError): pass
class ErrorInvalidRestriction(ResponseMessageError): pass
class ErrorInvalidRoutingType(ResponseMessageError): pass
class ErrorInvalidScheduledOofDuration(ResponseMessageError): pass
class ErrorInvalidSchemaVersionForMailboxVersion(ResponseMessageError): pass
class ErrorInvalidSecurityDescriptor(ResponseMessageError): pass
class ErrorInvalidSendItemSaveSettings(ResponseMessageError): pass
class ErrorInvalidSerializedAccessToken(ResponseMessageError): pass
class ErrorInvalidServerVersion(ResponseMessageError): pass
class ErrorInvalidSharingData(ResponseMessageError): pass
class ErrorInvalidSharingMessage(ResponseMessageError): pass
class ErrorInvalidSid(ResponseMessageError): pass
class ErrorInvalidSIPUri(ResponseMessageError): pass
class ErrorInvalidSmtpAddress(ResponseMessageError): pass
class ErrorInvalidSubfilterType(ResponseMessageError): pass
class ErrorInvalidSubfilterTypeNotAttendeeType(ResponseMessageError): pass
class ErrorInvalidSubfilterTypeNotRecipientType(ResponseMessageError): pass
class ErrorInvalidSubscription(ResponseMessageError): pass
class ErrorInvalidSubscriptionRequest(ResponseMessageError): pass
class ErrorInvalidSyncStateData(ResponseMessageError): pass
class ErrorInvalidTimeInterval(ResponseMessageError): pass
class ErrorInvalidUserInfo(ResponseMessageError): pass
class ErrorInvalidUserOofSettings(ResponseMessageError): pass
class ErrorInvalidUserPrincipalName(ResponseMessageError): pass
class ErrorInvalidUserSid(ResponseMessageError): pass
class ErrorInvalidUserSidMissingUPN(ResponseMessageError): pass
class ErrorInvalidValueForProperty(ResponseMessageError): pass
class ErrorInvalidWatermark(ResponseMessageError): pass
class ErrorIPGatewayNotFound(ResponseMessageError): pass
class ErrorIrresolvableConflict(ResponseMessageError): pass
class ErrorItemCorrupt(ResponseMessageError): pass
class ErrorItemNotFound(ResponseMessageError): pass
class ErrorItemPropertyRequestFailed(ResponseMessageError): pass
class ErrorItemSave(ResponseMessageError): pass
class ErrorItemSavePropertyError(ResponseMessageError): pass
class ErrorLegacyMailboxFreeBusyViewTypeNotMerged(ResponseMessageError): pass
class ErrorLocalServerObjectNotFound(ResponseMessageError): pass
class ErrorLogonAsNetworkServiceFailed(ResponseMessageError): pass
class ErrorMailboxConfiguration(ResponseMessageError): pass
class ErrorMailboxDataArrayEmpty(ResponseMessageError): pass
class ErrorMailboxDataArrayTooBig(ResponseMessageError): pass
class ErrorMailboxFailover(ResponseMessageError): pass
class ErrorMailboxLogonFailed(ResponseMessageError): pass
class ErrorMailboxMoveInProgress(ResponseMessageError): pass
class ErrorMailboxStoreUnavailable(ResponseMessageError): pass
class ErrorMailRecipientNotFound(ResponseMessageError): pass
class ErrorMailTipsDisabled(ResponseMessageError): pass
class ErrorManagedFolderAlreadyExists(ResponseMessageError): pass
class ErrorManagedFolderNotFound(ResponseMessageError): pass
class ErrorManagedFoldersRootFailure(ResponseMessageError): pass
class ErrorMeetingSuggestionGenerationFailed(ResponseMessageError): pass
class ErrorMessageDispositionRequired(ResponseMessageError): pass
class ErrorMessageSizeExceeded(ResponseMessageError): pass
class ErrorMessageTrackingNoSuchDomain(ResponseMessageError): pass
class ErrorMessageTrackingPermanentError(ResponseMessageError): pass
class ErrorMessageTrackingTransientError(ResponseMessageError): pass
class ErrorMimeContentConversionFailed(ResponseMessageError): pass
class ErrorMimeContentInvalid(ResponseMessageError): pass
class ErrorMimeContentInvalidBase64String(ResponseMessageError): pass
class ErrorMissedNotificationEvents(ResponseMessageError): pass
class ErrorMissingArgument(ResponseMessageError): pass
class ErrorMissingEmailAddress(ResponseMessageError): pass
class ErrorMissingEmailAddressForManagedFolder(ResponseMessageError): pass
class ErrorMissingInformationEmailAddress(ResponseMessageError): pass
class ErrorMissingInformationReferenceItemId(ResponseMessageError): pass
class ErrorMissingInformationSharingFolderId(ResponseMessageError): pass
class ErrorMissingItemForCreateItemAttachment(ResponseMessageError): pass
class ErrorMissingManagedFolderId(ResponseMessageError): pass
class ErrorMissingRecipients(ResponseMessageError): pass
class ErrorMissingUserIdInformation(ResponseMessageError): pass
class ErrorMoreThanOneAccessModeSpecified(ResponseMessageError): pass
class ErrorMoveCopyFailed(ResponseMessageError): pass
class ErrorMoveDistinguishedFolder(ResponseMessageError): pass
class ErrorNameResolutionMultipleResults(ResponseMessageError): pass
class ErrorNameResolutionNoMailbox(ResponseMessageError): pass
class ErrorNameResolutionNoResults(ResponseMessageError): pass
class ErrorNewEventStreamConnectionOpened(ResponseMessageError): pass
class ErrorNoApplicableProxyCASServersAvailable(ResponseMessageError): pass
class ErrorNoCalendar(ResponseMessageError): pass
class ErrorNoDestinationCASDueToKerberosRequirements(ResponseMessageError): pass
class ErrorNoDestinationCASDueToSSLRequirements(ResponseMessageError): pass
class ErrorNoDestinationCASDueToVersionMismatch(ResponseMessageError): pass
class ErrorNoFolderClassOverride(ResponseMessageError): pass
class ErrorNoFreeBusyAccess(ResponseMessageError): pass
class ErrorNonExistentMailbox(ResponseMessageError): pass
class ErrorNonPrimarySmtpAddress(ResponseMessageError): pass
class ErrorNoPropertyTagForCustomProperties(ResponseMessageError): pass
class ErrorNoPublicFolderReplicaAvailable(ResponseMessageError): pass
class ErrorNoPublicFolderServerAvailable(ResponseMessageError): pass
class ErrorNoRespondingCASInDestinationSite(ResponseMessageError): pass
class ErrorNotAllowedExternalSharingByPolicy(ResponseMessageError): pass
class ErrorNotDelegate(ResponseMessageError): pass
class ErrorNotEnoughMemory(ResponseMessageError): pass
class ErrorNotSupportedSharingMessage(ResponseMessageError): pass
class ErrorObjectTypeChanged(ResponseMessageError): pass
class ErrorOccurrenceCrossingBoundary(ResponseMessageError): pass
class ErrorOccurrenceTimeSpanTooBig(ResponseMessageError): pass
class ErrorOperationNotAllowedWithPublicFolderRoot(ResponseMessageError): pass
class ErrorOrganizationNotFederated(ResponseMessageError): pass
class ErrorOutlookRuleBlobExists(ResponseMessageError): pass
class ErrorParentFolderIdRequired(ResponseMessageError): pass
class ErrorParentFolderNotFound(ResponseMessageError): pass
class ErrorPasswordChangeRequired(ResponseMessageError): pass
class ErrorPasswordExpired(ResponseMessageError): pass
class ErrorPermissionNotAllowedByPolicy(ResponseMessageError): pass
class ErrorPhoneNumberNotDialable(ResponseMessageError): pass
class ErrorPropertyUpdate(ResponseMessageError): pass
class ErrorPropertyValidationFailure(ResponseMessageError): pass
class ErrorProxiedSubscriptionCallFailure(ResponseMessageError): pass
class ErrorProxyCallFailed(ResponseMessageError): pass
class ErrorProxyGroupSidLimitExceeded(ResponseMessageError): pass
class ErrorProxyRequestNotAllowed(ResponseMessageError): pass
class ErrorProxyRequestProcessingFailed(ResponseMessageError): pass
class ErrorProxyServiceDiscoveryFailed(ResponseMessageError): pass
class ErrorProxyTokenExpired(ResponseMessageError): pass
class ErrorPublicFolderRequestProcessingFailed(ResponseMessageError): pass
class ErrorPublicFolderServerNotFound(ResponseMessageError): pass
class ErrorQueryFilterTooLong(ResponseMessageError): pass
class ErrorQuotaExceeded(ResponseMessageError): pass
class ErrorReadEventsFailed(ResponseMessageError): pass
class ErrorReadReceiptNotPending(ResponseMessageError): pass
class ErrorRecurrenceEndDateTooBig(ResponseMessageError): pass
class ErrorRecurrenceHasNoOccurrence(ResponseMessageError): pass
class ErrorRemoveDelegatesFailed(ResponseMessageError): pass
class ErrorRequestAborted(ResponseMessageError): pass
class ErrorRequestStreamTooBig(ResponseMessageError): pass
class ErrorRequiredPropertyMissing(ResponseMessageError): pass
class ErrorResolveNamesInvalidFolderType(ResponseMessageError): pass
class ErrorResolveNamesOnlyOneContactsFolderAllowed(ResponseMessageError): pass
class ErrorResponseSchemaValidation(ResponseMessageError): pass
class ErrorRestrictionTooComplex(ResponseMessageError): pass
class ErrorRestrictionTooLong(ResponseMessageError): pass
class ErrorResultSetTooBig(ResponseMessageError): pass
class ErrorRulesOverQuota(ResponseMessageError): pass
class ErrorSavedItemFolderNotFound(ResponseMessageError): pass
class ErrorSchemaValidation(ResponseMessageError): pass
class ErrorSearchFolderNotInitialized(ResponseMessageError): pass
class ErrorSendAsDenied(ResponseMessageError): pass
class ErrorSendMeetingCancellationsRequired(ResponseMessageError): pass
class ErrorSendMeetingInvitationsOrCancellationsRequired(ResponseMessageError): pass
class ErrorSendMeetingInvitationsRequired(ResponseMessageError): pass
class ErrorSentMeetingRequestUpdate(ResponseMessageError): pass
class ErrorSentTaskRequestUpdate(ResponseMessageError): pass
class ErrorServerBusy(ResponseMessageError): pass
class ErrorServiceDiscoveryFailed(ResponseMessageError): pass
class ErrorSharingNoExternalEwsAvailable(ResponseMessageError): pass
class ErrorSharingSynchronizationFailed(ResponseMessageError): pass
class ErrorStaleObject(ResponseMessageError): pass
class ErrorSubmissionQuotaExceeded(ResponseMessageError): pass
class ErrorSubscriptionAccessDenied(ResponseMessageError): pass
class ErrorSubscriptionDelegateAccessNotSupported(ResponseMessageError): pass
class ErrorSubscriptionNotFound(ResponseMessageError): pass
class ErrorSubscriptionUnsubsribed(ResponseMessageError): pass
class ErrorSyncFolderNotFound(ResponseMessageError): pass
class ErrorTimeIntervalTooBig(ResponseMessageError): pass
class ErrorTimeoutExpired(ResponseMessageError): pass
class ErrorTimeZone(ResponseMessageError): pass
class ErrorToFolderNotFound(ResponseMessageError): pass
class ErrorTokenSerializationDenied(ResponseMessageError): pass
class ErrorTooManyObjectsOpened(ResponseMessageError): pass
class ErrorUnableToGetUserOofSettings(ResponseMessageError): pass
class ErrorUnifiedMessagingDialPlanNotFound(ResponseMessageError): pass
class ErrorUnifiedMessagingRequestFailed(ResponseMessageError): pass
class ErrorUnifiedMessagingServerNotFound(ResponseMessageError): pass
class ErrorUnsupportedCulture(ResponseMessageError): pass
class ErrorUnsupportedMapiPropertyType(ResponseMessageError): pass
class ErrorUnsupportedMimeConversion(ResponseMessageError): pass
class ErrorUnsupportedPathForQuery(ResponseMessageError): pass
class ErrorUnsupportedPathForSortGroup(ResponseMessageError): pass
class ErrorUnsupportedPropertyDefinition(ResponseMessageError): pass
class ErrorUnsupportedQueryFilter(ResponseMessageError): pass
class ErrorUnsupportedRecurrence(ResponseMessageError): pass
class ErrorUnsupportedSubFilter(ResponseMessageError): pass
class ErrorUnsupportedTypeForConversion(ResponseMessageError): pass
class ErrorUpdateDelegatesFailed(ResponseMessageError): pass
class ErrorUpdatePropertyMismatch(ResponseMessageError): pass
class ErrorUserNotAllowedByPolicy(ResponseMessageError): pass
class ErrorUserNotUnifiedMessagingEnabled(ResponseMessageError): pass
class ErrorUserWithoutFederatedProxyAddress(ResponseMessageError): pass
class ErrorValueOutOfRange(ResponseMessageError): pass
class ErrorVirusDetected(ResponseMessageError): pass
class ErrorVirusMessageDeleted(ResponseMessageError): pass
class ErrorVoiceMailNotImplemented(ResponseMessageError): pass
class ErrorWebRequestInInvalidState(ResponseMessageError): pass
class ErrorWin32InteropError(ResponseMessageError): pass
class ErrorWorkingHoursSaveFailed(ResponseMessageError): pass
class ErrorWorkingHoursXmlMalformed(ResponseMessageError): pass
class ErrorWrongServerVersion(ResponseMessageError): pass
class ErrorWrongServerVersionDelegate(ResponseMessageError): pass


# Microsoft recommends to cache the autodiscover data around 24 hours and perform autodiscover
# immediately following certain error responses from EWS. See more at
# http://blogs.msdn.com/b/mstehle/archive/2010/11/09/ews-best-practices-use-autodiscover.aspx

ERRORS_REQUIRING_REAUTODISCOVER = (
    ErrorAutoDiscoverFailed,
    ErrorConnectionFailed,
    ErrorIncorrectSchemaVersion,
    ErrorInvalidCrossForestCredentials,
    ErrorInvalidIdReturnedByResolveNames,
    ErrorInvalidNetworkServiceContext,
    ErrorMailboxMoveInProgress,
    ErrorMailboxMoveInProgress,
    ErrorMailboxStoreUnavailable,
    ErrorNameResolutionNoMailbox,
    ErrorNameResolutionNoResults,
    ErrorNotEnoughMemory,
)
