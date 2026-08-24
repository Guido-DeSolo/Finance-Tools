import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrozenNewsEvaluationTests(unittest.TestCase):
    def test_corpus_cases(self):
        corpus = json.loads((ROOT / "evaluation/news_corpus.json").read_text())
        self.assertEqual(corpus["symbols"], ["POS", "NEG", "MIX", "NOISE", "NONE"])
        self.assertEqual(corpus["summaries"]["NONE"]["articles"], [])
        for symbol in ("POS", "NEG", "MIX", "NOISE"):
            self.assertTrue(corpus["summaries"][symbol]["articles"])

    def test_frozen_files_match_manifest(self):
        freeze = json.loads((ROOT / "evaluation/news_freeze.json").read_text())
        for relative_path, expected in freeze["sha256"].items():
            actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative_path)


if __name__ == "__main__":
    unittest.main()
