import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agents"), str(ROOT / "data")]
import news


def summary():
    return {"symbol": "POS", "articles": [{"id": 0, "headline": "x"}]}


def result():
    return {
        "symbol": "POS", "status": "ANALYZED", "overall_sentiment": "positive",
        "confidence": 0.8, "materiality": "high", "catalyst_type": "guidance",
        "catalyst_direction": "positive",
        "article_assessments": [{"article_id": 0, "sentiment": "positive", "materiality": "high"}],
        "risk_flags": [],
    }


class NewsValidationTests(unittest.TestCase):
    def test_accepts_consistent_result(self):
        news.validate_news(result(), summary())

    def test_rejects_invalid_article_reference(self):
        value = result()
        value["article_assessments"][0]["article_id"] = 9
        with self.assertRaisesRegex(ValueError, "every supplied"):
            news.validate_news(value, summary())

    def test_rejects_overall_sentiment_contradiction(self):
        value = result()
        value["overall_sentiment"] = "negative"
        with self.assertRaisesRegex(ValueError, "contradicts"):
            news.validate_news(value, summary())

    @patch("news.request_news", side_effect=AssertionError("model must not be called"))
    def test_no_news_abstains_without_model(self, request):
        value, raw, invoked = news.analyze_news(
            {"symbol": "NONE", "articles": []}, "http://unused"
        )
        self.assertEqual(value["status"], "ABSTAIN")
        self.assertFalse(invoked)
        self.assertIsNone(raw)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
