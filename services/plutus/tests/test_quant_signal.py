import sys
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from quant_signal import quant_signal


def summary(return_5d=2, return_20d=6, volatility=2, volume=1.3):
    return {
        "symbol": "TEST",
        "market_available": True,
        "quality_reasons": [],
        "observations": {
            "return_1d_pct": 0.2,
            "return_5d_pct": return_5d,
            "return_20d_pct": return_20d,
            "return_60d_pct": 8,
            "volatility_20d_pct": volatility,
            "volume_ratio_20d": volume,
            "distance_from_20d_high_pct": -2,
            "distance_from_20d_low_pct": 10,
        },
    }


class QuantSignalTests(unittest.TestCase):
    def test_classifies_supportive_market(self):
        result = quant_signal(summary())
        self.assertEqual(result["status"], "ANALYZED")
        self.assertEqual(result["trend"], "bullish")
        self.assertEqual(result["momentum"], "moderate")
        self.assertEqual(result["volatility"], "normal")
        self.assertEqual(result["volume_confirmation"], "supportive")

    def test_classifies_bearish_extreme_market(self):
        result = quant_signal(summary(-12, -25, 8, 3))
        self.assertEqual(result["trend"], "bearish")
        self.assertEqual(result["momentum"], "strong")
        self.assertEqual(result["volatility"], "extreme")
        self.assertEqual(result["volume_confirmation"], "strong")
        self.assertIn("extreme_volatility", result["risk_flags"])

    def test_evidence_is_exact_non_null_input_subset(self):
        source = summary(volume=None)
        result = quant_signal(source)
        self.assertNotIn("volume_ratio_20d", result["evidence"])
        self.assertEqual(result["volume_confirmation"], "unavailable")
        self.assertIn("volume_unavailable", result["risk_flags"])

    def test_unavailable_market_abstains(self):
        source = {
            "symbol": "ATTO",
            "market_available": False,
            "quality_reasons": ["insufficient_history"],
            "observations": None,
        }
        self.assertEqual(
            quant_signal(source),
            {
                "symbol": "ATTO",
                "status": "ABSTAIN",
                "reason": "MARKET_DATA_UNAVAILABLE",
                "quality_reasons": ["insufficient_history"],
            },
        )

    def test_frozen_deterministic_contract(self):
        freeze = json.loads((ROOT / "evaluation/quant_signal_freeze.json").read_text())
        for relative_path, expected in freeze["sha256"].items():
            actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative_path)


if __name__ == "__main__":
    unittest.main()
