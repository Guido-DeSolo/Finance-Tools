"""Read current live technical-analysis snapshots for the Dixie TUI."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ACTIVE_SECONDS = 300


def load_active_analysis(
    database: Path, *, active_seconds: int = ACTIVE_SECONDS
) -> list[dict[str, Any]]:
    """Return newest-first snapshots for watched, recently traded book symbols."""
    if active_seconds <= 0:
        raise ValueError("active_seconds must be positive")
    if not database.is_file():
        return []
    cutoff = (datetime.now(UTC) - timedelta(seconds=active_seconds)).isoformat().replace(
        "+00:00", "Z"
    )
    try:
        db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT analysis.asset_class, analysis.symbol, analysis.feed,
                   analysis.location, analysis.source_trade_id,
                   analysis.trade_timestamp, analysis.bar_timestamp,
                   analysis.bars_buffered, analysis.indicators_json,
                   analysis.updated_at
            FROM technical_analysis_snapshots AS analysis
            INNER JOIN live_orderbooks AS book
              USING(asset_class, symbol, feed, location)
            INNER JOIN stream_watchlist AS watch
              USING(asset_class, symbol, feed, location)
            WHERE analysis.updated_at >= ?
            ORDER BY analysis.updated_at DESC, analysis.symbol
        """, (cutoff,)).fetchall()
        db.close()
    except sqlite3.Error:
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            indicators = json.loads(row["indicators_json"])
        except (TypeError, json.JSONDecodeError):
            indicators = {}
        result.append({**dict(row), "indicators": indicators})
    return result


def seconds_old(timestamp: str | None) -> int | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((datetime.now(UTC) - parsed).total_seconds()))
