#!/usr/bin/env python3
"""Persist Alpaca fills and benchmark them against nearest preceding local trades."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from df_fintech_term.api import AlpacaClient


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS execution_fills (
          activity_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, symbol TEXT NOT NULL,
          side TEXT NOT NULL, quantity REAL NOT NULL, fill_price REAL NOT NULL,
          transaction_time TEXT NOT NULL, raw_json TEXT NOT NULL, imported_at TEXT NOT NULL
        );
    """)


def persist_fills(db: sqlite3.Connection, activities: list[dict[str, Any]]) -> int:
    ensure_schema(db)
    saved = 0
    for item in activities:
        if item.get("activity_type") != "FILL":
            continue
        before = db.total_changes
        db.execute("""
            INSERT OR IGNORE INTO execution_fills VALUES (?,?,?,?,?,?,?,?,?)
        """, (item["id"], item["order_id"], str(item["symbol"]).upper(), item["side"],
              float(item["qty"]), float(item["price"]), item["transaction_time"],
              json.dumps(item, sort_keys=True), datetime.now(UTC).isoformat()))
        saved += db.total_changes - before
    db.commit()
    return saved


def preceding_trade(db: sqlite3.Connection, symbol: str, timestamp: str,
                    tolerance_seconds: int) -> tuple[float, str] | None:
    row = db.execute("""
        SELECT price, timestamp FROM live_trades
        WHERE symbol=? AND timestamp<=?
          AND julianday(?) - julianday(timestamp) <= ? / 86400.0
        ORDER BY timestamp DESC LIMIT 1
    """, (symbol, timestamp, timestamp, tolerance_seconds)).fetchone()
    return (float(row[0]), str(row[1])) if row else None


def analyze(db: sqlite3.Connection, tolerance_seconds: int = 60) -> dict[str, Any]:
    rows = db.execute("""
        SELECT activity_id,order_id,symbol,side,quantity,fill_price,transaction_time
        FROM execution_fills ORDER BY transaction_time
    """).fetchall()
    results = []
    for activity_id, order_id, symbol, side, quantity, price, timestamp in rows:
        reference = preceding_trade(db, symbol, timestamp, tolerance_seconds)
        slippage = None
        if reference and reference[0] > 0:
            slippage = ((price - reference[0]) / reference[0] * 10_000
                        if side == "buy" else (reference[0] - price) / reference[0] * 10_000)
        execution_cost = None
        if reference:
            execution_cost = ((price - reference[0]) * quantity
                              if side == "buy" else (reference[0] - price) * quantity)
        results.append({"activity_id": activity_id, "order_id": order_id, "symbol": symbol,
                        "side": side, "quantity": quantity, "fill_price": price,
                        "transaction_time": timestamp,
                        "reference_price": reference[0] if reference else None,
                        "reference_time": reference[1] if reference else None,
                        "slippage_bps": slippage, "execution_cost": execution_cost})
    matched = [item["slippage_bps"] for item in results if item["slippage_bps"] is not None]
    return {"benchmark": f"nearest preceding local trade within {tolerance_seconds}s",
            "fills": len(results), "matched": len(matched), "unmatched": len(results) - len(matched),
            "mean_slippage_bps": sum(matched) / len(matched) if matched else None,
            "total_slippage_cost": sum(item["execution_cost"] or 0 for item in results),
            "executions": results}


def fetch_all_fills(client: AlpacaClient, after: str | None, until: str | None) -> list[dict[str, Any]]:
    result = []
    token = None
    while True:
        page = client.account_activities(category="trade_activity", after=after, until=until,
                                         direction="asc", page_size=100, page_token=token)
        if not page:
            break
        result.extend(page)
        if len(page) < 100:
            break
        token = page[-1].get("id")
        if not token:
            break
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Alpaca fills and measure local execution quality.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--after")
    parser.add_argument("--until")
    parser.add_argument("--tolerance-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.tolerance_seconds < 0:
        parser.error("tolerance must be nonnegative")
    key_id = os.environ.get("APCA_API_KEY_ID", "")
    secret_key = os.environ.get("APCA_API_SECRET_KEY", "")
    if not key_id or not secret_key:
        parser.error("APCA_API_KEY_ID and APCA_API_SECRET_KEY are required")
    live = os.getenv("ALPACA_LIVE", "").lower() in {"1", "true", "yes"}
    client = AlpacaClient(key_id, secret_key,
                          "https://api.alpaca.markets" if live else "https://paper-api.alpaca.markets")
    activities = fetch_all_fills(client, args.after, args.until)
    db = sqlite3.connect(args.db)
    saved = persist_fills(db, activities)
    report = analyze(db, args.tolerance_seconds)
    db.close()
    report["imported"] = saved
    output = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
