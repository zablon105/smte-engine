import unittest
from datetime import datetime, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import PerformanceMetric, Trade
from app.services.performance_tracker import (
    calculate_metrics_from_outcomes,
    record_performance_metric,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class PerformanceTrackerTests(unittest.TestCase):
    def test_calculate_metrics_from_outcomes(self):
        # 10 trades: 4 wins at 2.0R, 6 losses at -1.0R
        # Win rate = 40%
        # Net R = (4 * 2.0) - (6 * 1.0) = +2.0R
        # Average R = 2.0 / 10 = +0.20R
        outcomes = [
            {"result": "TP_HIT"},
            {"result": "SL_HIT"},
            {"result": "TP_HIT"},
            {"result": "SL_HIT"},
            {"result": "SL_HIT"},
            {"result": "TP_HIT"},
            {"result": "SL_HIT"},
            {"result": "SL_HIT"},
            {"result": "TP_HIT"},
            {"result": "SL_HIT"},
        ]

        metrics = calculate_metrics_from_outcomes(outcomes, risk_reward=2.0)
        self.assertEqual(metrics["total_trades"], 10)
        self.assertEqual(metrics["win_count"], 4)
        self.assertEqual(metrics["loss_count"], 6)
        self.assertAlmostEqual(metrics["win_rate_pct"], 40.0)
        self.assertAlmostEqual(metrics["avg_r_multiple"], 0.20)
        self.assertAlmostEqual(metrics["net_r"], 2.0)

    def test_record_performance_metric_in_db(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()

        outcomes = [
            {"result": "TP_HIT"},
            {"result": "TP_HIT"},
            {"result": "SL_HIT"},
        ]

        metric = record_performance_metric(
            session,
            strategy_name="SMTE_TEST",
            period_start=datetime(2025, 1, 1),
            period_end=datetime(2025, 2, 1),
            outcomes=outcomes,
            risk_reward=2.0,
        )

        self.assertIsNotNone(metric.id)
        self.assertEqual(metric.total_trades, 3)
        self.assertEqual(metric.win_count, 2)
        self.assertAlmostEqual(float(metric.win_rate_pct), 66.67, places=1)
        session.close()

