import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "research"), str(ROOT / "data"), str(ROOT.parent)]

import daily_research
from test_candidate_packet import valid_document


class DailyResearchTests(unittest.TestCase):
    def test_prompt_marks_evidence_untrusted_and_bounds_news(self):
        document = valid_document()
        document["packets"][0]["news"] = [
            {"created_at": "2026-08-16", "headline": f"Story {index}",
             "summary": "Summary", "source": "Wire", "url": "url", "id": str(index)}
            for index in range(8)
        ]
        evidence = daily_research.distill_evidence(document)
        self.assertEqual(len(evidence["candidates"][0]["news"]), 5)
        prompt = daily_research.research_prompt(evidence)
        self.assertIn("untrusted evidence", prompt)
        self.assertIn("Do not recommend or execute trades", prompt)

    def test_notebook_embeds_authoritative_evidence(self):
        document = valid_document()
        document["packets"][0]["news"] = [{
            "headline": "Company's update ''' cannot escape", "created_at": "2026-08-16",
            "summary": "text", "source": "Wire", "url": "url", "id": "1",
        }]
        notebook = daily_research.build_notebook(document, "## Summary", "model")
        self.assertEqual(notebook["nbformat"], 4)
        source = "".join(notebook["cells"][2]["source"])
        compile(source, "notebook-cell", "exec")
        self.assertIn("## Summary", notebook["cells"][1]["source"])

    def test_publish_writes_versioned_artifacts_and_latest_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = daily_research.publish(
                valid_document(), "# Daily summary", root,
                datetime.fromisoformat("2026-08-24T12:34:56+00:00"),
            )
            latest = json.loads((root / "latest.json").read_text())
            notebook = json.loads(Path(manifest["notebook_path"]).read_text())
        self.assertEqual(latest["symbols"], ["TEST"])
        self.assertEqual(notebook["metadata"]["df_fintechterm"]["model"],
                         daily_research.LOCAL_LLM_MODEL)


if __name__ == "__main__":
    unittest.main()
