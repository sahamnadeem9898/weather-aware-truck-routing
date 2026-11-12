from django.test import SimpleTestCase

from planner.services.recommend import RouteSummary, build_segments, explain, rank, summarize
from planner.services.risk import Level

HOUR = 3600


def summary(route_id, *, no_travel=0.0, severe=0.0, high=0.0, avg=0.0, hours=10.0) -> RouteSummary:
    miles = (500.0, 0.0, high, severe, no_travel)
    worst = max((lvl for lvl in Level if miles[lvl] > 0), default=Level.LOW)
    return RouteSummary(route_id, hours * HOUR, miles, avg, worst)


def order(*summaries) -> str:
    return "".join(s.route_id for s in rank(list(summaries)))


class SegmentTests(SimpleTestCase):
    def test_segment_takes_the_worse_of_its_two_checkpoints(self):
        segments = build_segments(
            [0, 25, 50, 60], [Level.LOW, Level.HIGH, Level.LOW, Level.MODERATE]
        )
        self.assertEqual([s.level for s in segments], [Level.HIGH, Level.HIGH, Level.MODERATE])
        self.assertEqual([s.miles for s in segments], [25, 25, 10])

    def test_summary_adds_miles_per_level_and_weights_average_by_miles(self):
        segments = build_segments([0, 30, 40], [Level.LOW, Level.LOW, Level.SEVERE])
        result = summarize("A", 2 * HOUR, segments)
        self.assertEqual(result.miles_by_level, (30, 0, 0, 10, 0))
        self.assertAlmostEqual(result.avg_risk, (30 * 0 + 10 * 3) / 40)
        self.assertEqual(result.worst_level, Level.SEVERE)
        self.assertFalse(result.has_no_travel)


class RankingTests(SimpleTestCase):
    def test_fewest_severe_miles_wins_even_if_slower_and_more_high_miles(self):
        a = summary("A", severe=42, hours=8)
        b = summary("B", severe=0, high=200, avg=1.5, hours=12)
        self.assertEqual(order(a, b), "BA")

    def test_equal_severe_miles_so_high_miles_decide(self):
        a = summary("A", severe=10, high=50, hours=8)
        b = summary("B", severe=10, high=20, avg=2.0, hours=12)
        self.assertEqual(order(a, b), "BA")

    def test_equal_severe_and_high_so_average_risk_decides(self):
        a = summary("A", avg=0.60, hours=8)
        b = summary("B", avg=0.40, hours=12)
        self.assertEqual(order(a, b), "BA")

    def test_equal_everything_so_travel_time_decides(self):
        a = summary("A", hours=11)
        b = summary("B", hours=10)
        c = summary("C", hours=10.5)
        self.assertEqual(order(a, b, c), "BCA")

    def test_no_travel_miles_rank_below_any_amount_of_severe(self):
        a = summary("A", no_travel=5, hours=8)
        b = summary("B", severe=300, hours=14)
        self.assertEqual(order(a, b), "BA")

    def test_float_noise_does_not_decide_a_ranking(self):
        a = summary("A", avg=0.2000001, hours=11)
        b = summary("B", avg=0.2000002, hours=10)
        self.assertEqual(order(a, b), "BA")

    def test_full_tie_keeps_the_routing_apis_order(self):
        self.assertEqual(order(summary("A"), summary("B")), "AB")


class ExplainTests(SimpleTestCase):
    def test_names_the_first_criterion_that_differs(self):
        best, other = summary("B", severe=0), summary("A", severe=42)
        self.assertEqual(explain(best, other), "Route B has 0 Severe miles vs 42 on Route A.")

    def test_a_closed_rival_is_called_closed(self):
        best, other = summary("B", severe=300), summary("A", no_travel=100)
        self.assertEqual(explain(best, other), "Route A is closed: 100 No Travel miles.")

    def test_falls_through_to_travel_time(self):
        best, other = summary("B", hours=10), summary("A", hours=10.5)
        self.assertEqual(
            explain(best, other), "Route B has 10 h 00 min travel time vs 10 h 30 min on Route A."
        )
