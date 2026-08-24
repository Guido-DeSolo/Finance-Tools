import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agents"), str(ROOT / "data")]
import quant


def summary(available=True):
    return {
        "symbol": "PFE",
        "market_available": available,
        "quality_reasons": [] if available else ["extreme_adjacent_jump"],
        "observations": ({
            "return_1d_pct": 0.2, "return_5d_pct": 1.8,
            "return_20d_pct": 4.6, "return_60d_pct": 7.2,
            "volatility_20d_pct": 2.1, "volume_ratio_20d": 1.35,
            "distance_from_20d_high_pct": -3.2,
            "distance_from_20d_low_pct": 8.9,
        } if available else None),
    }


def result():
    return {
        "symbol": "PFE", "status": "ANALYZED", "trend": "bullish",
        "momentum": "moderate", "volatility": "normal",
        "volume_confirmation": "supportive", "time_horizon": "20d",
        "confidence": 0.72,
        "interpretation": "Market behavior is moderately supportive.",
        "risk_flags": [],
        "evidence_refs": ["return_20d_pct", "volatility_20d_pct", "volume_ratio_20d"],
    }


class QuantValidationTests(unittest.TestCase):
    def test_accepts_grounded_result(self):
        quant.validate_quant(result(), summary())

    def test_rejects_unknown_reference(self):
        value = result()
        value["evidence_refs"].append("earnings_growth")
        with self.assertRaisesRegex(ValueError, "absent"):
            quant.validate_quant(value, summary())

    def test_requires_category_supporting_references(self):
        value = result()
        value["evidence_refs"].remove("volatility_20d_pct")
        with self.assertRaisesRegex(ValueError, "volatility"):
            quant.validate_quant(value, summary())

    def test_missing_volume_requires_unavailable_interpretation(self):
        source = summary()
        source["observations"]["volume_ratio_20d"] = None
        value = result()
        value["volume_confirmation"] = "unavailable"
        value["evidence_refs"].remove("volume_ratio_20d")
        quant.validate_quant(value, source)

    @patch("quant.request_quant", side_effect=AssertionError("model must not be called"))
    def test_unavailable_market_abstains_without_model(self, request):
        value, raw, invoked = quant.analyze_market(
            summary(False), "http://unused", timeout=1
        )
        self.assertEqual(value["status"], "ABSTAIN")
        self.assertFalse(invoked)
        self.assertIsNone(raw)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
