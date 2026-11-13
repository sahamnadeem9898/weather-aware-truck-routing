import logging
import math

from rest_framework import status
from rest_framework.exceptions import ParseError, Throttled, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.views import exception_handler as drf_exception_handler

from .serializers import PlanRequestSerializer
from .services import geocoding
from .services.errors import PlannerError, UpstreamError
from .services.planner import TripRequest, plan_trip
from .throttles import GlobalPlanThrottle

logger = logging.getLogger(__name__)


def exception_handler(exc: Exception, context: dict) -> Response:
    """Every error leaves the API as {"code": ..., "detail": "..."}."""
    if isinstance(exc, PlannerError):
        logger.warning("Planner error (%s): %s", exc.code, exc)
        body = {"code": exc.code, "detail": str(exc)}
        headers = {}
        if isinstance(exc, UpstreamError) and exc.retry_after:
            body["retry_after"] = exc.retry_after
            headers["Retry-After"] = str(exc.retry_after)
        return Response(body, status=exc.status, headers=headers)
    if isinstance(exc, ValidationError):
        return Response(
            {"code": "invalid_input", "detail": _first_error(exc.detail)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, ParseError):
        return Response(
            {"code": "invalid_input", "detail": "The request body is not valid JSON."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, Throttled):
        wait = math.ceil(exc.wait) if exc.wait else 60
        return Response(
            {"code": "throttled", "detail": f"Too many requests. Try again in {wait} seconds."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(wait)},
        )
    response = drf_exception_handler(exc, context)
    if response is not None:  # other framework errors: 404, 405, 415, ...
        code = getattr(exc, "default_code", "error")
        response.data = {"code": str(code), "detail": str(getattr(exc, "detail", exc))}
        return response
    # Anything unexpected, such as a third-party API changing its response shape.
    logger.exception("Unexpected error", exc_info=exc)
    return Response(
        {"code": "server_error", "detail": "Something went wrong on the server. Try again."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _first_error(errors, path: str = "") -> str:
    """Flatten DRF's nested validation errors into one readable sentence."""
    if isinstance(errors, dict):
        field, value = next(iter(errors.items()))
        return _first_error(value, f"{path}{field}: " if not path else f"{path[:-2]}.{field}: ")
    if isinstance(errors, list) and errors:
        return _first_error(errors[0], path)
    return f"{path}{errors}"


class GeocodeView(APIView):
    """GET /api/geocode/?q=dal -> place suggestions for the autocomplete."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    def get(self, request: Request) -> Response:
        places = geocoding.suggest(request.query_params.get("q", ""))
        return Response(
            {"results": [{"label": p.label, "lat": p.lat, "lon": p.lon} for p in places]}
        )


class PlanView(APIView):
    """POST /api/plan/ -> three scored routes, a recommendation and the heatmap."""

    throttle_classes = [ScopedRateThrottle, GlobalPlanThrottle]
    throttle_scope = "plan"

    def post(self, request: Request) -> Response:
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        trip = TripRequest(
            origin=self._place(data["origin"]),
            destination=self._place(data["destination"]),
            departure_local=data["departure"],
            load_lb=data["load_lb"],
            interval_mi=data["interval_mi"],
            simulate_storm=data["simulate_storm"],
            storm_anchor_local=data.get("storm_anchor"),
        )
        return Response(plan_trip(trip))

    @staticmethod
    def _place(raw: dict) -> geocoding.Place:
        if raw.get("lat") is not None and raw.get("lon") is not None:
            return geocoding.Place(label=raw["text"], lat=raw["lat"], lon=raw["lon"])
        return geocoding.resolve(raw["text"])
