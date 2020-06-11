from ..errors import ErrorNonExistentMailbox, AutoDiscoverFailed
from ..fields import TextField, EmailAddressField, ChoiceField, Choice, EWSElementField, OnOffField, BooleanField, \
    IntegerField, BuildField, ProtocolListField
from ..properties import EWSElement, Fields
from ..transport import DEFAULT_ENCODING
from ..util import create_element, add_xml_child, to_xml, is_xml, xml_to_str, AUTODISCOVER_REQUEST_NS, \
    AUTODISCOVER_BASE_NS, AUTODISCOVER_RESPONSE_NS as RNS, ParseError


class AutodiscoverBase(EWSElement):
    NAMESPACE = RNS


class User(AutodiscoverBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/user-pox"""
    ELEMENT_NAME = 'User'
    FIELDS = Fields(
        TextField('display_name', field_uri='DisplayName', namespace=RNS),
        TextField('legacy_dn', field_uri='LegacyDN', namespace=RNS),
        TextField('deployment_id', field_uri='DeploymentId', namespace=RNS),  # GUID format
        EmailAddressField('autodiscover_smtp_address', field_uri='AutoDiscoverSMTPAddress', namespace=RNS),
    )
    __slots__ = tuple(f.name for f in FIELDS)


class IntExtUrlBase(AutodiscoverBase):
    FIELDS = Fields(
        TextField('external_url', field_uri='ExternalUrl', namespace=RNS),
        TextField('internal_url', field_uri='InternalUrl', namespace=RNS),
    )
    __slots__ = tuple(f.name for f in FIELDS)


class AddressBook(IntExtUrlBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/addressbook-pox"""
    ELEMENT_NAME = 'AddressBook'
    __slots__ = tuple()


class MailStore(IntExtUrlBase):
    ELEMENT_NAME = 'MailStore'
    __slots__ = tuple()


class NetworkRequirements(AutodiscoverBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/networkrequirements-pox"""
    ELEMENT_NAME = 'NetworkRequirements'
    FIELDS = Fields(
        TextField('ipv4_start', field_uri='IPv4Start', namespace=RNS),
        TextField('ipv4_end', field_uri='IPv4End', namespace=RNS),
        TextField('ipv6_start', field_uri='IPv6Start', namespace=RNS),
        TextField('ipv6_end', field_uri='IPv6End', namespace=RNS),
    )
    __slots__ = tuple(f.name for f in FIELDS)


class SimpleProtocol(AutodiscoverBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/protocol-pox

    Used for the 'Internal' and 'External' elements that may contain a stripped-down version of the Protocol element.

    Args:

    Returns:

    """
    ELEMENT_NAME = 'Protocol'
    FIELDS = Fields(
        ChoiceField('type', field_uri='Type', choices={
            Choice('WEB'), Choice('EXCH'), Choice('EXPR'), Choice('EXHTTP')
        }, namespace=RNS),
        TextField('as_url', field_uri='ASUrl', namespace=RNS),
    )
    __slots__ = tuple(f.name for f in FIELDS)


class IntExtBase(AutodiscoverBase):
    FIELDS = Fields(
        # TODO: 'OWAUrl' also has an AuthenticationMethod enum-style XML attribute
        TextField('owa_url', field_uri='OWAUrl', namespace=RNS),
        EWSElementField('protocol', value_cls=SimpleProtocol),
    )

    __slots__ = tuple(f.name for f in FIELDS)


class Internal(IntExtBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/internal-pox"""
    ELEMENT_NAME = 'Internal'
    __slots__ = tuple()


class External(IntExtBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/external-pox"""
    ELEMENT_NAME = 'External'
    __slots__ = tuple()


class Protocol(AutodiscoverBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/protocol-pox"""
    ELEMENT_NAME = 'Protocol'
    TYPES = ('WEB', 'EXCH', 'EXPR', 'EXHTTP')
    FIELDS = Fields(
        # Attribute 'Type' is ignored here. Has a name conflict with the child element and does not seem useful.
        TextField('version', field_uri='Version', is_attribute=True, namespace=RNS),
        ChoiceField('type', field_uri='Type', namespace=RNS, choices={Choice(p) for p in TYPES}),
        TextField('internal', field_uri='Internal', namespace=RNS),
        TextField('external', field_uri='External', namespace=RNS),
        IntegerField('ttl', field_uri='TTL', namespace=RNS, default=1),  # TTL for this autodiscover response, in hours
        TextField('server', field_uri='Server', namespace=RNS),
        TextField('server_dn', field_uri='ServerDN', namespace=RNS),
        BuildField('server_version', field_uri='ServerVersion', namespace=RNS),
        TextField('mdb_dn', field_uri='MdbDN', namespace=RNS),
        TextField('public_folder_server', field_uri='PublicFolderServer', namespace=RNS),
        IntegerField('port', field_uri='Port', namespace=RNS, min=1, max=65535),
        IntegerField('directory_port', field_uri='DirectoryPort', namespace=RNS, min=1, max=65535),
        IntegerField('referral_port', field_uri='ReferralPort', namespace=RNS, min=1, max=65535),
        TextField('as_url', field_uri='ASUrl', namespace=RNS),
        TextField('ews_url', field_uri='EwsUrl', namespace=RNS),
        TextField('emws_url', field_uri='EmwsUrl', namespace=RNS),
        TextField('sharing_url', field_uri='SharingUrl', namespace=RNS),
        TextField('ecp_url', field_uri='EcpUrl', namespace=RNS),
        TextField('ecp_url_um', field_uri='EcpUrl-um', namespace=RNS),
        TextField('ecp_url_aggr', field_uri='EcpUrl-aggr', namespace=RNS),
        TextField('ecp_url_mt', field_uri='EcpUrl-mt', namespace=RNS),
        TextField('ecp_url_ret', field_uri='EcpUrl-ret', namespace=RNS),
        TextField('ecp_url_sms', field_uri='EcpUrl-sms', namespace=RNS),
        TextField('ecp_url_publish', field_uri='EcpUrl-publish', namespace=RNS),
        TextField('ecp_url_photo', field_uri='EcpUrl-photo', namespace=RNS),
        TextField('ecp_url_tm', field_uri='EcpUrl-tm', namespace=RNS),
        TextField('ecp_url_tm_creating', field_uri='EcpUrl-tmCreating', namespace=RNS),
        TextField('ecp_url_tm_hiding', field_uri='EcpUrl-tmHiding', namespace=RNS),
        TextField('ecp_url_tm_editing', field_uri='EcpUrl-tmEditing', namespace=RNS),
        TextField('ecp_url_extinstall', field_uri='EcpUrl-extinstall', namespace=RNS),
        TextField('oof_url', field_uri='OOFUrl', namespace=RNS),
        TextField('oab_url', field_uri='OABUrl', namespace=RNS),
        TextField('um_url', field_uri='UMUrl', namespace=RNS),
        TextField('ews_partner_url', field_uri='EwsPartnerUrl', namespace=RNS),
        TextField('login_name', field_uri='LoginName', namespace=RNS),
        OnOffField('domain_required', field_uri='DomainRequired', namespace=RNS),
        TextField('domain_name', field_uri='DomainName', namespace=RNS),
        OnOffField('spa', field_uri='SPA', namespace=RNS, default=True),
        ChoiceField('auth_package', field_uri='AuthPackage', namespace=RNS, choices={
            Choice(c) for c in ('basic', 'kerb', 'kerbntlm', 'ntlm', 'certificate', 'negotiate', 'nego2')
        }),
        TextField('cert_principal_name', field_uri='CertPrincipalName', namespace=RNS),
        OnOffField('ssl', field_uri='SSL', namespace=RNS, default=True),
        OnOffField('auth_required', field_uri='AuthRequired', namespace=RNS, default=True),
        OnOffField('use_pop_path', field_uri='UsePOPAuth', namespace=RNS),
        OnOffField('smtp_last', field_uri='SMTPLast', namespace=RNS, default=False),
        EWSElementField('network_requirements', value_cls=NetworkRequirements),
        EWSElementField('address_book', value_cls=AddressBook),
        EWSElementField('mail_store', value_cls=MailStore),
    )

    __slots__ = tuple(f.name for f in FIELDS)

    @property
    def auth_type(self):
        # Translates 'auth_package' value to our own 'auth_type' enum vals
        from ..transport import NOAUTH, NTLM, BASIC, GSSAPI, SSPI, CBA
        if not self.auth_required:
            return NOAUTH
        return {
            # Missing in list are DIGEST and OAUTH2
            'basic': BASIC,
            'kerb': GSSAPI,
            'kerbntlm': NTLM,  # Means client can chose between NTLM and GSSAPI
            'ntlm': NTLM,
            'certificate': CBA,
            'negotiate': SSPI,  # Unsure about this one
            'nego2': GSSAPI,
            'anonymous': NOAUTH,  # Seen in some docs even though it's not mentioned in MSDN
        }.get(self.auth_package.lower(), NTLM)  # Default to NTLM


class Error(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/error-pox"""
    ELEMENT_NAME = 'Error'
    NAMESPACE = AUTODISCOVER_BASE_NS
    FIELDS = Fields(
        TextField('id', field_uri='Id', namespace=AUTODISCOVER_BASE_NS, is_attribute=True),
        TextField('time', field_uri='Time', namespace=AUTODISCOVER_BASE_NS, is_attribute=True),
        TextField('code', field_uri='ErrorCode', namespace=AUTODISCOVER_BASE_NS),
        TextField('message', field_uri='Message', namespace=AUTODISCOVER_BASE_NS),
        TextField('debug_data', field_uri='DebugData', namespace=AUTODISCOVER_BASE_NS),
    )

    __slots__ = tuple(f.name for f in FIELDS)


class Account(AutodiscoverBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/account-pox"""
    ELEMENT_NAME = 'Account'
    REDIRECT_URL = 'redirectUrl'
    REDIRECT_ADDR = 'redirectAddr'
    SETTINGS = 'settings'
    ACTIONS = (REDIRECT_URL, REDIRECT_ADDR, SETTINGS)
    FIELDS = Fields(
        ChoiceField('type', field_uri='AccountType', namespace=RNS, choices={Choice('email')}),
        ChoiceField('action', field_uri='Action', namespace=RNS, choices={Choice(p) for p in ACTIONS}),
        BooleanField('microsoft_online', field_uri='MicrosoftOnline', namespace=RNS),
        TextField('redirect_url', field_uri='RedirectURL', namespace=RNS),
        EmailAddressField('redirect_address', field_uri='RedirectAddr', namespace=RNS),
        TextField('image', field_uri='Image', namespace=RNS),  # Path to image used for branding
        TextField('service_home', field_uri='ServiceHome', namespace=RNS),  # URL to website of ISP
        ProtocolListField('protocols'),
        # 'SmtpAddress' is inside the 'PublicFolderInformation' element
        TextField('public_folder_smtp_address', field_uri='SmtpAddress', namespace=RNS),
    )

    __slots__ = tuple(f.name for f in FIELDS)

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {}
        public_folder_information = elem.find('{%s}PublicFolderInformation' % cls.NAMESPACE)
        for f in cls.FIELDS:
            if f.name == 'public_folder_smtp_address':
                if public_folder_information is None:
                    continue
                kwargs[f.name] = f.from_xml(elem=public_folder_information, account=account)
                continue
            kwargs[f.name] = f.from_xml(elem=elem, account=account)
        cls._clear(elem)
        return cls(**kwargs)


class Response(AutodiscoverBase):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/response-pox"""
    ELEMENT_NAME = 'Response'
    FIELDS = Fields(
        EWSElementField('user', value_cls=User),
        EWSElementField('account', value_cls=Account),
    )

    __slots__ = tuple(f.name for f in FIELDS)

    @property
    def redirect_address(self):
        try:
            if self.account.action != Account.REDIRECT_ADDR:
                return None
            return self.account.redirect_address
        except AttributeError:
            return None

    @property
    def redirect_url(self):
        try:
            if self.account.action != Account.REDIRECT_URL:
                return None
            return self.account.redirect_url
        except AttributeError:
            return None

    @property
    def autodiscover_smtp_address(self):
        # AutoDiscoverSMTPAddress might not be present in the XML. In this case, use the original email address.
        try:
            if self.account.action != Account.SETTINGS:
                return None
            return self.user.autodiscover_smtp_address
        except AttributeError:
            return None

    @property
    def protocol(self):
        # There are three possible protocol types: EXCH, EXPR and WEB. EXPR is meant for EWS. See
        # https://techcommunity.microsoft.com/t5/blogs/blogarticleprintpage/blog-id/Exchange/article-id/16
        # We allow fallback to EXCH if EXPR is not available, to support installations where EXPR is not available.
        protocols = {p.type: p for p in self.account.protocols}
        if 'EXPR' in protocols:
            return protocols['EXPR']
        if 'EXCH' in protocols:
            return protocols['EXCH']
        # Neither type was found. Give up
        raise ValueError('No valid protocols in response: %s' % self.account.protocols)


class ErrorResponse(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/response-pox

    Like 'Response', but with a different namespace.

    Args:

    Returns:

    """
    ELEMENT_NAME = 'Response'
    NAMESPACE = AUTODISCOVER_BASE_NS
    FIELDS = Fields(
        EWSElementField('error', value_cls=Error),
    )

    __slots__ = tuple(f.name for f in FIELDS)


class Autodiscover(EWSElement):
    ELEMENT_NAME = 'Autodiscover'
    NAMESPACE = AUTODISCOVER_BASE_NS
    FIELDS = Fields(
        EWSElementField('response', value_cls=Response),
        EWSElementField('error_response', value_cls=ErrorResponse),
    )

    __slots__ = tuple(f.name for f in FIELDS)

    @staticmethod
    def _clear(elem):
        # Parent implementation also clears the parent, but this element doesn't have one.
        elem.clear()

    @classmethod
    def from_bytes(cls, bytes_content):
        """An Autodiscover request and response example is available at:
        https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/pox-autodiscover-response-for-exchange

        Args:
          bytes_content: 

        Returns:

        """
        if not is_xml(bytes_content):
            raise ValueError('Response is not XML: %s' % bytes_content)
        try:
            root = to_xml(bytes_content).getroot()
        except ParseError:
            raise ValueError('Error parsing XML: %s' % bytes_content)
        if root.tag != cls.response_tag():
            raise ValueError('Unknown root element in XML: %s' % bytes_content)
        return cls.from_xml(elem=root, account=None)

    def raise_errors(self):
        # Find an error message in the response and raise the relevant exception
        try:
            errorcode = self.error_response.error.code
            message = self.error_response.error.message
            if message in ('The e-mail address cannot be found.', "The email address can't be found."):
                raise ErrorNonExistentMailbox('The SMTP address has no mailbox associated with it')
            raise AutoDiscoverFailed('Unknown error %s: %s' % (errorcode, message))
        except AttributeError:
            raise AutoDiscoverFailed('Unknown autodiscover error response: %s' % self)

    @staticmethod
    def payload(email):
        # Builds a full Autodiscover XML request
        payload = create_element('Autodiscover', attrs=dict(xmlns=AUTODISCOVER_REQUEST_NS))
        request = create_element('Request')
        add_xml_child(request, 'EMailAddress', email)
        add_xml_child(request, 'AcceptableResponseSchema', RNS)
        payload.append(request)
        return xml_to_str(payload, encoding=DEFAULT_ENCODING, xml_declaration=True)
