"""Research-only, source-specific session windows in New York local time."""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, Tuple
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time


WINDOW_PROFILES: Dict[str, Tuple[SessionWindow, ...]] = {
    "forex_handbook": (
        SessionWindow("ASIA", time(20), time(0)),
        SessionWindow("LONDON_OPEN", time(2), time(5)),
        SessionWindow("NEW_YORK", time(7), time(10)),
        SessionWindow("LONDON_CLOSE", time(10), time(12)),
    ),
    "forex_mansoori": (
        SessionWindow("ASIA", time(22), time(0)),
        SessionWindow("LONDON_OPEN", time(2), time(5)),
        SessionWindow("NEW_YORK", time(7), time(10)),
        SessionWindow("LONDON_CLOSE", time(10), time(12)),
    ),
    "indices_handbook": (
        SessionWindow("ASIA", time(20), time(0)),
        SessionWindow("LONDON_OPEN", time(2), time(5)),
        SessionWindow("NEW_YORK_AM", time(8, 30), time(11)),
        SessionWindow("NEW_YORK_PM", time(13, 30), time(16)),
    ),
    "indices_mansoori": (
        SessionWindow("ASIA", time(20), time(0)),
        SessionWindow("LONDON_OPEN", time(2), time(5)),
        SessionWindow("NEW_YORK_AM", time(8, 30), time(12)),
        SessionWindow("LUNCH", time(12), time(13)),
        SessionWindow("NEW_YORK_PM", time(13), time(16)),
    ),
    "silver_bullet": (
        SessionWindow("LONDON", time(3), time(4)),
        SessionWindow("NEW_YORK_AM", time(10), time(11)),
        SessionWindow("NEW_YORK_PM", time(14), time(15)),
    ),
}


def active_session_windows(timestamp: datetime, profile: str) -> Tuple[str, ...]:
    """Return windows containing a timezone-aware instant for one profile.

    Profiles preserve source disagreements for research and backtesting. This
    helper is not wired to trade-signal generation.
    """
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    try:
        windows = WINDOW_PROFILES[profile]
    except KeyError as error:
        raise ValueError(f"Unknown session window profile: {profile}") from error

    local_time = timestamp.astimezone(NEW_YORK).time().replace(tzinfo=None)
    active = []
    for window in windows:
        if window.start < window.end:
            contains_time = window.start <= local_time < window.end
        else:
            contains_time = local_time >= window.start or local_time < window.end
        if contains_time:
            active.append(window.name)
    return tuple(active)
