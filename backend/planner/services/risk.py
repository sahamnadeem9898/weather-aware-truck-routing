"""Weather risk classification. Pure functions, no I/O.

Thresholds and load rules come straight from the assessment brief.

Boundary rule: a value that sits exactly on a boundary goes to the HIGHER
band (25 mph is Moderate, 0.25 in/hr is High), except the top of the rain and
snow tables, which the brief writes as strictly greater than (">1.00",
">3.0"): exactly 1.00 in/hr of rain is still Severe.
"""

from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return LEVEL_LABELS[self]


LEVEL_LABELS = {
    Level.LOW: "Low",
    Level.MODERATE: "Moderate",
    Level.HIGH: "High",
    Level.SEVERE: "Severe",
    Level.NO_TRAVEL: "No Travel",
}

# (lower bound, level), worst band first.
WIND_MPH = [
    (55.0, Level.NO_TRAVEL),
    (45.0, Level.SEVERE),
    (35.0, Level.HIGH),
    (25.0, Level.MODERATE),
]
RAIN_IN_HR = [
    (1.00, Level.NO_TRAVEL),
    (0.50, Level.SEVERE),
    (0.25, Level.HIGH),
    (0.10, Level.MODERATE),
]
SNOW_IN_HR = [(3.0, Level.NO_TRAVEL), (2.0, Level.SEVERE), (1.0, Level.HIGH), (0.5, Level.MODERATE)]

# Load rules: wind 45-54 mph over MEDIUM_LOAD_LB is No Travel; 35-44 mph over
# HEAVY_LOAD_LB is Severe.
HEAVY_LOAD_LB = 40_000
MEDIUM_LOAD_LB = 30_000


@dataclass(frozen=True)
class Assessment:
    """Risk at one place and time, with the pieces that produced it."""

    level: Level
    wind_level: Level
    rain_level: Level
    snow_level: Level
    load_rule_applied: bool
    reason: str


def band(value: float, table: list[tuple[float, Level]], *, strict_top: bool = False) -> Level:
    """Classify `value` against a threshold table (worst band first)."""
    for i, (limit, level) in enumerate(table):
        exceeded = value > limit if (strict_top and i == 0) else value >= limit
        if exceeded:
            return level
    return Level.LOW


def wind_level(wind_mph: float, load_lb: float) -> tuple[Level, bool]:
    """Wind band after load rules. Returns (level, whether a load rule raised it)."""
    base = band(wind_mph, WIND_MPH)
    if 45 <= wind_mph < 55 and load_lb > MEDIUM_LOAD_LB:
        return Level.NO_TRAVEL, True
    if 35 <= wind_mph < 45 and load_lb > HEAVY_LOAD_LB:
        return Level.SEVERE, True
    return base, False


def overall_level(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Level:
    """Just the overall level, for loops that score thousands of points."""
    wind, _ = wind_level(wind_mph, load_lb)
    rain = band(rain_in_hr, RAIN_IN_HR, strict_top=True)
    snow = band(snow_in_hr, SNOW_IN_HR, strict_top=True)
    return max(wind, rain, snow)


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall level is the worst of wind (after load rules), rain and snow."""
    wind, load_rule = wind_level(wind_mph, load_lb)
    rain = band(rain_in_hr, RAIN_IN_HR, strict_top=True)
    snow = band(snow_in_hr, SNOW_IN_HR, strict_top=True)
    level = max(wind, rain, snow)
    return Assessment(
        level=level,
        wind_level=wind,
        rain_level=rain,
        snow_level=snow,
        load_rule_applied=load_rule and wind == level,
        reason=_reason(
            level, wind, rain, snow, load_rule, wind_mph, rain_in_hr, snow_in_hr, load_lb
        ),
    )


def _reason(
    level: Level,
    wind: Level,
    rain: Level,
    snow: Level,
    load_rule: bool,
    wind_mph: float,
    rain_in_hr: float,
    snow_in_hr: float,
    load_lb: float,
) -> str:
    """One short sentence naming what drives the level."""
    if level == Level.LOW:
        return "Wind, rain and snow are all below the Moderate thresholds."
    drivers = []
    if wind == level:
        text = f"wind {wind_mph:.0f} mph"
        if load_rule:
            limit = MEDIUM_LOAD_LB if level == Level.NO_TRAVEL else HEAVY_LOAD_LB
            text += f" with a {load_lb:,.0f} lb load (over {limit:,} lb)"
        drivers.append(text)
    if rain == level:
        drivers.append(f"rain {rain_in_hr:.2f} in/hr")
    if snow == level:
        drivers.append(f"snow {snow_in_hr:.1f} in/hr")
    return f"{level.label}: " + " and ".join(drivers) + "."
