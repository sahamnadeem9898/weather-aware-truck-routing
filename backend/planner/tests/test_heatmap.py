from datetime import timedelta

from django.test import SimpleTestCase

from planner.services import heatmap
from planner.services.geo import flat_miles

from .helpers import DEPARTURE, FakeForecast, sample, straight_route


class CorridorGridTests(SimpleTestCase):
    def test_points_stay_inside_the_corridor_and_under_the_cap(self):
        route = straight_route(600)
        points, step = heatmap.corridor_grid([route.coords])
        self.assertGreater(len(points), 30)
        self.assertLessEqual(len(points), heatmap.MAX_POINTS)
        self.assertIn(step, heatmap.STEP_OPTIONS_DEG)
        for point in points:
            nearest = min(flat_miles(point, c) for c in route.coords)
            self.assertLessEqual(nearest, heatmap.CORRIDOR_HALF_WIDTH_MI + 8)

    def test_grid_covers_every_route(self):
        north, south = straight_route(300, lat=40.0), straight_route(300, lat=36.0)
        points, _ = heatmap.corridor_grid([north.coords, south.coords])
        lats = [lat for _, lat in points]
        self.assertGreater(max(lats), 39.5)
        self.assertLess(min(lats), 36.5)


class FrameTests(SimpleTestCase):
    def test_one_frame_per_hour_from_0_to_48(self):
        points = [(-100.0, 35.0), (-99.5, 35.0)]
        frames = heatmap.build_frames(points, FakeForecast(), DEPARTURE, 20_000)
        for key in ("wind", "rain", "snow", "level"):
            self.assertEqual(len(frames[key]), 49)
            self.assertEqual(len(frames[key][0]), len(points))

    def test_frame_n_is_the_weather_n_hours_after_departure(self):
        def by_hour(lat, lon, when):
            return sample(wind=(when - DEPARTURE) / timedelta(hours=1))

        frames = heatmap.build_frames([(-100.0, 35.0)], FakeForecast(by_hour), DEPARTURE, 20_000)
        self.assertEqual(frames["wind"][0], [0.0])
        self.assertEqual(frames["wind"][30], [30.0])
        self.assertEqual(frames["level"][30], [1])  # 30 mph is Moderate

    def test_levels_apply_the_load_rules(self):
        windy = FakeForecast(lambda lat, lon, when: sample(wind=40))
        light = heatmap.build_frames([(-100.0, 35.0)], windy, DEPARTURE, 25_000)
        heavy = heatmap.build_frames([(-100.0, 35.0)], windy, DEPARTURE, 42_000)
        self.assertEqual(light["level"][0], [2])
        self.assertEqual(heavy["level"][0], [3])
