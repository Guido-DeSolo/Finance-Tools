import copy
import math
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

import candidate_packet


def valid_document():
    return {
        "generated_at": "2026-08-16T00:00:00+00:00",
        "candidate_count": 1,
        "score_selection": "latest row per symbol",
        "packets": [
            {
                "rank": 1,
                "symbol": "TEST",
                "watchlist": {
                    "symbol": "TEST",
                    "scored_at": "2026-08-16T00:00:00+00:00",
                    "total_score": 10.0,
                    "insider_score": 8.0,
                    "news_score": 2.0,
                    "market_score": 0.0,
                },
                "insider_events": [],
                "news": [],
                "market": {
                    "source": "alpaca_iex_adjusted_all",
                    "quality_pass": True,
                    "reasons": [],
                    "bar_count": 21,
                    "first_date": "2026-07-17",
                    "last_date": "2026-08-15",
                    "stats": {
                        "last_close": 12.0,
                        "median_volume": 1000,
                        "last_volume": 1200,
                        "last_volume_vs_median": 1.2,
                        "return_1d": 0.01,
                        "return_5d": 0.03,
                        "return_20d": 0.1,
                        "return_60d": None,
                    },
                },
            }
        ],
    }


class DocumentValidationTests(unittest.TestCase):
    def test_accepts_valid_document(self):
        candidate_packet.validate_document(valid_document())

    def test_rejects_duplicate_symbols(self):
        document = valid_document()
        document["packets"].append(copy.deepcopy(document["packets"][0]))
        document["packets"][1]["rank"] = 2
        document["candidate_count"] = 2
        with self.assertRaisesRegex(ValueError, "duplicated"):
            candidate_packet.validate_document(document)

    def test_rejects_non_finite_number(self):
        document = valid_document()
        document["packets"][0]["watchlist"]["total_score"] = math.inf
        with self.assertRaisesRegex(ValueError, "non-finite"):
            candidate_packet.validate_document(document)

    def test_rejects_failed_market_with_stats(self):
        document = valid_document()
        market = document["packets"][0]["market"]
        market["quality_pass"] = False
        market["reasons"] = ["insufficient_history"]
        with self.assertRaisesRegex(ValueError, "failed quality"):
            candidate_packet.validate_document(document)


class PriceSummaryTests(unittest.TestCase):
    def test_rejects_short_history(self):
        bars = [
            {
                "date": "2026-08-15",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 100,
            }
        ]
        result = candidate_packet.price_summary(bars)
        self.assertFalse(result["quality_pass"])
        self.assertIn("insufficient_history", result["reasons"])
        self.assertIsNone(result["stats"])


if __name__ == "__main__":
    unittest.main()
