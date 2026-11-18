import unittest
import sys
from unittest.mock import patch

from core.execution.run_scalper import main, run_scalp_cycle


class RunScalperTests(unittest.TestCase):
    @patch("core.execution.run_scalper.sync_and_manage_open_trades")
    @patch("core.execution.run_scalper.scan_symbol_for_scalp", return_value=None)
    @patch("core.execution.run_scalper.mt5_client")
    def test_dry_run_does_not_manage_open_trades(
        self, mock_mt5_client, _mock_scan, mock_sync
    ):
        run_scalp_cycle(db=None, symbols=["EURUSD.m"], ltf="M5", dry_run=True)

        mock_mt5_client.connect.assert_called_once()
        mock_mt5_client.disconnect.assert_called_once()
        mock_sync.assert_not_called()

    @patch("core.execution.run_scalper.sync_and_manage_open_trades")
    @patch("core.execution.run_scalper.scan_symbol_for_scalp", return_value=None)
    @patch("core.execution.run_scalper.mt5_client")
    def test_live_cycle_manages_open_trades(
        self, mock_mt5_client, _mock_scan, mock_sync
    ):
        mock_sync.return_value = {
            "managed": 0,
            "closed": 0,
            "breakeven_set": 0,
        }

        run_scalp_cycle(db=None, symbols=["EURUSD.m"], ltf="M5", dry_run=False)

        mock_sync.assert_called_once_with(None, breakeven_trigger_r=1.0)

    @patch("core.execution.run_scalper.sync_and_manage_open_trades")
    @patch("core.execution.run_scalper.SessionLocal")
    @patch.object(sys, "argv", ["run_scalper", "--sync-trades", "--dry-run"])
    def test_dry_run_sync_command_does_not_manage_trades(
        self, mock_session_local, mock_sync
    ):
        main()

        mock_sync.assert_not_called()
        mock_session_local.return_value.close.assert_called_once()

    @patch("core.execution.run_scalper.scan_symbol_for_scalp")
    @patch("core.execution.run_scalper.mt5_client")
    def test_run_scalp_cycle_passes_strategy_parameter(
        self, _mock_mt5_client, mock_scan
    ):
        mock_scan.return_value = None
        run_scalp_cycle(db=None, symbols=["EURUSD.m"], ltf="M5", strategy="unicorn", dry_run=True)
        mock_scan.assert_called_once_with(None, "EURUSD.m", ltf="M5", strategy="unicorn")

    def test_scan_symbol_for_scalp_rejects_unknown_strategy(self):
        from core.execution.run_scalper import scan_symbol_for_scalp
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_inst = MagicMock()
        mock_inst.digits = 5
        mock_inst.pip_size = 0.00001
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_inst

        with self.assertRaisesRegex(ValueError, "Unknown strategy"):
            scan_symbol_for_scalp(mock_db, "EURUSD.m", ltf="M5", strategy="invalid_strategy")



if __name__ == "__main__":
    unittest.main()
