import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import Candle, Instrument, MarketStructure
from core.market_structure.detector import (
    MarketStructureEvent,
    detect_market_structure,
    detect_structure_events,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class MarketStructureUnitTests(unittest.TestCase):
    def test_detects_bullish_bos_and_choch(self):
        """
        Builds a price path:
        1. Low at index 2 (swing low at 10.0)
        2. High at index 5 (swing high at 15.0)
        3. Higher Low at index 8 (swing low at 12.0)
        4. Break above 15.0 at index 11 (close 16.0) -> Bullish CHOCH (initial establishment of bullish trend)
        5. Higher High at index 13 (swing high at 18.0)
        6. Break above 18.0 at index 17 (close 19.0) -> Bullish BOS (continuation of bullish trend)
        """
        candles = [
            {"time": 0, "open": 11.0, "high": 12.0, "low": 10.5, "close": 11.0},
            {"time": 1, "open": 11.0, "high": 11.5, "low": 10.5, "close": 11.0},
            {"time": 2, "open": 11.0, "high": 11.5, "low": 10.0, "close": 10.5},  # Swing Low at 10.0
            {"time": 3, "open": 10.5, "high": 12.0, "low": 10.5, "close": 11.5},
            {"time": 4, "open": 11.5, "high": 13.0, "low": 11.0, "close": 12.5},
            {"time": 5, "open": 12.5, "high": 15.0, "low": 12.0, "close": 14.0},  # Swing High at 15.0
            {"time": 6, "open": 14.0, "high": 14.2, "low": 13.0, "close": 13.5},
            {"time": 7, "open": 13.5, "high": 13.8, "low": 12.5, "close": 13.0},
            {"time": 8, "open": 13.0, "high": 13.5, "low": 12.0, "close": 12.5},  # Higher Low at 12.0
            {"time": 9, "open": 12.5, "high": 14.0, "low": 12.5, "close": 13.5},
            {"time": 10, "open": 13.5, "high": 14.5, "low": 13.0, "close": 14.2},
            {"time": 11, "open": 14.2, "high": 16.5, "low": 14.0, "close": 16.0}, # Break above 15.0 -> CHOCH
            {"time": 12, "open": 16.0, "high": 17.0, "low": 15.5, "close": 16.5},
            {"time": 13, "open": 16.5, "high": 18.0, "low": 16.0, "close": 17.5}, # Swing High at 18.0
            {"time": 14, "open": 17.5, "high": 17.8, "low": 16.5, "close": 17.0},
            {"time": 15, "open": 17.0, "high": 17.2, "low": 16.8, "close": 17.0},
            {"time": 16, "open": 17.0, "high": 17.5, "low": 16.9, "close": 17.3},
            {"time": 17, "open": 17.3, "high": 19.5, "low": 17.0, "close": 19.0}, # Break above 18.0 -> BOS
        ]

        events = detect_structure_events(candles, swing_length=2)
        self.assertEqual(len(events), 2)

        # First event: CHOCH (trend turned bullish)
        self.assertEqual(events[0].event_type, "CHOCH")
        self.assertEqual(events[0].direction, "BULLISH")
        self.assertEqual(events[0].swing_price, 15.0)
        self.assertEqual(events[0].break_price, 16.0)
        self.assertEqual(events[0].occurred_at, 11)

        # Second event: BOS (continuation of bullish trend)
        self.assertEqual(events[1].event_type, "BOS")
        self.assertEqual(events[1].direction, "BULLISH")
        self.assertEqual(events[1].swing_price, 18.0)
        self.assertEqual(events[1].break_price, 19.0)
        self.assertEqual(events[1].occurred_at, 17)

    def test_detects_bearish_choch_when_uptrend_breaks_higher_low(self):
        """
        After establishing an uptrend, breaking the higher low at 12.0
        should trigger a BEARISH CHOCH.
        """
        candles = [
            {"time": 0, "open": 11.0, "high": 12.0, "low": 10.5, "close": 11.0},
            {"time": 1, "open": 11.0, "high": 11.5, "low": 10.5, "close": 11.0},
            {"time": 2, "open": 11.0, "high": 11.5, "low": 10.0, "close": 10.5},
            {"time": 3, "open": 10.5, "high": 12.0, "low": 10.5, "close": 11.5},
            {"time": 4, "open": 11.5, "high": 13.0, "low": 11.0, "close": 12.5},
            {"time": 5, "open": 12.5, "high": 15.0, "low": 12.0, "close": 14.0},  # Swing High at 15.0
            {"time": 6, "open": 14.0, "high": 14.2, "low": 13.0, "close": 13.5},
            {"time": 7, "open": 13.5, "high": 13.8, "low": 12.5, "close": 13.0},
            {"time": 8, "open": 13.0, "high": 13.5, "low": 12.0, "close": 12.5},  # Higher Low at 12.0
            {"time": 9, "open": 12.5, "high": 14.0, "low": 12.5, "close": 13.5},
            {"time": 10, "open": 13.5, "high": 14.5, "low": 13.0, "close": 14.2},
            {"time": 11, "open": 14.2, "high": 16.5, "low": 14.0, "close": 16.0}, # Break above 15.0 -> BULLISH CHOCH
            # Now reversal down:
            {"time": 12, "open": 16.0, "high": 16.2, "low": 13.0, "close": 13.5},
            {"time": 13, "open": 13.5, "high": 13.8, "low": 11.0, "close": 11.5}, # Breaks below 12.0 -> BEARISH CHOCH
        ]

        events = detect_structure_events(candles, swing_length=2)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_type, "CHOCH")
        self.assertEqual(events[0].direction, "BULLISH")

        self.assertEqual(events[1].event_type, "CHOCH")
        self.assertEqual(events[1].direction, "BEARISH")
        self.assertEqual(events[1].swing_price, 12.0)
        self.assertEqual(events[1].break_price, 11.5)
        self.assertEqual(events[1].occurred_at, 13)


class MarketStructureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.instrument = Instrument(
            id=1,
            symbol="EURUSD.m",
            digits=5,
            pip_size=0.00001,
            contract_size=100000,
        )
        self.session.add(self.instrument)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_detect_market_structure_stores_in_db_and_deduplicates(self):
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        raw_candles = [
            {"high": 1.1020, "low": 1.1005, "open": 1.1010, "close": 1.1010},
            {"high": 1.1015, "low": 1.1005, "open": 1.1010, "close": 1.1010},
            {"high": 1.1015, "low": 1.1000, "open": 1.1010, "close": 1.1005},  # Swing low at 1.1000
            {"high": 1.1020, "low": 1.1005, "open": 1.1005, "close": 1.1015},
            {"high": 1.1030, "low": 1.1010, "open": 1.1015, "close": 1.1025},
            {"high": 1.1050, "low": 1.1020, "open": 1.1025, "close": 1.1040},  # Swing high at 1.1050
            {"high": 1.1042, "low": 1.1030, "open": 1.1040, "close": 1.1035},
            {"high": 1.1038, "low": 1.1025, "open": 1.1035, "close": 1.1030},
            {"high": 1.1035, "low": 1.1020, "open": 1.1030, "close": 1.1025},  # Swing low at 1.1020
            {"high": 1.1040, "low": 1.1025, "open": 1.1025, "close": 1.1035},
            {"high": 1.1045, "low": 1.1030, "open": 1.1035, "close": 1.1042},
            {"high": 1.1065, "low": 1.1040, "open": 1.1042, "close": 1.1060},  # Break above 1.1050
        ]

        from datetime import timedelta
        for i, c in enumerate(raw_candles):
            candle = Candle(
                instrument_id=1,
                timeframe="M15",
                open_time=base_time + timedelta(minutes=15 * i),
                open=c["open"],
                high=c["high"],
                low=c["low"],
                close=c["close"],
                volume=100,
            )
            self.session.add(candle)
        self.session.commit()

        created = detect_market_structure(
            self.session,
            instrument_id=1,
            timeframe="M15",
            lookback=50,
            swing_length=2,
        )
        self.assertEqual(created, 1)

        records = self.session.query(MarketStructure).all()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].direction, "BULLISH")
        self.assertAlmostEqual(float(records[0].swing_price), 1.1050)
        self.assertAlmostEqual(float(records[0].break_price), 1.1060)

        # Calling again should deduplicate (created == 0)
        created_again = detect_market_structure(
            self.session,
            instrument_id=1,
            timeframe="M15",
            lookback=50,
            swing_length=2,
        )
        self.assertEqual(created_again, 0)

