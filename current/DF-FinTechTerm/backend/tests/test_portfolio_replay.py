import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))

import portfolio_replay


class ReplayTests(unittest.TestCase):
    def test_costs_and_adverse_slippage_reduce_long_return(self):
        fill = portfolio_replay.replay_trade(
            {"symbol": "AAPL", "side": "long", "quantity": 10},
            ("2026-01-01", 100), ("2026-01-02", 110), 10, 1,
        )
        self.assertAlmostEqual(fill.entry_fill_price, 100.1)
        self.assertAlmostEqual(fill.exit_fill_price, 109.89)
        self.assertAlmostEqual(fill.net_pnl, 95.9)

    def test_replay_uses_one_requested_timeframe_and_reports_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.sqlite3"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE bars(symbol TEXT,timeframe TEXT,timestamp TEXT,open REAL,asset_class TEXT,feed TEXT,adjustment TEXT)")
            db.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?)", [
                ("AAPL", "1Day", "2026-01-02", 100, "stock", "iex", "all"),
                ("AAPL", "1Day", "2026-01-03", 105, "stock", "iex", "all"),
                ("AAPL", "1Min", "2026-01-02", 999, "stock", "iex", "all"),
            ])
            db.commit(); db.close()
            result = portfolio_replay.run_replay(path, [
                {"symbol": "AAPL", "quantity": 2, "entry_time": "2026-01-01",
                 "exit_time": "2026-01-03", "timeframe": "1Day"},
                {"symbol": "NONE", "quantity": 1, "entry_time": "2026-01-01",
                 "exit_time": "2026-01-03"},
            ], 0, 0)
        self.assertEqual(result["summary"]["trades"], 1)
        self.assertEqual(result["trades"][0]["entry_market_price"], 100)
        self.assertEqual(result["trades"][0]["series"]["feed"], "iex")
        self.assertEqual(len(result["skipped"]), 1)


if __name__ == "__main__":
    unittest.main()
