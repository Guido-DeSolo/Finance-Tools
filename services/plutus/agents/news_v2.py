#!/usr/bin/env python3
"""NEWS v2: model-only per-article sentiment and materiality classification."""

import json


DEFAULT_OLLAMA_URL = "http://192.168.0.2:11434"
DEFAULT_MODEL = "mvkvl/sentiments:llama3"
SENTIMENT_VALUES = ("positive", "negative", "neutral")
MATERIALITY_VALUES = ("low", "moderate", "high")
REQUIRED_FIELDS = {"symbol", "status", "article_assessments"}

NEWS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(REQUIRED_FIELDS),
    "properties": {
        "symbol": {"type": "string", "minLength": 1},
        "status": {"type": "string", "enum": ["ANALYZED"]},
        "article_assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["article_id", "sentiment", "materiality"],
                "properties": {
                    "article_id": {"type": "integer", "minimum": 0},
                    "sentiment": {"type": "string", "enum": list(SENTIMENT_VALUES)},
                    "materiality": {"type": "string", "enum": list(MATERIALITY_VALUES)},
                },
            },
        },
    },
}

SYSTEM_PROMPT = """You are the NEWS article classifier.

For every supplied article, classify only:
1. sentiment: likely directional implication for the supplied symbol
2. materiality: likely relevance and significance to the supplied symbol

Do not aggregate articles. Do not identify catalysts. Do not create risk flags.
Do not discuss market prices, insiders, fundamentals, or facts outside the article.
Do not repeat headlines or article text. Reference every article exactly once by
article_id. Return only JSON matching the schema."""


def validate_assessments(result, summary):
    if not isinstance(result, dict):
        raise ValueError("NEWS v2 result must be an object")
    missing = REQUIRED_FIELDS - set(result)
    extra = set(result) - REQUIRED_FIELDS
    if missing:
        raise ValueError(f"NEWS v2 result missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"NEWS v2 result has unexpected fields: {', '.join(sorted(extra))}")
    if result["symbol"] != summary["symbol"]:
        raise ValueError("NEWS v2 symbol does not match summary")
    if result["status"] != "ANALYZED":
        raise ValueError("model result must be ANALYZED; Python owns abstention")
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
        if assessment["sentiment"] not in SENTIMENT_VALUES:
            raise ValueError("invalid article sentiment")
        if assessment["materiality"] not in MATERIALITY_VALUES:
            raise ValueError("invalid article materiality")


def build_request(summary, model):
    return {
        "model": model,
        "stream": False,
        "format": NEWS_SCHEMA,
        "options": {"temperature": 0, "num_predict": 350},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "Classify each article in this news summary:\n"
                + json.dumps(summary, sort_keys=True, separators=(",", ":"))
            )},
        ],
    }


def request_assessments(summary, base_url, model=DEFAULT_MODEL, timeout=900, max_attempts=2):
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
            validate_assessments(result, summary)
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
