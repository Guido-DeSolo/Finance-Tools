#!/usr/bin/env python3
"""Qwen3 synthesis over normalized branch signals only."""

import json
import math


DEFAULT_OLLAMA_URL = "http://192.168.0.2:11434"
DEFAULT_MODEL = "qwen3:14b"
SIGNALS = ("insider", "quant", "news")
STATUS_VALUES = ("ANALYZED", "INSUFFICIENT_EVIDENCE", "REJECT_INCONSISTENT")
STANCE_VALUES = ("bullish", "bearish", "neutral")
HORIZON_VALUES = ("1d", "5d", "20d", "60d")
ACTION_VALUES = ("consider_long", "consider_short", "watch")
RISK_VALUES = (
    "sparse_evidence", "conflicting_direction", "abstaining_quant",
    "abstaining_news", "abstaining_insider", "high_volatility",
    "input_quality_concern",
)
REQUIRED_FIELDS = {
    "symbol", "status", "stance", "confidence", "time_horizon", "thesis",
    "supporting_signals", "contradicting_signals", "risk_flags", "action",
}

SYNTHESIS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": sorted(REQUIRED_FIELDS),
    "properties": {
        "symbol": {"type": "string", "minLength": 1},
        "status": {"type": "string", "enum": list(STATUS_VALUES)},
        "stance": {"type": "string", "enum": list(STANCE_VALUES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "time_horizon": {"type": "string", "enum": list(HORIZON_VALUES)},
        "thesis": {"type": "string", "minLength": 1},
        "supporting_signals": {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": list(SIGNALS)},
        },
        "contradicting_signals": {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": list(SIGNALS)},
        },
        "risk_flags": {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": list(RISK_VALUES)},
        },
        "action": {"type": "string", "enum": list(ACTION_VALUES)},
    },
}

SYSTEM_PROMPT = """You synthesize three normalized evidence branches: insider,
quant, and news. Reconcile them into a directional thesis only when the normalized
signals support one.

Do not restate or invent buyer counts, prices, returns, article facts, catalysts,
company fundamentals, or causal explanations. Reference only insider, quant, and
news. Never reference an abstaining branch as supporting or contradicting evidence.
Use INSUFFICIENT_EVIDENCE when fewer than two branches are analyzed or directional
evidence is too weak. Use REJECT_INCONSISTENT when strong directional branches
conflict without a defensible resolution. Return only JSON matching the schema."""


def branch_direction(name, branch):
    if branch["status"] != "ANALYZED":
        return None
    if name == "insider":
        return "positive" if branch["strength"] in ("strong", "moderate", "weak") else "neutral"
    if name == "quant":
        return {"bullish": "positive", "bearish": "negative", "neutral": "neutral"}[branch["trend"]]
    return {
        "positive": "positive", "negative": "negative",
        "neutral": "neutral", "mixed": "mixed",
    }[branch["overall_sentiment"]]


def validate_synthesis(result, synthesis_input):
    if not isinstance(result, dict):
        raise ValueError("synthesis result must be an object")
    missing = REQUIRED_FIELDS - set(result)
    extra = set(result) - REQUIRED_FIELDS
    if missing:
        raise ValueError(f"synthesis missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"synthesis has unexpected fields: {', '.join(sorted(extra))}")
    if result["symbol"] != synthesis_input["symbol"]:
        raise ValueError("synthesis symbol mismatch")
    for field, allowed in (
        ("status", STATUS_VALUES), ("stance", STANCE_VALUES),
        ("time_horizon", HORIZON_VALUES), ("action", ACTION_VALUES),
    ):
        if result[field] not in allowed:
            raise ValueError(f"invalid {field}: {result[field]!r}")
    confidence = result["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be numeric")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be finite and between 0 and 1")
    if not isinstance(result["thesis"], str) or not result["thesis"].strip():
        raise ValueError("thesis must be non-empty")
    for field in ("supporting_signals", "contradicting_signals"):
        values = result[field]
        if not isinstance(values, list) or len(values) != len(set(values)) or any(
            value not in SIGNALS for value in values
        ):
            raise ValueError(f"{field} must contain unique known signals")
    if set(result["supporting_signals"]) & set(result["contradicting_signals"]):
        raise ValueError("a signal cannot both support and contradict")
    if not isinstance(result["risk_flags"], list) or any(
        flag not in RISK_VALUES for flag in result["risk_flags"]
    ) or len(result["risk_flags"]) != len(set(result["risk_flags"])):
        raise ValueError("risk_flags contains invalid or duplicate values")

    analyzed = {
        name for name in SIGNALS if synthesis_input[name]["status"] == "ANALYZED"
    }
    referenced = set(result["supporting_signals"]) | set(result["contradicting_signals"])
    if not referenced.issubset(analyzed):
        raise ValueError("synthesis references an abstaining branch")
    if len(analyzed) < 2 and result["status"] != "INSUFFICIENT_EVIDENCE":
        raise ValueError("fewer than two analyzed branches requires insufficient evidence")

    if result["status"] == "ANALYZED":
        if result["stance"] == "neutral" or not result["supporting_signals"]:
            raise ValueError("analyzed synthesis requires a directional stance and support")
        expected_action = {
            "bullish": "consider_long", "bearish": "consider_short"
        }[result["stance"]]
        if result["action"] != expected_action or confidence <= 0:
            raise ValueError("analyzed stance, action, and confidence are inconsistent")
        desired = "positive" if result["stance"] == "bullish" else "negative"
        opposite = "negative" if desired == "positive" else "positive"
        for name in analyzed:
            direction = branch_direction(name, synthesis_input[name])
            if direction == desired and name not in result["supporting_signals"]:
                raise ValueError(f"{name} must be listed as supporting")
            if direction == opposite and name not in result["contradicting_signals"]:
                raise ValueError(f"{name} must be listed as contradicting")
    else:
        if result["stance"] != "neutral" or result["action"] != "watch" or confidence != 0:
            raise ValueError("non-analyzed synthesis must be neutral watch with zero confidence")
        if result["status"] == "REJECT_INCONSISTENT" and len(result["contradicting_signals"]) < 2:
            raise ValueError("inconsistent rejection requires at least two conflicting signals")

    quant = synthesis_input["quant"]
    expected_horizon = quant.get("preferred_horizon", "20d")
    if result["time_horizon"] != expected_horizon:
        raise ValueError("time horizon must match normalized quant horizon or default 20d")


def build_request(synthesis_input, model):
    return {
        "model": model, "stream": False, "format": SYNTHESIS_SCHEMA,
        "options": {"temperature": 0, "num_predict": 650},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "Synthesize this normalized evidence:\n"
                + json.dumps(synthesis_input, sort_keys=True, separators=(",", ":"))
            )},
        ],
    }


def request_synthesis(synthesis_input, base_url, model=DEFAULT_MODEL, timeout=900, max_attempts=2):
    import requests

    request = build_request(synthesis_input, model)
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
            validate_synthesis(result, synthesis_input)
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
