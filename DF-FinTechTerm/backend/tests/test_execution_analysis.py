import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "evaluation"), str(ROOT.parent)]

import execution_analysis


def database():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE live_trades(symbol TEXT,price REAL,timestamp TEXT,received_at TEXT)")
    execution_analysis.ensure_schema(db)
    return db


class ExecutionTests(unittest.TestCase):
    def test_import_is_idempotent_and_analysis_marks_unmatched(self):
        db = database()
        activities = [{"activity_type": "FILL", "id": "fill-1", "order_id": "order-1",
                       "symbol": "AAPL", "side": "buy", "qty": "2", "price": "101",
                       "transaction_time": "2026-01-01T10:00:05Z"},
                      {"activity_type": "FILL", "id": "fill-2", "order_id": "order-2",
                       "symbol": "NONE", "side": "sell", "qty": "1", "price": "5",
                       "transaction_time": "2026-01-01T10:00:05Z"}]
        self.assertEqual(execution_analysis.persist_fills(db, activities), 2)
        self.assertEqual(execution_analysis.persist_fills(db, activities), 0)
        db.execute("INSERT INTO live_trades VALUES (?,?,?,?)",
                   ("AAPL", 100, "2026-01-01T10:00:00Z", "2026-01-01T10:00:00Z"))
        report = execution_analysis.analyze(db, 10)
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["unmatched"], 1)
        self.assertAlmostEqual(report["executions"][0]["slippage_bps"], 100)
        self.assertEqual(report["total_slippage_cost"], 2)
        db.close()

    def test_fill_fetch_paginates_by_activity_id(self):
        client = MagicMock()
        first = [{"id": str(index)} for index in range(100)]
        client.account_activities.side_effect = [first, [{"id": "last"}]]
        result = execution_analysis.fetch_all_fills(client, "after", None)
        self.assertEqual(len(result), 101)
        self.assertEqual(client.account_activities.call_args_list[1].kwargs["page_token"], "99")


if __name__ == "__main__":
    unittest.main()
