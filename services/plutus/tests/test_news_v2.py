import sys
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agents"), str(ROOT / "data")]
import news_v2
from news_signal import aggregate_news


class NewsV2Tests(unittest.TestCase):
    def test_validates_exact_article_ids(self):
        summary = {"symbol": "MIX", "articles": [{"id": 0}, {"id": 1}]}
        result = {
            "symbol": "MIX", "status": "ANALYZED",
            "article_assessments": [
                {"article_id": 0, "sentiment": "positive", "materiality": "high"},
                {"article_id": 1, "sentiment": "negative", "materiality": "high"},
            ],
        }
        news_v2.validate_assessments(result, summary)
        signal = aggregate_news(summary, result)
        self.assertEqual(signal["overall_sentiment"], "mixed")
        self.assertTrue(signal["conflicting_articles"])
        self.assertEqual(signal["sentiment_balance"], 0)

    def test_deterministic_aggregation_counts(self):
        summary = {"symbol": "POS", "articles": [{"id": 0}, {"id": 1}]}
        result = {
            "symbol": "POS", "status": "ANALYZED",
            "article_assessments": [
                {"article_id": 1, "sentiment": "neutral", "materiality": "low"},
                {"article_id": 0, "sentiment": "positive", "materiality": "high"},
            ],
        }
        signal = aggregate_news(summary, result)
        self.assertEqual(signal["overall_sentiment"], "positive")
        self.assertEqual(signal["confidence"], 0.5)
        self.assertEqual(signal["high_materiality_count"], 1)
        self.assertEqual([item["article_id"] for item in signal["article_assessments"]], [0, 1])

    def test_empty_news_abstains_deterministically(self):
        self.assertEqual(
            aggregate_news({"symbol": "NONE", "articles": []}, None),
            {"symbol": "NONE", "status": "ABSTAIN", "reason": "NO_RECENT_NEWS"},
        )

    def test_frozen_v2_contract(self):
        freeze = json.loads((ROOT / "evaluation/news_v2_freeze.json").read_text())
        for relative_path, expected in freeze["sha256"].items():
            actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative_path)


if __name__ == "__main__":
    unittest.main()
