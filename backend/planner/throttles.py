from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


class GlobalPlanThrottle(SimpleRateThrottle):
    """One budget shared by every client.

    The per-client limit can be dodged by rotating IP addresses; this cap
    protects the free third-party APIs (and their quota) regardless.
    """

    scope = "plan_global"

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return "throttle_plan_global"
