#!/usr/bin/env python3
"""Replay explicit trade plans against stored bars with transparent costs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReplayFill:
    symbol: str
    side: str
    quantity: float
    entry_time: str
    exit_time: str
    entry_market_price: float
    exit_market_price: float
    entry_fill_price: float
    exit_fill_price: float
    gross_pnl: float
    costs: float
    net_pnl: float
    return_pct: float


def execution_price(price: float, side: str, entering: bool, slippage_bps: float) -> float:
    adverse = slippage_bps / 10_000
    direction = 1 if (side == "long") == entering else -1
    return price * (1 + direction * adverse)


def replay_trade(plan: dict[str, Any], entry: tuple[str, float], exit: tuple[str, float],
                 slippage_bps: float, commission: float) -> ReplayFill:
    symbol = str(plan["symbol"]).upper()
    side = str(plan.get("side", "long")).lower()
    quantity = float(plan["quantity"])
    if side not in {"long", "short"} or quantity <= 0:
        raise ValueError("side must be long/short and quantity must be positive")
    entry_fill = execution_price(entry[1], side, True, slippage_bps)
    exit_fill = execution_price(exit[1], side, False, slippage_bps)
    multiplier = 1 if side == "long" else -1
    gross = (exit_fill - entry_fill) * quantity * multiplier
    costs = commission * 2
    net = gross - costs
    capital = entry_fill * quantity
    return ReplayFill(symbol, side, quantity, entry[0], exit[0], entry[1], exit[1],
                      entry_fill, exit_fill, gross, costs, net,
                      net / capital * 100 if capital else 0)


def next_bar(db: sqlite3.Connection, symbol: str, timestamp: str,
             timeframe: str, series: tuple[str, str, str] | None = None
             ) -> tuple[str, float, str, str, str] | None:
    where = ""
    parameters: list[Any] = [symbol, timeframe, timestamp]
    if series:
        where = " AND asset_class=? AND feed=? AND adjustment=?"
        parameters.extend(series)
    row = db.execute(f"""
        SELECT timestamp, open, asset_class, feed, adjustment FROM bars
        WHERE symbol=? AND timeframe=? AND timestamp>=? {where}
        ORDER BY timestamp ASC, asset_class, feed, adjustment LIMIT 1
    """, parameters).fetchone()
    return (str(row[0]), float(row[1]), str(row[2]), str(row[3]), str(row[4])) if row else None


def summarize(fills: list[ReplayFill], initial_capital: float) -> dict[str, Any]:
    if initial_capital <= 0:
        raise ValueError("initial capital must be positive")
    cumulative = peak = max_drawdown = 0.0
    for fill in sorted(fills, key=lambda item: item.exit_time):
        cumulative += fill.net_pnl
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    return {
        "trades": len(fills),
        "wins": sum(fill.net_pnl > 0 for fill in fills),
        "win_rate_pct": sum(fill.net_pnl > 0 for fill in fills) / len(fills) * 100 if fills else 0,
        "gross_pnl": sum(fill.gross_pnl for fill in fills),
        "total_costs": sum(fill.costs for fill in fills),
        "net_pnl": sum(fill.net_pnl for fill in fills),
        "initial_capital": initial_capital,
        "net_return_pct": sum(fill.net_pnl for fill in fills) / initial_capital * 100,
        "max_drawdown_currency": max_drawdown,
        "max_drawdown_pct_of_initial": max_drawdown / initial_capital * 100,
    }


def run_replay(database: Path, plans: list[dict[str, Any]], slippage_bps: float,
               commission: float, initial_capital: float = 100_000) -> dict[str, Any]:
    if slippage_bps < 0 or commission < 0:
        raise ValueError("cost assumptions must be nonnegative")
    if not isinstance(plans, list):
        raise ValueError("trade plan must be a JSON array")
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    fills: list[ReplayFill] = []
    rendered_trades: list[dict[str, Any]] = []
    skipped = []
    for plan in plans:
        symbol = str(plan.get("symbol") or "").upper()
        timeframe = str(plan.get("timeframe") or "1Day")
        entry = next_bar(db, symbol, str(plan.get("entry_time") or ""), timeframe)
        series = (entry[2], entry[3], entry[4]) if entry else None
        exit = next_bar(db, symbol, str(plan.get("exit_time") or ""), timeframe, series)
        if not entry or not exit or exit[0] <= entry[0]:
            skipped.append({"plan": plan, "reason": "missing or non-forward bar"})
            continue
        fill = replay_trade(plan, entry[:2], exit[:2], slippage_bps, commission)
        fills.append(fill)
        rendered_trades.append({**asdict(fill), "series": {
            "asset_class": entry[2], "timeframe": timeframe,
            "feed": entry[3], "adjustment": entry[4],
        }})
    db.close()
    return {
        "assumptions": {"fill": "next stored bar open", "slippage_bps_each_side": slippage_bps,
                        "commission_each_order": commission},
        "summary": summarize(fills, initial_capital),
        "trades": rendered_trades, "skipped": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay an explicit JSON trade plan against SQLite bars.")
    parser.add_argument("plan", type=Path, help="JSON array: symbol, side, quantity, entry_time, exit_time")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--slippage-bps", type=float, default=5)
    parser.add_argument("--commission", type=float, default=0)
    parser.add_argument("--initial-capital", type=float, default=100_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_replay(args.db, json.loads(args.plan.read_text()), args.slippage_bps,
                        args.commission, args.initial_capital)
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
