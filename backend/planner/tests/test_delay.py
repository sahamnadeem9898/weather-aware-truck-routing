from datetime import timedelta

from django.test import SimpleTestCase

from planner.services.checkpoints import build_checkpoints
from planner.services.delay import MAX_WAIT_HOURS, hours_until_clear
from planner.services.weather import ForecastUnavailable

from .helpers import DEPARTURE, FakeForecast, sample, straight_route


class HoursUntilClearTests(SimpleTestCase):
    def setUp(self):
        # 300 miles at 60 mph: the truck is on the road for 5 hours.
        self.checkpoints = build_checkpoints(straight_route(300, mph=60), 50)

    def wait(self, weather, load=20_000):
        return hours_until_clear(self.checkpoints, FakeForecast(weather), DEPARTURE, load)

    def test_waits_until_the_whole_drive_misses_the_storm(self):
        # 60 mph wind everywhere until 6 hours after the planned departure.
        storm_ends = DEPARTURE + timedelta(hours=6)
        self.assertEqual(
            self.wait(lambda lat, lon, when: sample(wind=60 if when < storm_ends else 5)), 6
        )

    def test_a_storm_ahead_on_the_road_counts_at_the_delayed_arrival_time(self):
        # Wind only at the destination (reached 5 h in), ending at hour 7.5.
        # Leaving 2 h late arrives at hour 7, still in it; 3 h late arrives at hour 8.
        end_lon = self.checkpoints[-1].lon
        storm_ends = DEPARTURE + timedelta(hours=7.5)

        def weather(lat, lon, when):
            return sample(wind=60 if abs(lon - end_lon) < 0.3 and when < storm_ends else 5)

        self.assertEqual(self.wait(weather), 3)

    def test_load_rules_apply_to_the_wait(self):
        # 50 mph is Severe for a light load (passable) but No Travel above 30,000 lb.
        storm_ends = DEPARTURE + timedelta(hours=4)

        def weather(lat, lon, when):
            return sample(wind=50 if when < storm_ends else 5)

        self.assertEqual(self.wait(weather, load=42_000), 4)
        self.assertEqual(self.wait(weather, load=20_000), 1)

    def test_none_when_it_never_clears(self):
        self.assertIsNone(self.wait(lambda lat, lon, when: sample(wind=60)))

    def test_none_when_the_forecast_runs_out(self):
        def weather(lat, lon, when):
            if when > DEPARTURE + timedelta(hours=10):
                raise ForecastUnavailable(when)
            return sample(wind=60)

        self.assertIsNone(self.wait(weather))

    def test_search_is_bounded(self):
        forecast = FakeForecast(lambda lat, lon, when: sample(wind=60))
        hours_until_clear(self.checkpoints[:1], forecast, DEPARTURE, 20_000)
        self.assertEqual(len(forecast.calls), MAX_WAIT_HOURS)
