import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "research"), str(ROOT.parent)]

import watchlist_fundamental as subject


SCHEMA = """
CREATE TABLE stream_watchlist (asset_class TEXT, symbol TEXT, feed TEXT, location TEXT, added_at TEXT);
CREATE TABLE live_trades (asset_class TEXT, symbol TEXT, trade_id TEXT, timestamp TEXT, price REAL,
 size REAL, exchange TEXT, tape TEXT, taker_side TEXT, feed TEXT, location TEXT);
CREATE TABLE technical_analysis_snapshots (asset_class TEXT, symbol TEXT, feed TEXT, location TEXT,
 source_trade_id TEXT, trade_timestamp TEXT, bar_timestamp TEXT, bars_buffered INTEGER,
 indicators_json TEXT, updated_at TEXT);
CREATE TABLE news_articles (article_id TEXT, headline TEXT, summary TEXT, created_at TEXT,
 updated_at TEXT, source TEXT, url TEXT, raw_json TEXT);
CREATE TABLE news_article_symbols (article_id TEXT, symbol TEXT);
"""


class WatchlistFundamentalTests(unittest.TestCase):
    def make_database(self, path: Path) -> None:
        with sqlite3.connect(path) as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO stream_watchlist VALUES (?,?,?,?,?)",
                       ("stock", "AAPL", "iex", "us", "2026-08-01T00:00:00Z"))
            db.executemany("INSERT INTO live_trades VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
                ("stock", "AAPL", "1", "2026-08-25T12:00:01Z", 100, 2, "V", "A", None, "iex", "us"),
                ("stock", "AAPL", "2", "2026-08-25T12:00:59Z", 101, 3, "V", "A", None, "iex", "us"),
                ("stock", "AAPL", "old", "2026-08-24T11:00:00Z", 90, 1, "V", "A", None, "iex", "us"),
            ])
            db.execute("INSERT INTO technical_analysis_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                       ("stock", "AAPL", "iex", "us", "2", "2026-08-25T12:00:59Z",
                        "2026-08-25T12:00:00Z", 50, '{"rsi":55}', "2026-08-25T12:01:00Z"))
            db.execute("INSERT INTO news_articles VALUES (?,?,?,?,?,?,?,?)",
                       ("newsdata:1", "Headline", "Summary", "2026-08-25T15:00:00Z",
                        "2026-08-25T15:00:00Z", "Wire", "https://example.test", '{"provider":"newsdata"}'))
            db.execute("INSERT INTO news_article_symbols VALUES (?,?)", ("newsdata:1", "AAPL"))

    def test_collects_every_in_window_movement_ta_and_news(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "market.sqlite3"
            self.make_database(database)
            document = subject.collect_evidence(database, datetime(2026, 8, 25, tzinfo=UTC),
                                                datetime(2026, 8, 26, tzinfo=UTC))
        packet = document["symbols"][0]
        self.assertEqual([row["trade_id"] for row in packet["movements"]], ["1", "2"])
        self.assertEqual(packet["market_summary"]["trade_count"], 2)
        self.assertEqual(packet["minute_bars"][0]["close"], 101)
        self.assertEqual(packet["latest_live_orderbook_ta"]["indicators"]["rsi"], 55)
        self.assertEqual(packet["news"][0]["provider"], "newsdata")

    def test_one_call_and_one_notebook_with_symbol_header(self):
        prompts = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "market.sqlite3"
            self.make_database(database)
            manifest = subject.run(database, root / "output",
                datetime(2026, 8, 26, tzinfo=UTC),
                lambda messages: prompts.append(messages[0]["content"]) or "### Evidence observed\nFinding")
            notebook = json.loads(Path(manifest["notebook_path"]).read_text())
            evidence = json.loads(Path(manifest["evidence_path"]).read_text())
        self.assertEqual(len(prompts), 1)
        self.assertIn('"trade_count":2', prompts[0])
        self.assertIn('"minute_bars"', prompts[0])
        self.assertIn("NON-NEGOTIABLE RULES", prompts[0])
        self.assertIn("## AAPL", "".join(notebook["cells"][1]["source"]))
        self.assertEqual(len(evidence["symbols"][0]["movements"]), 2)


if __name__ == "__main__":
    unittest.main()
