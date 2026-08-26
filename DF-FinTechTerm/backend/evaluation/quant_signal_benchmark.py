#!/usr/bin/env python3
"""Regression benchmark for deterministic QUANT normalization."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from quant_signal import quant_signal


CORPUS = Path(__file__).with_name("quant_corpus.json")
OUTPUT = Path(__file__).parent / "results/quant_deterministic.json"


def validate_case(summary, result):
    if result["symbol"] != summary["symbol"]:
        raise ValueError("symbol mismatch")
    if not summary["market_available"]:
        if result["status"] != "ABSTAIN":
            raise ValueError("unavailable market did not abstain")
        if result["quality_reasons"] != summary["quality_reasons"]:
            raise ValueError("abstention quality reasons changed")
        return
    if result["status"] != "ANALYZED":
        raise ValueError("available market did not analyze")
    expected_evidence = {
        key: value
        for key, value in summary["observations"].items()
        if value is not None
    }
    if result["evidence"] != expected_evidence:
        raise ValueError("result evidence differs from supplied observations")
    output_unavailable = result["volume_confirmation"] == "unavailable"
    input_unavailable = summary["observations"]["volume_ratio_20d"] is None
    if output_unavailable != input_unavailable:
        raise ValueError("volume availability contradiction")


def main():
    corpus = json.loads(CORPUS.read_text())
    artifact = {"benchmark_version": 2, "engine": "deterministic", "results": {}}
    for symbol in corpus["symbols"]:
        summary = corpus["summaries"][symbol]
        result = quant_signal(summary)
        validate_case(summary, result)
        artifact["results"][symbol] = {"status": "accepted", "result": result}
    artifact["ready"] = len(artifact["results"]) == len(corpus["symbols"])
    output = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(output)
    print(output, end="")


if __name__ == "__main__":
    main()
