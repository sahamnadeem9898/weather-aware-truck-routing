from unittest.mock import patch

from django.core.cache import caches
from django.test import SimpleTestCase

from planner.services import routing
from planner.services.errors import NoRouteFound, UpstreamError

from .helpers import straight_route

ORIGIN, DESTINATION = (-100.0, 35.0), (-94.7, 35.0)


def provider(*batches):
    """A fake routing provider returning one batch of routes per call."""
    queue = list(batches)

    def call(points, alternates):
        result = queue.pop(0) if queue else []
        if isinstance(result, Exception):
            raise result
        return result

    return call


class FindRoutesTests(SimpleTestCase):
    def setUp(self):
        caches["routes"].clear()

    def test_returns_the_providers_three_alternatives(self):
        routes = [straight_route(300, lat=lat) for lat in (35.0, 35.5, 36.0)]
        with patch.object(routing, "_valhalla", provider(routes)):
            found = routing.find_routes(ORIGIN, DESTINATION)
        self.assertEqual(found, routes)

    def test_duplicate_alternatives_are_dropped_and_replaced_by_via_routes(self):
        main = straight_route(300, lat=35.0)
        twin = straight_route(300, lat=35.001)  # the same road, a few hundred feet away
        via_north = straight_route(310, lat=35.6)
        via_south = straight_route(320, lat=34.4)

        def fake(points, alternates):
            if len(points) == 2:
                return [main, twin]
            return [via_north] if points[1][1] > 35.0 else [via_south]

        with patch.object(routing, "_valhalla", fake):
            found = routing.find_routes(ORIGIN, DESTINATION)
        self.assertEqual(len(found), 3)
        self.assertIs(found[0], main)
        self.assertNotIn(twin, found)
        self.assertCountEqual(found[1:], [via_north, via_south])

    def test_absurd_detours_are_rejected(self):
        main = straight_route(300, lat=35.0)
        detour = straight_route(900, lat=37.0)

        def fake(points, alternates):
            return [main] if len(points) == 2 else [detour]

        with patch.object(routing, "_valhalla", fake):
            self.assertEqual(routing.find_routes(ORIGIN, DESTINATION), [main])

    def test_falls_back_to_osrm_when_valhalla_fails(self):
        routes = [straight_route(300, lat=lat) for lat in (35.0, 35.5, 36.0)]
        down = UpstreamError("routing", "down", http_status=503)
        with (
            patch.object(routing, "_valhalla", provider(down)),
            patch.object(routing, "_osrm", provider(routes)),
        ):
            self.assertEqual(routing.find_routes(ORIGIN, DESTINATION), routes)

    def test_no_route_from_every_provider_is_reported_as_no_route(self):
        missing = NoRouteFound("none")
        with (
            patch.object(routing, "_valhalla", provider(missing)),
            patch.object(routing, "_osrm", provider(NoRouteFound("none"))),
        ):
            with self.assertRaises(NoRouteFound):
                routing.find_routes(ORIGIN, DESTINATION)

    def test_same_origin_and_destination_is_rejected(self):
        with self.assertRaises(NoRouteFound):
            routing.find_routes(ORIGIN, ORIGIN)


class ProviderParsingTests(SimpleTestCase):
    # "_ibE_ibE_ibE_ibE" decodes (precision 6) to (0.036, 0.036) -> (0.072, 0.072).
    SHAPE = "_ibE_ibE_ibE_ibE_ibE_ibE"

    def test_valhalla_spreads_maneuver_time_along_the_shape(self):
        trip = {
            "legs": [
                {
                    "shape": self.SHAPE,
                    "maneuvers": [
                        {"begin_shape_index": 0, "end_shape_index": 1, "time": 100.0},
                        {"begin_shape_index": 1, "end_shape_index": 2, "time": 300.0},
                    ],
                }
            ]
        }
        route = routing._valhalla_trip_to_route(trip)
        self.assertEqual(route.cum_seconds, [0.0, 100.0, 400.0])
        self.assertEqual(route.duration_s, 400.0)
        _, halfway = route.position_at(
            route.cum_miles[1] + (route.cum_miles[2] - route.cum_miles[1]) / 2
        )
        self.assertAlmostEqual(halfway, 250.0)

    def test_osrm_times_are_capped_at_truck_speed(self):
        raw = {
            "geometry": self.SHAPE,
            "duration": 2.0,
            # 1 second per ~3.5 mile segment would be a very fast car.
            "legs": [{"annotation": {"duration": [1.0, 1.0]}}],
        }
        route = routing._osrm_route_to_route(raw)
        mph = route.distance_mi / (route.duration_s / 3600)
        self.assertAlmostEqual(mph, routing.TRUCK_MAX_MPH, places=3)
