import unittest
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import Candle, Instrument, TradingSession
from core.sessions.builder import (
    DEFAULT_SESSIONS,
    build_sessions_from_candles,
    populate_sessions,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class SessionUnitTests(unittest.TestCase):
    def test_builds_sessions_correctly(self):
        c_date = date(2025, 3, 10)
        # Create candles in Asia (02:00, 04:00), London (08:00, 10:00), NY (13:00, 15:00)
        candles = [
            {"open_time": datetime(2025, 3, 10, 2, 0, tzinfo=timezone.utc), "high": 1.1020, "low": 1.1000},
            {"open_time": datetime(2025, 3, 10, 4, 0, tzinfo=timezone.utc), "high": 1.1050, "low": 1.1010},
            {"open_time": datetime(2025, 3, 10, 8, 0, tzinfo=timezone.utc), "high": 1.1100, "low": 1.1040},
            {"open_time": datetime(2025, 3, 10, 10, 0, tzinfo=timezone.utc), "high": 1.1120, "low": 1.1080},
            {"open_time": datetime(2025, 3, 10, 13, 0, tzinfo=timezone.utc), "high": 1.1150, "low": 1.1090},
            {"open_time": datetime(2025, 3, 10, 15, 0, tzinfo=timezone.utc), "high": 1.1130, "low": 1.1070},
        ]

        sessions = build_sessions_from_candles(candles, DEFAULT_SESSIONS)
        self.assertEqual(len(sessions), 3)

        session_map = {s.session_name: s for s in sessions}

        # ASIA
        self.assertIn("ASIA", session_map)
        asia = session_map["ASIA"]
        self.assertEqual(asia.session_date, c_date)
        self.assertEqual(asia.session_high, 1.1050)
        self.assertEqual(asia.session_low, 1.1000)
        self.assertEqual(asia.start_time, datetime(2025, 3, 10, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(asia.end_time, datetime(2025, 3, 10, 8, 0, tzinfo=timezone.utc))

        # LONDON
        self.assertIn("LONDON", session_map)
        london = session_map["LONDON"]
        # Notice candles at 08:00, 10:00, and also 13:00, 15:00 fall in London (07:00-16:00)
        self.assertEqual(london.session_high, 1.1150)
        self.assertEqual(london.session_low, 1.1040)

        # NEWYORK
        self.assertIn("NEWYORK", session_map)
        ny = session_map["NEWYORK"]
        self.assertEqual(ny.session_high, 1.1150)
        self.assertEqual(ny.session_low, 1.1070)


class SessionIntegrationTests(unittest.TestCase):
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

    def test_populate_sessions_in_db(self):
        # Insert M15 candles for London session
        c_date = date(2025, 5, 1)
        for hour in range(8, 12):
            candle = Candle(
                instrument_id=1,
                timeframe="M15",
                open_time=datetime(2025, 5, 1, hour, 0, tzinfo=timezone.utc),
                open=1.1000,
                high=1.1050 + (hour * 0.001),
                low=1.0980 - (hour * 0.001),
                close=1.1020,
                volume=500,
            )
            self.session.add(candle)
        self.session.commit()

        count = populate_sessions(self.session, instrument_id=1, timeframe="M15")
        self.assertGreater(count, 0)

        records = self.session.query(TradingSession).all()
        self.assertEqual(len(records), 1)  # Only London had candles
        self.assertEqual(records[0].session_name, "LONDON")
        self.assertAlmostEqual(float(records[0].session_high), 1.1050 + 11 * 0.001)

        # Test idempotency (re-running with same candles should not duplicate)
        count_again = populate_sessions(self.session, instrument_id=1, timeframe="M15")
        self.assertEqual(count_again, 0)
        records_after = self.session.query(TradingSession).all()
        self.assertEqual(len(records_after), 1)

