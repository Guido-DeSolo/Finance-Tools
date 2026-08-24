#!/usr/bin/env python3
"""Narrow article sentiment and catalyst classifier."""

import json
import math


DEFAULT_OLLAMA_URL = "http://192.168.0.2:11434"
DEFAULT_MODEL = "mvkvl/sentiments:llama3"
SENTIMENT_VALUES = ("positive", "negative", "neutral", "mixed")
ARTICLE_SENTIMENT_VALUES = ("positive", "negative", "neutral")
MATERIALITY_VALUES = ("low", "moderate", "high")
CATALYST_VALUES = (
    "earnings", "guidance", "regulatory", "litigation", "financing",
    "merger_acquisition", "product", "management", "macro", "other", "none",
)
DIRECTION_VALUES = ("positive", "negative", "mixed", "neutral")
RISK_FLAG_VALUES = (
    "low_information", "conflicting_articles", "unclear_symbol_relevance",
    "source_quality_uncertain",
)
REQUIRED_FIELDS = {
    "symbol", "status", "overall_sentiment", "confidence", "materiality",
    "catalyst_type", "catalyst_direction", "article_assessments", "risk_flags",
}

NEWS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(REQUIRED_FIELDS),
    "properties": {
        "symbol": {"type": "string", "minLength": 1},
        "status": {"type": "string", "enum": ["ANALYZED"]},
        "overall_sentiment": {"type": "string", "enum": list(SENTIMENT_VALUES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "materiality": {"type": "string", "enum": list(MATERIALITY_VALUES)},
        "catalyst_type": {"type": "string", "enum": list(CATALYST_VALUES)},
        "catalyst_direction": {"type": "string", "enum": list(DIRECTION_VALUES)},
        "article_assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["article_id", "sentiment", "materiality"],
                "properties": {
                    "article_id": {"type": "integer", "minimum": 0},
                    "sentiment": {"type": "string", "enum": list(ARTICLE_SENTIMENT_VALUES)},
                    "materiality": {"type": "string", "enum": list(MATERIALITY_VALUES)},
                },
            },
        },
        "risk_flags": {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": list(RISK_FLAG_VALUES)},
        },
    },
}

SYSTEM_PROMPT = """You are the NEWS sentiment specialist.

Classify only the supplied article text. Do not discuss market prices, insider
activity, company fundamentals, or facts outside the articles. Do not invent a
catalyst or event. Do not repeat headlines or article facts. Reference every
article exactly once by article_id.

Sentiment describes likely directional implications for the supplied symbol, not
the emotional tone of the writing. Materiality describes likely relevance to the
symbol. Use catalyst_type=none and catalyst_direction=neutral when no supported
catalyst exists. Return only JSON matching the schema."""


def validate_news(result, summary):
    if not isinstance(result, dict):
        raise ValueError("news result must be an object")
    missing = REQUIRED_FIELDS - set(result)
    extra = set(result) - REQUIRED_FIELDS
    if missing:
        raise ValueError(f"news result missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"news result has unexpected fields: {', '.join(sorted(extra))}")
    if result["symbol"] != summary["symbol"]:
        raise ValueError("news symbol does not match summary")
    if result["status"] != "ANALYZED":
        raise ValueError("model result must be ANALYZED; Python owns abstention")
    for field, allowed in (
        ("overall_sentiment", SENTIMENT_VALUES), ("materiality", MATERIALITY_VALUES),
        ("catalyst_type", CATALYST_VALUES), ("catalyst_direction", DIRECTION_VALUES),
    ):
        if result[field] not in allowed:
            raise ValueError(f"invalid {field}: {result[field]!r}")
    confidence = result["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be numeric")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be finite and between 0 and 1")
    flags = result["risk_flags"]
    if not isinstance(flags, list) or len(flags) != len(set(flags)) or any(
        flag not in RISK_FLAG_VALUES for flag in flags
    ):
        raise ValueError("risk_flags contains invalid or duplicate values")

    assessments = result["article_assessments"]
    if not isinstance(assessments, list):
        raise ValueError("article_assessments must be an array")
    expected_ids = {article["id"] for article in summary["articles"]}
    actual_ids = [assessment.get("article_id") for assessment in assessments]
    if set(actual_ids) != expected_ids or len(actual_ids) != len(expected_ids):
        raise ValueError("article_assessments must reference every supplied article ID once")
    for assessment in assessments:
        if set(assessment) != {"article_id", "sentiment", "materiality"}:
            raise ValueError("article assessment fields are invalid")
        if assessment["sentiment"] not in ARTICLE_SENTIMENT_VALUES:
            raise ValueError("invalid article sentiment")
        if assessment["materiality"] not in MATERIALITY_VALUES:
            raise ValueError("invalid article materiality")

    sentiments = {assessment["sentiment"] for assessment in assessments}
    expected_overall = (
        "mixed" if {"positive", "negative"}.issubset(sentiments)
        else "positive" if "positive" in sentiments
        else "negative" if "negative" in sentiments
        else "neutral"
    )
    if result["overall_sentiment"] != expected_overall:
        raise ValueError("overall sentiment contradicts article assessments")
    levels = {"low": 0, "moderate": 1, "high": 2}
    expected_materiality = max(
        (assessment["materiality"] for assessment in assessments),
        key=levels.get,
    )
    if result["materiality"] != expected_materiality:
        raise ValueError("overall materiality must equal highest article materiality")
    if result["catalyst_type"] == "none" and result["catalyst_direction"] != "neutral":
        raise ValueError("no catalyst requires neutral catalyst direction")


def build_request(summary, model):
    return {
        "model": model,
        "stream": False,
        "format": NEWS_SCHEMA,
        "options": {"temperature": 0, "num_predict": 600},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "Classify this normalized news summary:\n"
                + json.dumps(summary, sort_keys=True, separators=(",", ":"))
            )},
        ],
    }


def request_news(summary, base_url, model=DEFAULT_MODEL, timeout=900, max_attempts=2):
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
            validate_news(result, summary)
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


def analyze_news(summary, base_url, model=DEFAULT_MODEL, timeout=900):
    if not summary["articles"]:
        from news_summary import abstain_result
        return abstain_result(summary), None, False
    result, raw = request_news(summary, base_url, model, timeout)
    return result, raw, True
