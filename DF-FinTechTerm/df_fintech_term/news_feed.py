"""Merge live Alpaca news and NewsData.io into one newest-first feed."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Any


def _timestamp(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_live_news(database: Path, limit: int = 100) -> list[dict[str, str]]:
    """Read both streamed providers without creating or changing the database."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if not database.is_file():
        return []
    try:
        db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        rows = db.execute("""
            SELECT article_id, updated_at, source, headline, url
            FROM news_articles
            ORDER BY updated_at DESC, article_id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        db.close()
    except sqlite3.Error:
        return []
    return [
        {
            "timestamp": row[1] or "",
            "source": row[2] or ("NewsData" if row[0].startswith("newsdata:") else "Alpaca"),
            "title": row[3] or "Untitled",
            "url": row[4] or "",
            "provider": "NewsData" if row[0].startswith("newsdata:") else "Alpaca",
        }
        for row in rows
    ]


def merge_news(*feeds: list[dict[str, str]], limit: int = 200) -> list[dict[str, str]]:
    """Deduplicate the two providers and return a single newest-first feed."""
    retained: dict[str, dict[str, str]] = {}
    for item in (entry for feed in feeds for entry in feed):
        title = " ".join(item.get("title", "").split())
        if not title:
            continue
        key = item.get("url") or title.casefold()
        existing = retained.get(key)
        if existing is None or _timestamp(item.get("timestamp")) > _timestamp(existing.get("timestamp")):
            retained[key] = {**item, "title": title}
    return sorted(
        retained.values(),
        key=lambda item: (_timestamp(item.get("timestamp")), item.get("title", "")),
        reverse=True,
    )[:limit]
