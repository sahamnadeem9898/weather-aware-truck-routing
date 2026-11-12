import os
from unittest.mock import patch

from django.test import SimpleTestCase

from config.settings import env_origin, env_url

WORKER = "https://open-meteo-proxy.example.workers.dev"
DEFAULT = "https://api.open-meteo.com"


class ServiceUrlSettingTests(SimpleTestCase):
    def origin(self, value: str | None) -> str:
        env = {} if value is None else {"OPEN_METEO_URL": value}
        with patch.dict(os.environ, env, clear=True):
            return env_origin("OPEN_METEO_URL", DEFAULT)

    def test_unset_or_blank_uses_the_default(self):
        self.assertEqual(self.origin(None), DEFAULT)
        self.assertEqual(self.origin("   "), DEFAULT)

    def test_common_paste_mistakes_still_give_the_worker_origin(self):
        for value in [
            WORKER,
            WORKER + "/",
            f"  {WORKER}/  ",
            WORKER.removeprefix("https://"),
            WORKER + "/v1/search?name=Denver",
            WORKER + "/v1",
        ]:
            with self.subTest(value=value):
                self.assertEqual(self.origin(value), WORKER)

    def test_other_service_urls_lose_only_the_trailing_slash(self):
        with patch.dict(os.environ, {"VALHALLA_URL": "https://routing.example/valhalla/"}):
            self.assertEqual(env_url("VALHALLA_URL", "x"), "https://routing.example/valhalla")
