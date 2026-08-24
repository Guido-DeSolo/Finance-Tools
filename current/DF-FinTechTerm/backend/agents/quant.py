#!/usr/bin/env python3
"""Narrow market-evidence interpreter with deterministic abstention."""

import json
import math


DEFAULT_OLLAMA_URL = "http://192.168.0.2:11434"
DEFAULT_MODEL = "qwen2-math:7b"
STATUS_VALUES = ("ANALYZED", "ABSTAIN")
TREND_VALUES = ("bullish", "bearish", "neutral")
MOMENTUM_VALUES = ("strong", "moderate", "weak", "neutral")
VOLATILITY_VALUES = ("low", "normal", "high", "extreme")
VOLUME_VALUES = ("supportive", "contradictory", "neutral", "unavailable")
HORIZON_VALUES = ("1d", "5d", "20d", "60d")
REQUIRED_FIELDS = {
    "symbol", "status", "trend", "momentum", "volatility",
    "volume_confirmation", "time_horizon", "confidence", "interpretation",
    "risk_flags", "evidence_refs",
}

QUANT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(REQUIRED_FIELDS),
    "properties": {
        "symbol": {"type": "string", "minLength": 1},
        "status": {"type": "string", "enum": list(STATUS_VALUES)},
        "trend": {"type": "string", "enum": list(TREND_VALUES)},
        "momentum": {"type": "string", "enum": list(MOMENTUM_VALUES)},
        "volatility": {"type": "string", "enum": list(VOLATILITY_VALUES)},
        "volume_confirmation": {"type": "string", "enum": list(VOLUME_VALUES)},
        "time_horizon": {"type": "string", "enum": list(HORIZON_VALUES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "interpretation": {"type": "string", "minLength": 1},
        "risk_flags": {
            "type": "array", "items": {"type": "string", "minLength": 1}
        },
        "evidence_refs": {
            "type": "array", "items": {"type": "string", "minLength": 1}
        },
    },
}

SYSTEM_PROMPT = """You are the quantitative specialist.

You receive a compact set of already-computed market observations.

Do not calculate new statistics.
Do not infer company fundamentals.
Do not discuss news or insiders.
Do not invent catalysts.
Do not predict exact prices.
Interpret only the supplied numerical market evidence.

Every material claim must correspond to one or more evidence_refs. Reference only
exact keys from observations. Return status ANALYZED; unavailable inputs are handled
deterministically before you are called. Return only JSON matching the schema."""


def validate_quant(result, summary):
    if not isinstance(result, dict):
        raise ValueError("quant result must be an object")
    missing = REQUIRED_FIELDS - set(result)
    extra = set(result) - REQUIRED_FIELDS
    if missing:
        raise ValueError(f"quant result missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"quant result has unexpected fields: {', '.join(sorted(extra))}")
    if result["symbol"] != summary["symbol"]:
        raise ValueError("quant symbol does not match market summary")
    if result["status"] != "ANALYZED":
        raise ValueError("model result must be ANALYZED; Python owns abstention")
    for field, allowed in (
        ("trend", TREND_VALUES), ("momentum", MOMENTUM_VALUES),
        ("volatility", VOLATILITY_VALUES),
        ("volume_confirmation", VOLUME_VALUES), ("time_horizon", HORIZON_VALUES),
    ):
        if result[field] not in allowed:
            raise ValueError(f"invalid {field}: {result[field]!r}")
    confidence = result["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number")
    if not math.isfinite(confidence) or not 0 < confidence <= 1:
        raise ValueError("ANALYZED confidence must be finite and greater than 0 through 1")
    if not isinstance(result["interpretation"], str) or not result["interpretation"].strip():
        raise ValueError("interpretation must be a non-empty string")
    if not isinstance(result["risk_flags"], list) or not all(
        isinstance(value, str) and value.strip() for value in result["risk_flags"]
    ):
        raise ValueError("risk_flags must be an array of non-empty strings")
    refs = result["evidence_refs"]
    if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)):
        raise ValueError("evidence_refs must be a non-empty array of unique keys")
    available = {
        key for key, value in summary["observations"].items() if value is not None
    }
    if not all(isinstance(ref, str) and ref in available for ref in refs):
        raise ValueError("evidence_refs contains a key absent from observations")

    required_refs = {"volatility_20d_pct"}
    horizon_ref = f"return_{result['time_horizon']}_pct"
    required_refs.add(horizon_ref)
    if not required_refs.issubset(refs):
        raise ValueError(
            "evidence_refs must support the selected horizon, volatility, and volume interpretations"
        )
    volume_available = summary["observations"].get("volume_ratio_20d") is not None
    if volume_available:
        if "volume_ratio_20d" not in refs or result["volume_confirmation"] == "unavailable":
            raise ValueError("available volume must be interpreted and referenced")
    elif result["volume_confirmation"] != "unavailable" or "volume_ratio_20d" in refs:
        raise ValueError("unavailable volume must not be interpreted or referenced")


def build_request(summary, model):
    return {
        "model": model,
        "stream": False,
        "format": QUANT_SCHEMA,
        "options": {"temperature": 0, "num_predict": 500},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Interpret this market summary:\n"
                + json.dumps(summary, sort_keys=True, separators=(",", ":")),
            },
        ],
    }


def request_quant(summary, base_url, model, timeout, max_attempts=2):
    import requests

    request = build_request(summary, model)
    last_error = None
    for attempt in range(1, max_attempts + 1):
        response = requests.post(
            f"{base_url.rstrip('/')}/api/chat", json=request, timeout=timeout
        )
        response.raise_for_status()
        raw = response.json().get("message", {}).get("content")
        if not isinstance(raw, str):
            raise ValueError("Ollama response missing string message.content")
        try:
            result = json.loads(raw)
            validate_quant(result, summary)
            return result, raw
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
        if attempt < max_attempts:
            request["messages"].extend([
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    "The response failed deterministic validation. Correct only this error "
                    f"and return the complete JSON again: {last_error}"
                )},
            ])
    raise last_error


def analyze_market(summary, base_url, model=DEFAULT_MODEL, timeout=900):
    if not summary["market_available"]:
        from market_summary import abstain_result
        return abstain_result(summary), None, False
    result, raw = request_quant(summary, base_url, model, timeout)
    return result, raw, True
