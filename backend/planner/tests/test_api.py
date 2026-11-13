from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework.exceptions import Throttled
from rest_framework.test import APIClient

from planner.services import planner
from planner.services.errors import NoRouteFound, RateLimited, UpstreamError
from planner.services.geocoding import Place
from planner.views import exception_handler

from .helpers import FakeForecast, sample, straight_route

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
BODY = {
    "origin": {"text": "Amarillo, TX", "lat": 35.0, "lon": -100.0},
    "destination": {"text": "Fort Smith, AR", "lat": 35.0, "lon": -94.7},
    "departure": "2026-11-13T08:00",  # 14:00 UTC in America/Chicago
    "load_lb": 42_000,
    "interval_mi": 50,
}
DEPARTURE_UTC = datetime(2026, 11, 13, 14, 0, tzinfo=UTC)


class PlanApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        # Route A is fastest; B and C run further north and are slower.
        self.routes = [
            straight_route(300, mph=60, lat=35.0),
            straight_route(300, mph=55, lat=36.0),
            straight_route(300, mph=50, lat=37.0),
        ]
        self.forecast = FakeForecast()

    def post(self, body=None, forecast=None):
        with (
            patch.object(planner.routing, "find_routes", return_value=self.routes),
            patch.object(planner.weather, "timezone_name", return_value="America/Chicago"),
            patch.object(planner.weather, "load_forecast", return_value=forecast or self.forecast),
            patch.object(planner, "datetime", wraps=datetime) as clock,
        ):
            clock.now.return_value = NOW
            return self.client.post("/api/plan/", body or BODY, format="json")

    def test_returns_three_routes_with_checkpoints_and_a_heatmap(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([r["id"] for r in data["routes"]], ["A", "B", "C"])
        self.assertEqual(data["departure"], "2026-11-13T14:00:00Z")
        self.assertEqual(data["timezone"], "America/Chicago")
        route = data["routes"][0]
        self.assertEqual([c["mile"] for c in route["checkpoints"]][:3], [0, 50, 100])
        self.assertEqual(len(route["segments"]), len(route["checkpoints"]) - 1)
        self.assertEqual(len(data["heatmap"]["level"]), 49)
        self.assertEqual(len(data["heatmap"]["level"][0]), len(data["heatmap"]["points"]))

    def test_calm_weather_recommends_the_fastest_route(self):
        data = self.post().json()
        self.assertEqual(data["recommendation"]["route_id"], "A")
        self.assertIn("travel time", data["recommendation"]["reasons"][0])
        self.assertIn("Fastest", data["routes"][0]["tags"])

    def test_weather_is_read_at_each_checkpoints_arrival_time(self):
        self.post()
        route_a_calls = [call for call in self.forecast.calls if call[0] == 35.0][:8]
        at_mile_250 = next(
            when for lat, lon, when in route_a_calls if abs(lon - (-100 + 250 / 56.66)) < 0.05
        )
        # 250 miles at 60 mph is 4 h 10 min after the 14:00 UTC departure.
        self.assertAlmostEqual(
            (at_mile_250 - DEPARTURE_UTC).total_seconds(), 250 / 60 * 3600, delta=60
        )

    def test_storm_that_arrives_later_only_hits_the_route_that_is_there_then(self):
        # Severe wind along latitude 35 (route A), but only from 3 hours after departure.
        def late_storm(lat, lon, when):
            stormy = abs(lat - 35.0) < 0.3 and when >= DEPARTURE_UTC + timedelta(hours=3)
            return sample(wind=50 if stormy else 5)

        data = self.post(forecast=FakeForecast(late_storm)).json()
        route_a = data["routes"][0]
        levels = {c["mile"]: c["level"] for c in route_a["checkpoints"]}
        self.assertEqual(levels[150], 0)  # reached at 2 h 30 min: before the storm
        self.assertEqual(levels[200], 4)  # reached at 3 h 20 min: 50 mph + 42,000 lb = No Travel
        self.assertTrue(route_a["has_no_travel"])
        self.assertEqual(data["recommendation"]["route_id"], "B")
        self.assertIn("Route A is closed", " ".join(data["recommendation"]["reasons"]))

    def test_lighter_load_changes_the_level_and_the_pick(self):
        def windy_on_a(lat, lon, when):
            return sample(wind=40 if abs(lat - 35.0) < 0.3 else 5)

        heavy = self.post(forecast=FakeForecast(windy_on_a)).json()
        light = self.post({**BODY, "load_lb": 25_000}, FakeForecast(windy_on_a)).json()
        self.assertEqual(heavy["routes"][0]["worst_level"], 3)  # Severe by the load rule
        self.assertEqual(light["routes"][0]["worst_level"], 2)  # High
        self.assertEqual(heavy["recommendation"]["route_id"], "B")
        self.assertEqual(light["recommendation"]["route_id"], "B")  # still fewer High miles

    def test_a_closed_route_is_never_recommended_and_says_how_long_to_wait(self):
        # No Travel wind on route A for the first 8 hours; B and C stay calm.
        clears = DEPARTURE_UTC + timedelta(hours=8)

        def weather(lat, lon, when):
            return sample(wind=60 if abs(lat - 35.0) < 0.3 and when < clears else 5)

        data = self.post(forecast=FakeForecast(weather)).json()
        route_a, route_b = data["routes"][0], data["routes"][1]
        self.assertTrue(route_a["has_no_travel"])
        self.assertEqual(route_a["rank"], 3)
        self.assertEqual(route_a["wait"]["hours"], 8)
        self.assertEqual(route_a["wait"]["departure"], "2026-11-13T22:00:00Z")
        self.assertEqual(route_a["wait"]["departure_local"], "2026-11-13T16:00")
        self.assertIsNone(route_b["wait"])
        self.assertEqual(data["recommendation"]["route_id"], "B")
        self.assertIsNone(data["recommendation"]["wait"])
        self.assertIn("Route A is closed", " ".join(data["recommendation"]["reasons"]))

    def test_every_route_closed_means_no_recommendation_only_a_wait(self):
        # Gale everywhere for 5 hours, and for 9 hours on routes A and B.
        def weather(lat, lon, when):
            hours = 9 if lat < 36.5 else 5
            return sample(wind=60 if when < DEPARTURE_UTC + timedelta(hours=hours) else 5)

        data = self.post(forecast=FakeForecast(weather)).json()
        recommendation = data["recommendation"]
        self.assertTrue(recommendation["no_safe_route"])
        self.assertIsNone(recommendation["route_id"])
        self.assertEqual(recommendation["reasons"], [])
        # Route C opens first, so that is the wait the driver is told about.
        self.assertEqual(recommendation["wait"]["route_id"], "C")
        self.assertEqual(recommendation["wait"]["hours"], 5)
        self.assertTrue(all(route["has_no_travel"] for route in data["routes"]))

    def test_no_wait_is_offered_when_nothing_clears_in_the_forecast(self):
        gale = FakeForecast(lambda lat, lon, when: sample(wind=60))
        data = self.post(forecast=gale).json()
        self.assertIsNone(data["recommendation"]["route_id"])
        self.assertIsNone(data["recommendation"]["wait"])
        self.assertTrue(all(route["wait"] is None for route in data["routes"]))

    def test_storm_drill_is_flagged_and_raises_risk(self):
        data = self.post({**BODY, "simulate_storm": True}).json()
        self.assertTrue(data["simulated"])
        self.assertGreater(data["routes"][0]["worst_level"], 0)

    def test_storm_drill_stays_put_when_the_driver_leaves_later(self):
        first = self.post({**BODY, "simulate_storm": True}).json()
        wait = first["routes"][0]["wait"]
        self.assertTrue(first["routes"][0]["has_no_travel"])
        self.assertEqual(first["storm_anchor"], BODY["departure"])
        later = self.post(
            {
                **BODY,
                "simulate_storm": True,
                "departure": wait["departure_local"],
                "storm_anchor": first["storm_anchor"],
            }
        ).json()
        # Leaving when the app said to, against the same storm, route A is open.
        self.assertFalse(later["routes"][0]["has_no_travel"])
        self.assertEqual(later["storm_anchor"], BODY["departure"])

    def test_invalid_input_gets_a_readable_message(self):
        cases = [
            ({**BODY, "interval_mi": 30}, "interval_mi"),
            ({**BODY, "load_lb": -5}, "load_lb"),
            ({**BODY, "departure": "tomorrow"}, "departure"),
            ({**BODY, "origin": {"text": ""}}, "origin.text"),
        ]
        for body, field in cases:
            with self.subTest(field=field):
                response = self.post(body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_input")
                self.assertIn(field, response.json()["detail"])

    def test_absurd_dates_are_a_clear_error_not_a_crash(self):
        cases = [
            {**BODY, "departure": "9999-12-31T23:00"},
            {**BODY, "simulate_storm": True, "storm_anchor": "9999-12-31T23:00"},
            {**BODY, "simulate_storm": True, "storm_anchor": "2026-01-01T00:00"},
        ]
        for body in cases:
            with self.subTest(body=body):
                response = self.post(body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "invalid_trip")

    def test_unknown_timezone_falls_back_to_utc_and_says_so(self):
        with patch.object(planner.weather, "timezone_name", return_value="Mars/Olympus_Mons"):
            with (
                patch.object(planner.routing, "find_routes", return_value=self.routes),
                patch.object(planner.weather, "load_forecast", return_value=self.forecast),
                patch.object(planner, "datetime", wraps=datetime) as clock,
            ):
                clock.now.return_value = NOW
                data = self.client.post("/api/plan/", BODY, format="json").json()
        self.assertEqual(data["timezone"], "UTC")
        self.assertEqual(data["departure"], "2026-11-13T08:00:00Z")

    def test_departure_outside_the_forecast_window_is_rejected(self):
        for departure in ("2026-11-10T08:00", "2026-12-20T08:00"):
            with self.subTest(departure=departure):
                response = self.post({**BODY, "departure": departure})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "invalid_trip")

    def test_free_text_places_are_geocoded(self):
        place = Place("Amarillo, Texas, US", 35.0, -100.0)
        body = {**BODY, "origin": {"text": "Amarillo"}}
        with patch("planner.views.geocoding.resolve", return_value=place) as resolve:
            data = self.post(body).json()
        resolve.assert_called_once_with("Amarillo")
        self.assertEqual(data["origin"]["label"], "Amarillo, Texas, US")


class ErrorApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def post_with(self, **patches):
        with (
            patch.object(planner.weather, "timezone_name", return_value="America/Chicago"),
            patch.object(planner, "datetime", wraps=datetime) as clock,
            patch.multiple(planner.routing, **patches),
        ):
            clock.now.return_value = NOW
            return self.client.post("/api/plan/", BODY, format="json")

    def test_no_route(self):
        response = self.post_with(
            find_routes=lambda *a: (_ for _ in ()).throw(NoRouteFound("No drivable route."))
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"code": "no_route", "detail": "No drivable route."})

    def test_upstream_failure(self):
        error = UpstreamError("routing", "Routing services are unavailable right now.")
        response = self.post_with(find_routes=lambda *a: (_ for _ in ()).throw(error))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["code"], "upstream_error")

    def test_rate_limit_tells_the_client_when_to_retry(self):
        error = RateLimited("weather", "The weather service is busy.", retry_after=60)
        response = self.post_with(find_routes=lambda *a: (_ for _ in ()).throw(error))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "rate_limited")
        self.assertEqual(response.json()["retry_after"], 60)
        self.assertEqual(response["Retry-After"], "60")

    def test_a_brief_outage_tells_the_client_to_retry_soon(self):
        error = UpstreamError("weather", "Not responding.", http_status=525, retry_after=5)
        response = self.post_with(find_routes=lambda *a: (_ for _ in ()).throw(error))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["retry_after"], 5)
        self.assertEqual(response["Retry-After"], "5")

    def test_health_check_answers_whatever_the_host(self):
        response = self.client.get("/api/health/", HTTP_HOST="10.0.0.5:10000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_unknown_place(self):
        with (
            patch("planner.services.geocoding.suggest", return_value=[]),
            patch("planner.services.geocoding._nominatim", return_value=None),
        ):
            response = self.client.post(
                "/api/plan/", {**BODY, "origin": {"text": "Zzyzxqq"}}, format="json"
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "place_not_found")

    def test_both_geocoders_down_is_an_outage_not_a_spelling_mistake(self):
        down = UpstreamError("geocoding", "down", http_status=503)
        with (
            patch("planner.services.geocoding.suggest", side_effect=down),
            patch("planner.services.geocoding._nominatim", side_effect=down),
        ):
            response = self.client.post(
                "/api/plan/", {**BODY, "origin": {"text": "Amarillo"}}, format="json"
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["code"], "upstream_error")

    def test_malformed_json_gets_the_standard_error_shape(self):
        response = self.client.post("/api/plan/", "{oops", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"code": "invalid_input", "detail": "The request body is not valid JSON."},
        )

    def test_throttled_and_unexpected_errors_get_the_standard_shape(self):
        throttled = exception_handler(Throttled(wait=12.3), {})
        self.assertEqual(throttled.status_code, 429)
        self.assertEqual(throttled.data["code"], "throttled")
        self.assertEqual(throttled["Retry-After"], "13")
        with self.assertLogs("planner.views", level="ERROR"):
            crashed = exception_handler(KeyError("hourly"), {})
        self.assertEqual(crashed.status_code, 500)
        self.assertEqual(crashed.data["code"], "server_error")
        self.assertNotIn("hourly", crashed.data["detail"])

    def test_geocode_endpoint(self):
        places = [Place("Denver, Colorado, US", 39.74, -104.98)]
        with patch("planner.views.geocoding.suggest", return_value=places):
            response = self.client.get("/api/geocode/", {"q": "den"})
        self.assertEqual(response.json()["results"][0]["label"], "Denver, Colorado, US")
