"""Rolling technical analysis for symbols with live order books."""

from __future__ import annotations

import asyncio
import argparse
import json
import sqlite3
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import technical_indicators as ta
except ImportError:
    package_root = Path(__file__).resolve().parents[4] / "packages" / "technical-indicators"
    if package_root.is_dir():
        sys.path.insert(0, str(package_root))
    import technical_indicators as ta

from alpaca_store import DEFAULT_DB, connect, now

BUFFER_BARS = 200
POLL_SECONDS = 0.25
WARM_TRADES = 5_000


@dataclass
class Bar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def minute_bucket(timestamp: str) -> str:
    """Normalize an RFC-3339 trade timestamp to its UTC minute label."""
    if len(timestamp) < 16 or timestamp[4] != "-" or timestamp[7] != "-":
        raise ValueError(f"invalid trade timestamp: {timestamp!r}")
    return timestamp[:16] + ":00Z"


class SymbolBuffer:
    def __init__(self, max_bars: int = BUFFER_BARS):
        self.bars: deque[Bar] = deque(maxlen=max_bars)

    def add_trade(self, timestamp: str, price: float, size: float) -> None:
        bucket = minute_bucket(timestamp)
        if self.bars and self.bars[-1].timestamp == bucket:
            bar = self.bars[-1]
            bar.high = max(bar.high, price)
            bar.low = min(bar.low, price)
            bar.close = price
            bar.volume += size
        else:
            self.bars.append(Bar(bucket, price, price, price, price, size))

    def indicators(self) -> dict[str, Any]:
        close = [bar.close for bar in self.bars]
        high = [bar.high for bar in self.bars]
        low = [bar.low for bar in self.bars]
        volume = [bar.volume for bar in self.bars]
        macd = ta.MACD(close)
        aroon_up, aroon_down = ta.AROON(high, low)
        stochastic = ta.STOCHASTIC(high, low, close)
        return {
            "obv": ta.OBV(close, volume)[-1],
            "adx": ta.ADX(high, low, close)[-1],
            "adl": ta.ADL(high, low, close, volume)[-1],
            "aroon_up": aroon_up[-1],
            "aroon_down": aroon_down[-1],
            "macd": macd.macd[-1],
            "macd_signal": macd.signal[-1],
            "macd_histogram": macd.histogram[-1],
            "rsi": ta.RSI(close)[-1],
            "stochastic_k": stochastic.k[-1],
            "stochastic_d": stochastic.d[-1],
        }


class LiveAnalyzer:
    def __init__(self, max_bars: int = BUFFER_BARS):
        self.max_bars = max_bars
        self.buffers: dict[tuple[str, str, str, str], SymbolBuffer] = {}
        self.last_rowid = 0

    def process(self, db: sqlite3.Connection, row: sqlite3.Row) -> None:
        key = (row["asset_class"], row["symbol"], row["feed"], row["location"])
        buffer = self.buffers.setdefault(key, SymbolBuffer(self.max_bars))
        buffer.add_trade(row["timestamp"], float(row["price"]), float(row["size"]))
        values = buffer.indicators()
        bar = buffer.bars[-1]
        db.execute("""
            INSERT INTO technical_analysis_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_class, symbol, feed, location) DO UPDATE SET
              source_trade_id=excluded.source_trade_id,
              trade_timestamp=excluded.trade_timestamp,
              bar_timestamp=excluded.bar_timestamp,
              bars_buffered=excluded.bars_buffered,
              indicators_json=excluded.indicators_json,
              updated_at=excluded.updated_at
        """, (*key, row["trade_id"], row["timestamp"], bar.timestamp, len(buffer.bars),
              json.dumps(values, sort_keys=True, separators=(",", ":")), now()))
        self.last_rowid = max(self.last_rowid, row["rowid"])

    def next_rows(self, db: sqlite3.Connection, *, warm: bool = False) -> list[sqlite3.Row]:
        db.row_factory = sqlite3.Row
        if warm and self.last_rowid == 0:
            return db.execute("""
                SELECT * FROM (
                  SELECT trade.rowid AS rowid, trade.*
                  FROM live_trades AS trade
                  INNER JOIN live_orderbooks AS book
                    USING(asset_class, symbol, feed, location)
                  ORDER BY trade.rowid DESC LIMIT ?
                ) ORDER BY rowid
            """, (WARM_TRADES,)).fetchall()
        return db.execute("""
            SELECT trade.rowid AS rowid, trade.*
            FROM live_trades AS trade
            INNER JOIN live_orderbooks AS book
              USING(asset_class, symbol, feed, location)
            WHERE trade.rowid > ? ORDER BY trade.rowid LIMIT 1000
        """, (self.last_rowid,)).fetchall()

    def cycle(self, db: sqlite3.Connection, *, warm: bool = False) -> int:
        rows = self.next_rows(db, warm=warm)
        for row in rows:
            self.process(db, row)
        if rows:
            db.commit()
        return len(rows)


async def run(database: Path, poll_seconds: float = POLL_SECONDS) -> None:
    analyzer = LiveAnalyzer()
    warm = True
    while True:
        db = connect(database)
        try:
            if warm:
                analyzer.cycle(db, warm=True)
                warm = False
            while True:
                analyzer.cycle(db)
                await asyncio.sleep(poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"live analysis failed: {error}; retrying in 1s", file=sys.stderr, flush=True)
            await asyncio.sleep(1)
        finally:
            db.close()


def report(database: Path, symbol: str | None = None) -> None:
    db = connect(database)
    db.row_factory = sqlite3.Row
    where = "WHERE symbol=?" if symbol else ""
    params = (symbol.upper(),) if symbol else ()
    rows = db.execute(f"""
        SELECT asset_class, symbol, feed, location, trade_timestamp,
               bars_buffered, indicators_json
        FROM technical_analysis_snapshots {where}
        ORDER BY symbol, asset_class, feed, location
    """, params).fetchall()
    db.close()
    if not rows:
        print("No live technical-analysis snapshots stored")
        return
    for row in rows:
        values = json.loads(row["indicators_json"])
        rendered = "  ".join(
            f"{name.upper()}={value:.4f}" if isinstance(value, (int, float)) else f"{name.upper()}=warming"
            for name, value in values.items()
        )
        print(f"{row['symbol']} [{row['asset_class']} {row['feed'] or row['location']}] "
              f"bars={row['bars_buffered']} trade={row['trade_timestamp']}")
        print(rendered)


def main() -> None:
    parser = argparse.ArgumentParser(description="Show latest per-trade technical analysis")
    parser.add_argument("symbol", nargs="?")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    report(args.db, args.symbol)


if __name__ == "__main__":
    main()
