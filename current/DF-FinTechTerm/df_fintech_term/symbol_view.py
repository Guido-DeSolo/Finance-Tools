"""Command parsing and read-only stored context for symbol workspaces."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Command:
    destination: str
    symbol: str = ""
    focus_orders: bool = False


def parse_command(text: str) -> Command:
    tokens = text.upper().replace("<GO>", "GO").split()
    if not tokens:
        raise ValueError("command is empty")
    aliases = {
        "DASH": "dashboard", "DASHBOARD": "dashboard",
        "TICKER": "ticker", "INDUSTRY": "industry", "TA": "analysis",
        "WATCH": "watchlist", "WATCHLIST": "watchlist",
    }
    if tokens[0] in {"ORDERS", "ORDER"}:
        return Command("dashboard", focus_orders=True)
    if tokens[0] in aliases:
        return Command(aliases[tokens[0]])
    symbol = tokens[0]
    if not all(character.isalnum() or character in ".-/" for character in symbol):
        raise ValueError("invalid symbol")
    if len(tokens) > 2 or (len(tokens) == 2 and tokens[1] not in {"GO", "CHART", "NEWS", "TA"}):
        raise ValueError("expected SYMBOL [GO|CHART|NEWS|TA]")
    return Command("symbol", symbol=symbol)


def sparkline(values: list[float], width: int) -> str:
    if width <= 0 or not values:
        return ""
    values = values[-width:]
    low, high = min(values), max(values)
    if high == low:
        return "─" * len(values)
    blocks = "▁▂▃▄▅▆▇█"
    return "".join(blocks[int((value - low) / (high - low) * (len(blocks) - 1))] for value in values)


def load_symbol_profile(database: Path, symbol: str) -> dict[str, Any]:
    """Load available metadata, bars, news, and analysis without changing SQLite."""
    profile: dict[str, Any] = {"symbol": symbol, "bars": [], "news": [], "analysis": {}}
    if not database.is_file():
        return profile
    try:
        db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        db.row_factory = sqlite3.Row
        asset = db.execute("""
            SELECT name, exchange, asset_class, tradable, fractionable, marginable, shortable
            FROM assets WHERE symbol=? ORDER BY last_seen_at DESC LIMIT 1
        """, (symbol,)).fetchone()
        classification = db.execute("""
            SELECT sector, industry, company_name FROM symbol_classifications
            WHERE symbol=? ORDER BY CASE status WHEN 'classified' THEN 0 ELSE 1 END LIMIT 1
        """, (symbol,)).fetchone()
        bars = db.execute("""
            WITH chosen AS (
                SELECT asset_class, timeframe, feed, adjustment FROM bars
                WHERE symbol=?
                ORDER BY CASE timeframe
                    WHEN '1Day' THEN 0 WHEN '1Hour' THEN 1 WHEN '15Min' THEN 2
                    WHEN '5Min' THEN 3 WHEN '1Min' THEN 4 ELSE 5 END,
                    timestamp DESC LIMIT 1
            )
            SELECT bars.timestamp, bars.close, bars.timeframe FROM bars
            JOIN chosen USING(asset_class, timeframe, feed, adjustment)
            WHERE bars.symbol=? ORDER BY bars.timestamp DESC LIMIT 80
        """, (symbol, symbol)).fetchall()
        news = db.execute("""
            SELECT article.updated_at, article.source, article.headline, article.url
            FROM news_articles AS article
            JOIN news_article_symbols AS tagged USING(article_id)
            WHERE tagged.symbol=? ORDER BY article.updated_at DESC LIMIT 8
        """, (symbol,)).fetchall()
        analysis = db.execute("""
            SELECT indicators_json, updated_at FROM technical_analysis_snapshots
            WHERE symbol=? ORDER BY updated_at DESC LIMIT 1
        """, (symbol,)).fetchone()
        db.close()
    except sqlite3.Error:
        return profile
    if asset:
        profile["asset"] = dict(asset)
    if classification:
        profile["classification"] = dict(classification)
    profile["bars"] = [dict(row) for row in reversed(bars)]
    profile["news"] = [dict(row) for row in news]
    if analysis:
        try:
            indicators = json.loads(analysis["indicators_json"] or "{}")
        except json.JSONDecodeError:
            indicators = {}
        profile["analysis"] = {**indicators, "updated_at": analysis["updated_at"]}
    return profile
