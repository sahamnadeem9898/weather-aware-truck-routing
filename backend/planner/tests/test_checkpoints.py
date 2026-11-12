from django.test import SimpleTestCase

from planner.services.checkpoints import build_checkpoints

from .helpers import straight_route


class CheckpointTests(SimpleTestCase):
    def test_one_checkpoint_every_interval_plus_both_ends(self):
        route = straight_route(105)
        miles = [cp.mile for cp in build_checkpoints(route, 25)]
        self.assertEqual(miles[:-1], [0, 25, 50, 75, 100])
        self.assertAlmostEqual(miles[-1], route.distance_mi)

    def test_each_interval_option_spaces_checkpoints_evenly(self):
        route = straight_route(300.3)
        for interval in (10, 25, 50):
            with self.subTest(interval=interval):
                miles = [cp.mile for cp in build_checkpoints(route, interval)]
                gaps = [b - a for a, b in zip(miles, miles[1:], strict=False)]
                self.assertTrue(all(abs(gap - interval) < 1e-6 for gap in gaps[:-1]))
                self.assertLessEqual(gaps[-1], interval + 0.5)

    def test_no_stub_checkpoint_just_before_the_destination(self):
        route = straight_route(100.2)
        miles = [cp.mile for cp in build_checkpoints(route, 25)]
        self.assertEqual(len(miles), 5)  # 0, 25, 50, 75, destination (100 is dropped)

    def test_elapsed_time_comes_from_the_route_not_the_departure(self):
        route = straight_route(300, mph=50)
        checkpoint = build_checkpoints(route, 50)[-2]  # mile 250
        self.assertAlmostEqual(checkpoint.mile, 250)
        self.assertAlmostEqual(checkpoint.elapsed_s, 5 * 3600, delta=1)

    def test_checkpoints_lie_on_the_route(self):
        route = straight_route(200)
        for cp in build_checkpoints(route, 50):
            self.assertAlmostEqual(cp.lat, 35.0)
            self.assertGreaterEqual(cp.lon, route.coords[0][0])
            self.assertLessEqual(cp.lon, route.coords[-1][0])
