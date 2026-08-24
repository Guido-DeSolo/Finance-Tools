#!/usr/bin/env python3
"""Download Alpaca historical stock bars into an idempotent SQLite database."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API_URL = "https://data.alpaca.markets/v2/stocks/bars"
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    default_end = utc_now() - dt.timedelta(minutes=20)
    parser = argparse.ArgumentParser(
        description="Fetch highly granular Alpaca stock bars and upsert them into SQLite.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("symbols", nargs="+", help="Symbols; commas and spaces are accepted")
    parser.add_argument("--start", default="2016-01-01", help="Inclusive RFC-3339 timestamp or date")
    parser.add_argument("--end", default=iso_utc(default_end), help="Inclusive RFC-3339 timestamp or date")
    parser.add_argument("--timeframe", default="1Min", help="Alpaca bar timeframe")
    parser.add_argument("--feed", default="iex", choices=("iex", "sip", "otc", "boats"))
    parser.add_argument("--adjustment", default="raw", help="raw, split, dividend, spin-off, all, or a comma list")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--asof", help="YYYY-MM-DD symbol-mapping date, or '-' to disable")
    parser.add_argument("--db", default=os.path.expanduser("~/market_data.sqlite3"))
    parser.add_argument("--batch-size", type=int, default=50, help="Symbols per API request")
    parser.add_argument("--page-limit", type=int, default=10_000, choices=range(1, 10_001), metavar="1..10000")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=8)
    return parser.parse_args()


def normalize_symbols(values: list[str]) -> list[str]:
    symbols = sorted({part.strip().upper() for value in values for part in value.split(",") if part.strip()})
    invalid = [symbol for symbol in symbols if not SYMBOL_RE.fullmatch(symbol)]
    if invalid:
        raise ValueError("Invalid symbol(s): " + ", ".join(invalid))
    return symbols


def connect(path: str) -> sqlite3.Connection:
    path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS bars (
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            feed TEXT NOT NULL,
            adjustment TEXT NOT NULL,
            currency TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            trade_count INTEGER,
            vwap REAL,
            ingested_at TEXT NOT NULL,
            PRIMARY KEY (symbol, timestamp, timeframe, feed, adjustment, currency)
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS bars_timestamp_idx ON bars(timestamp);
        CREATE INDEX IF NOT EXISTS bars_symbol_time_idx ON bars(symbol, timestamp);

        CREATE TABLE IF NOT EXISTS ingestion_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            symbols TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            feed TEXT NOT NULL,
            adjustment TEXT NOT NULL,
            currency TEXT NOT NULL,
            rows_received INTEGER NOT NULL DEFAULT 0,
            pages_received INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT
        );
        """
    )
    return db


def get_json(url: str, headers: dict[str, str], timeout: float, max_retries: int) -> dict:
    for attempt in range(max_retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == max_retries:
                raise RuntimeError(f"Alpaca HTTP {exc.code}: {body}") from exc
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60.0, 2**attempt)
            print(f"HTTP {exc.code}; retrying in {delay:g}s", file=sys.stderr)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == max_retries:
                raise RuntimeError(f"Network failure after {max_retries + 1} attempts: {exc}") from exc
            time.sleep(min(60.0, 2**attempt))
    raise AssertionError("unreachable")


def chunks(items: list[str], size: int):
    for offset in range(0, len(items), size):
        yield items[offset : offset + size]


def main() -> int:
    args = parse_args()
    try:
        symbols = normalize_symbols(args.symbols)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not symbols or args.batch_size < 1:
        print("At least one symbol and a positive --batch-size are required", file=sys.stderr)
        return 2

    key_id = os.environ.get("APCA_API_KEY_ID")
    secret_key = os.environ.get("APCA_API_SECRET_KEY")
    if not key_id or not secret_key:
        print("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in your environment.", file=sys.stderr)
        return 2

    headers = {
        "APCA-API-KEY-ID": key_id,
        "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
        "User-Agent": "personal-alpaca-sqlite-ingester/1.0",
    }
    run_id = str(uuid.uuid4())
    started = iso_utc(utc_now())
    db = connect(args.db)
    db.execute(
        """INSERT INTO ingestion_runs
        (run_id, started_at, symbols, start_time, end_time, timeframe, feed,
         adjustment, currency, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')""",
        (run_id, started, ",".join(symbols), args.start, args.end, args.timeframe,
         args.feed, args.adjustment, args.currency.upper()),
    )
    db.commit()
    total_rows = total_pages = 0

    try:
        for symbol_batch in chunks(symbols, args.batch_size):
            page_token = None
            while True:
                params = {
                    "symbols": ",".join(symbol_batch),
                    "timeframe": args.timeframe,
                    "start": args.start,
                    "end": args.end,
                    "limit": str(args.page_limit),
                    "adjustment": args.adjustment,
                    "feed": args.feed,
                    "currency": args.currency.upper(),
                    "sort": "asc",
                }
                if args.asof:
                    params["asof"] = args.asof
                if page_token:
                    params["page_token"] = page_token
                payload = get_json(API_URL + "?" + urllib.parse.urlencode(params), headers, args.timeout, args.max_retries)
                ingested_at = iso_utc(utc_now())
                rows = []
                for symbol, bars in (payload.get("bars") or {}).items():
                    for bar in bars:
                        rows.append((
                            symbol, bar["t"], args.timeframe, args.feed, args.adjustment,
                            args.currency.upper(), bar["o"], bar["h"], bar["l"], bar["c"],
                            bar["v"], bar.get("n"), bar.get("vw"), ingested_at,
                        ))
                db.executemany(
                    """INSERT INTO bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, timestamp, timeframe, feed, adjustment, currency)
                    DO UPDATE SET open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume,
                    trade_count=excluded.trade_count, vwap=excluded.vwap,
                    ingested_at=excluded.ingested_at""",
                    rows,
                )
                total_rows += len(rows)
                total_pages += 1
                db.execute(
                    "UPDATE ingestion_runs SET rows_received=?, pages_received=? WHERE run_id=?",
                    (total_rows, total_pages, run_id),
                )
                db.commit()
                print(f"page {total_pages}: {len(rows):,} bars; total {total_rows:,}", file=sys.stderr)
                page_token = payload.get("next_page_token")
                if not page_token:
                    break
        db.execute(
            "UPDATE ingestion_runs SET finished_at=?, status='complete' WHERE run_id=?",
            (iso_utc(utc_now()), run_id),
        )
        db.commit()
    except Exception as exc:
        db.execute(
            "UPDATE ingestion_runs SET finished_at=?, status='failed', error=? WHERE run_id=?",
            (iso_utc(utc_now()), str(exc), run_id),
        )
        db.commit()
        raise
    finally:
        db.close()

    print(f"Stored {total_rows:,} bars in {os.path.abspath(os.path.expanduser(args.db))}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
