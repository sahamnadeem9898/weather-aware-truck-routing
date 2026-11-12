from unittest.mock import Mock, patch

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
