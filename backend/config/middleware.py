from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

HEALTH_PATH = "/api/health/"


class HealthCheckMiddleware:
    """Answer the hosting platform's health check before anything else runs.

    Health checks can arrive with an internal hostname, which Django's
    ALLOWED_HOSTS check would reject with a 400 and so fail the deploy.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == HEALTH_PATH:
            return JsonResponse({"status": "ok"})
        return self.get_response(request)
