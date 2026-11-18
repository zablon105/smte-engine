"""Multi-timeframe alignment profiles and pairing validation."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class TimeframeProfile:
    name: str
    htf_context: str
    ltf_entries: Tuple[str, ...]
    description: str


TIMEFRAME_PROFILES: Dict[str, TimeframeProfile] = {
    "position": TimeframeProfile(
        name="position",
        htf_context="1M",
        ltf_entries=("1W", "1D"),
        description="Position trading: Monthly context with Weekly/Daily entries.",
    ),
    "swing": TimeframeProfile(
        name="swing",
        htf_context="1D",
        ltf_entries=("4H", "1H"),
        description="Swing trading: Daily context with 4H/1H structure and entries.",
    ),
    "short_term": TimeframeProfile(
        name="short_term",
        htf_context="4H",
        ltf_entries=("1H", "15M"),
        description="Short-term trading: 4H context with 1H/15M entries.",
    ),
    "intraday": TimeframeProfile(
        name="intraday",
        htf_context="1H",
        ltf_entries=("15M", "5M"),
        description="Intraday trading: 1H context with 15M/5M execution.",
    ),
    "daily_bias_weekly": TimeframeProfile(
        name="daily_bias_weekly",
        htf_context="1W",
        ltf_entries=("4H",),
        description="Daily Bias SOP: Weekly context with 4H execution.",
    ),
    "daily_bias_daily": TimeframeProfile(
        name="daily_bias_daily",
        htf_context="1D",
        ltf_entries=("1H",),
        description="Daily Bias SOP: Daily context with 1H execution.",
    ),
    "crt_intraday": TimeframeProfile(
        name="crt_intraday",
        htf_context="1D",
        ltf_entries=("1H", "15M"),
        description="22CRT intraday: Daily/4H key levels, 1H orderflow, 15M entry.",
    ),
}


def get_timeframe_profile(profile_name: str) -> TimeframeProfile:
    """Retrieve a timeframe alignment profile by name."""
    try:
        return TIMEFRAME_PROFILES[profile_name]
    except KeyError as error:
        raise ValueError(f"Unknown timeframe profile: {profile_name}") from error


def get_aligned_entry_timeframes(htf: str, profile_name: Optional[str] = None) -> Tuple[str, ...]:
    """Return matching execution timeframes for a given HTF timeframe.

    If profile_name is specified, checks that profile. Otherwise searches across all profiles.
    """
    if profile_name:
        profile = get_timeframe_profile(profile_name)
        if profile.htf_context == htf:
            return profile.ltf_entries
        return ()

    results = []
    for profile in TIMEFRAME_PROFILES.values():
        if profile.htf_context == htf:
            for ltf in profile.ltf_entries:
                if ltf not in results:
                    results.append(ltf)
    return tuple(results)


def is_valid_timeframe_pairing(
    htf: str,
    ltf: str,
    profile_name: Optional[str] = None,
) -> bool:
    """Validate whether an HTF and LTF pairing adheres to the research alignment framework."""
    if profile_name:
        profile = get_timeframe_profile(profile_name)
        return profile.htf_context == htf and ltf in profile.ltf_entries

    for profile in TIMEFRAME_PROFILES.values():
        if profile.htf_context == htf and ltf in profile.ltf_entries:
            return True
    return False

