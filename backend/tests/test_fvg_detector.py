import unittest
from types import SimpleNamespace

from core.market_analysis.fvg_detector import detect_and_store_fvgs, detect_fvgs


class DetectFvgsTests(unittest.TestCase):
    def test_detects_bullish_gap_and_marks_partial_mitigation(self):
        candles = [
            {"time": 1, "high": 10.0, "low": 8.0},
            {"time": 2, "high": 12.0, "low": 9.0},
            {"time": 3, "high": 14.0, "low": 11.0},
            {"time": 4, "high": 13.0, "low": 10.5},
        ]

        fvgs = detect_fvgs(candles)

        bullish_gap = next(fvg for fvg in fvgs if fvg.direction == "bullish")
        self.assertEqual((bullish_gap.zone_low, bullish_gap.zone_high), (10.0, 11.0))
        self.assertEqual(bullish_gap.created_at, 3)
        self.assertEqual(bullish_gap.candle_index, 2)
        self.assertEqual(bullish_gap.status, "partial")
        self.assertIsNone(bullish_gap.mitigated_at)
        self.assertEqual(bullish_gap.fill_percentage, 50.0)

    def test_detects_bearish_gap_and_uses_open_time_for_objects(self):
        candles = [
            SimpleNamespace(open_time=1, high=12.0, low=10.0),
            SimpleNamespace(open_time=2, high=11.0, low=8.0),
            SimpleNamespace(open_time=3, high=9.0, low=7.0),
            SimpleNamespace(open_time=4, high=9.5, low=7.5),
            SimpleNamespace(open_time=5, high=10.0, low=7.0),
        ]

        fvgs = detect_fvgs(candles)

        bearish_gap = next(fvg for fvg in fvgs if fvg.direction == "bearish")
        self.assertEqual((bearish_gap.zone_low, bearish_gap.zone_high), (9.0, 10.0))
        self.assertEqual(bearish_gap.created_at, 3)
        self.assertEqual(bearish_gap.status, "filled")
        self.assertEqual(bearish_gap.mitigated_at, 5)
        self.assertEqual(bearish_gap.fill_percentage, 100.0)

    def test_unmitigated_gap_has_zero_fill_percentage(self):
        candles = [
            {"time": 1, "high": 10.0, "low": 8.0},
            {"time": 2, "high": 12.0, "low": 9.0},
            {"time": 3, "high": 14.0, "low": 11.0},
        ]

        bullish_gap = next(fvg for fvg in detect_fvgs(candles) if fvg.direction == "bullish")

        self.assertEqual(bullish_gap.status, "open")
        self.assertEqual(bullish_gap.fill_percentage, 0.0)

    def test_minimum_gap_size_filters_small_gaps(self):
        candles = [
            {"time": 1, "high": 10.0, "low": 8.0},
            {"time": 2, "high": 12.0, "low": 9.0},
            {"time": 3, "high": 14.0, "low": 10.5},
        ]

        self.assertEqual(detect_fvgs(candles, min_gap_size=0.6), [])
        self.assertEqual(len(detect_fvgs(candles, min_gap_size=0.5)), 1)

    def test_rejects_negative_minimum_gap_size(self):
        with self.assertRaises(ValueError):
            detect_fvgs([], min_gap_size=-0.1)

    def test_detect_and_store_replaces_rows_for_the_requested_scope(self):
        from app.models.models import Candle, FairValueGap

        candle_rows = [
            SimpleNamespace(open_time=1, high=10.0, low=8.0),
            SimpleNamespace(open_time=2, high=12.0, low=9.0),
            SimpleNamespace(open_time=3, high=14.0, low=11.0),
            SimpleNamespace(open_time=4, high=13.0, low=10.5),
        ]

        class FakeQuery:
            def __init__(self, model, db=None, rows=None):
                self.model = model
                self.db = db
                self.rows = rows
                self.filters = ()

            def filter(self, *conditions):
                self.filters = conditions
                return self

            def order_by(self, *_):
                return self

            def all(self):
                return self.rows

            def delete(self, synchronize_session):
                self.db.deleted_scope = self.filters
                self.db.synchronize_session = synchronize_session

        class FakeDB:
            def __init__(self):
                self.fvg_model = None
                self.committed = False
                self.rolled_back = False

            def query(self, *entities):
                if entities[0] is FairValueGap:
                    return FakeQuery(FairValueGap, db=self)
                return FakeQuery(Candle, rows=candle_rows)

            def add_all(self, rows):
                self.fvg_model = rows[0]
                self.stored_rows = rows

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

        db = FakeDB()

        count = detect_and_store_fvgs(db, instrument_id=7, timeframe="M15")

        self.assertEqual(count, 1)
        self.assertEqual(db.fvg_model.gap_type, "BULLISH")
        self.assertEqual(db.fvg_model.top_price, 11.0)
        self.assertEqual(db.fvg_model.bottom_price, 10.0)
        self.assertEqual(db.fvg_model.fill_percentage, 50.0)
        self.assertEqual(db.fvg_model.instrument_id, 7)
        self.assertEqual(db.fvg_model.timeframe, "M15")
        self.assertTrue(db.committed)
        self.assertFalse(db.rolled_back)
        self.assertEqual(len(db.deleted_scope), 2)
        self.assertFalse(db.synchronize_session)


if __name__ == "__main__":
    unittest.main()
