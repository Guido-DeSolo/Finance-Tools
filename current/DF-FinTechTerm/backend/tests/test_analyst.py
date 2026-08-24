import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
import analyst


def summary(news=True, market=True, insider=True):
    return {
        "symbol": "PFE",
        "insider": {"signal_strength": "high" if insider else "none"},
        "news": {"count": 2 if news else 0, "items": (
            [{"id": 0}, {"id": 1}] if news else []
        )},
        "market": {"available": market},
        "quality": [],
    }


def analysis():
    return {
        "symbol": "PFE",
        "stance": "bullish",
        "confidence": 0.67,
        "time_horizon": "20d",
        "insider_interpretation": "Supportive",
        "news_interpretation": "Moderately supportive",
        "market_interpretation": "Supportive",
        "thesis": "The available evidence is directionally supportive.",
        "bear_case": ["Support could weaken."],
        "catalysts": ["Supportive developments may reinforce the signal."],
        "invalidation_conditions": ["The evidence mix turns negative."],
        "evidence_refs": {"insider": True, "news": [0, 1], "market": True},
        "action": "consider_long",
    }


class AnalysisValidationTests(unittest.TestCase):
    def test_accepts_valid_analysis(self):
        analyst.validate_analysis(analysis(), summary())

    def test_rejects_extra_fields(self):
        value = analysis()
        value["purchase_value"] = 100
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            analyst.validate_analysis(value, summary())

    def test_rejects_confidence_out_of_range(self):
        value = analysis()
        value["confidence"] = 67
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            analyst.validate_analysis(value, summary())

    def test_requires_every_news_reference_once(self):
        value = analysis()
        value["evidence_refs"]["news"] = [0]
        with self.assertRaisesRegex(ValueError, "every supplied news ID"):
            analyst.validate_analysis(value, summary())

    def test_references_follow_availability(self):
        value = analysis()
        value["evidence_refs"] = {"insider": False, "news": [], "market": False}
        analyst.validate_analysis(value, summary(news=False, market=False, insider=False))

    def test_rejects_market_reference_when_unavailable(self):
        with self.assertRaisesRegex(ValueError, "market evidence reference"):
            analyst.validate_analysis(analysis(), summary(market=False))


class RequestTests(unittest.TestCase):
    def test_request_is_non_streaming_and_schema_constrained(self):
        request = analyst.build_request(summary(), "analyst:latest")
        self.assertFalse(request["stream"])
        self.assertEqual(request["format"], analyst.ANALYSIS_SCHEMA)
        self.assertEqual(request["options"], {"temperature": 0, "num_predict": 800})


if __name__ == "__main__":
    unittest.main()
