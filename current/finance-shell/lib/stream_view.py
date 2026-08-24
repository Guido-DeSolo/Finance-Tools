"""Read-only live terminal view of Finance Shell market-stream data."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

def age(timestamp: str | None) -> str:
    if not timestamp:
        return "-"
    try:
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        seconds = max(0.0, (datetime.now(UTC) - value).total_seconds())
        return f"{seconds:.1f}s"
    except ValueError:
        return "?"


def price(value: object) -> str:
    return "-" if value is None else f"{float(value):,.8f}".rstrip("0").rstrip(".")


def size(value: object) -> str:
    return "-" if value is None else f"{float(value):,.8f}".rstrip("0").rstrip(".")


def books(db: sqlite3.Connection, symbol: str | None, asset_class: str | None) -> list[sqlite3.Row]:
    db.row_factory = sqlite3.Row
    clauses, values = [], []
    if symbol:
        clauses.append("symbol=?")
        values.append(symbol.upper())
    if asset_class:
        clauses.append("asset_class=?")
        values.append(asset_class)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return db.execute(
        "SELECT * FROM live_orderbooks" + where + " ORDER BY asset_class, symbol", values
    ).fetchall()


def overview(db: sqlite3.Connection) -> str:
    rows = books(db, None, None)
    lines = ["CLASS    SYMBOL           BEST BID           BEST ASK           AGE      DEPTH"]
    for row in rows:
        bids = json.loads(row["bids_json"])
        asks = json.loads(row["asks_json"])
        best_bid = price(bids[0].get("p")) if bids else "-"
        best_ask = price(asks[0].get("p")) if asks else "-"
        depth = f"{len(bids)}/{len(asks)}" if row["is_full_depth"] else "top"
        lines.append(
            f"{row['asset_class']:<8} {row['symbol']:<16} {best_bid:<18} "
            f"{best_ask:<18} {age(row['received_at']):<8} {depth}"
        )
    if not rows:
        lines.append("No live books received yet.")
    watched = db.execute("SELECT count(*) FROM stream_watchlist").fetchone()[0]
    lines.append(f"\n{watched} watched symbol(s), {len(rows)} current book(s)")
    return "\n".join(lines)


def detail(db: sqlite3.Connection, symbol: str, asset_class: str | None, depth: int) -> str:
    matches = books(db, symbol, asset_class)
    if not matches:
        return f"No live book received for {symbol.upper()} yet."
    row = matches[0]
    bids = json.loads(row["bids_json"])
    asks = json.loads(row["asks_json"])
    kind = "full depth" if row["is_full_depth"] else "top of book"
    lines = [
        f"{row['symbol']}  {row['asset_class']}  {kind}  "
        f"source={row['feed'] or row['location']}  age={age(row['received_at'])}",
        f"Market timestamp: {row['timestamp']}",
        "",
        " #   BID SIZE           BID PRICE          | ASK PRICE          ASK SIZE",
    ]
    for index in range(max(min(depth, max(len(bids), len(asks))), 0)):
        bid = bids[index] if index < len(bids) else {}
        ask = asks[index] if index < len(asks) else {}
        lines.append(
            f"{index + 1:>2}   {size(bid.get('s')):>18} {price(bid.get('p')):>18} | "
            f"{price(ask.get('p')):<18} {size(ask.get('s')):<18}"
        )
    trades = db.execute("""
        SELECT timestamp, price, size, taker_side FROM live_trades
        WHERE asset_class=? AND symbol=? ORDER BY timestamp DESC LIMIT 8
    """, (row["asset_class"], row["symbol"])).fetchall()
    lines.extend(("", "RECENT TRADES", "TIME                                PRICE              SIZE        SIDE"))
    if trades:
        for timestamp, trade_price, trade_size, side in trades:
            lines.append(f"{timestamp:<35} {price(trade_price):>16} {size(trade_size):>16} {side or '-'}")
    else:
        lines.append("No trades received yet.")
    events = db.execute("""
        SELECT event_type, timestamp FROM live_market_events
        WHERE asset_class=? AND symbol=? ORDER BY timestamp DESC LIMIT 6
    """, (row["asset_class"], row["symbol"])).fetchall()
    if events:
        lines.extend(("", "LATEST EVENTS  " + "  ".join(f"{kind}@{stamp}" for kind, stamp in events)))
    return "\n".join(lines)


def render(database: Path, symbol: str | None, asset_class: str | None, depth: int) -> str:
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        body = detail(db, symbol, asset_class, depth) if symbol else overview(db)
    finally:
        db.close()
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"FINANCE SHELL LIVE STREAM                         {stamp}\n\n{body}\n\nCtrl-C to exit"


def run(args: argparse.Namespace) -> None:
    if args.depth < 1:
        raise SystemExit("--depth must be at least 1")
    if args.interval < 0.1:
        raise SystemExit("--interval must be at least 0.1 seconds")
    interactive = not args.once
    try:
        if interactive:
            print("\033[?25l", end="", flush=True)
        while True:
            output = render(args.db, args.symbol, args.asset_class, args.depth)
            if interactive:
                print("\033[H\033[2J" + output, end="", flush=True)
            else:
                print(output)
            if args.once:
                return
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if interactive:
            print("\033[?25h")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("symbol", nargs="?", help="optional symbol for a detailed book view")
    parser.add_argument("--class", dest="asset_class", choices=("stock", "crypto"))
    parser.add_argument("--depth", type=int, default=10, help="book levels to display; default 10")
    parser.add_argument("--interval", type=float, default=1.0, help="refresh seconds; default 1")
    parser.add_argument("--once", action="store_true", help="render one frame and exit")
