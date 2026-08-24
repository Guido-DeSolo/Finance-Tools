import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

from evidence_summary import reduce_packet


def packet():
    return {
        "symbol": "PFE",
        "watchlist": {
            "insider_score": 30,
            "unique_buyers_30d": 3,
            "ceo_buy_30d": True,
            "cfo_buy_30d": False,
            "cluster_buy_30d": True,
            "buy_value_30d": 2_960_110,
        },
        "news": [
            {"headline": "First", "summary": "One"},
            {"headline": "Second", "summary": ""},
        ],
        "market": {
            "quality_pass": True,
            "reasons": [],
            "stats": {
                "return_1d": 0.01,
                "return_5d": 0.01234,
                "return_20d": 0.048,
                "return_60d": 0.1,
                "last_volume_vs_median": 1.1,
            },
        },
    }


class EvidenceReducerTests(unittest.TestCase):
    def test_reduces_and_converts_returns_to_percent(self):
        summary = reduce_packet(packet())
        self.assertEqual(summary["insider"]["signal_strength"], "high")
        self.assertEqual(summary["news"]["count"], 2)
        self.assertEqual([item["id"] for item in summary["news"]["items"]], [0, 1])
        self.assertEqual(summary["market"]["return_5d_pct"], 1.23)
        self.assertEqual(summary["market"]["return_20d_pct"], 4.8)
        self.assertEqual(summary["market"]["volume_signal"], "normal")

    def test_rejected_market_has_no_statistics(self):
        source = packet()
        source["market"] = {
            "quality_pass": False,
            "reasons": ["extreme_adjacent_jump"],
            "stats": None,
        }
        summary = reduce_packet(source)
        self.assertFalse(summary["market"]["available"])
        self.assertIsNone(summary["market"]["return_20d_pct"])
        self.assertEqual(summary["market"]["volume_signal"], "unavailable")
        self.assertEqual(summary["quality"], ["extreme_adjacent_jump"])

    def test_flags_flat_returns_and_missing_volume(self):
        source = packet()
        source["market"]["stats"].update(
            return_1d=0, return_5d=0, return_20d=0, return_60d=0,
            last_volume_vs_median=None,
        )
        quality = reduce_packet(source)["quality"]
        self.assertIn("all_available_market_returns_are_zero", quality)
        self.assertIn("market_volume_ratio_unavailable", quality)


if __name__ == "__main__":
    unittest.main()
