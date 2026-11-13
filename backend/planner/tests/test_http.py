from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from planner.services import http
from planner.services.errors import UpstreamError


def response(status: int, body) -> Mock:
    mock = Mock(ok=200 <= status < 300, status_code=status)
    mock.json.return_value = body
    return mock


class RequestJsonTests(SimpleTestCase):
    def call(self, mocked):
        with patch.object(http._session, "request", return_value=mocked):
            return http.request_json("weather", "GET", "https://example.test")

    def test_error_message_keeps_only_text_from_the_body(self):
        body = {"error": True, "reason": "Minutely API request limit exceeded."}
        with self.assertRaises(UpstreamError) as caught:
            self.call(response(429, body))
        self.assertEqual(
            str(caught.exception),
            "The weather service returned an error (429). Minutely API request limit exceeded.",
        )
        self.assertEqual(caught.exception.http_status, 429)

    def test_unreadable_success_body_is_an_error(self):
        broken = response(200, None)
        broken.json.side_effect = ValueError
        with self.assertRaisesMessage(UpstreamError, "unreadable"):
            self.call(broken)

    def test_success_returns_the_json(self):
        self.assertEqual(self.call(response(200, {"ok": 1})), {"ok": 1})


PROXY = "https://proxy.test"
DIRECT = "https://api.test"


@patch.object(http.time, "sleep")
class FailoverTests(SimpleTestCase):
    def setUp(self):
        http._cooling_until.clear()

    def call(self, *answers, mirrors=(PROXY, DIRECT)):
        """Run one failover request; `answers` are what successive calls get."""
        with patch.object(http._session, "request", side_effect=list(answers)) as sent:
            try:
                return http.request_json_failover("weather", mirrors, "/v1/forecast")
            finally:
                self.urls = [call.args[1] for call in sent.call_args_list]

    def test_an_outage_on_the_proxy_falls_back_to_the_api(self, _sleep):
        body = self.call(response(525, None), response(200, {"ok": 1}))
        self.assertEqual(body, {"ok": 1})
        self.assertEqual(self.urls, [PROXY + "/v1/forecast", DIRECT + "/v1/forecast"])

    def test_a_dropped_connection_falls_back_too(self, _sleep):
        body = self.call(requests.ConnectionError(), response(200, {"ok": 1}))
        self.assertEqual(body, {"ok": 1})

    def test_rate_limits_and_bad_requests_are_not_retried(self, _sleep):
        for status in (400, 429):
            with self.subTest(status=status), self.assertRaises(UpstreamError):
                self.call(response(status, {"reason": "no"}))
            self.assertEqual(len(self.urls), 1)

    def test_when_everything_fails_the_first_mirror_gets_a_second_try(self, _sleep):
        with self.assertRaises(UpstreamError) as caught:
            self.call(response(525, None), response(503, None), response(525, None))
        self.assertEqual(
            self.urls, [PROXY + "/v1/forecast", DIRECT + "/v1/forecast", PROXY + "/v1/forecast"]
        )
        self.assertEqual(caught.exception.http_status, 525)

    def test_a_mirror_that_just_failed_is_tried_last(self, _sleep):
        self.call(response(525, None), response(200, {"ok": 1}))
        self.call(response(200, {"ok": 2}))
        self.assertEqual(self.urls, [DIRECT + "/v1/forecast"])

    def test_one_mirror_is_tried_twice(self, _sleep):
        body = self.call(response(502, None), response(200, {"ok": 1}), mirrors=(DIRECT, DIRECT))
        self.assertEqual(body, {"ok": 1})
        self.assertEqual(self.urls, [DIRECT + "/v1/forecast"] * 2)
