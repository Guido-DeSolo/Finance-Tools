# Frozen analyst benchmark v1

This directory freezes the analyst-readiness test. Candidate models must be tested
without changing `corpus.json`, `rubric.json`, the analyst prompt/schema, or the
validators. A new benchmark version is required for any such change.

The five summaries test news use, rejected market data, conflicting evidence,
positive momentum, and suspicious/limited market data. Each symbol is scored out
of six: evidence fidelity (2), missing-data handling (1), unsupported-claim
avoidance (2), and stance/action coherence (1). Readiness requires at least 26/30
and zero critical contradictions. Latency is recorded but never scored.

Run a candidate without database access or insertion:

```bash
PYTHONPATH=/tmp/broker-deps python3 evaluation/benchmark.py \
  --candidate qwen3:14b --model analyst:latest
```

The JSON output is an audit artifact for manual scoring against `rubric.json`.
