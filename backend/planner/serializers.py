from rest_framework import serializers

INTERVAL_CHOICES = (10, 25, 50)
MAX_LOAD_LB = 200_000


class PlaceInputSerializer(serializers.Serializer):
    """Either free text, or text plus the coordinates of a picked suggestion."""

    text = serializers.CharField(max_length=200, trim_whitespace=True)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False, allow_null=True)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False, allow_null=True)


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceInputSerializer()
    destination = PlaceInputSerializer()
    # Wall-clock time at the origin, no timezone: "2026-11-13T08:00".
    departure = serializers.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"], default_timezone=None
    )
    load_lb = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)
    interval_mi = serializers.ChoiceField(choices=INTERVAL_CHOICES)
    simulate_storm = serializers.BooleanField(default=False)
    storm_anchor = serializers.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"], default_timezone=None, required=False, allow_null=True
    )

    def validate_departure(self, value):
        # DRF attaches the server timezone; the planner wants the naive wall time.
        return value.replace(tzinfo=None)

    def validate_storm_anchor(self, value):
        return value.replace(tzinfo=None) if value else None
