import json
import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrozenEvaluationTests(unittest.TestCase):
    def test_frozen_corpus_shape(self):
        corpus = json.loads((ROOT / "evaluation/corpus.json").read_text())
        self.assertEqual(corpus["version"], 1)
        self.assertEqual(corpus["symbols"], ["PFE", "ATTO", "OTLK", "CAMP", "HEPA"])
        self.assertEqual(set(corpus["summaries"]), set(corpus["symbols"]))
        for symbol in corpus["symbols"]:
            self.assertEqual(corpus["summaries"][symbol]["symbol"], symbol)

    def test_rubric_totals_30_and_latency_is_excluded(self):
        rubric = json.loads((ROOT / "evaluation/rubric.json").read_text())
        per_symbol = sum(item["maximum"] for item in rubric["per_symbol"].values())
        self.assertEqual(per_symbol * 5, rubric["maximum_score"])
        self.assertEqual(rubric["readiness_threshold"], 26)
        self.assertTrue(rubric["require_zero_critical_contradictions"])
        self.assertFalse(rubric["latency_is_scored"])

    def test_frozen_files_match_manifest(self):
        freeze = json.loads((ROOT / "evaluation/freeze.json").read_text())
        for relative_path, expected in freeze["sha256"].items():
            actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative_path)


if __name__ == "__main__":
    unittest.main()
