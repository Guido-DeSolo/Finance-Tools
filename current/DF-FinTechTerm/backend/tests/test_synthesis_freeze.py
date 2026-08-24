import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrozenSynthesisTests(unittest.TestCase):
    def test_corpus_expected_cases(self):
        corpus = json.loads((ROOT / "evaluation/synthesis_corpus.json").read_text())
        self.assertEqual(corpus["symbols"], ["BULL", "BEAR", "CONFLICT", "SPARSE", "NEUTRAL"])
        self.assertEqual(corpus["expected_status"]["CONFLICT"], "REJECT_INCONSISTENT")
        self.assertEqual(corpus["expected_status"]["SPARSE"], "INSUFFICIENT_EVIDENCE")

    def test_frozen_files_match_manifest(self):
        freeze = json.loads((ROOT / "evaluation/synthesis_freeze.json").read_text())
        for relative_path, expected in freeze["sha256"].items():
            actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative_path)


if __name__ == "__main__":
    unittest.main()
