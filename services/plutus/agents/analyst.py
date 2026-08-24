#!/usr/bin/env python3
"""Interpret one reduced evidence summary with Ollama and persist the result."""

import argparse
import json
import math
from pathlib import Path


AGENT_NAME = "analyst"
DEFAULT_OLLAMA_URL = "http://192.168.0.2:11434"
DEFAULT_MODEL = "analyst:latest"
STANCE_VALUES = ("bullish", "bearish", "neutral")
HORIZON_VALUES = ("1d", "5d", "20d", "60d")
ACTION_VALUES = ("consider_long", "consider_short", "watch", "avoid")
LIST_FIELDS = ("bear_case", "catalysts", "invalidation_conditions")
INTERPRETATION_FIELDS = (
    "insider_interpretation",
    "news_interpretation",
    "market_interpretation",
)
REQUIRED_FIELDS = {
    "symbol", "stance", "confidence", "time_horizon", "thesis", "action",
    "evidence_refs", *LIST_FIELDS, *INTERPRETATION_FIELDS,
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(REQUIRED_FIELDS),
    "properties": {
        "symbol": {"type": "string", "minLength": 1},
        "stance": {"type": "string", "enum": list(STANCE_VALUES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "time_horizon": {"type": "string", "enum": list(HORIZON_VALUES)},
        **{
            field: {"type": "string", "minLength": 1}
            for field in (*INTERPRETATION_FIELDS, "thesis")
        },
        **{
            field: {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            }
            for field in LIST_FIELDS
        },
        "evidence_refs": {
            "type": "object",
            "additionalProperties": False,
            "required": ["insider", "news", "market"],
            "properties": {
                "insider": {"type": "boolean"},
                "news": {"type": "array", "items": {"type": "integer", "minimum": 0}},
                "market": {"type": "boolean"},
            },
        },
        "action": {"type": "string", "enum": list(ACTION_VALUES)},
    },
}

SYSTEM_PROMPT = """You are a cautious equity research analyst. You receive a
small, deterministic evidence summary. Python owns every fact in that summary;
your only job is to interpret what the evidence means.

Do not restate or copy counts, flags, prices, returns, dollar values, headlines, or
other raw facts into the response. Do not invent company fundamentals, events,
causes, or facts outside the summary. Use each evidence category that is present.
When market.available is false, say that market evidence is unavailable and do not
infer a market direction. Treat every quality item as a limitation. News references
must use only the supplied item IDs.

Before responding, internally verify that every interpretation follows from the
summary. If a field is present, do not call it missing. If absent, do not infer it.
Confidence must be a decimal from 0.0 through 1.0. Return only JSON matching the
provided schema. This is research, not an order or execution instruction."""


def load_packet(path, symbol):
    with open(path, encoding="utf-8") as packet_file:
        document = json.load(packet_file)
    packets = document.get("packets")
    if not isinstance(packets, list):
        raise ValueError("candidate document packets must be an array")
    matches = [packet for packet in packets if packet.get("symbol") == symbol]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one packet for {symbol}, found {len(matches)}")
    return matches[0]


def validate_analysis(analysis, summary):
    if not isinstance(analysis, dict):
        raise ValueError("analysis must be an object")
    missing = REQUIRED_FIELDS - set(analysis)
    extra = set(analysis) - REQUIRED_FIELDS
    if missing:
        raise ValueError(f"analysis missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"analysis has unexpected fields: {', '.join(sorted(extra))}")
    if analysis["symbol"] != summary["symbol"]:
        raise ValueError("analysis symbol does not match evidence summary")
    if analysis["stance"] not in STANCE_VALUES:
        raise ValueError(f"invalid stance: {analysis['stance']!r}")
    if analysis["time_horizon"] not in HORIZON_VALUES:
        raise ValueError(f"invalid time_horizon: {analysis['time_horizon']!r}")
    if analysis["action"] not in ACTION_VALUES:
        raise ValueError(f"invalid action: {analysis['action']!r}")

    confidence = analysis["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be finite and between 0 and 1")

    for field in (*INTERPRETATION_FIELDS, "thesis"):
        if not isinstance(analysis[field], str) or not analysis[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    for field in LIST_FIELDS:
        values = analysis[field]
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise ValueError(f"{field} must be an array of non-empty strings")

    refs = analysis["evidence_refs"]
    if not isinstance(refs, dict) or set(refs) != {"insider", "news", "market"}:
        raise ValueError("evidence_refs must contain only insider, news, and market")
    if not isinstance(refs["insider"], bool) or not isinstance(refs["market"], bool):
        raise ValueError("insider and market evidence references must be boolean")
    if not isinstance(refs["news"], list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in refs["news"]
    ):
        raise ValueError("news evidence references must be integer IDs")

    insider_available = summary["insider"]["signal_strength"] != "none"
    if refs["insider"] != insider_available:
        raise ValueError("insider evidence reference does not match availability")
    if refs["market"] != summary["market"]["available"]:
        raise ValueError("market evidence reference does not match availability")
    expected_news = {item["id"] for item in summary["news"]["items"]}
    if set(refs["news"]) != expected_news or len(refs["news"]) != len(expected_news):
        raise ValueError("news evidence references must include every supplied news ID once")


def build_request(summary, model):
    return {
        "model": model,
        "stream": False,
        "format": ANALYSIS_SCHEMA,
        "options": {"temperature": 0, "num_predict": 800},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Interpret this normalized evidence summary:\n"
                + json.dumps(summary, sort_keys=True, separators=(",", ":")),
            },
        ],
    }


def request_analysis(summary, base_url, model, timeout, max_attempts=2):
    import requests

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    request = build_request(summary, model)
    last_error = None
    for attempt in range(1, max_attempts + 1):
        response = requests.post(
            f"{base_url.rstrip('/')}/api/chat", json=request, timeout=timeout
        )
        response.raise_for_status()
        envelope = response.json()
        try:
            raw_response = envelope["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ValueError("Ollama response missing message.content") from exc
        if not isinstance(raw_response, str):
            raise ValueError("Ollama message.content must be a string")
        try:
            analysis = json.loads(raw_response)
            validate_analysis(analysis, summary)
            return analysis, raw_response
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
        if attempt < max_attempts:
            request["messages"].extend(
                [
                    {"role": "assistant", "content": raw_response},
                    {
                        "role": "user",
                        "content": (
                            "The response failed deterministic validation. Correct the "
                            "specific error and return the complete JSON object again. "
                            f"Do not add facts. Error: {last_error}"
                        ),
                    },
                ]
            )
    raise last_error


def store_analysis(conn, analysis, packet, summary, raw_response, model):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_analyses (
                symbol, agent_name, model_name, stance, confidence, time_horizon,
                action, insider_interpretation, news_interpretation,
                market_interpretation, thesis, bear_case, catalysts,
                invalidation_conditions, evidence_refs, evidence_summary, packet,
                raw_response
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                %s::jsonb, %s
            ) RETURNING id, analyzed_at
            """,
            (
                analysis["symbol"], AGENT_NAME, model, analysis["stance"],
                analysis["confidence"], analysis["time_horizon"], analysis["action"],
                analysis["insider_interpretation"], analysis["news_interpretation"],
                analysis["market_interpretation"], analysis["thesis"],
                json.dumps(analysis["bear_case"]), json.dumps(analysis["catalysts"]),
                json.dumps(analysis["invalidation_conditions"]),
                json.dumps(analysis["evidence_refs"]), json.dumps(summary),
                json.dumps(packet), raw_response,
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def main():
    parser = argparse.ArgumentParser(description="Analyze and store one candidate packet.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--packet-file", default="data/candidate_packets.json", type=Path)
    parser.add_argument("--timeout", default=300, type=float)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    import psycopg
    import sys

    data_path = Path(__file__).resolve().parents[1] / "data"
    sys.path.insert(0, str(data_path))
    from candidate_packet import validate_document
    from evidence_summary import reduce_packet
    from settings import load_settings

    with open(args.packet_file, encoding="utf-8") as packet_file:
        validate_document(json.load(packet_file))
    packet = load_packet(args.packet_file, args.symbol.upper())
    summary = reduce_packet(packet)
    settings = load_settings(("DATABASE_URL",))
    base_url = settings.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)
    model = settings.get("ANALYST_MODEL", DEFAULT_MODEL)
    analysis, raw_response = request_analysis(summary, base_url, model, args.timeout)
    with psycopg.connect(settings["DATABASE_URL"]) as conn:
        analysis_id, analyzed_at = store_analysis(
            conn, analysis, packet, summary, raw_response, model
        )
    print(json.dumps({"id": analysis_id, "analyzed_at": analyzed_at.isoformat(), **analysis}))


if __name__ == "__main__":
    main()
