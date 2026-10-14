"""
rescore_all.py
One-shot repair and re-score, with NO MT5 and NO new data needed:

1. Recomputes order block mitigation over the FULL candle history
   (fixes the old 2000-candle limit and gives every block a correct
   mitigated_at time).
2. Re-scores every existing CRT setup in place using the fixed,
   time-aware order block matching in confluence.py.

Candles, setups and trade signals are not touched, so the same trades
are evaluated before and after - only the scores can change.

Usage (from SMTE/backend, with smte-env activated):
    python rescore_all.py
"""

from app.database.base import SessionLocal
from app.models.models import Instrument
from core.order_blocks.detector import mark_mitigated_blocks
from core.scoring.confluence import score_crt_setups_v4


def main():
    db = SessionLocal()
    try:
        instruments = db.query(Instrument).order_by(Instrument.symbol).all()
        for instrument in instruments:
            digits = instrument.digits
            point = float(instrument.pip_size)

            changed = mark_mitigated_blocks(db, instrument.id, "M15", recheck_all=True)
            scored = score_crt_setups_v4(db, instrument.id, 15.0, 10.0, digits, point)
            print(
                f"{instrument.symbol}: {changed} order blocks corrected, "
                f"{scored} setups re-scored"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()