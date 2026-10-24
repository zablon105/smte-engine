"""
run_full_pipeline.py
Orchestrates the ENTIRE SMTE pipeline across multiple symbols in
one run: data collection -> order blocks -> liquidity zones ->
CRT setups -> FVG detection -> confluence scoring -> trade signals -> backtest.

This exists because doing all of this manually, symbol by symbol,
command by command, is slow and error-prone. Running it once here
gives a much larger, more statistically meaningful sample to
evaluate the system against.

Usage (from SMTE/backend, with smte-env activated):
    python run_full_pipeline.py                      routine run (recent data)
    python run_full_pipeline.py --min-score 0        signals at every score (for evaluation)
    python run_full_pipeline.py --backfill --min-score 0 --quiet
    python run_full_pipeline.py --symbols EURUSD.m --backfill --min-score 0 --quiet
"""

from app.database.base import SessionLocal
from app.models.models import Instrument
from app.services import mt5_client
from app.services.data_collector import collect
from app.services.history_loader import collect_history
from core.order_blocks.detector import detect_order_blocks, mark_mitigated_blocks
from core.liquidity.detector import detect_liquidity_zones, mark_swept_zones
from core.crt.detector import detect_crt_setups_mtf
from core.market_analysis.fvg_detector import detect_and_store_fvgs
from core.market_structure.detector import detect_market_structure
from core.sessions.builder import populate_sessions
from core.smt.detector import detect_all_smt_divergences
from core.dol.targeter import identify_dol_targets, update_dol_targets
from core.scoring.confluence import score_crt_setups_v4
from core.execution.signal_generator import generate_signals
from strategy_backtest.signal_backtest import backtest_all_signals


SYMBOLS = [
    "EURUSD.m", "GBPUSD.m", "USDJPY.m", "USDCHF.m",
    "AUDUSD.m", "USDCAD.m", "NZDUSD.m", "XAUUSD.m", "BTCUSD.m",
]

# Candle counts for routine runs (roughly a year of data per timeframe)
M15_COUNT = 25000   # ~ 8-9 months of M15 bars
H1_COUNT = 6000      # ~ 1 year of H1 bars
H4_COUNT = 1500      # ~ 1 year of H4 bars

# Candle counts for --backfill (roughly 4 years, if the broker has them)
BACKFILL_M15_COUNT = 100000
BACKFILL_H1_COUNT = 25000
BACKFILL_H4_COUNT = 6500

# Default minimum confluence score for a signal to be generated.
# Override per run with --min-score (use 0 to generate signals at every
# score, which is what you need to test whether score predicts outcome).
MIN_SCORE = 15
RISK_REWARD = 2.0


def count_results(results):
    tp = sum(1 for r in results if r["result"] == "TP_HIT")
    sl = sum(1 for r in results if r["result"] == "SL_HIT")
    pending = sum(1 for r in results if r["result"] == "NO_OUTCOME_YET")
    return tp, sl, pending


def run_for_symbol(
    symbol: str,
    min_gap_pips: float = 1.0,
    min_score: int = MIN_SCORE,
    counts: dict = None,
    backfill: bool = False,
):
    if counts is None:
        counts = {"M15": M15_COUNT, "H1": H1_COUNT, "H4": H4_COUNT}

    print(f"\n{'=' * 60}")
    print(f"Processing {symbol}")
    print(f"{'=' * 60}")

    # --- Step 1: Collect candle data ---
    # A backfill uses the chunked loader so a very large pull is saved
    # in small pieces; routine runs use the normal collector.
    loader = collect_history if backfill else collect
    print(f"[{symbol}] Collecting candles...")
    loader(symbol, "M15", counts["M15"])
    loader(symbol, "H1", counts["H1"])
    loader(symbol, "H4", counts["H4"])

    # From here on, MT5 connection is no longer needed per-symbol
    # (the loaders already connect/disconnect internally), so we
    # open our own DB session for the rest of the pipeline.
    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=symbol).first()
        if instrument is None:
            print(f"[{symbol}] ERROR: instrument not found after collection, skipping.")
            return None

        digits = instrument.digits
        point = float(instrument.pip_size)
        true_pip = point * 10 if digits in (3, 5) else point

        # --- Step 2: Order blocks (M15) ---
        print(f"[{symbol}] Detecting order blocks...")
        ob_created = detect_order_blocks(db, instrument.id, "M15", counts["M15"])
        ob_mitigated = mark_mitigated_blocks(db, instrument.id, "M15")
        print(f"[{symbol}]   order blocks: {ob_created} created, {ob_mitigated} mitigated")

        # --- Step 3: Liquidity zones (M15, H1, H4) ---
        print(f"[{symbol}] Detecting liquidity zones...")
        for tf in ("M15", "H1", "H4"):
            lz_created = detect_liquidity_zones(db, instrument.id, tf, counts[tf], 3.0, digits, point)
            lz_swept = mark_swept_zones(db, instrument.id, tf)
            print(f"[{symbol}]   liquidity [{tf}]: {lz_created} created, {lz_swept} swept")

        # --- Step 4: CRT setups (H4 range -> M15 manipulation) ---
        print(f"[{symbol}] Detecting CRT setups...")
        crt_created = detect_crt_setups_mtf(db, instrument.id, "H4", "M15", counts["H4"])
        print(f"[{symbol}]   CRT setups: {crt_created} created")

        # --- Step 5: FVG detection (M15 and H1 only) ---
        print(f"[{symbol}] Detecting fair value gaps...")
        min_gap_size = min_gap_pips * true_pip
        for tf in ("M15", "H1"):
            fvg_created = detect_and_store_fvgs(
                db, instrument.id, tf, min_gap_size
            )
            print(f"[{symbol}]   FVG [{tf}]: {fvg_created} stored")

        # --- Step 5b: Market Structure (M15 and H1) ---
        print(f"[{symbol}] Detecting market structure (BOS/CHOCH)...")
        for tf in ("M15", "H1"):
            ms_created = detect_market_structure(db, instrument.id, tf, counts[tf])
            print(f"[{symbol}]   structure [{tf}]: {ms_created} created")

        # --- Step 5c: Trading Sessions (ASIA, LONDON, NEWYORK) ---
        print(f"[{symbol}] Populating trading sessions...")
        sessions_populated = populate_sessions(db, instrument.id, "M15", counts["M15"])
        print(f"[{symbol}]   sessions: {sessions_populated} updated/created")

        # --- Step 5d: SMT Divergence (M15 and H1) ---
        print(f"[{symbol}] Detecting SMT divergence...")
        for tf in ("M15", "H1"):
            smt_created = detect_all_smt_divergences(db, instrument.id, tf, counts[tf])
            print(f"[{symbol}]   SMT [{tf}]: {smt_created} created")

        # --- Step 5e: Draw on Liquidity (DOL) ---
        print(f"[{symbol}] Updating Draw on Liquidity (DOL) targets...")
        for tf in ("H1", "H4"):
            identify_dol_targets(db, instrument.id, tf)
        update_dol_targets(db, instrument.id, "M15", counts["M15"])

        # --- Step 6: Confluence scoring ---
        print(f"[{symbol}] Scoring setups...")
        scored = score_crt_setups_v4(
            db, instrument.id, 15.0, 10.0, digits, point
        )
        print(f"[{symbol}]   scored: {scored} setups")

        # --- Step 7: Trade signal generation ---
        print(f"[{symbol}] Generating trade signals (min score {min_score})...")
        signals_created = generate_signals(db, instrument.id, min_score, RISK_REWARD, 3.0, digits, point)
        print(f"[{symbol}]   signals created: {signals_created}")

        # --- Step 8: Backtest ---
        print(f"[{symbol}] Backtesting signals...")
        results = backtest_all_signals(db, instrument.id, "M15")
        return {"symbol": symbol, "results": results}

    finally:
        db.close()


def main(
    min_gap_pips: float = 1.0,
    min_score: int = MIN_SCORE,
    symbols: list = None,
    backfill: bool = False,
    quiet: bool = False,
):
    if symbols is None:
        symbols = SYMBOLS

    if backfill:
        counts = {"M15": BACKFILL_M15_COUNT, "H1": BACKFILL_H1_COUNT, "H4": BACKFILL_H4_COUNT}
        print("BACKFILL MODE: pulling a large amount of history. This can take a long time.")
    else:
        counts = {"M15": M15_COUNT, "H1": H1_COUNT, "H4": H4_COUNT}

    print(f"Minimum signal score for this run: {min_score}")
    print(f"Candles per timeframe: M15={counts['M15']}, H1={counts['H1']}, H4={counts['H4']}")
    print(f"Symbols: {', '.join(symbols)}")

    all_results = []

    for symbol in symbols:
        try:
            result = run_for_symbol(symbol, min_gap_pips, min_score, counts, backfill)
            if result:
                all_results.append(result)
                if quiet:
                    tp, sl, pending = count_results(result["results"])
                    print(f"[{symbol}] backtest: {len(result['results'])} signals "
                          f"-> TP={tp}, SL={sl}, pending={pending}")
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
        tp, sl, pending = count_results(results)

        total_tp += tp
        total_sl += sl
        total_pending += pending

        print(f"\n{symbol}: {len(results)} signals -> TP={tp}, SL={sl}, pending={pending}")
        if not quiet:
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
    print("  (This total counts overlapping duplicate trades. For trustworthy numbers use")
    print("   strategy_backtest.split_report and strategy_backtest.excursion_report.)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the full SMTE analysis and backtest pipeline.")
    parser.add_argument(
        "--min-gap-pips",
        type=float,
        default=1.0,
        help="Ignore FVGs smaller than this pip size (default: 1.0).",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=MIN_SCORE,
        help=f"Minimum confluence score for a signal (default: {MIN_SCORE}). "
             "Use 0 to generate signals at every score.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Only run these symbols, e.g. --symbols EURUSD.m GBPUSD.m (default: all).",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Pull about 4 years of history (100,000 M15 / 25,000 H1 / 6,500 H4 candles).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print one summary line per symbol instead of every signal.",
    )
    arguments = parser.parse_args()
    if arguments.min_gap_pips < 0:
        parser.error("--min-gap-pips must be non-negative")
    if arguments.min_score < 0:
        parser.error("--min-score must be non-negative")
    if arguments.symbols is not None:
        unknown = [s for s in arguments.symbols if s not in SYMBOLS]
        if unknown:
            parser.error(f"unknown symbol(s): {', '.join(unknown)}. Choose from: {', '.join(SYMBOLS)}")
    main(
        arguments.min_gap_pips,
        arguments.min_score,
        arguments.symbols,
        arguments.backfill,
        arguments.quiet,
    )