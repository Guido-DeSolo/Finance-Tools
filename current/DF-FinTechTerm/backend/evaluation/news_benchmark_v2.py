#!/usr/bin/env python3
"""Run frozen NEWS v2 article-classification benchmark without persistence."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agents"), str(ROOT / "data")]
import news_v2
from news_signal import aggregate_news
from settings import load_settings


CORPUS_PATH = Path(__file__).with_name("news_corpus.json")


def main():
    parser = argparse.ArgumentParser(description="Run frozen NEWS benchmark v2.")
    parser.add_argument("--model", default=news_v2.DEFAULT_MODEL)
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    settings = load_settings()
    base_url = args.base_url or settings.get("OLLAMA_BASE_URL", news_v2.DEFAULT_OLLAMA_URL)
    corpus = json.loads(CORPUS_PATH.read_text())
    artifact = {
        "benchmark_version": 2, "model": args.model,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "latency_is_scored": False, "results": {},
    }
    for symbol in corpus["symbols"]:
        print(f"EVALUATING {symbol}", file=sys.stderr, flush=True)
        started = time.monotonic()
        summary = corpus["summaries"][symbol]
        try:
            if not summary["articles"]:
                signal = aggregate_news(summary, None)
                model_result = raw = None
                invoked = False
            else:
                model_result, raw = news_v2.request_assessments(
                    summary, base_url, args.model, args.timeout
                )
                signal = aggregate_news(summary, model_result)
                invoked = True
            entry = {
                "status": "accepted", "model_invoked": invoked,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "model_result": model_result, "news_signal": signal,
                "raw_response": raw,
            }
        except Exception as exc:
            entry = {
                "status": "rejected", "model_invoked": bool(summary["articles"]),
                "elapsed_seconds": round(time.monotonic() - started, 3),
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
