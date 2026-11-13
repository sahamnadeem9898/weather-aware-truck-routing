from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from planner.services import weather
from planner.services.errors import RateLimited, UpstreamError

MIDNIGHT = datetime(2026, 11, 13, tzinfo=UTC)
T0 = int(MIDNIGHT.timestamp())


def open_meteo_location(wind_by_hour: list[float | None]) -> dict:
    """A one-day Open-Meteo response body for a single location."""
    n = len(wind_by_hour)
    return {
        "hourly": {
            "time": [T0 + 3600 * i for i in range(n)],
            "wind_speed_10m": wind_by_hour,
            "wind_gusts_10m": [None if w is None else w + 10 for w in wind_by_hour],
            "rain": [0.1] * n,
            "showers": [0.05] * n,
            "snowfall": [0.0] * n,
        }
    }


class WeatherTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def load(self, cells, response, hours=5):
        with patch.object(weather, "request_json_failover", return_value=response) as http:
            forecast = weather.load_forecast(cells, MIDNIGHT, MIDNIGHT + timedelta(hours=hours))
        return forecast, http

    def test_requests_the_units_the_risk_table_uses(self):
        _, http = self.load([(35.0, -100.0)], open_meteo_location([5.0] * 24))
        params = http.call_args.kwargs["params"]
        self.assertEqual(params["wind_speed_unit"], "mph")
        self.assertEqual(params["precipitation_unit"], "inch")
        self.assertEqual(params["timezone"], "GMT")

    def test_lookup_uses_the_hour_of_the_requested_time(self):
        forecast, _ = self.load(
            [(35.0, -100.0)], open_meteo_location([float(h) for h in range(24)])
        )
        self.assertEqual(forecast.at(35.0, -100.0, MIDNIGHT + timedelta(hours=7)).wind_mph, 7.0)
        # 9:40 is closer to 10:00 than to 9:00.
        self.assertEqual(
            forecast.at(35.0, -100.0, MIDNIGHT + timedelta(hours=9, minutes=40)).wind_mph, 10.0
        )

    def test_rain_is_rain_plus_showers(self):
        forecast, _ = self.load([(35.0, -100.0)], open_meteo_location([5.0] * 24))
        self.assertAlmostEqual(forecast.at(35.0, -100.0, MIDNIGHT).rain_in_hr, 0.15)

    def test_nearby_points_share_one_cell(self):
        self.assertEqual(weather.cell_for(35.04, -100.04), weather.cell_for(34.96, -99.96))

    def test_batches_all_cells_into_one_request(self):
        cells = [(35.0, -100.0), (35.1, -100.0), (35.2, -100.0)]
        _, http = self.load(cells, [open_meteo_location([5.0] * 24)] * 3)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(http.call_args.kwargs["params"]["latitude"], "35.0,35.1,35.2")

    def test_second_load_is_served_from_cache(self):
        self.load([(35.0, -100.0)], open_meteo_location([5.0] * 24))
        _, http = self.load([(35.0, -100.0)], open_meteo_location([5.0] * 24))
        http.assert_not_called()

    def test_time_outside_the_forecast_raises_a_clear_error(self):
        forecast, _ = self.load([(35.0, -100.0)], open_meteo_location([5.0] * 24))
        with self.assertRaises(weather.ForecastUnavailable):
            forecast.at(35.0, -100.0, MIDNIGHT + timedelta(days=3))

    def test_hours_with_missing_values_are_not_treated_as_calm(self):
        body = open_meteo_location([5.0, None, 5.0])
        forecast, _ = self.load([(35.0, -100.0)], body, hours=2)
        with self.assertRaises(weather.ForecastUnavailable):
            forecast.at(35.0, -100.0, MIDNIGHT + timedelta(hours=1))

    def test_minute_limit_says_how_long_to_wait(self):
        error = UpstreamError("weather", "Minutely API request limit exceeded.", http_status=429)
        with patch.object(weather, "request_json_failover", side_effect=error):
            with self.assertRaisesMessage(RateLimited, "rate limiting") as caught:
                weather.load_forecast([(35.0, -100.0)], MIDNIGHT, MIDNIGHT)
        self.assertEqual(caught.exception.retry_after, weather.MINUTE_LIMIT_RETRY_SECONDS)

    def test_daily_limit_is_not_worth_waiting_a_minute_for(self):
        error = UpstreamError("weather", "Daily API request limit exceeded.", http_status=429)
        with patch.object(weather, "request_json_failover", side_effect=error):
            with self.assertRaises(RateLimited) as caught:
                weather.load_forecast([(35.0, -100.0)], MIDNIGHT, MIDNIGHT)
        self.assertIsNone(caught.exception.retry_after)

    def test_an_outage_says_trying_again_will_help(self):
        error = UpstreamError("weather", "The weather service returned an error (525).", 525)
        with patch.object(weather, "request_json_failover", side_effect=error):
            with self.assertRaisesMessage(UpstreamError, "not responding") as caught:
                weather.load_forecast([(35.0, -100.0)], MIDNIGHT, MIDNIGHT)
        self.assertEqual(caught.exception.retry_after, weather.TRANSIENT_RETRY_SECONDS)

    @override_settings(OPEN_METEO_URL="https://proxy.test")
    def test_asks_the_proxy_first_and_open_meteo_as_the_fallback(self):
        _, http = self.load([(35.0, -100.0)], open_meteo_location([5.0] * 24))
        mirrors = http.call_args.args[1]
        self.assertEqual(mirrors, ("https://proxy.test", "https://api.open-meteo.com"))

    def test_batches_that_arrived_are_kept_when_another_batch_fails(self):
        cells = [(35.0 + i / 10, -100.0) for i in range(weather.CELLS_PER_REQUEST + 1)]
        limited = UpstreamError("weather", "Minutely API request limit exceeded.", http_status=429)

        def first_batch_only(*args, **kwargs):
            batch = kwargs["params"]["latitude"].split(",")
            if len(batch) == 1:
                raise limited
            return [open_meteo_location([5.0] * 24)] * len(batch)

        with patch.object(weather, "request_json_failover", side_effect=first_batch_only):
            with self.assertRaises(RateLimited):
                weather.load_forecast(cells, MIDNIGHT, MIDNIGHT)
        # The retry asks only for the one cell that failed.
        retry = [open_meteo_location([5.0] * 24)]
        with patch.object(weather, "request_json_failover", return_value=retry) as http:
            weather.load_forecast(cells, MIDNIGHT, MIDNIGHT)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(http.call_args.kwargs["params"]["latitude"], str(cells[-1][0]))

    @override_settings(WIND_FIELD="gust")
    def test_gusts_can_be_used_as_the_risk_wind(self):
        forecast, _ = self.load([(35.0, -100.0)], open_meteo_location([20.0] * 24))
        result = forecast.at(35.0, -100.0, MIDNIGHT)
        self.assertEqual(result.wind_mph, 30.0)
        self.assertEqual(result.wind_speed_mph, 20.0)
