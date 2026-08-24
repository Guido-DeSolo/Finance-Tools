from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


def load_industries(database: Path) -> list[dict[str, Any]]:
    """Return classified industries whose symbols have stored market data."""
    if not database.is_file():
        return []
    uri = f"{database.resolve().as_uri()}?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True)
        rows = db.execute("""
            WITH data_symbols AS (
                SELECT asset_class, symbol FROM bars
                UNION SELECT asset_class, symbol FROM live_trades
                UNION SELECT asset_class, symbol FROM live_market_events
                UNION SELECT asset_class, symbol FROM live_orderbooks
            )
            SELECT classification.industry, classification.sector,
                   classification.symbol, classification.company_name
            FROM symbol_classifications AS classification
            JOIN data_symbols AS data
              ON data.asset_class=classification.asset_class
             AND data.symbol=classification.symbol
            WHERE classification.status='classified'
              AND classification.industry IS NOT NULL
            ORDER BY classification.industry COLLATE NOCASE,
                     classification.symbol COLLATE NOCASE
        """).fetchall()
        db.close()
    except sqlite3.Error:
        return []
    grouped: list[dict[str, Any]] = []
    for industry, sector, symbol, company in rows:
        if not grouped or grouped[-1]["industry"] != industry:
            grouped.append({"industry": industry, "sector": sector, "symbols": []})
        if not any(item["symbol"] == symbol for item in grouped[-1]["symbols"]):
            grouped[-1]["symbols"].append({"symbol": symbol, "company": company})
    return grouped


def tickrs_command(industry: dict[str, Any]) -> list[str]:
    symbols = [item["symbol"] for item in industry.get("symbols", []) if item.get("symbol")]
    if not symbols:
        raise ValueError("selected industry has no symbols")
    return ["tickrs", "--symbols", ",".join(symbols)]
