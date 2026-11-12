from django.test import SimpleTestCase

from planner.services.risk import Level, assess, overall_level

LIGHT, MEDIUM_EDGE, HEAVY_EDGE = 10_000, 30_000, 40_000


def level(wind=0.0, rain=0.0, snow=0.0, load=LIGHT) -> Level:
    return assess(wind, rain, snow, load).level


class WindBandTests(SimpleTestCase):
    def test_every_band_edge(self):
        cases = [
            (0, Level.LOW), (24.9, Level.LOW),
            (25, Level.MODERATE), (34.9, Level.MODERATE),
            (35, Level.HIGH), (44.9, Level.HIGH),
            (45, Level.SEVERE), (54.9, Level.SEVERE),
            (55, Level.NO_TRAVEL), (90, Level.NO_TRAVEL),
        ]  # fmt: skip
        for wind, expected in cases:
            with self.subTest(wind=wind):
                self.assertEqual(level(wind=wind), expected)


class RainBandTests(SimpleTestCase):
    def test_every_band_edge(self):
        cases = [
            (0.09, Level.LOW),
            (0.10, Level.MODERATE), (0.24, Level.MODERATE),
            (0.25, Level.HIGH), (0.49, Level.HIGH),
            (0.50, Level.SEVERE),
            (1.00, Level.SEVERE),  # the brief says No Travel is strictly > 1.00
            (1.01, Level.NO_TRAVEL),
        ]  # fmt: skip
        for rain, expected in cases:
            with self.subTest(rain=rain):
                self.assertEqual(level(rain=rain), expected)


class SnowBandTests(SimpleTestCase):
    def test_every_band_edge(self):
        cases = [
            (0.4, Level.LOW),
            (0.5, Level.MODERATE), (0.9, Level.MODERATE),
            (1.0, Level.HIGH), (1.9, Level.HIGH),
            (2.0, Level.SEVERE),
            (3.0, Level.SEVERE),  # the brief says No Travel is strictly > 3.0
            (3.1, Level.NO_TRAVEL),
        ]  # fmt: skip
        for snow, expected in cases:
            with self.subTest(snow=snow):
                self.assertEqual(level(snow=snow), expected)


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(level(wind=55, load=0), Level.NO_TRAVEL)
        self.assertEqual(level(wind=55, load=80_000), Level.NO_TRAVEL)

    def test_45_to_54_mph_is_no_travel_only_above_30000_lb(self):
        self.assertEqual(level(wind=46, load=MEDIUM_EDGE), Level.SEVERE)
        self.assertEqual(level(wind=46, load=MEDIUM_EDGE + 1), Level.NO_TRAVEL)
        self.assertEqual(level(wind=54.9, load=MEDIUM_EDGE + 1), Level.NO_TRAVEL)

    def test_35_to_44_mph_is_severe_only_above_40000_lb(self):
        self.assertEqual(level(wind=40, load=HEAVY_EDGE), Level.HIGH)
        self.assertEqual(level(wind=40, load=HEAVY_EDGE + 1), Level.SEVERE)
        self.assertEqual(level(wind=44.9, load=HEAVY_EDGE + 1), Level.SEVERE)

    def test_load_does_not_change_wind_below_35_mph(self):
        self.assertEqual(level(wind=34.9, load=80_000), Level.MODERATE)

    def test_load_does_not_change_rain_or_snow(self):
        self.assertEqual(level(rain=0.3, load=80_000), Level.HIGH)
        self.assertEqual(level(snow=1.5, load=80_000), Level.HIGH)

    def test_assessment_reports_when_a_load_rule_decided_the_level(self):
        self.assertTrue(assess(40, 0, 0, 42_000).load_rule_applied)
        self.assertFalse(assess(40, 0, 0, 25_000).load_rule_applied)
        # Rain already makes it No Travel, so the Severe-by-load wind is not the driver.
        self.assertFalse(assess(40, 1.5, 0, 42_000).load_rule_applied)


class OverallLevelTests(SimpleTestCase):
    def test_matches_assess_everywhere(self):
        for wind in (0, 25, 35, 40, 45, 50, 55):
            for rain in (0, 0.1, 0.3, 0.6, 1.2):
                for snow in (0, 0.5, 1.5, 2.5, 3.5):
                    for load in (20_000, 35_000, 45_000):
                        with self.subTest(wind=wind, rain=rain, snow=snow, load=load):
                            self.assertEqual(
                                overall_level(wind, rain, snow, load),
                                assess(wind, rain, snow, load).level,
                            )


class CombinedTests(SimpleTestCase):
    def test_level_is_the_worst_of_wind_rain_and_snow(self):
        self.assertEqual(level(wind=26, rain=0.3, snow=2.5), Level.SEVERE)
        self.assertEqual(level(wind=50, rain=0.05, snow=0.0), Level.SEVERE)
        self.assertEqual(level(wind=10, rain=0.6, snow=0.0), Level.SEVERE)

    def test_reason_names_the_driving_condition(self):
        self.assertIn("rain 0.60 in/hr", assess(10, 0.6, 0, LIGHT).reason)
        reason = assess(40, 0, 0, 42_000).reason
        self.assertIn("wind 40 mph", reason)
        self.assertIn("over 40,000 lb", reason)
