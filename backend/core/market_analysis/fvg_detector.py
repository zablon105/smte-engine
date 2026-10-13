"""
Fair Value Gap (FVG) detector.

Pure detection logic: takes candles ordered oldest to newest and
returns the FVGs found. Candles may be dictionaries or objects with
high/low and time fields. The project's Candle model uses open_time.
The optional database helper stores results without changing the
detector's existing return format or pipeline behavior.
"""

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class FVG:
    direction: str
    zone_low: float
    zone_high: float
    created_at: Any
    candle_index: int
    status: str = "open"
    mitigated_at: Optional[Any] = None
    fill_percentage: float = 0.0

    @property
    def size(self) -> float:
        return self.zone_high - self.zone_low


def _get(candle: Any, field: str) -> Any:
    """Read a field from either a dict or an object."""
    if isinstance(candle, dict):
        return candle[field]
    return getattr(candle, field)


def _get_time(candle: Any) -> Any:
    """Support the generic `time` name and the project's `open_time`."""
    if isinstance(candle, dict):
        if "time" in candle:
            return candle["time"]
        return candle["open_time"]
    if hasattr(candle, "time"):
        return candle.time
    return getattr(candle, "open_time")


def detect_fvgs(candles: List[Any], min_gap_size: float = 0.0) -> List[FVG]:
    """
    Scan candles for 3-candle imbalances.

    `min_gap_size` is measured in price units. For EURUSD, 0.0002
    represents 2 pips. It must be non-negative.
    """
    if min_gap_size < 0:
        raise ValueError("min_gap_size must be non-negative")

    fvgs: List[FVG] = []

    for i in range(2, len(candles)):
        c1, c3 = candles[i - 2], candles[i]

        c1_high, c1_low = float(_get(c1, "high")), float(_get(c1, "low"))
        c3_high, c3_low = float(_get(c3, "high")), float(_get(c3, "low"))

        if c1_high < c3_low and (c3_low - c1_high) >= min_gap_size:
            fvgs.append(
                FVG(
                    direction="bullish",
                    zone_low=c1_high,
                    zone_high=c3_low,
                    created_at=_get_time(c3),
                    candle_index=i,
                )
            )
        elif c1_low > c3_high and (c1_low - c3_high) >= min_gap_size:
            fvgs.append(
                FVG(
                    direction="bearish",
                    zone_low=c3_high,
                    zone_high=c1_low,
                    created_at=_get_time(c3),
                    candle_index=i,
                )
            )

    _update_mitigation(fvgs, candles)
    return fvgs


def _update_mitigation(fvgs: List[FVG], candles: List[Any]) -> None:
    """
    Mark gaps partial/filled when later candle ranges trade into them.

    For a bullish gap, price retraces down into the zone. For a
    bearish gap, price retraces up into it. `mitigated_at` records the
    candle that fully fills the gap; partial entries leave it unset.
    """
    for fvg in fvgs:
        deepest = 0.0
        for j in range(fvg.candle_index + 1, len(candles)):
            high = float(_get(candles[j], "high"))
            low = float(_get(candles[j], "low"))

            if fvg.direction == "bullish":
                if low <= fvg.zone_low:
                    fvg.status = "filled"
                    fvg.mitigated_at = _get_time(candles[j])
                    fvg.fill_percentage = 100.0
                    break
                deepest = max(deepest, fvg.zone_high - low)
                if deepest > 0:
                    fvg.status = "partial"
            else:
                if high >= fvg.zone_high:
                    fvg.status = "filled"
                    fvg.mitigated_at = _get_time(candles[j])
                    fvg.fill_percentage = 100.0
                    break
                deepest = max(deepest, high - fvg.zone_low)
                if deepest > 0:
                    fvg.status = "partial"

        if fvg.status != "filled":
            fvg.fill_percentage = round(deepest / fvg.size * 100.0, 2)


def detect_and_store_fvgs(
    db: Any,
    instrument_id: int,
    timeframe: str,
    min_gap_size: float = 0.0,
) -> int:
    """
    Rebuild stored FVGs for one instrument and timeframe.

    Existing FVG rows are replaced only for the requested instrument
    and timeframe. The delete and inserts are committed together; on
    failure the transaction is rolled back and the error is re-raised.
    """
    from app.models.models import Candle, FairValueGap

    rows = (
        db.query(Candle.open_time, Candle.high, Candle.low)
        .filter(
            Candle.instrument_id == instrument_id,
            Candle.timeframe == timeframe,
        )
        .order_by(Candle.open_time.asc())
        .all()
    )
    candles = [
        {"time": row.open_time, "high": float(row.high), "low": float(row.low)}
        for row in rows
    ]
    fvgs = detect_fvgs(candles, min_gap_size)

    try:
        db.query(FairValueGap).filter(
            FairValueGap.instrument_id == instrument_id,
            FairValueGap.timeframe == timeframe,
        ).delete(synchronize_session=False)

        db.add_all(
            [
                FairValueGap(
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    gap_type=fvg.direction.upper(),
                    top_price=fvg.zone_high,
                    bottom_price=fvg.zone_low,
                    formed_at=fvg.created_at,
                    filled_at=fvg.mitigated_at,
                    fill_percentage=fvg.fill_percentage,
                )
                for fvg in fvgs
            ]
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return len(fvgs)
