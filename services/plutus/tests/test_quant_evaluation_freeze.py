import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrozenQuantEvaluationTests(unittest.TestCase):
    def test_corpus_cases_and_abstention_case(self):
        corpus = json.loads((ROOT / "evaluation/quant_corpus.json").read_text())
        self.assertEqual(corpus["symbols"], ["PFE", "OTLK", "CAMP", "HEPA", "ATTO"])
        self.assertFalse(corpus["summaries"]["ATTO"]["market_available"])
        self.assertIsNone(corpus["summaries"]["ATTO"]["observations"])
        for symbol in ("PFE", "OTLK", "CAMP", "HEPA"):
            self.assertTrue(corpus["summaries"][symbol]["market_available"])

    def test_frozen_files_match_manifest(self):
        freeze = json.loads((ROOT / "evaluation/quant_freeze.json").read_text())
        for relative_path, expected in freeze["sha256"].items():
            actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative_path)


if __name__ == "__main__":
    unittest.main()
