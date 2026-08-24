#!/usr/bin/env python3
"""Run the frozen five-symbol analyst benchmark without database access."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "data"))

import analyst
from settings import load_settings


CORPUS_PATH = Path(__file__).with_name("corpus.json")


def main():
    parser = argparse.ArgumentParser(description="Run frozen analyst benchmark v1.")
    parser.add_argument("--candidate", required=True, help="Human-readable base-model label.")
    parser.add_argument("--model", help="Ollama model tag; defaults to ANALYST_MODEL.")
    parser.add_argument("--base-url", help="Defaults to OLLAMA_BASE_URL.")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    settings = load_settings()
    model = args.model or settings.get("ANALYST_MODEL", analyst.DEFAULT_MODEL)
    base_url = args.base_url or settings.get("OLLAMA_BASE_URL", analyst.DEFAULT_OLLAMA_URL)
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    result = {
        "benchmark_version": corpus["version"],
        "candidate": args.candidate,
        "model": model,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "latency_is_scored": False,
        "results": {},
    }

    for symbol in corpus["symbols"]:
        print(f"EVALUATING {symbol}", file=sys.stderr, flush=True)
        started = time.monotonic()
        try:
            analysis, raw_response = analyst.request_analysis(
                corpus["summaries"][symbol], base_url, model, args.timeout
            )
            entry = {
                "status": "accepted",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "analysis": analysis,
                "raw_response": raw_response,
            }
        except Exception as exc:
            entry = {
                "status": "rejected",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "error": str(exc),
            }
        result["results"][symbol] = entry
        print(f"{entry['status'].upper()} {symbol}", file=sys.stderr, flush=True)

    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
