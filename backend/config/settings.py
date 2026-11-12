"""Django settings.

The app is stateless: no database, no sessions, no auth. Everything it needs
comes from third-party APIs and is held in the in-process cache.
"""

import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_url(name: str, default: str) -> str:
    """A service base URL, forgiving about spaces, a trailing slash or a missing scheme."""
    value = os.environ.get(name, "").strip().rstrip("/")
    if not value:
        return default
    return value if "://" in value else f"https://{value}"


def env_origin(name: str, default: str) -> str:
    """Only scheme://host of a URL setting, so pasting a full test link still works."""
    parts = urlsplit(env_url(name, default))
    return f"{parts.scheme}://{parts.netloc}" if parts.netloc else default


DEBUG = env_bool("DJANGO_DEBUG", False)
# Nothing is signed (no sessions, auth or CSRF tokens), so when no key is
# configured a random one per process is safe, and no default key is in the code.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or secrets.token_urlsafe(50)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.onrender.com")
if render_host := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(render_host)

INSTALLED_APPS = [
    "rest_framework",
    "planner",
]

MIDDLEWARE = [
    "config.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES: dict = {}

USE_TZ = True
TIME_ZONE = "UTC"

# The built React app is served by WhiteNoise from the site root, so one
# Render web service hosts both halves.
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", REPO_DIR / "frontend" / "dist"))
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None
WHITENOISE_INDEX_FILE = True
# In development, pick up a rebuilt frontend without restarting the server.
WHITENOISE_AUTOREFRESH = DEBUG


def _is_hashed_asset(path: str, url: str) -> bool:
    """Vite fingerprints everything under /assets/, so it can be cached forever."""
    return url.startswith("/assets/")


WHITENOISE_IMMUTABLE_FILE_TEST = _is_hashed_asset

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Browsers remember to use HTTPS only (sent on HTTPS responses only).
SECURE_HSTS_SECONDS = 0 if DEBUG else 60 * 60 * 24 * 365

# In-process caches. Routes get their own small cache because one trip's
# geometry is 1-4 MB; the free hosting tier has 512 MB of memory in total.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "default",
        "OPTIONS": {"MAX_ENTRIES": 20_000},
    },
    "routes": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "routes",
        "OPTIONS": {"MAX_ENTRIES": 24},
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Per client IP, plus one shared cap on plans (see planner/throttles.py),
    # to stay well inside the free weather API's quota.
    "DEFAULT_THROTTLE_RATES": {"plan": "12/min", "plan_global": "30/min", "geocode": "120/min"},
    # Behind Render's proxy the client IP is the last X-Forwarded-For entry;
    # earlier entries are whatever the client sent and can't be trusted.
    "NUM_PROXIES": int(os.environ.get("NUM_PROXIES", "1")),
    "EXCEPTION_HANDLER": "planner.views.exception_handler",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

# --- Third-party services (all free and keyless) ---------------------------
VALHALLA_URL = env_url("VALHALLA_URL", "https://valhalla1.openstreetmap.de")
OSRM_URL = env_url("OSRM_URL", "https://router.project-osrm.org")
# Open-Meteo, or the Cloudflare Worker in deploy/ that forwards to it. Both
# serve /v1/forecast and /v1/search from the root, so only the origin is kept.
OPEN_METEO_URL = env_origin("OPEN_METEO_URL", "https://api.open-meteo.com")
OPEN_METEO_GEOCODING_URL = env_origin(
    "OPEN_METEO_GEOCODING_URL", "https://geocoding-api.open-meteo.com"
)
NOMINATIM_URL = env_url("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "stormline-truck-routing-demo/1.0")

# --- Planner tuning --------------------------------------------------------
# Which Open-Meteo wind field the risk table is applied to: "speed" (sustained
# 10 m wind) or "gust". Gusts are always returned for display.
WIND_FIELD = os.environ.get("WIND_FIELD", "speed")
# Upper bound on distinct forecast cells per plan. Open-Meteo's free tier
# counts each location as one call and allows 600 a minute.
MAX_WEATHER_CELLS = int(os.environ.get("MAX_WEATHER_CELLS", "560"))
ROUTE_CACHE_SECONDS = 60 * 60
WEATHER_CACHE_SECONDS = 60 * 60  # forecasts update about hourly
GEOCODE_CACHE_SECONDS = 24 * 60 * 60
