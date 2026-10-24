import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from core.execution.scalp_refiner import detect_ltf_mss_and_fvg, ScalpEntry


def make_candle(open_val, high_val, low_val, close_val, dt):
    return SimpleNamespace(
        open=open_val,
        high=high_val,
        low=low_val,
        close=close_val,
        open_time=dt,
    )


class ScalpRefinerTests(unittest.TestCase):
    def test_bullish_mss_and_fvg_detection(self):
        t0 = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
        pip = 0.0001

        # M5 candles sequence:
        # Candle 0: Range high 1.1020, close 1.1010
        # Candle 1: Drop to 1.1000
        # Candle 2: Sweep lower to 1.0980 (lowest low), closes 1.0990
        # Candle 3: Massive Bullish Displacement rallying from 1.0990 up to 1.1030 (breaks 1.1020 MSS!)
        # Candle 4: Pullback to 1.1015 (above candle 2 high 1.1000 -> Bullish FVG between 1.1000 and 1.1015)
        candles = [
            make_candle(1.1015, 1.1020, 1.1005, 1.1010, t0),
            make_candle(1.1010, 1.1012, 1.0995, 1.1000, t0 + timedelta(minutes=5)),
            make_candle(1.1000, 1.1005, 1.0980, 1.0990, t0 + timedelta(minutes=10)),  # Sweep at 1.0980
            make_candle(1.0990, 1.1035, 1.0988, 1.1030, t0 + timedelta(minutes=15)),  # Displacement & MSS break!
            make_candle(1.1030, 1.1032, 1.1015, 1.1020, t0 + timedelta(minutes=20)),
        ]

        result = detect_ltf_mss_and_fvg(
            ltf_candles=candles,
            direction="BULLISH",
            sweep_price=1.0980,
            pip_size=pip,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "BUY")
        self.assertAlmostEqual(result["invalidation_price"], 1.0980)
        # Stop loss should be placed 2 pips below sweep wick (1.0980 - 0.0002 = 1.0978)
        self.assertAlmostEqual(result["stop_loss"], 1.0978)
        self.assertTrue(result["entry_price"] > 1.0980)

    def test_bearish_mss_and_fvg_detection(self):
        t0 = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
        pip = 0.0001

        # M5 candles sequence:
        # Candle 0: Range low 1.0980
        # Candle 1: Rally up to 1.1020 (sweep)
        # Candle 2: Massive Bearish Displacement dumping to 1.0970 (breaks 1.0980 MSS!)
        candles = [
            make_candle(1.0985, 1.0990, 1.0980, 1.0985, t0),
            make_candle(1.0985, 1.1020, 1.0982, 1.1015, t0 + timedelta(minutes=5)),  # Sweep high at 1.1020
            make_candle(1.1015, 1.1018, 1.0968, 1.0970, t0 + timedelta(minutes=10)), # Displacement & MSS break!
        ]

        result = detect_ltf_mss_and_fvg(
            ltf_candles=candles,
            direction="BEARISH",
            sweep_price=1.1020,
            pip_size=pip,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "SELL")
        self.assertAlmostEqual(result["invalidation_price"], 1.1020)
        # Stop loss should be placed 2 pips above sweep wick (1.1020 + 0.0002 = 1.1022)
        self.assertAlmostEqual(result["stop_loss"], 1.1022)

    def test_no_displacement_returns_none(self):
        t0 = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
        pip = 0.0001

        # Flat candles, no break of swing high
        candles = [
            make_candle(1.1015, 1.1025, 1.1010, 1.1015, t0),
            make_candle(1.1015, 1.1018, 1.0990, 1.0995, t0 + timedelta(minutes=5)),
            make_candle(1.0995, 1.1000, 1.0992, 1.0998, t0 + timedelta(minutes=10)),
        ]

        result = detect_ltf_mss_and_fvg(
            ltf_candles=candles,
            direction="BULLISH",
            sweep_price=1.0990,
            pip_size=pip,
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
