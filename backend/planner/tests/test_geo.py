from django.test import SimpleTestCase

from planner.services.geo import (
    cumulative_miles,
    decode_polyline,
    haversine_miles,
    interpolate_along,
    simplify,
)

DALLAS = (-96.797, 32.7767)
DENVER = (-104.9903, 39.7392)


class GeoTests(SimpleTestCase):
    def test_haversine_matches_a_known_distance(self):
        self.assertAlmostEqual(haversine_miles(DALLAS, DENVER), 663, delta=3)

    def test_decode_polyline(self):
        # Reference example from the polyline format documentation (precision 5).
        coords = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
        self.assertEqual(coords, [(-120.2, 38.5), (-120.95, 40.7), (-126.453, 43.252)])

    def test_interpolate_along_finds_the_midpoint(self):
        coords = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        cum = cumulative_miles(coords)
        point, index, fraction = interpolate_along(coords, cum, cum[-1] * 0.75)
        self.assertAlmostEqual(point[0], 1.5, places=5)
        self.assertEqual(index, 1)
        self.assertAlmostEqual(fraction, 0.5, places=5)

    def test_interpolate_along_clamps_past_the_end(self):
        coords = [(0.0, 0.0), (1.0, 0.0)]
        point, _, _ = interpolate_along(coords, cumulative_miles(coords), 1e9)
        self.assertEqual(point, (1.0, 0.0))

    def test_simplify_drops_collinear_points_and_keeps_corners(self):
        line = [(0.0, 0.0), (1.0, 0.00001), (2.0, 0.0), (2.0, 1.0)]
        self.assertEqual(simplify(line, 0.001), [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0)])
