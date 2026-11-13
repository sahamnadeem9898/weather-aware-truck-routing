"""Errors the API turns into clear messages for the driver."""


class PlannerError(Exception):
    """Base class: `code` is machine-readable, the message is shown in the UI."""

    code = "planner_error"
    status = 400


class PlaceNotFound(PlannerError):
    code = "place_not_found"
    status = 422


class NoRouteFound(PlannerError):
    code = "no_route"
    status = 422


class InvalidTrip(PlannerError):
    code = "invalid_trip"
    status = 422


class UpstreamError(PlannerError):
    """A third-party API failed, timed out or rate limited us.

    `retry_after` (seconds) is set when trying again soon is likely to work;
    the app then retries once on its own.
    """

    code = "upstream_error"
    status = 502

    def __init__(
        self,
        service: str,
        message: str,
        http_status: int | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.service = service
        self.http_status = http_status
        self.retry_after = retry_after


class RateLimited(UpstreamError):
    """A free API's quota is used up. `retry_after` is set when waiting will help."""

    code = "rate_limited"
    status = 503

    def __init__(self, service: str, message: str, retry_after: int | None = None):
        super().__init__(service, message, http_status=429, retry_after=retry_after)
