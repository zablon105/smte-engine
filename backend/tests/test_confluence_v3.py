import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import (
    CrtSetup,
    FairValueGap,
    Instrument,
    MarketStructure,
    SmtDivergence,
    SetupScore,
    TradingSession,
)
from core.scoring.confluence import score_crt_setups_v3, score_crt_setups_v4


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class ScoreCrtSetupsV3Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.session.add_all(
            [
                Instrument(
                    id=1,
                    symbol="EURUSD.test",
                    digits=4,
                    pip_size=0.0001,
                    contract_size=100000,
                ),
                Instrument(
                    id=2,
                    symbol="GBPUSD.test",
                    digits=4,
                    pip_size=0.0001,
                    contract_size=100000,
                ),
            ]
        )

        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        setups = [
            CrtSetup(
                id=1,
                instrument_id=1,
                timeframe="M15",
                setup_direction="BULLISH",
                phase="DISTRIBUTION",
                range_high=1.11,
                range_low=1.09,
                manipulation_price=1.1,
                detected_at=base_time,
                is_valid=True,
            ),
            CrtSetup(
                id=2,
                instrument_id=1,
                timeframe="M15",
                setup_direction="BULLISH",
                phase="DISTRIBUTION",
                range_high=1.11,
                range_low=1.09,
                manipulation_price=1.1,
                detected_at=base_time + timedelta(hours=2),
                is_valid=True,
            ),
            CrtSetup(
                id=3,
                instrument_id=1,
                timeframe="M15",
                setup_direction="BULLISH",
                phase="DISTRIBUTION",
                range_high=1.11,
                range_low=1.09,
                manipulation_price=1.1,
                detected_at=base_time + timedelta(hours=30),
                is_valid=True,
            ),
        ]
        self.session.add_all(setups)
        self.session.flush()
        self.session.add_all(
            [
                FairValueGap(
                    instrument_id=1,
                    timeframe="M15",
                    gap_type="BULLISH",
                    bottom_price=1.0995,
                    top_price=1.1005,
                    formed_at=base_time - timedelta(minutes=30),
                    filled_at=base_time + timedelta(hours=1),
                    fill_percentage=100,
                ),
                FairValueGap(
                    instrument_id=1,
                    timeframe="H1",
                    gap_type="BULLISH",
                    bottom_price=1.0995,
                    top_price=1.1005,
                    formed_at=base_time + timedelta(hours=1),
                    filled_at=base_time + timedelta(hours=1, minutes=30),
                    fill_percentage=100,
                ),
                FairValueGap(
                    instrument_id=1,
                    timeframe="H4",
                    gap_type="BULLISH",
                    bottom_price=1.0995,
                    top_price=1.1005,
                    formed_at=base_time - timedelta(hours=1),
                    filled_at=None,
                    fill_percentage=0,
                ),
            ]
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_scores_only_fvgs_not_filled_before_each_setup(self):
        processed = score_crt_setups_v3(
            self.session,
            instrument_id=1,
            digits=4,
            point=0.0001,
        )

        self.assertEqual(processed, 3)
        scores = {
            score.crt_setup_id: score
            for score in self.session.query(SetupScore).all()
        }
        self.assertEqual(scores[1].fvg_score, 5)
        self.assertEqual(scores[1].total_score, 8)
        self.assertEqual(scores[2].fvg_score, 0)
        self.assertEqual(scores[2].total_score, 3)
        self.assertEqual(scores[3].fvg_score, 0)
        self.assertEqual(scores[3].total_score, 3)

    def test_v4_scores_only_prior_recent_directional_events_and_recorded_sessions(self):
        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.session.add_all(
            [
                MarketStructure(
                    instrument_id=1,
                    timeframe="M15",
                    event_type="BOS",
                    direction="BULLISH",
                    swing_price=1.09,
                    break_price=1.1,
                    occurred_at=base_time - timedelta(hours=2),
                ),
                MarketStructure(
                    instrument_id=1,
                    timeframe="H4",
                    event_type="BOS",
                    direction="BULLISH",
                    swing_price=1.09,
                    break_price=1.1,
                    occurred_at=base_time - timedelta(minutes=10),
                ),
                MarketStructure(
                    instrument_id=1,
                    timeframe="M15",
                    event_type="BOS",
                    direction="BULLISH",
                    swing_price=1.09,
                    break_price=1.1,
                    occurred_at=base_time + timedelta(minutes=1),
                ),
                MarketStructure(
                    instrument_id=1,
                    timeframe="M15",
                    event_type="BOS",
                    direction="BULLISH",
                    swing_price=1.09,
                    break_price=1.1,
                    occurred_at=base_time - timedelta(hours=25),
                ),
                SmtDivergence(
                    instrument_id=1,
                    correlated_instrument_id=2,
                    timeframe="M15",
                    divergence_type="BULLISH",
                    detected_at=base_time - timedelta(hours=1),
                ),
                SmtDivergence(
                    instrument_id=1,
                    correlated_instrument_id=1,
                    timeframe="M15",
                    divergence_type="BULLISH",
                    detected_at=base_time - timedelta(minutes=1),
                ),
                SmtDivergence(
                    instrument_id=1,
                    correlated_instrument_id=2,
                    timeframe="M15",
                    divergence_type="BULLISH",
                    detected_at=base_time + timedelta(minutes=1),
                ),
                SmtDivergence(
                    instrument_id=1,
                    correlated_instrument_id=2,
                    timeframe="M15",
                    divergence_type="BULLISH",
                    detected_at=base_time - timedelta(hours=25),
                ),
                TradingSession(
                    instrument_id=1,
                    session_date=base_time.date(),
                    session_name="LONDON",
                    start_time=base_time - timedelta(minutes=30),
                    end_time=base_time + timedelta(hours=1),
                ),
            ]
        )
        self.session.commit()

        processed = score_crt_setups_v4(
            self.session,
            instrument_id=1,
            digits=4,
            point=0.0001,
        )

        self.assertEqual(processed, 3)
        scores = {
            score.crt_setup_id: score
            for score in self.session.query(SetupScore).all()
        }
        self.assertEqual(scores[1].structure_score, 5)
        self.assertEqual(scores[1].smt_score, 5)
        self.assertEqual(scores[1].session_score, 3)
        self.assertEqual(scores[1].total_score, 21)
        self.assertEqual(scores[2].structure_score, 5)
        self.assertEqual(scores[2].smt_score, 5)
        self.assertEqual(scores[2].session_score, 0)
        self.assertEqual(scores[2].total_score, 13)
        self.assertEqual(scores[3].structure_score, 0)
        self.assertEqual(scores[3].smt_score, 0)
        self.assertEqual(scores[3].session_score, 0)
        self.assertEqual(scores[3].total_score, 3)


if __name__ == "__main__":
    unittest.main()
