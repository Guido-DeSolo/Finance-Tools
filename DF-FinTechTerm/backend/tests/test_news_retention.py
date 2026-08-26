from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))

from news_retention import cutoff, prune_sqlite


class NewsRetentionTests(unittest.TestCase):
    def test_default_cutoff_is_seven_days(self):
        current = datetime(2026, 8, 24, 12, tzinfo=UTC)
        self.assertEqual(cutoff(7, current_time=current), current - timedelta(days=7))

    def test_invalid_retention_is_rejected(self):
        with self.assertRaises(ValueError):
            cutoff(0)

    def test_sqlite_prunes_old_articles_and_cascades_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news.sqlite3"
            db = sqlite3.connect(path)
            db.execute("PRAGMA foreign_keys = ON")
            db.executescript("""
                CREATE TABLE news_articles (
                    article_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE news_article_symbols (
                    article_id TEXT NOT NULL REFERENCES news_articles(article_id)
                        ON DELETE CASCADE,
                    symbol TEXT NOT NULL
                );
            """)
            db.executemany(
                "INSERT INTO news_articles VALUES (?, ?)",
                (("old", "2026-08-16T11:59:59Z"),
                 ("boundary", "2026-08-17T12:00:00Z"),
                 ("new", "2026-08-24T11:00:00Z")),
            )
            db.executemany(
                "INSERT INTO news_article_symbols VALUES (?, ?)",
                (("old", "OLD"), ("new", "NEW")),
            )
            db.commit()
            db.close()

            removed = prune_sqlite(path, datetime(2026, 8, 17, 12, tzinfo=UTC))

            db = sqlite3.connect(path)
            self.assertEqual(removed, 1)
            self.assertEqual(
                db.execute("SELECT article_id FROM news_articles ORDER BY article_id").fetchall(),
                [("boundary",), ("new",)],
            )
            self.assertEqual(
                db.execute("SELECT article_id FROM news_article_symbols").fetchall(),
                [("new",)],
            )
            db.close()

    def test_missing_sqlite_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite3"
            self.assertEqual(prune_sqlite(path, datetime.now(UTC)), 0)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
