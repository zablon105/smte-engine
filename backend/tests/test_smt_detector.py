import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import Candle, Instrument, SmtDivergence
from core.smt.detector import (
    detect_all_smt_divergences,
    detect_smt_divergence,
    detect_smt_events,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class SmtDetectorUnitTests(unittest.TestCase):
    def test_detects_bullish_smt_divergence(self):
        """
        Pair A: Low 1 at 10.0, Low 2 at 8.0 (Lower Low)
        Pair B: Low 1 at 20.0, Low 2 at 22.0 (Higher Low)
        -> Bullish SMT
        """
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        # Create candles for Pair A (swing low at idx 2, swing low at idx 6)
        candles_a = [
            {"open_time": base_time + timedelta(hours=0), "high": 12.0, "low": 11.0},
            {"open_time": base_time + timedelta(hours=1), "high": 11.5, "low": 10.5},
            {"open_time": base_time + timedelta(hours=2), "high": 11.0, "low": 10.0},  # Low 1 = 10.0
            {"open_time": base_time + timedelta(hours=3), "high": 12.0, "low": 10.5},
            {"open_time": base_time + timedelta(hours=4), "high": 13.0, "low": 11.0},
            {"open_time": base_time + timedelta(hours=5), "high": 11.0, "low": 9.0},
            {"open_time": base_time + timedelta(hours=6), "high": 10.0, "low": 8.0},   # Low 2 = 8.0 (Lower Low)
            {"open_time": base_time + timedelta(hours=7), "high": 10.5, "low": 8.5},
            {"open_time": base_time + timedelta(hours=8), "high": 11.0, "low": 9.0},
        ]

        # Create candles for Pair B (swing low at idx 2, swing low at idx 6)
        candles_b = [
            {"open_time": base_time + timedelta(hours=0), "high": 22.0, "low": 21.0},
            {"open_time": base_time + timedelta(hours=1), "high": 21.5, "low": 20.5},
            {"open_time": base_time + timedelta(hours=2), "high": 21.0, "low": 20.0},  # Low 1 = 20.0
            {"open_time": base_time + timedelta(hours=3), "high": 22.0, "low": 20.5},
            {"open_time": base_time + timedelta(hours=4), "high": 24.0, "low": 21.0},
            {"open_time": base_time + timedelta(hours=5), "high": 23.5, "low": 22.5},
            {"open_time": base_time + timedelta(hours=6), "high": 23.0, "low": 22.0},  # Low 2 = 22.0 (Higher Low!)
            {"open_time": base_time + timedelta(hours=7), "high": 24.0, "low": 22.5},
            {"open_time": base_time + timedelta(hours=8), "high": 25.0, "low": 23.0},
        ]

        events = detect_smt_events(candles_a, candles_b, swing_length=2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].divergence_type, "BULLISH")

    def test_detects_bearish_smt_divergence(self):
        """
        Pair A: High 1 at 15.0, High 2 at 18.0 (Higher High)
        Pair B: High 1 at 25.0, High 2 at 23.0 (Lower High)
        -> Bearish SMT
        """
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        candles_a = [
            {"open_time": base_time + timedelta(hours=0), "high": 13.0, "low": 11.0},
            {"open_time": base_time + timedelta(hours=1), "high": 14.0, "low": 12.0},
            {"open_time": base_time + timedelta(hours=2), "high": 15.0, "low": 13.0},  # High 1 = 15.0
            {"open_time": base_time + timedelta(hours=3), "high": 14.0, "low": 12.0},
            {"open_time": base_time + timedelta(hours=4), "high": 13.0, "low": 11.0},
            {"open_time": base_time + timedelta(hours=5), "high": 16.0, "low": 14.0},
            {"open_time": base_time + timedelta(hours=6), "high": 18.0, "low": 15.0},  # High 2 = 18.0 (Higher High)
            {"open_time": base_time + timedelta(hours=7), "high": 17.0, "low": 14.0},
            {"open_time": base_time + timedelta(hours=8), "high": 16.0, "low": 13.0},
        ]

        candles_b = [
            {"open_time": base_time + timedelta(hours=0), "high": 23.0, "low": 21.0},
            {"open_time": base_time + timedelta(hours=1), "high": 24.0, "low": 22.0},
            {"open_time": base_time + timedelta(hours=2), "high": 25.0, "low": 23.0},  # High 1 = 25.0
            {"open_time": base_time + timedelta(hours=3), "high": 24.0, "low": 22.0},
            {"open_time": base_time + timedelta(hours=4), "high": 22.0, "low": 20.0},
            {"open_time": base_time + timedelta(hours=5), "high": 22.5, "low": 20.5},
            {"open_time": base_time + timedelta(hours=6), "high": 23.0, "low": 21.0},  # High 2 = 23.0 (Lower High!)
            {"open_time": base_time + timedelta(hours=7), "high": 22.0, "low": 20.0},
            {"open_time": base_time + timedelta(hours=8), "high": 21.0, "low": 19.0},
        ]

        events = detect_smt_events(candles_a, candles_b, swing_length=2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].divergence_type, "BEARISH")


class SmtDetectorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.inst_eur = Instrument(
            id=1,
            symbol="EURUSD.m",
            digits=5,
            pip_size=0.00001,
            contract_size=100000,
        )
        self.inst_gbp = Instrument(
            id=2,
            symbol="GBPUSD.m",
            digits=5,
            pip_size=0.00001,
            contract_size=100000,
        )
        self.session.add_all([self.inst_eur, self.inst_gbp])
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_detect_all_smt_divergences_stores_and_deduplicates(self):
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        # Add candles for EUR (Low at idx 2 = 1.0900, Low at idx 6 = 1.0850)
        lows_eur = [1.0950, 1.0920, 1.0900, 1.0930, 1.0940, 1.0900, 1.0850, 1.0880, 1.0900]
        # Add candles for GBP (Low at idx 2 = 1.2500, Low at idx 6 = 1.2550)
        lows_gbp = [1.2550, 1.2520, 1.2500, 1.2530, 1.2580, 1.2570, 1.2550, 1.2580, 1.2600]

        for i in range(len(lows_eur)):
            t = base_time + timedelta(hours=i)
            self.session.add(
                Candle(
                    instrument_id=1,
                    timeframe="H1",
                    open_time=t,
                    open=lows_eur[i] + 0.0010,
                    high=lows_eur[i] + 0.0020,
                    low=lows_eur[i],
                    close=lows_eur[i] + 0.0010,
                    volume=100,
                )
            )
            self.session.add(
                Candle(
                    instrument_id=2,
                    timeframe="H1",
                    open_time=t,
                    open=lows_gbp[i] + 0.0010,
                    high=lows_gbp[i] + 0.0020,
                    low=lows_gbp[i],
                    close=lows_gbp[i] + 0.0010,
                    volume=100,
                )
            )
        self.session.commit()

        created = detect_all_smt_divergences(self.session, instrument_id=1, timeframe="H1")
        self.assertEqual(created, 1)

        records = self.session.query(SmtDivergence).all()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].divergence_type, "BULLISH")
        self.assertEqual(records[0].correlated_instrument_id, 2)

        # Idempotency: re-running should not create duplicate
        created_again = detect_all_smt_divergences(self.session, instrument_id=1, timeframe="H1")
        self.assertEqual(created_again, 0)

