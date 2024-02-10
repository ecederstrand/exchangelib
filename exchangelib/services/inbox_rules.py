from typing import Optional

from ..errors import ErrorInvalidOperation
from ..properties import CreateRuleOperation, DeleteRuleOperation, InboxRules, Operations, Rule, SetRuleOperation
from ..util import add_xml_child, create_element, set_xml_value
from ..version import EXCHANGE_2010
from .common import EWSAccountService


class GetInboxRules(EWSAccountService):
    """
    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getinboxrules-operation

    The GetInboxRules operation uses Exchange Web Services to retrieve Inbox rules in the identified user's mailbox.
    """
    SERVICE_NAME = "GetInboxRules"
    supported_from = EXCHANGE_2010
    element_container_name = InboxRules.response_tag()
    ERRORS_TO_CATCH_IN_RESPONSE = EWSAccountService.ERRORS_TO_CATCH_IN_RESPONSE + (
        ErrorInvalidOperation,
    )

    def call(self, mailbox: Optional[str] = None):
        if not mailbox:
            mailbox = self.account.primary_smtp_address
        payload = self.get_payload(mailbox=mailbox)
        elements = self._get_elements(payload=payload)
        return self._elems_to_objs(elements)

    def _elem_to_obj(self, elem):
        return Rule.from_xml(elem=elem, account=self.account)

    def get_payload(self, mailbox):
        payload = create_element(f"m:{self.SERVICE_NAME}")
        add_xml_child(payload, 'm:MailboxSmtpAddress', mailbox)
        return payload

class UpdateInboxRules(EWSAccountService):
    """
    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/updateinboxrules-operation

    The UpdateInboxRules operation updates the authenticated user's Inbox rules by applying the specified operations.
    UpdateInboxRules is used to create an Inbox rule, to set an Inbox rule, or to delete an Inbox rule.

    When you use the UpdateInboxRules operation, Exchange Web Services deletes client-side send rules.
    Client-side send rules are stored on the client in the rule Folder Associated Information (FAI) Message and nowhere else.
    EWS deletes this rule FAI message by default, based on the expectation that Outlook will recreate it.
    However, Outlook can't recreate rules that don't also exist as an extended rule, and client-side send rules don't exist as extended rules.
    As a result, these rules are lost. We suggest you consider this when designing your solution.
    """
    SERVICE_NAME = "UpdateInboxRules"
    supported_from = EXCHANGE_2010
    ERRORS_TO_CATCH_IN_RESPONSE = EWSAccountService.ERRORS_TO_CATCH_IN_RESPONSE + (
        ErrorInvalidOperation,
    )


class CreateInboxRule(UpdateInboxRules):
    """
    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/updateinboxrules-operation#updateinboxrules-create-rule-request-example
    """

    def call(self, rule: Rule, remove_outlook_rule_blob: bool = True):
        payload = self.get_payload(
            rule=rule, remove_outlook_rule_blob=remove_outlook_rule_blob)
        return self._get_elements(payload=payload)

    def get_payload(self, rule: Rule,
                    remove_outlook_rule_blob: bool = True):
        payload = create_element(f"m:{self.SERVICE_NAME}")
        add_xml_child(payload, 'm:RemoveOutlookRuleBlob',
                      remove_outlook_rule_blob)
        operations = Operations(
            create_rule_operation=CreateRuleOperation(rule=rule))
        set_xml_value(payload, operations, version=self.account.version)
        return payload


class SetInboxRule(UpdateInboxRules):
    """
    MSDN:
    https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/updateinboxrules-operation#updateinboxrules-set-rule-request-example
    """

    def call(self, rule: Rule, remove_outlook_rule_blob: bool = True):
        payload = self.get_payload(
            rule=rule, remove_outlook_rule_blob=remove_outlook_rule_blob)
        return self._get_elements(payload=payload)

    def get_payload(self, rule: Rule,
                    remove_outlook_rule_blob: bool = True):
        if not rule.rule_id:
            raise ValueError("rule_id cannot be empty")
        payload = create_element(f"m:{self.SERVICE_NAME}")
        add_xml_child(payload, 'm:RemoveOutlookRuleBlob',
                      remove_outlook_rule_blob)
        operations = Operations(set_rule_operation=SetRuleOperation(rule=rule))
        set_xml_value(payload, operations, version=self.account.version)
        return payload


class DeleteInboxRule(UpdateInboxRules):
    """
    MSDN:
    https://learn.microsoft.com/en-us/exchange/client-developer/web-service-reference/updateinboxrules-operation#updateinboxrules-delete-rule-request-example
    """

    def call(self, rule_id: str, remove_outlook_rule_blob: bool = True):
        payload = self.get_payload(
            rule_id=rule_id, remove_outlook_rule_blob=remove_outlook_rule_blob)
        return self._get_elements(payload=payload)

    def get_payload(self, rule_id: str, remove_outlook_rule_blob: bool = True):
        if not rule_id:
            raise ValueError("rule_id cannot be empty")
        payload = create_element(f"m:{self.SERVICE_NAME}")
        add_xml_child(payload, 'm:RemoveOutlookRuleBlob',
                      remove_outlook_rule_blob)
        operations = Operations(
            delete_rule_operation=DeleteRuleOperation(rule_id=rule_id))
        set_xml_value(payload, operations, version=self.account.version)
        return payload
