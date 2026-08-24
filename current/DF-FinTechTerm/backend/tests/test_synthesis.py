import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agents"), str(ROOT / "data")]
import synthesis
from synthesis_input import build_synthesis_input


def aligned_input():
    return build_synthesis_input(
        "BULL",
        {"status": "ANALYZED", "strength": "strong", "cluster": True, "senior_management": True, "risk_flags": []},
        {"status": "ANALYZED", "trend": "bullish", "momentum": "moderate", "volatility": "normal", "volume_confirmation": "supportive", "preferred_horizon": "20d", "signal_strength": 0.6, "risk_flags": []},
        {"status": "ANALYZED", "overall_sentiment": "positive", "confidence": 1.0, "conflicting_articles": False, "high_materiality_count": 1, "sentiment_balance": 1},
    )


def bullish_result():
    return {
        "symbol": "BULL", "status": "ANALYZED", "stance": "bullish",
        "confidence": 0.8, "time_horizon": "20d",
        "thesis": "The normalized evidence is directionally aligned.",
        "supporting_signals": ["insider", "quant", "news"],
        "contradicting_signals": [], "risk_flags": [], "action": "consider_long",
    }


class SynthesisTests(unittest.TestCase):
    def test_accepts_aligned_bullish_result(self):
        synthesis.validate_synthesis(bullish_result(), aligned_input())

    def test_rejects_unknown_or_abstaining_reference(self):
        source = aligned_input()
        source["news"] = {"status": "ABSTAIN", "reason": "NO_RECENT_NEWS"}
        with self.assertRaisesRegex(ValueError, "abstaining"):
            synthesis.validate_synthesis(bullish_result(), source)

    def test_rejects_stance_action_mismatch(self):
        value = bullish_result()
        value["action"] = "consider_short"
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            synthesis.validate_synthesis(value, aligned_input())

    def test_sparse_input_requires_insufficient_evidence(self):
        source = aligned_input()
        source["quant"] = {"status": "ABSTAIN", "reason": "MARKET_DATA_UNAVAILABLE"}
        source["news"] = {"status": "ABSTAIN", "reason": "NO_RECENT_NEWS"}
        value = {
            "symbol": "BULL", "status": "INSUFFICIENT_EVIDENCE", "stance": "neutral",
            "confidence": 0.0, "time_horizon": "20d", "thesis": "Only one branch is available.",
            "supporting_signals": ["insider"], "contradicting_signals": [],
            "risk_flags": ["sparse_evidence", "abstaining_quant", "abstaining_news"],
            "action": "watch",
        }
        synthesis.validate_synthesis(value, source)


if __name__ == "__main__":
    unittest.main()
