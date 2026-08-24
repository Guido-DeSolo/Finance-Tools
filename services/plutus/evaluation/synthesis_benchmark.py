#!/usr/bin/env python3
"""Run the frozen normalized-signal synthesis benchmark without persistence."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "data"))
import synthesis
from settings import load_settings


CORPUS_PATH = Path(__file__).with_name("synthesis_corpus.json")


def main():
    parser = argparse.ArgumentParser(description="Run frozen synthesis benchmark v1.")
    parser.add_argument("--model", default=synthesis.DEFAULT_MODEL)
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    settings = load_settings()
    base_url = args.base_url or settings.get("OLLAMA_BASE_URL", synthesis.DEFAULT_OLLAMA_URL)
    corpus = json.loads(CORPUS_PATH.read_text())
    artifact = {
        "benchmark_version": corpus["version"], "model": args.model,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "latency_is_scored": False, "results": {},
    }
    for symbol in corpus["symbols"]:
        print(f"EVALUATING {symbol}", file=sys.stderr, flush=True)
        started = time.monotonic()
        try:
            result, raw = synthesis.request_synthesis(
                corpus["inputs"][symbol], base_url, args.model, args.timeout
            )
            entry = {
                "status": "accepted", "elapsed_seconds": round(time.monotonic() - started, 3),
                "result": result, "raw_response": raw,
            }
        except Exception as exc:
            entry = {
                "status": "rejected", "elapsed_seconds": round(time.monotonic() - started, 3),
                "error": str(exc),
            }
        artifact["results"][symbol] = entry
        print(f"{entry['status'].upper()} {symbol}", file=sys.stderr, flush=True)
    artifact["finished_at"] = datetime.now(timezone.utc).isoformat()
    output = json.dumps(artifact, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
