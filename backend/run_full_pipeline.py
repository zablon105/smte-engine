"""
run_full_pipeline.py
Orchestrates the ENTIRE SMTE pipeline across multiple symbols in
one run: data collection -> order blocks -> liquidity zones ->
CRT setups -> confluence scoring -> trade signals -> backtest.

This exists because doing all of this manually, symbol by symbol,
command by command, is slow and error-prone. Running it once here
gives a much larger, more statistically meaningful sample to
evaluate the system against.

Usage (from SMTE/backend, with smte-env activated):
    python run_full_pipeline.py
"""

from app.database.base import SessionLocal
from app.models.models import Instrument
from app.services import mt5_client
from app.services.data_collector import collect
from core.order_blocks.detector import detect_order_blocks, mark_mitigated_blocks
from core.liquidity.detector import detect_liquidity_zones, mark_swept_zones
from core.crt.detector import detect_crt_setups_mtf
from core.scoring.confluence import score_crt_setups_v2
from core.execution.signal_generator import generate_signals
from strategy_backtest.signal_backtest import backtest_all_signals


SYMBOLS = [
    "EURUSD.m", "GBPUSD.m", "USDJPY.m", "USDCHF.m",
    "AUDUSD.m", "USDCAD.m", "NZDUSD.m", "XAUUSD.m",
]

# Candle counts chosen to give roughly a year+ of history per timeframe
M15_COUNT = 25000   # ~ 8-9 months of M15 bars
H1_COUNT = 6000      # ~ 1 year of H1 bars
H4_COUNT = 1500      # ~ 1 year of H4 bars

MIN_SCORE = 7
RISK_REWARD = 2.0


def run_for_symbol(symbol: str):
    print(f"\n{'=' * 60}")
    print(f"Processing {symbol}")
    print(f"{'=' * 60}")

    # --- Step 1: Collect candle data ---
    print(f"[{symbol}] Collecting candles...")
    collect(symbol, "M15", M15_COUNT)
    collect(symbol, "H1", H1_COUNT)
    collect(symbol, "H4", H4_COUNT)

    # From here on, MT5 connection is no longer needed per-symbol
    # (collect() already connects/disconnects internally), so we
    # open our own DB session for the rest of the pipeline.
    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=symbol).first()
        if instrument is None:
            print(f"[{symbol}] ERROR: instrument not found after collection, skipping.")
            return None

        digits = instrument.digits
        point = float(instrument.pip_size)

        # --- Step 2: Order blocks (M15) ---
        print(f"[{symbol}] Detecting order blocks...")
        ob_created = detect_order_blocks(db, instrument.id, "M15", M15_COUNT)
        ob_mitigated = mark_mitigated_blocks(db, instrument.id, "M15")
        print(f"[{symbol}]   order blocks: {ob_created} created, {ob_mitigated} mitigated")

        # --- Step 3: Liquidity zones (M15, H1, H4) ---
        print(f"[{symbol}] Detecting liquidity zones...")
        for tf, count in [("M15", M15_COUNT), ("H1", H1_COUNT), ("H4", H4_COUNT)]:
            lz_created = detect_liquidity_zones(db, instrument.id, tf, count, 3.0, digits, point)
            lz_swept = mark_swept_zones(db, instrument.id, tf)
            print(f"[{symbol}]   liquidity [{tf}]: {lz_created} created, {lz_swept} swept")

        # --- Step 4: CRT setups (H4 range -> M15 manipulation) ---
        print(f"[{symbol}] Detecting CRT setups...")
        crt_created = detect_crt_setups_mtf(db, instrument.id, "H4", "M15", H4_COUNT)
        print(f"[{symbol}]   CRT setups: {crt_created} created")

        # --- Step 5: Confluence scoring ---
        print(f"[{symbol}] Scoring setups...")
        scored = score_crt_setups_v2(db, instrument.id, 15.0, 10.0, digits, point)
        print(f"[{symbol}]   scored: {scored} setups")

        # --- Step 6: Trade signal generation ---
        print(f"[{symbol}] Generating trade signals...")
        signals_created = generate_signals(db, instrument.id, MIN_SCORE, RISK_REWARD, 3.0, digits, point)
        print(f"[{symbol}]   signals created: {signals_created}")

        # --- Step 7: Backtest ---
        print(f"[{symbol}] Backtesting signals...")
        results = backtest_all_signals(db, instrument.id, "M15")
        return {"symbol": symbol, "results": results}

    finally:
        db.close()


def main():
    all_results = []

    for symbol in SYMBOLS:
        try:
            result = run_for_symbol(symbol)
            if result:
                all_results.append(result)
        except Exception as e:
            print(f"[{symbol}] ERROR during processing: {e}")
            continue

    # --- Aggregate summary across all symbols ---
    print(f"\n{'=' * 60}")
    print("AGGREGATE BACKTEST SUMMARY (all symbols combined)")
    print(f"{'=' * 60}")

    total_tp = 0
    total_sl = 0
    total_pending = 0

    for entry in all_results:
        symbol = entry["symbol"]
        results = entry["results"]
        tp = sum(1 for r in results if r["result"] == "TP_HIT")
        sl = sum(1 for r in results if r["result"] == "SL_HIT")
        pending = sum(1 for r in results if r["result"] == "NO_OUTCOME_YET")

        total_tp += tp
        total_sl += sl
        total_pending += pending

        print(f"\n{symbol}: {len(results)} signals -> TP={tp}, SL={sl}, pending={pending}")
        for r in results:
            print(f"  [{r['direction']}] entry={r['entry_price']:.5f} -> {r['result']} at {r['hit_at']}")

    total_decided = total_tp + total_sl
    win_rate = (total_tp / total_decided * 100) if total_decided > 0 else 0

    print(f"\n{'=' * 60}")
    print(f"TOTAL ACROSS ALL SYMBOLS: {total_decided} decided signals ({total_pending} still pending)")
    print(f"  TP hit: {total_tp}")
    print(f"  SL hit: {total_sl}")
    print(f"  Win rate: {win_rate:.1f}%")
    print(f"  Expected value at {RISK_REWARD}:1 RR: "
          f"{(win_rate/100 * RISK_REWARD) - ((1 - win_rate/100) * 1):.2f}R per trade")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()