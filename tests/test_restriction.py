import datetime
import zoneinfo

from exchangelib.folders import Calendar, Root
from exchangelib.queryset import Q
from exchangelib.restriction import Restriction
from exchangelib.util import xml_to_str
from exchangelib.version import EXCHANGE_2007, Build, Version

from .common import TimedTestCase, mock_account, mock_protocol


class RestrictionTest(TimedTestCase):
    def test_magic(self):
        self.assertEqual(str(Q()), "Q()")

    def test_q(self):
        version = Version(build=EXCHANGE_2007)
        account = mock_account(version=version, protocol=mock_protocol(version=version, service_endpoint="example.com"))
        root = Root(account=account)
        tz = zoneinfo.ZoneInfo("Europe/Copenhagen")
        start = datetime.datetime(2020, 9, 26, 8, 0, 0, tzinfo=tz)
        end = datetime.datetime(2020, 9, 26, 11, 0, 0, tzinfo=tz)
        result = """\
<m:Restriction xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
    <t:And xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
        <t:Or>
            <t:Contains ContainmentMode="Substring" ContainmentComparison="Exact">
                <t:FieldURI FieldURI="item:Categories"/>
                <t:Constant Value="FOO"/>
            </t:Contains>
            <t:Contains ContainmentMode="Substring" ContainmentComparison="Exact">
                <t:FieldURI FieldURI="item:Categories"/>
                <t:Constant Value="BAR"/>
            </t:Contains>
        </t:Or>
        <t:IsGreaterThan>
            <t:FieldURI FieldURI="calendar:End"/>
            <t:FieldURIOrConstant>
                <t:Constant Value="2020-09-26T08:00:00+02:00"/>
            </t:FieldURIOrConstant>
        </t:IsGreaterThan>
        <t:IsLessThan>
            <t:FieldURI FieldURI="calendar:Start"/>
            <t:FieldURIOrConstant>
                <t:Constant Value="2020-09-26T11:00:00+02:00"/>
            </t:FieldURIOrConstant>
        </t:IsLessThan>
    </t:And>
</m:Restriction>"""
        q = Q(Q(categories__contains="FOO") | Q(categories__contains="BAR"), start__lt=end, end__gt=start)
        r = Restriction(q, folders=[Calendar(root=root)], applies_to=Restriction.ITEMS)
        self.assertEqual(str(r), "".join(s.lstrip() for s in result.split("\n")))
        # Test empty Q
        q = Q()
        self.assertEqual(q.to_xml(folders=[Calendar()], version=version, applies_to=Restriction.ITEMS), None)
        with self.assertRaises(ValueError):
            Restriction(q, folders=[Calendar(root=root)], applies_to=Restriction.ITEMS)
        # Test validation
        with self.assertRaises(ValueError):
            Q(datetime_created__range=(1,))  # Must have exactly 2 args
        with self.assertRaises(ValueError):
            Q(datetime_created__range=(1, 2, 3))  # Must have exactly 2 args
        with self.assertRaises(TypeError):
            Q(datetime_created=Build(15, 1)).clean(version=Version(build=EXCHANGE_2007))  # Must be serializable
        with self.assertRaises(ValueError):
            # Must be a timezone-aware datetime
            Q(datetime_created=datetime.datetime(2017, 1, 1)).clean(version=Version(build=EXCHANGE_2007))
        with self.assertRaises(ValueError):
            Q(categories__contains=[[1, 2], [3, 4]]).clean(version=Version(build=EXCHANGE_2007))  # Must be single value

    def test_q_expr(self):
        self.assertEqual(Q().expr(), None)
        self.assertEqual((~Q()).expr(), None)
        self.assertEqual(Q(x=5).expr(), "x == 5")
        self.assertEqual((~Q(x=5)).expr(), "x != 5")
        q = (Q(b__contains="a", x__contains=5) | Q(~Q(a__contains="c"), f__gt=3, c=6)) & ~Q(y=9, z__contains="b")
        self.assertEqual(
            str(q),  # str() calls expr()
            "((b contains 'a' AND x contains 5) OR (NOT a contains 'c' AND c == 6 AND f > 3)) "
            "AND NOT (y == 9 AND z contains 'b')",
        )
        self.assertEqual(
            repr(q),
            "Q('AND', Q('OR', Q('AND', Q(b contains 'a'), Q(x contains 5)), Q('AND', Q('NOT', Q(a contains 'c')), "
            "Q(c == 6), Q(f > 3))), Q('NOT', Q('AND', Q(y == 9), Q(z contains 'b'))))",
        )
        # Test simulated IN expression
        in_q = Q(foo__in=[1, 2, 3])
        self.assertEqual(in_q.conn_type, Q.OR)
        self.assertEqual(len(in_q.children), 3)

    def test_q_inversion(self):
        version = Version(build=EXCHANGE_2007)
        account = mock_account(version=version, protocol=mock_protocol(version=version, service_endpoint="example.com"))
        root = Root(account=account)
        self.assertEqual((~Q(foo=5)).op, Q.NE)
        self.assertEqual((~Q(foo__not=5)).op, Q.EQ)
        self.assertEqual((~Q(foo__lt=5)).op, Q.GTE)
        self.assertEqual((~Q(foo__lte=5)).op, Q.GT)
        self.assertEqual((~Q(foo__gt=5)).op, Q.LTE)
        self.assertEqual((~Q(foo__gte=5)).op, Q.LT)
        # Test not not Q on a non-leaf
        self.assertEqual(Q(foo__contains=("bar", "baz")).conn_type, Q.AND)
        self.assertEqual((~Q(foo__contains=("bar", "baz"))).conn_type, Q.NOT)
        self.assertEqual((~~Q(foo__contains=("bar", "baz"))).conn_type, Q.AND)
        self.assertEqual(Q(foo__contains=("bar", "baz")), ~~Q(foo__contains=("bar", "baz")))
        # Test generated XML of 'Not' statement when there is only one child. Skip 't:And' between 't:Not' and 't:Or'.
        result = """\
<m:Restriction xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
    <t:Not xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
        <t:Or>
            <t:IsEqualTo>
                <t:FieldURI FieldURI="item:Subject"/>
                <t:FieldURIOrConstant>
                    <t:Constant Value="bar"/>
                </t:FieldURIOrConstant>
            </t:IsEqualTo>
            <t:IsEqualTo>
                <t:FieldURI FieldURI="item:Subject"/>
                <t:FieldURIOrConstant>
                    <t:Constant Value="baz"/>
                </t:FieldURIOrConstant>
            </t:IsEqualTo>
        </t:Or>
    </t:Not>
</m:Restriction>"""
        q = ~(Q(subject="bar") | Q(subject="baz"))
        self.assertEqual(
            xml_to_str(q.to_xml(folders=[Calendar(root=root)], version=version, applies_to=Restriction.ITEMS)),
            "".join(s.lstrip() for s in result.split("\n")),
        )

    def test_q_boolean_ops(self):
        self.assertEqual((Q(foo=5) & Q(foo=6)).conn_type, Q.AND)
        self.assertEqual((Q(foo=5) | Q(foo=6)).conn_type, Q.OR)

    def test_q_failures(self):
        with self.assertRaises(ValueError):
            # Invalid value
            Q(foo=None).clean(version=Version(build=EXCHANGE_2007))

    def test_q_never(self):
        # Tests Q with conn_type NEVER. This is for cases where the user makes queries that would return an empty
        # result, but the server does not support this type of query. The only example so far is 'foo__in=[]' which
        # should always match nothing.
        self.assertEqual(Q(foo__in=[]), Q(conn_type=Q.NEVER))  # __in with empty sequence should translate to NEVER
        self.assertTrue(Q(foo__in=[]).is_never())  # Test the flag
        self.assertEqual(~Q(foo__in=[]), Q())  # Negation should translate to the no-op
        self.assertTrue(~Q(foo__in=[]).is_empty())  # Negation should translate to a no-op

        # Test in combination with AND and OR
        self.assertEqual(Q(foo__in=[], bar="baz"), Q(conn_type=Q.NEVER))  # NEVER removes all other args
        self.assertEqual(Q(foo__in=[]) & Q(bar="baz"), Q(conn_type=Q.NEVER))  # NEVER removes all other args
        self.assertEqual(Q(foo__in=[]) | Q(bar="baz"), Q(bar="baz"))  # OR removes all 'never' args

    def test_q_simplification(self):
        self.assertEqual(Q(foo="bar") & Q(), Q(foo="bar"))
        self.assertEqual(Q() & Q(foo="bar"), Q(foo="bar"))

        self.assertEqual(Q("foo") & Q(), Q("foo"))
        self.assertEqual(Q() & Q("foo"), Q("foo"))

    def test_q_querystring(self):
        self.assertEqual(Q("this is a QS").expr(), "this is a QS")
        self.assertEqual(Q(Q("this is a QS")), Q("this is a QS"))
        self.assertEqual(Q(Q(Q(Q("this is a QS")))), Q("this is a QS"))

        with self.assertRaises(ValueError):
            Q("this is a QS") & Q(foo="bar")
        with self.assertRaises(TypeError):
            Q(5)
