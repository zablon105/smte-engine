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
from core.dol.targeter import identify_dol_targets, update_dol_targets
from core.market_structure.detector import detect_market_structure
from core.order_blocks.detector import mark_mitigated_blocks
from core.scoring.confluence import score_crt_setups_v4
from core.sessions.builder import populate_sessions
from core.smt.detector import detect_all_smt_divergences


def main():
    db = SessionLocal()
    try:
        instruments = db.query(Instrument).order_by(Instrument.symbol).all()
        for instrument in instruments:
            digits = instrument.digits
            point = float(instrument.pip_size)

            print(f"\n[{instrument.symbol}] Running full detector pass & rescoring...")
            changed = mark_mitigated_blocks(db, instrument.id, "M15", recheck_all=True)
            print(f"[{instrument.symbol}]   order blocks corrected: {changed}")

            # 1. Market Structure (M15, H1)
            for tf, lookback in (("M15", 50000), ("H1", 15000)):
                ms = detect_market_structure(db, instrument.id, tf, lookback=lookback)
                print(f"[{instrument.symbol}]   structure [{tf}]: {ms} created")

            # 2. Trading Sessions
            sess = populate_sessions(db, instrument.id, "M15", lookback=50000)
            print(f"[{instrument.symbol}]   sessions: {sess} populated/updated")

            # 3. SMT Divergence
            for tf, lookback in (("M15", 50000), ("H1", 15000)):
                smt = detect_all_smt_divergences(db, instrument.id, tf, lookback=lookback)
                print(f"[{instrument.symbol}]   SMT [{tf}]: {smt} created")

            # 4. DOL Targets
            for tf in ("H1", "H4"):
                identify_dol_targets(db, instrument.id, tf)
            update_dol_targets(db, instrument.id, "M15", lookback=50000)

            # 5. Full v4 Confluence Scoring
            scored = score_crt_setups_v4(db, instrument.id, 15.0, 10.0, digits, point)
            print(f"[{instrument.symbol}]   setups re-scored with v4 confluence: {scored}")
    finally:
        db.close()


if __name__ == "__main__":
    main()