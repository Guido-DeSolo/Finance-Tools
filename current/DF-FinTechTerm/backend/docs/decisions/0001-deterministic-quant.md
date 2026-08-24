# ADR 0001: Deterministic QUANT interpretation

## Status

Accepted.

## Decision

Remove `qwen2-math:7b` from the DF-FinTechTerm architecture. QUANT interpretation is a
deterministic normalization implemented by `data/quant_signal.py`.

## Evidence

`qwen2-math:7b` was evaluated as a narrow QUANT specialist against the frozen
five-case corpus. Four of four model-invoked cases referenced observation fields
that were not supplied, including after a correction retry. Only ATTO passed
because Python generated its abstention without invoking the model.

## Consequences

QUANT adds no stochastic inference, model load, invented values, or evidence-key
drift. Thresholds are provisional normalization rules and may later be replaced by
empirically calibrated deterministic thresholds. The failed model benchmark and
artifacts remain preserved as project history.
