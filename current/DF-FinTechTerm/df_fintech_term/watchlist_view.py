from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


def load_stream_watchlist(database: Path) -> list[dict[str, Any]]:
    if not database.is_file():
        return []
    uri = f"{database.resolve().as_uri()}?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True)
        rows = db.execute("""
            SELECT asset_class, symbol, feed, location, added_at
            FROM stream_watchlist
            ORDER BY asset_class, symbol, feed, location
        """).fetchall()
        db.close()
    except sqlite3.Error:
        return []
    return [dict(zip(("asset_class", "symbol", "feed", "location", "added_at"), row))
            for row in rows]


def unique_symbols(entries: list[dict[str, Any]], asset_class: str | None = None) -> list[str]:
    return sorted({str(item["symbol"]) for item in entries
                   if asset_class is None or item.get("asset_class") == asset_class})
