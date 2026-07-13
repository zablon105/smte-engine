"""
detector.py
Core CRT (Candle Range Theory) detection logic.

Beginner note on the theory being coded here:
  1. RANGE       - a candle establishes a high/low range.
  2. MANIPULATION - the very next candle (or a lower-timeframe candle
                    within the range's window) wicks beyond that range
                    (sweeping liquidity resting above/below it) but
                    then CLOSES back inside the range. This is the
                    "fakeout" - smart money grabbing liquidity before
                    the real move.
  3. DISTRIBUTION - a candle after that confirms a real, decisive
                    move in the OPPOSITE direction of the manipulation
                    wick. This is the actual tradeable move.

Example: if a candle wicks below the range low but closes back above
it, that's a bullish manipulation (sell-side liquidity was swept).
If a later candle then closes higher than the manipulation candle,
that confirms bullish distribution - i.e. a genuine upward move is
likely underway.

This file contains TWO versions of the detector:
  - detect_crt_setups()      : single-timeframe (simpler, noisier)
  - detect_crt_setups_mtf()  : multi-timeframe (recommended - uses a
                                higher timeframe like H4 to define the
                                range, and a lower timeframe like M15
                                to find manipulation/distribution)
"""

from datetime import timedelta
from sqlalchemy import select
from app.models.models import Candle, CrtSetup


# ============================================================
# SHARED HELPERS (used by both versions below)
# ============================================================

def _fetch_candles(db, instrument_id: int, timeframe: str, lookback: int):
    """
    Returns the most recent `lookback` candles for an instrument/timeframe,
    ordered oldest -> newest (so we can walk through them in sequence).
    """
    stmt = (
        select(Candle)
        .where(Candle.instrument_id == instrument_id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.desc())
        .limit(lookback)
    )
    candles = db.execute(stmt).scalars().all()
    candles.reverse()  # now oldest -> newest
    return candles


def _fetch_candles_between(db, instrument_id: int, timeframe: str, start, end):
    """
    Returns candles for an instrument/timeframe strictly between
    two timestamps, ordered oldest -> newest.
    """
    stmt = (
        select(Candle)
        .where(
            Candle.instrument_id == instrument_id,
            Candle.timeframe == timeframe,
            Candle.open_time > start,
            Candle.open_time <= end,
        )
        .order_by(Candle.open_time.asc())
    )
    return db.execute(stmt).scalars().all()


def _setup_already_exists(db, range_candle_id: int, direction: str) -> bool:
    """
    Prevents creating duplicate CrtSetup rows if the detector is
    re-run over candles it has already analyzed.
    """
    existing = (
        db.query(CrtSetup)
        .filter_by(range_candle_id=range_candle_id, setup_direction=direction)
        .first()
    )
    return existing is not None


# ============================================================
# SINGLE-TIMEFRAME VERSION
# Simpler, but noisier - treats every candle as a potential range
# candle and only checks its immediate neighbor for manipulation.
# ============================================================

def detect_crt_setups(db, instrument_id: int, timeframe: str, lookback: int = 200) -> int:
    """
    Walks through recent candles looking for the CRT range ->
    manipulation -> distribution pattern on a SINGLE timeframe.
    Saves any newly confirmed or pending setups into the crt_setups
    table.

    Returns the number of NEW setup rows created.
    """
    candles = _fetch_candles(db, instrument_id, timeframe, lookback)
    created_count = 0

    # We need at least 3 candles to check: range, manipulation, distribution
    for i in range(len(candles) - 2):
        range_candle = candles[i]
        manipulation_candle = candles[i + 1]
        distribution_candle = candles[i + 2]

        direction = None
        manipulation_price = None

        # --- Bullish CRT: manipulation dips below range low, closes back above ---
        if (
            manipulation_candle.low < range_candle.low
            and manipulation_candle.close > range_candle.low
        ):
            direction = "BULLISH"
            manipulation_price = manipulation_candle.low

        # --- Bearish CRT: manipulation spikes above range high, closes back below ---
        elif (
            manipulation_candle.high > range_candle.high
            and manipulation_candle.close < range_candle.high
        ):
            direction = "BEARISH"
            manipulation_price = manipulation_candle.high

        if direction is None:
            continue  # no manipulation pattern at this position, move on

        if _setup_already_exists(db, range_candle.id, direction):
            continue  # already recorded this one, skip

        # Check whether the distribution candle confirms the real move
        if direction == "BULLISH":
            distribution_confirmed = distribution_candle.close > manipulation_candle.close
        else:
            distribution_confirmed = distribution_candle.close < manipulation_candle.close

        phase = "DISTRIBUTION" if distribution_confirmed else "MANIPULATION"

        setup = CrtSetup(
            instrument_id=instrument_id,
            timeframe=timeframe,
            range_candle_id=range_candle.id,
            setup_direction=direction,
            phase=phase,
            range_high=range_candle.high,
            range_low=range_candle.low,
            manipulation_price=manipulation_price,
            detected_at=manipulation_candle.open_time,
            is_valid=True,
        )
        db.add(setup)
        created_count += 1

    db.commit()
    return created_count


# ============================================================
# MULTI-TIMEFRAME VERSION (RECOMMENDED)
# Uses a higher timeframe candle (e.g. H4) to define the range,
# and checks a lower timeframe (e.g. M15) for the manipulation
# and distribution phases. This filters out much of the noise
# from the single-timeframe version, since H4 ranges are far
# less frequent and more meaningful than M15-to-M15 wiggles.
#
# IMPORTANT: the distribution (confirmation) search is allowed to
# extend BEYOND the original H4 range window. If the manipulation
# wick happens late within the H4 window, there's little time left
# inside that same window for a real follow-through move - so
# without this extension, almost everything gets stuck at
# "MANIPULATION" and never confirms. Extending the search window
# (via distribution_buffer_periods) gives the follow-through move
# room to happen after the H4 candle closes, which is when it
# usually actually does.
# ============================================================

TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440, "W1": 10080, "MN1": 43200,
}


def detect_crt_setups_mtf(
    db,
    instrument_id: int,
    range_timeframe: str = "H4",
    manipulation_timeframe: str = "M15",
    lookback: int = 100,
    distribution_buffer_periods: int = 3,
) -> int:
    """
    Multi-timeframe CRT detection.

    For each higher-timeframe range candle (e.g. H4), looks at the
    lower-timeframe candles (e.g. M15) that occurred during that
    range candle's window to find the manipulation wick + reclaim.
    Then searches an EXTENDED window (the original window PLUS
    `distribution_buffer_periods` additional range-timeframe periods)
    for a distribution-phase confirmation.

    Note: the resulting CrtSetup row's `timeframe` field is set to
    the manipulation_timeframe (the actionable/execution timeframe),
    while `range_candle_id` points to the higher-timeframe candle
    that defined the range.
    """
    range_candles = _fetch_candles(db, instrument_id, range_timeframe, lookback)
    minutes = TIMEFRAME_MINUTES[range_timeframe]
    created_count = 0

    for range_candle in range_candles:
        window_end = range_candle.open_time + timedelta(minutes=minutes)
        extended_end = range_candle.open_time + timedelta(
            minutes=minutes * (1 + distribution_buffer_periods)
        )

        # Fetch enough lower-timeframe candles to cover BOTH the
        # original range window (for manipulation) AND the extended
        # buffer afterward (for distribution confirmation).
        all_lower_candles = _fetch_candles_between(
            db, instrument_id, manipulation_timeframe, range_candle.open_time, extended_end
        )

        if len(all_lower_candles) < 2:
            continue  # not enough lower-timeframe data yet

        manipulation_candle = None
        direction = None
        manipulation_price = None
        manipulation_index = None

        # Manipulation must be found within the ORIGINAL window only
        for idx, candle in enumerate(all_lower_candles):
            if candle.open_time > window_end:
                break  # stop looking for manipulation once past the range window
            if candle.low < range_candle.low and candle.close > range_candle.low:
                direction = "BULLISH"
                manipulation_price = candle.low
                manipulation_candle = candle
                manipulation_index = idx
                break
            elif candle.high > range_candle.high and candle.close < range_candle.high:
                direction = "BEARISH"
                manipulation_price = candle.high
                manipulation_candle = candle
                manipulation_index = idx
                break

        if direction is None:
            continue  # no manipulation happened in this range's window

        if _setup_already_exists(db, range_candle.id, direction):
            continue

        # Distribution confirmation now requires a CLOSE BEYOND THE
        # OPPOSITE RANGE BOUNDARY - not just beyond the manipulation
        # candle's close. This is a much stronger, more meaningful
        # signal: it means price didn't just recover from the sweep,
        # it broke clean through the OTHER side of the entire range.
        distribution_confirmed = False
        for candle in all_lower_candles[manipulation_index + 1:]:
            if direction == "BULLISH" and candle.close > range_candle.high:
                distribution_confirmed = True
                break
            elif direction == "BEARISH" and candle.close < range_candle.low:
                distribution_confirmed = True
                break

        phase = "DISTRIBUTION" if distribution_confirmed else "MANIPULATION"

        setup = CrtSetup(
            instrument_id=instrument_id,
            timeframe=manipulation_timeframe,
            range_candle_id=range_candle.id,
            setup_direction=direction,
            phase=phase,
            range_high=range_candle.high,
            range_low=range_candle.low,
            manipulation_price=manipulation_price,
            detected_at=manipulation_candle.open_time,
            is_valid=True,
        )
        db.add(setup)
        created_count += 1

    db.commit()
    return created_count