"""Select a stored SEC industry and launch tickrs for its symbols."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import sqlite3
from pathlib import Path

from .alpaca_store import DEFAULT_DB, connect


def industries(db: sqlite3.Connection) -> list[tuple[str, list[str]]]:
    rows = db.execute("""
        WITH eligible_symbols AS (
            SELECT 'stock' AS asset_class, symbol FROM assets
            WHERE asset_class='us_equity' AND status='active'
            UNION
            SELECT asset_class, symbol FROM bars
            UNION SELECT asset_class, symbol FROM live_trades
            UNION SELECT asset_class, symbol FROM live_market_events
            UNION SELECT asset_class, symbol FROM live_orderbooks
        )
        SELECT classification.industry, classification.symbol
        FROM symbol_classifications AS classification
        JOIN eligible_symbols AS data
          ON data.asset_class=classification.asset_class
         AND data.symbol=classification.symbol
        WHERE classification.status IN ('classified', 'unclassified', 'unmatched', 'error')
          AND classification.industry IS NOT NULL
        ORDER BY classification.industry COLLATE NOCASE,
                 classification.symbol COLLATE NOCASE
    """).fetchall()
    grouped: list[tuple[str, list[str]]] = []
    for industry, symbol in rows:
        if not grouped or grouped[-1][0] != industry:
            grouped.append((industry, []))
        if symbol not in grouped[-1][1]:
            grouped[-1][1].append(symbol)
    return grouped


def choose(items: list[tuple[str, list[str]]]) -> tuple[str, list[str]]:
    print("Available industries:\n")
    for number, (industry, symbols) in enumerate(items, 1):
        print(f"{number:>3}. {industry} ({len(symbols)} symbol{'s' if len(symbols) != 1 else ''})")
    print("  0. Cancel")
    while True:
        try:
            value = input("\nSelect an industry: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(130)
        if value == "0":
            raise SystemExit(0)
        try:
            index = int(value) - 1
        except ValueError:
            index = -1
        if 0 <= index < len(items):
            return items[index]
        print(f"Enter a number from 0 to {len(items)}.")


def named(items: list[tuple[str, list[str]]], name: str) -> tuple[str, list[str]]:
    matches = [item for item in items if item[0].casefold() == name.casefold()]
    if not matches:
        raise SystemExit(f"unknown industry: {name}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(prog="df-fintechterm tickrs-industry")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--industry", help="select an exact industry name without prompting")
    parser.add_argument("--dry-run", action="store_true", help="print rather than launch tickrs")
    parser.add_argument("tickrs_args", nargs=argparse.REMAINDER,
                        help="arguments after -- are forwarded to tickrs")
    args = parser.parse_args()
    forwarded = args.tickrs_args[1:] if args.tickrs_args[:1] == ["--"] else args.tickrs_args
    db = connect(args.db)
    items = industries(db)
    db.close()
    if not items:
        raise SystemExit("no classified industries with stored data; run: df-fintechterm classify refresh")
    industry, symbols = named(items, args.industry) if args.industry else choose(items)
    command = ["tickrs", "--symbols", ",".join(symbols), *forwarded]
    print(f"Opening {industry}: {', '.join(symbols)}")
    if args.dry_run:
        print(shlex.join(command))
        return
    if shutil.which("tickrs") is None:
        raise SystemExit("tickrs is not installed")
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
