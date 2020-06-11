import datetime

from ..errors import NaiveDateTimeNotAllowed
from ..ewsdatetime import EWSDateTime
from ..fields import WEEKDAY_NAMES
from ..util import create_element, set_xml_value, xml_text_to_value, peek, TNS, MNS
from ..version import EXCHANGE_2010
from .common import EWSService


class GetServerTimeZones(EWSService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/getservertimezones"""
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
            attrs=dict(ReturnFullTimeZoneData='true' if return_full_timezone_data else 'false'),
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
        for timezonedef in container:
            tz_id = timezonedef.get('Id')
            tz_name = timezonedef.get('Name')
            tz_periods = self._get_periods(timezonedef)
            tz_transitions_groups = self._get_transitions_groups(timezonedef)
            tz_transitions = self._get_transitions(timezonedef)
            yield (tz_id, tz_name, tz_periods, tz_transitions, tz_transitions_groups)

    @staticmethod
    def _get_periods(timezonedef):
        tz_periods = {}
        periods = timezonedef.find('{%s}Periods' % TNS)
        for period in periods.findall('{%s}Period' % TNS):
            # Convert e.g. "trule:Microsoft/Registry/W. Europe Standard Time/2006-Daylight" to (2006, 'Daylight')
            p_year, p_type = period.get('Id').rsplit('/', 1)[1].split('-')
            tz_periods[(int(p_year), p_type)] = dict(
                name=period.get('Name'),
                bias=xml_text_to_value(period.get('Bias'), datetime.timedelta)
            )
        return tz_periods

    @staticmethod
    def _get_transitions_groups(timezonedef):
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
                    occurrence = xml_text_to_value(transition.find('{%s}Occurrence' % TNS).text, int)
                    if occurrence == -1:
                        # See TimeZoneTransition.from_xml()
                        occurrence = 5
                    tz_transitions_groups[tg_id].append(dict(
                        to=(int(to_year), to_type),
                        offset=xml_text_to_value(transition.find('{%s}TimeOffset' % TNS).text, datetime.timedelta),
                        iso_month=xml_text_to_value(transition.find('{%s}Month' % TNS).text, int),
                        iso_weekday=WEEKDAY_NAMES.index(transition.find('{%s}DayOfWeek' % TNS).text) + 1,
                        occurrence=occurrence,
                    ))
        return tz_transitions_groups

    @staticmethod
    def _get_transitions(timezonedef):
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
        return tz_transitions
