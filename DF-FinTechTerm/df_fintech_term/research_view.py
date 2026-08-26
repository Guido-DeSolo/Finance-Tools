"""Read locally published daily-research manifests for the TUI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _terminal_text(value: Any) -> str:
    return "".join(character for character in str(value) if character in "\n\t" or ord(character) >= 32)


def load_latest_research(directory: Path) -> dict[str, Any]:
    path = directory / "latest.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    required = {"generated_at", "model", "candidate_count", "symbols", "summary", "notebook_path"}
    if not isinstance(payload, dict) or not required <= payload.keys():
        return {}
    payload["summary"] = _terminal_text(payload["summary"])
    return payload
