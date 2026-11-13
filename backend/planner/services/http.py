"""One place for outbound HTTP: shared session, timeouts, uniform errors."""

import time
from collections.abc import Iterable
from typing import Any

import requests
from django.conf import settings

from .errors import UpstreamError

_session = requests.Session()

Timeout = float | tuple[float, float]  # seconds, or (connect, read)

# A mirror that just failed is tried last for this long, so a path that is
# having trouble does not slow down every request while it recovers.
COOLDOWN_SECONDS = 120.0
# Pause before asking the same mirror again.
RETRY_PAUSE_SECONDS = 0.5
_cooling_until: dict[str, float] = {}


def request_json(
    service: str,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    timeout: Timeout = 25.0,
) -> Any:
    """Call a JSON API. Raises UpstreamError on network errors and non-2xx."""
    try:
        response = _session.request(
            method,
            url,
            params=params,
            json=json,
            timeout=timeout,
            headers={"User-Agent": settings.HTTP_USER_AGENT, "Accept": "application/json"},
        )
    except requests.RequestException as exc:
        raise UpstreamError(service, f"The {service} service could not be reached.") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if not response.ok:
        detail = ""
        if isinstance(payload, dict):
            # e.g. OSRM: {"code": "NoRoute", "message": "Impossible route between points"}
            # Only text fields: Open-Meteo, for one, sends {"error": true, "reason": "..."}.
            parts = [payload.get(key) for key in ("code", "reason", "error", "message")]
            detail = " ".join(part for part in parts if isinstance(part, str) and part)
        raise UpstreamError(
            service,
            f"The {service} service returned an error ({response.status_code}). {detail}".strip(),
            http_status=response.status_code,
        )
    if payload is None:
        raise UpstreamError(service, f"The {service} service returned an unreadable response.")
    return payload


def is_transient(exc: UpstreamError) -> bool:
    """A failure that a second try may not hit: no answer at all, or a 5xx."""
    return exc.http_status is None or exc.http_status >= 500


def request_json_failover(
    service: str,
    bases: Iterable[str],
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: Timeout = 25.0,
) -> Any:
    """GET `path` from mirrors of one API (say, a proxy and the API itself).

    A transient failure moves on to the next mirror, and the failing one is
    tried last for a while. Every mirror gets one try and the first gets a
    second, so a single dropped connection never fails a request. Any other
    error (a 4xx, such as a rate limit) is raised straight away.
    """
    mirrors = list(dict.fromkeys(bases))
    now = time.monotonic()
    mirrors.sort(key=lambda base: _cooling_until.get(base, 0.0) > now)  # stable: healthy first
    attempts = [*mirrors, mirrors[0]]

    failures: list[UpstreamError] = []
    for number, base in enumerate(attempts):
        if number == len(mirrors):
            time.sleep(RETRY_PAUSE_SECONDS)
        try:
            result = request_json(service, "GET", base + path, params=params, timeout=timeout)
        except UpstreamError as exc:
            if not is_transient(exc):
                raise
            _cooling_until[base] = time.monotonic() + COOLDOWN_SECONDS
            failures.append(exc)
            continue
        _cooling_until.pop(base, None)
        return result
    raise failures[0]
