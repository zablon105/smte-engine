"""
test_api.py
Automated tests for FastAPI REST API endpoints.
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


class TestFastAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ONLINE")
        self.assertIn("mt5_connected", data)
        self.assertIn("database_connected", data)

    def test_get_open_trades(self):
        response = self.client.get("/api/v1/trades/open")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_trade_history(self):
        response = self.client.get("/api/v1/trades/history?limit=10")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_active_signals(self):
        response = self.client.get("/api/v1/signals/active?limit=5")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_market_instruments(self):
        response = self.client.get("/api/v1/market/instruments")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_market_sessions(self):
        response = self.client.get("/api/v1/market/sessions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("current_utc_time", data)
        self.assertIn("active_session", data)
        self.assertIn("is_killzone", data)

    def test_get_analytics_account(self):
        response = self.client.get("/api/v1/analytics/account")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("balance", data)
        self.assertIn("equity", data)
        self.assertIn("currency", data)

    def test_get_analytics_performance(self):
        response = self.client.get("/api/v1/analytics/performance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_trades", data)
        self.assertIn("win_rate_pct", data)
        self.assertIn("profit_factor", data)
        self.assertIn("equity_curve", data)

    def test_get_strategy_performance(self):
        response = self.client.get("/api/v1/analytics/strategies")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 4)
        strategies = [s["strategy_name"] for s in data]
        self.assertTrue(any("Turtle Soup" in s for s in strategies))
        self.assertTrue(any("Unicorn" in s for s in strategies))


if __name__ == "__main__":
    unittest.main()
