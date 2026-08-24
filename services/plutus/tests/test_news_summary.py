import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from news_summary import abstain_result, reduce_news


class NewsSummaryTests(unittest.TestCase):
    def test_sorts_filters_and_assigns_stable_ids(self):
        rows = [
            {"created_at": "2026-08-10T00:00:00Z", "headline": "Older", "summary": "", "source": "A"},
            {"created_at": "2026-08-14T00:00:00Z", "headline": "Newer", "summary": "S", "source": "B"},
            {"created_at": "2026-01-01T00:00:00Z", "headline": "Expired", "source": "C"},
        ]
        result = reduce_news("TEST", rows, "2026-08-15T00:00:00Z")
        self.assertEqual([item["headline"] for item in result["articles"]], ["Newer", "Older"])
        self.assertEqual([item["id"] for item in result["articles"]], [0, 1])

    def test_suppresses_near_duplicate_headlines(self):
        rows = [
            {"created_at": "2026-08-14T01:00:00Z", "headline": "Company raises full-year guidance", "source": "A"},
            {"created_at": "2026-08-14T00:00:00Z", "headline": "Company raises full year guidance", "source": "B"},
        ]
        self.assertEqual(len(reduce_news("TEST", rows, "2026-08-15T00:00:00Z")["articles"]), 1)

    def test_empty_summary_abstains(self):
        self.assertEqual(
            abstain_result({"symbol": "NONE", "articles": []}),
            {"symbol": "NONE", "status": "ABSTAIN", "reason": "NO_RECENT_NEWS"},
        )


if __name__ == "__main__":
    unittest.main()
