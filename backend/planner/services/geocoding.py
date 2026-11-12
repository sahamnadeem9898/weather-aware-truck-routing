"""Turning what the driver types into coordinates.

- Suggestions while typing: Open-Meteo's geocoder (fast, keyless, built for
  prefix search on place names).
- Free text submitted without picking a suggestion: the same geocoder first
  (it understands "Dallas, TX"), then Nominatim, which also handles street
  addresses.
"""

import hashlib
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from .errors import PlaceNotFound, UpstreamError
from .http import request_json


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


MAX_QUERY_LENGTH = 200


def suggest(query: str, limit: int = 6) -> list[Place]:
    """Place suggestions for a partial name."""
    query = query.strip()[:MAX_QUERY_LENGTH]
    if len(query) < 2:
        return []
    key = _key("suggest", f"{query}:{limit}")
    if (places := cache.get(key)) is None:
        data = request_json(
            "geocoding",
            "GET",
            f"{settings.OPEN_METEO_GEOCODING_URL}/v1/search",
            params={"name": query, "count": limit, "language": "en", "format": "json"},
            timeout=8.0,
        )
        places = [_open_meteo_place(item) for item in data.get("results", [])]
        cache.set(key, places, settings.GEOCODE_CACHE_SECONDS)
    return places


def resolve(text: str) -> Place:
    """Best single match for free text. Raises PlaceNotFound if nothing matches."""
    text = text.strip()
    key = _key("resolve", text)
    if (place := cache.get(key)) is not None:
        return place

    place = None
    lookups = (_best_suggestion, _nominatim)
    failures = 0
    for lookup in lookups:
        try:
            place = lookup(text)
        except UpstreamError:
            failures += 1  # one geocoder being down should not fail the request
            continue
        if place is not None:
            break
    if place is None:
        if failures == len(lookups):
            raise UpstreamError(
                "geocoding", "Place search is unavailable right now. Try again shortly."
            )
        raise PlaceNotFound(f'Could not find "{text}". Check the spelling or pick a suggestion.')

    cache.set(key, place, settings.GEOCODE_CACHE_SECONDS)
    return place


def _key(prefix: str, text: str) -> str:
    """Cache key safe for any backend (no spaces or control characters)."""
    return f"{prefix}:{hashlib.sha1(text.lower().encode()).hexdigest()}"


def _best_suggestion(text: str) -> Place | None:
    matches = suggest(text, limit=1)
    return matches[0] if matches else None


def _open_meteo_place(item: dict) -> Place:
    parts = [item.get("name"), item.get("admin1"), item.get("country_code")]
    return Place(
        label=", ".join(p for p in parts if p),
        lat=float(item["latitude"]),
        lon=float(item["longitude"]),
    )


def _nominatim(text: str) -> Place | None:
    results = request_json(
        "geocoding",
        "GET",
        f"{settings.NOMINATIM_URL}/search",
        params={"q": text, "format": "jsonv2", "limit": 1, "accept-language": "en"},
        timeout=8.0,
    )
    if not results:
        return None
    top = results[0]
    # Keep the label short: first three parts of "A, B, C, D, Country".
    label = ", ".join(top["display_name"].split(", ")[:3])
    return Place(label=label, lat=float(top["lat"]), lon=float(top["lon"]))
