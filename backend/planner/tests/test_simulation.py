from datetime import timedelta

from django.test import SimpleTestCase

from planner.services import simulation

from .helpers import DEPARTURE, FakeForecast, straight_route


class StormDrillTests(SimpleTestCase):
    def setUp(self):
        self.route = straight_route(600, mph=60)
        self.storm = simulation.storm_on_route(FakeForecast(), self.route, DEPARTURE)
        (self.lon, self.lat), elapsed = self.route.position_at(
            self.route.distance_mi * simulation.STORM_POSITION
        )
        self.peak = DEPARTURE + timedelta(seconds=elapsed)

    def test_storm_peaks_where_and_when_the_truck_meets_it(self):
        at_peak = self.storm.at(self.lat, self.lon, self.peak)
        self.assertAlmostEqual(at_peak.wind_mph, simulation.PEAK_WIND_MPH, places=2)
        self.assertAlmostEqual(at_peak.rain_in_hr, simulation.PEAK_RAIN_IN_HR, places=2)

    def test_storm_fades_with_distance_and_time(self):
        far = self.storm.at(self.lat, self.lon + 8, self.peak)
        late = self.storm.at(self.lat, self.lon, self.peak + timedelta(hours=30))
        self.assertLess(far.wind_mph, 1)
        self.assertLess(late.wind_mph, 1)

    def test_storm_falls_as_snow_in_the_north(self):
        north = straight_route(600, lat=44.0)
        storm = simulation.storm_on_route(FakeForecast(), north, DEPARTURE)
        (lon, lat), elapsed = north.position_at(north.distance_mi * simulation.STORM_POSITION)
        at_peak = storm.at(lat, lon, DEPARTURE + timedelta(seconds=elapsed))
        self.assertAlmostEqual(at_peak.snow_in_hr, simulation.PEAK_SNOW_IN_HR, places=2)
        self.assertEqual(at_peak.rain_in_hr, 0.0)
