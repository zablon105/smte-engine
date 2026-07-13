"""
run_collector.py
Command-line entry point for running the MT5 data collector.

Usage examples (from SMTE/backend, with smte-env activated):
    python -m app.services.run_collector --symbol EURUSD.m --timeframe M15 --count 1000
    python -m app.services.run_collector --symbol GBPUSD.m --timeframe H1 --count 500
"""

import argparse
from app.services.data_collector import collect


def main():
    parser = argparse.ArgumentParser(description="Collect MT5 candle data into the SMTE database.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--timeframe", required=True, choices=[
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"
    ])
    parser.add_argument("--count", type=int, default=1000, help="Number of recent candles to fetch")
    args = parser.parse_args()

    collect(args.symbol, args.timeframe, args.count)


if __name__ == "__main__":
    main()