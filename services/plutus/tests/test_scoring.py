import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

import watchlist


class InsiderScoreTests(unittest.TestCase):
    def test_cluster_and_executive_buying_raise_score(self):
        baseline = watchlist.insider_score(1, 1, 20_000, 0, False, False)
        conviction = watchlist.insider_score(2, 2, 20_000, 0, True, True)
        self.assertGreater(conviction, baseline)

    def test_small_purchase_is_penalized(self):
        small = watchlist.insider_score(1, 1, 9_999, 0, False, False)
        meaningful = watchlist.insider_score(1, 1, 10_000, 0, False, False)
        self.assertGreater(meaningful, small)


class NewsScoreTests(unittest.TestCase):
    def test_news_score_is_capped(self):
        self.assertEqual(watchlist.news_score(10_000, 10_000, 10_000, 10_000), 20.0)

    def test_recent_news_has_more_weight(self):
        self.assertGreater(
            watchlist.news_score(1, 0, 0, 0),
            watchlist.news_score(0, 0, 0, 1),
        )


if __name__ == "__main__":
    unittest.main()
