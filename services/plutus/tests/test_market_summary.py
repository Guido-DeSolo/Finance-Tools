import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))
from market_summary import abstain_result, reduce_market


def packet():
    return {
        "symbol": "PFE",
        "market": {
            "quality_pass": True,
            "reasons": [],
            "stats": {
                "return_1d": 0.004,
                "return_5d": 0.018,
                "return_20d": 0.046,
                "return_60d": 0.072,
                "volatility_20d": 0.021,
                "volume_ratio_20d": 1.354,
                "distance_from_20d_high": -0.032,
                "distance_from_20d_low": 0.089,
            },
        },
    }


class MarketSummaryTests(unittest.TestCase):
    def test_reduces_approved_market_statistics(self):
        summary = reduce_market(packet())
        self.assertTrue(summary["market_available"])
        self.assertEqual(summary["observations"]["return_20d_pct"], 4.6)
        self.assertEqual(summary["observations"]["volume_ratio_20d"], 1.35)

    def test_missing_optional_observation_remains_available_with_reason(self):
        source = packet()
        source["market"]["stats"]["volume_ratio_20d"] = None
        summary = reduce_market(source)
        self.assertTrue(summary["market_available"])
        self.assertIn(
            "missing_quant_observation:volume_ratio_20d", summary["quality_reasons"]
        )

    def test_missing_core_observation_is_unavailable(self):
        source = packet()
        source["market"]["stats"]["volatility_20d"] = None
        self.assertFalse(reduce_market(source)["market_available"])

    def test_rejected_market_abstains_without_model(self):
        source = packet()
        source["symbol"] = "ATTO"
        source["market"] = {
            "quality_pass": False,
            "reasons": ["extreme_adjacent_jump"],
            "stats": None,
        }
        result = abstain_result(reduce_market(source))
        self.assertEqual(result["status"], "ABSTAIN")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["evidence_refs"], [])


if __name__ == "__main__":
    unittest.main()
