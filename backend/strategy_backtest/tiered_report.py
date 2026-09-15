"""
tiered_report.py
Breaks down backtest win rate BY score tier, to answer the real
question: does a higher confluence score actually predict a better
outcome, or is the scoring system currently just noise?

Usage (from SMTE/backend, with smte-env activated):
    python -m strategy_backtest.tiered_report --symbol EURUSD.m
    (omit --symbol to run across ALL instruments in the database)
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument, TradeSignal, SetupScore, CrtSetup
from strategy_backtest.signal_backtest import backtest_signal


def _score_tier(total_score: int) -> str:
    if total_score >= 15:
        return "High (15+)"
    elif total_score >= 10:
        return "Medium (10-14)"
    else:
        return "Low (7-9)"


def generate_tiered_report(db, instrument_ids: list[int], timeframe: str = "M15"):
    tiers = {
        "High (15+)": {"tp": 0, "sl": 0, "pending": 0},
        "Medium (10-14)": {"tp": 0, "sl": 0, "pending": 0},
        "Low (7-9)": {"tp": 0, "sl": 0, "pending": 0},
    }

    signals = (
        db.query(TradeSignal, SetupScore, CrtSetup)
        .join(SetupScore, SetupScore.id == TradeSignal.setup_score_id)
        .join(CrtSetup, CrtSetup.id == TradeSignal.crt_setup_id)
        .filter(TradeSignal.instrument_id.in_(instrument_ids))
        .all()
    )

    for signal, score, setup in signals:
        tier = _score_tier(score.total_score)
        outcome = backtest_signal(db, signal, setup, timeframe)

        if outcome["result"] == "TP_HIT":
            tiers[tier]["tp"] += 1
        elif outcome["result"] == "SL_HIT":
            tiers[tier]["sl"] += 1
        else:
            tiers[tier]["pending"] += 1

    return tiers


def main():
    parser = argparse.ArgumentParser(description="Backtest win rate broken down by confluence score tier.")
    parser.add_argument("--symbol", default=None, help="Optional: restrict to one symbol, e.g. EURUSD.m")
    parser.add_argument("--timeframe", default="M15")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.symbol:
            instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
            if instrument is None:
                print(f"No instrument found for symbol '{args.symbol}'.")
                return
            instrument_ids = [instrument.id]
            label = args.symbol
        else:
            instrument_ids = [i.id for i in db.query(Instrument).all()]
            label = "ALL SYMBOLS"

        tiers = generate_tiered_report(db, instrument_ids, args.timeframe)

        print(f"\n{'=' * 60}")
        print(f"WIN RATE BY SCORE TIER ({label})")
        print(f"{'=' * 60}")

        for tier_name in ["High (15+)", "Medium (10-14)", "Low (7-9)"]:
            data = tiers[tier_name]
            decided = data["tp"] + data["sl"]
            win_rate = (data["tp"] / decided * 100) if decided > 0 else 0
            ev = (win_rate / 100 * 2.0) - ((1 - win_rate / 100) * 1.0) if decided > 0 else 0

            print(f"\n{tier_name}:")
            print(f"  Total signals: {data['tp'] + data['sl'] + data['pending']}")
            print(f"  TP: {data['tp']}, SL: {data['sl']}, Pending: {data['pending']}")
            print(f"  Win rate: {win_rate:.1f}%")
            print(f"  Expected value at 2:1 RR: {ev:.2f}R per trade")

        print(f"\n{'=' * 60}")
    finally:
        db.close()


if __name__ == "__main__":
    main()