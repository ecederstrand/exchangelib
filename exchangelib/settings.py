from .ewsdatetime import UTC_NOW
from .fields import DateTimeField, MessageField, ChoiceField, Choice
from .properties import EWSElement, OutOfOffice
from .util import create_element, set_xml_value


class OofSettings(EWSElement):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/oofsettings"""
    ELEMENT_NAME = 'OofSettings'
    REQUEST_ELEMENT_NAME = 'UserOofSettings'

    ENABLED = 'Enabled'
    SCHEDULED = 'Scheduled'
    DISABLED = 'Disabled'
    FIELDS = [
        ChoiceField('state', field_uri='OofState', is_required=True,
                    choices={Choice(ENABLED), Choice(SCHEDULED), Choice(DISABLED)}),
        ChoiceField('external_audience', field_uri='ExternalAudience',
                    choices={Choice('None'), Choice('Known'), Choice('All')}, default='All'),
        DateTimeField('start', field_uri='StartTime'),
        DateTimeField('end', field_uri='EndTime'),
        MessageField('internal_reply', field_uri='InternalReply'),
        MessageField('external_reply', field_uri='ExternalReply'),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def clean(self, version=None):
        super(OofSettings, self).clean(version=version)
        if self.state == self.SCHEDULED:
            if not self.start or not self.end:
                raise ValueError("'start' and 'end' must be set when state is '%s'" % self.SCHEDULED)
            if self.start >= self.end:
                raise ValueError("'start' must be before 'end'")
            if self.end < UTC_NOW():
                raise ValueError("'end' must be in the future")
        if self.state != self.DISABLED and (not self.internal_reply or not self.external_reply):
            raise ValueError("'internal_reply' and 'external_reply' must be set when state is not '%s'" % self.DISABLED)

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {}
        for attr in ('state', 'external_audience', 'internal_reply', 'external_reply'):
            f = cls.get_field_by_fieldname(attr)
            kwargs[attr] = f.from_xml(elem=elem, account=account)
        kwargs.update(OutOfOffice.duration_to_start_end(elem=elem, account=account))
        cls._clear(elem)
        return cls(**kwargs)

    def to_xml(self, version):
        self.clean(version=version)
        elem = create_element('t:%s' % self.REQUEST_ELEMENT_NAME)
        for attr in ('state', 'external_audience'):
            value = getattr(self, attr)
            if value is None:
                continue
            f = self.get_field_by_fieldname(attr)
            set_xml_value(elem, f.to_xml(value, version=version), version=version)
        if self.start or self.end:
            duration = create_element('t:Duration')
            if self.start:
                f = self.get_field_by_fieldname('start')
                set_xml_value(duration, f.to_xml(self.start, version=version), version)
            if self.end:
                f = self.get_field_by_fieldname('end')
                set_xml_value(duration, f.to_xml(self.end, version=version), version)
            elem.append(duration)
        for attr in ('internal_reply', 'external_reply'):
            value = getattr(self, attr)
            if value is None:
                value = ''  # The value can be empty, but the XML element must always be present
            f = self.get_field_by_fieldname(attr)
            set_xml_value(elem, f.to_xml(value, version=version), version)
        return elem

    def __hash__(self):
        # Customize comparison
        if self.state == self.DISABLED:
            # All values except state are ignored by the server
            relevant_attrs = ('state',)
        elif self.state != self.SCHEDULED:
            # 'start' and 'end' values are ignored by the server, and the server always returns today's date
            relevant_attrs = tuple(f.name for f in self.FIELDS if f.name not in ('start', 'end'))
        else:
            relevant_attrs = tuple(f.name for f in self.FIELDS)
        return hash(tuple(getattr(self, attr) for attr in relevant_attrs))
