"""One place for outbound HTTP: shared session, timeouts, uniform errors."""

from typing import Any

import requests
from django.conf import settings

from .errors import UpstreamError

_session = requests.Session()


def request_json(
    service: str,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    timeout: float = 25.0,
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
