"""Route summaries and the recommendation ranking. Pure functions, no I/O.

Ranking order from the brief:
  1. fewest Severe miles
  2. fewest High miles
  3. lowest average risk
  4. shortest travel time

The brief does not say how No Travel miles rank. A route with any No Travel
miles is closed: it sorts last (criterion 0) and is never recommended.
"""

from dataclasses import dataclass

from .risk import Level

# Precision used when comparing, so float noise can't decide a ranking and
# near-identical routes fall through to the next criterion.
MILES_PRECISION = 1
AVG_RISK_PRECISION = 2
SECONDS_PER_MINUTE = 60


@dataclass(frozen=True)
class Segment:
    """The stretch of road between two consecutive checkpoints."""

    from_mile: float
    to_mile: float
    level: Level

    @property
    def miles(self) -> float:
        return self.to_mile - self.from_mile


@dataclass(frozen=True)
class RouteSummary:
    route_id: str
    duration_s: float
    miles_by_level: tuple[float, float, float, float, float]
    avg_risk: float
    worst_level: Level

    @property
    def has_no_travel(self) -> bool:
        return self.miles_by_level[Level.NO_TRAVEL] > 0


def build_segments(miles: list[float], levels: list[Level]) -> list[Segment]:
    """Turn checkpoint levels into road segments.

    A segment takes the WORSE level of the two checkpoints that bound it: if
    either end is dangerous, the miles between them are treated as dangerous.
    """
    return [
        Segment(miles[i], miles[i + 1], max(levels[i], levels[i + 1]))
        for i in range(len(miles) - 1)
    ]


def summarize(route_id: str, duration_s: float, segments: list[Segment]) -> RouteSummary:
    by_level = [0.0] * len(Level)
    for seg in segments:
        by_level[seg.level] += seg.miles
    total = sum(by_level)
    avg = sum(level * miles for level, miles in enumerate(by_level)) / total if total else 0.0
    worst = max((seg.level for seg in segments), default=Level.LOW)
    return RouteSummary(route_id, duration_s, tuple(by_level), avg, worst)  # type: ignore[arg-type]


def ranking_key(summary: RouteSummary) -> tuple[float, float, float, float, int]:
    miles = summary.miles_by_level
    return (
        round(miles[Level.NO_TRAVEL], MILES_PRECISION),  # 0. added rule, see module docstring
        round(miles[Level.SEVERE], MILES_PRECISION),  # 1. fewest Severe miles
        round(miles[Level.HIGH], MILES_PRECISION),  # 2. fewest High miles
        round(summary.avg_risk, AVG_RISK_PRECISION),  # 3. lowest average risk
        round(summary.duration_s / SECONDS_PER_MINUTE),  # 4. shortest travel time
    )


def rank(summaries: list[RouteSummary]) -> list[RouteSummary]:
    """Best route first. Python's sort is stable, so full ties keep API order."""
    return sorted(summaries, key=ranking_key)


def _format_duration(minutes: float) -> str:
    hours, mins = divmod(int(round(minutes)), 60)
    return f"{hours} h {mins:02d} min" if hours else f"{mins} min"


_CRITERIA = [
    ("No Travel miles", lambda v: f"{v:g}"),
    ("Severe miles", lambda v: f"{v:g}"),
    ("High miles", lambda v: f"{v:g}"),
    ("average risk", lambda v: f"{v:.2f}"),
    ("travel time", _format_duration),
]


def explain(best: RouteSummary, other: RouteSummary) -> str:
    """Why `best` outranks `other`: the first criterion on which they differ."""
    if other.has_no_travel and not best.has_no_travel:
        miles = round(other.miles_by_level[Level.NO_TRAVEL], MILES_PRECISION)
        return f"Route {other.route_id} is closed: {miles:g} No Travel miles."
    for (name, fmt), mine, theirs in zip(
        _CRITERIA, ranking_key(best), ranking_key(other), strict=False
    ):
        if mine != theirs:
            return (
                f"Route {best.route_id} has {fmt(mine)} {name} vs "
                f"{fmt(theirs)} on Route {other.route_id}."
            )
    return f"Route {best.route_id} ties with Route {other.route_id} on every criterion."
