"""Alpaca asset catalog and historical bars persisted in SQLite."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DEFAULT_DB = Path(
    os.environ.get(
        "ALPACA_DATA_DB",
        Path.home() / ".local/share/df-fintechterm/market-data/alpaca.sqlite3",
    )
).expanduser()
DATA_URL = "https://data.alpaca.markets"
TRADING_URL = "https://api.alpaca.markets"
TIMEFRAME = re.compile(
    r"^(?:([1-9]|[1-5][0-9])(?:Min|T)|([1-9]|1[0-9]|2[0-3])(?:Hour|H)|"
    r"1(?:Day|D)|1(?:Week|W)|(?:1|2|3|4|6|12)(?:Month|M))$"
)


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def credentials() -> dict[str, str]:
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("set APCA_API_KEY_ID and APCA_API_SECRET_KEY first")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT,
            asset_class TEXT NOT NULL,
            exchange TEXT,
            status TEXT,
            tradable INTEGER NOT NULL,
            fractionable INTEGER NOT NULL,
            marginable INTEGER NOT NULL,
            shortable INTEGER NOT NULL,
            easy_to_borrow INTEGER NOT NULL,
            attributes_json TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(asset_class, symbol)
        );
        CREATE INDEX IF NOT EXISTS assets_symbol ON assets(symbol);
        CREATE TABLE IF NOT EXISTS bars (
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            trade_count INTEGER,
            vwap REAL,
            feed TEXT NOT NULL DEFAULT '',
            adjustment TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY(asset_class, symbol, timeframe, timestamp, feed, adjustment)
        );
        CREATE INDEX IF NOT EXISTS bars_lookup
            ON bars(asset_class, symbol, timeframe, timestamp);
        CREATE TABLE IF NOT EXISTS fetch_runs (
            id INTEGER PRIMARY KEY,
            operation TEXT NOT NULL,
            asset_class TEXT,
            symbol TEXT,
            timeframe TEXT,
            requested_start TEXT,
            requested_end TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            pages INTEGER NOT NULL DEFAULT 0,
            rows_saved INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS stream_subscriptions (
            service_id TEXT PRIMARY KEY,
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            feed TEXT NOT NULL,
            location TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(asset_class, symbol, feed, location)
        );
        CREATE TABLE IF NOT EXISTS stream_watchlist (
            asset_class TEXT NOT NULL CHECK(asset_class IN ('stock', 'crypto')),
            symbol TEXT NOT NULL,
            feed TEXT NOT NULL DEFAULT 'iex',
            location TEXT NOT NULL DEFAULT 'us',
            added_at TEXT NOT NULL,
            PRIMARY KEY(asset_class, symbol, feed, location)
        );
        CREATE TABLE IF NOT EXISTS live_trades (
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trade_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            price REAL NOT NULL,
            size REAL NOT NULL,
            exchange TEXT,
            tape TEXT,
            conditions_json TEXT NOT NULL,
            taker_side TEXT,
            feed TEXT NOT NULL,
            location TEXT NOT NULL,
            received_at TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            PRIMARY KEY(asset_class, symbol, trade_id, timestamp, feed, location)
        );
        CREATE INDEX IF NOT EXISTS live_trades_lookup
            ON live_trades(asset_class, symbol, timestamp);
        CREATE TABLE IF NOT EXISTS live_orderbooks (
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            feed TEXT NOT NULL,
            location TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            bids_json TEXT NOT NULL,
            asks_json TEXT NOT NULL,
            is_full_depth INTEGER NOT NULL,
            received_at TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            PRIMARY KEY(asset_class, symbol, feed, location)
        );
        CREATE TABLE IF NOT EXISTS live_market_events (
            event_id TEXT PRIMARY KEY,
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            feed TEXT NOT NULL,
            location TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            received_at TEXT NOT NULL,
            raw_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS live_market_events_lookup
            ON live_market_events(asset_class, symbol, timestamp, event_type);
        CREATE TABLE IF NOT EXISTS technical_analysis_snapshots (
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            feed TEXT NOT NULL,
            location TEXT NOT NULL,
            source_trade_id TEXT NOT NULL,
            trade_timestamp TEXT NOT NULL,
            bar_timestamp TEXT NOT NULL,
            bars_buffered INTEGER NOT NULL,
            indicators_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(asset_class, symbol, feed, location)
        );
        CREATE INDEX IF NOT EXISTS technical_analysis_updated
            ON technical_analysis_snapshots(updated_at DESC);
        CREATE TABLE IF NOT EXISTS symbol_classifications (
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            classification_system TEXT NOT NULL,
            classification_code TEXT,
            industry TEXT,
            sector TEXT,
            company_name TEXT,
            cik TEXT,
            source_url TEXT,
            status TEXT NOT NULL,
            classified_at TEXT NOT NULL,
            PRIMARY KEY(asset_class, symbol, classification_system)
        );
        CREATE INDEX IF NOT EXISTS symbol_classifications_industry
            ON symbol_classifications(sector, industry);
        CREATE TABLE IF NOT EXISTS news_articles (
            article_id TEXT PRIMARY KEY,
            headline TEXT NOT NULL,
            summary TEXT,
            author TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            content TEXT,
            url TEXT,
            source TEXT,
            received_at TEXT NOT NULL,
            raw_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS news_articles_updated ON news_articles(updated_at DESC);
        CREATE TABLE IF NOT EXISTS news_article_symbols (
            article_id TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            PRIMARY KEY(article_id, symbol)
        );
        CREATE INDEX IF NOT EXISTS news_article_symbols_lookup
            ON news_article_symbols(symbol, article_id);
        CREATE TABLE IF NOT EXISTS news_sentiment (
            article_id TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            label TEXT NOT NULL,
            score REAL NOT NULL CHECK(score BETWEEN -1 AND 1),
            confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
            impact_horizon TEXT NOT NULL,
            rationale TEXT NOT NULL,
            analyzed_at TEXT NOT NULL,
            total_duration_ns INTEGER,
            prompt_eval_count INTEGER,
            eval_count INTEGER,
            raw_response_json TEXT NOT NULL,
            PRIMARY KEY(article_id, model, prompt_version)
        );
        CREATE INDEX IF NOT EXISTS news_sentiment_score
            ON news_sentiment(label, score, analyzed_at);
    """)
    return db


class Alpaca:
    def __init__(
        self, key_id: str | None = None, secret_key: str | None = None
    ) -> None:
        if key_id is None and secret_key is None:
            self.headers = credentials()
        elif key_id and secret_key:
            self.headers = {
                "APCA-API-KEY-ID": key_id,
                "APCA-API-SECRET-KEY": secret_key,
            }
        else:
            raise ValueError("provide both Alpaca key_id and secret_key")

    def get(self, base: str, path: str, params: dict[str, object]) -> object:
        query = urlencode({key: value for key, value in params.items() if value is not None})
        request = Request(f"{base}{path}?{query}", headers={**self.headers, "User-Agent": "df-fintechterm/1"})
        for attempt in range(5):
            try:
                with urlopen(request, timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                detail = error.read().decode("utf-8", "replace")[:500]
                if (error.code == 429 or 500 <= error.code <= 599) and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Alpaca HTTP {error.code}: {detail}") from error
            except (URLError, TimeoutError, json.JSONDecodeError) as error:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Alpaca request failed: {error}") from error
        raise AssertionError("unreachable")


def sync_assets(args: argparse.Namespace) -> None:
    db = connect(args.db)
    api = Alpaca()
    stamp = now()
    saved = 0
    for asset_class in ("us_equity", "crypto"):
        result = api.get(TRADING_URL, "/v2/assets", {"asset_class": asset_class, "status": args.status})
        if not isinstance(result, list):
            raise SystemExit("Alpaca assets response was not a list")
        for asset in result:
            db.execute("""
                INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    symbol=excluded.symbol, name=excluded.name,
                    asset_class=excluded.asset_class, exchange=excluded.exchange,
                    status=excluded.status, tradable=excluded.tradable,
                    fractionable=excluded.fractionable, marginable=excluded.marginable,
                    shortable=excluded.shortable, easy_to_borrow=excluded.easy_to_borrow,
                    attributes_json=excluded.attributes_json, raw_json=excluded.raw_json,
                    last_seen_at=excluded.last_seen_at
            """, (
                asset["id"], asset["symbol"], asset.get("name"), asset.get("class", asset_class),
                asset.get("exchange"), asset.get("status"), bool(asset.get("tradable")),
                bool(asset.get("fractionable")), bool(asset.get("marginable")),
                bool(asset.get("shortable")), bool(asset.get("easy_to_borrow")),
                json.dumps(asset.get("attributes", []), sort_keys=True),
                json.dumps(asset, sort_keys=True), stamp, stamp,
            ))
            saved += 1
        db.commit()
        print(f"Saved {len(result):,} {asset_class} assets")
    print(f"Catalog sync complete: {saved:,} assets in {args.db}")


def normalize_timeframe(value: str) -> str:
    if not TIMEFRAME.fullmatch(value):
        raise argparse.ArgumentTypeError("unsupported timeframe; run: df-fintechterm alpaca timeframes")
    return value


def positive_int(value: str, name: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{name} must be a positive integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError(f"{name} must be a positive integer")
    return number


def page_limit(value: str) -> int:
    number = positive_int(value, "limit")
    if number > 10000:
        raise argparse.ArgumentTypeError("limit must be between 1 and 10000")
    return number


def save_bars(db: sqlite3.Connection, args: argparse.Namespace, bars: list[dict]) -> int:
    rows = []
    stamp = now()
    # The existing `feed` column identifies the upstream data source. For
    # stocks that is IEX/SIP/etc.; for crypto it is the Alpaca location.
    source = getattr(args, "feed", None) if args.asset_class == "stock" else getattr(args, "location", None)
    for bar in bars:
        rows.append((args.asset_class, args.symbol, args.timeframe, bar["t"], bar["o"],
                     bar["h"], bar["l"], bar["c"], bar["v"], bar.get("n"),
                     bar.get("vw"), source or "", args.adjustment or "", stamp))
    db.executemany("""
        INSERT INTO bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_class, symbol, timeframe, timestamp, feed, adjustment)
        DO UPDATE SET open=excluded.open, high=excluded.high, low=excluded.low,
          close=excluded.close, volume=excluded.volume, trade_count=excluded.trade_count,
          vwap=excluded.vwap, fetched_at=excluded.fetched_at
    """, rows)
    return len(rows)


def requested_symbols(values: str | list[str]) -> list[str]:
    """Normalize repeated and comma-separated history symbols without reordering them."""
    inputs = [values] if isinstance(values, str) else values
    symbols: list[str] = []
    for value in inputs:
        for part in value.split(","):
            symbol = part.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    if not symbols:
        raise ValueError("at least one symbol is required")
    return symbols


def history_one(args: argparse.Namespace) -> None:
    args.symbol = args.symbol.upper()
    db = connect(args.db)
    api = Alpaca()
    run = db.execute("""
        INSERT INTO fetch_runs(operation, asset_class, symbol, timeframe,
          requested_start, requested_end, started_at, status)
        VALUES('history', ?, ?, ?, ?, ?, ?, 'running')
    """, (args.asset_class, args.symbol, args.timeframe, args.start, args.end, now())).lastrowid
    db.commit()
    token = None
    seen_tokens: set[str] = set()
    pages = rows = 0
    try:
        while True:
            params = {"timeframe": args.timeframe, "start": args.start, "end": args.end,
                      "limit": args.limit, "page_token": token, "sort": "asc"}
            if args.asset_class == "stock":
                path = f"/v2/stocks/{quote(args.symbol, safe='')}/bars"
                params.update({"feed": args.feed, "adjustment": args.adjustment, "asof": args.asof})
                payload = api.get(DATA_URL, path, params)
                if not isinstance(payload, dict) or not isinstance(payload.get("bars", []), list):
                    raise RuntimeError("unexpected Alpaca stock-bars response")
                batch = payload.get("bars", [])
            else:
                path = f"/v1beta3/crypto/{args.location}/bars"
                params["symbols"] = args.symbol
                payload = api.get(DATA_URL, path, params)
                if not isinstance(payload, dict) or not isinstance(payload.get("bars", {}), dict):
                    raise RuntimeError("unexpected Alpaca crypto-bars response")
                batch = payload.get("bars", {}).get(args.symbol, [])
                if not isinstance(batch, list):
                    raise RuntimeError("unexpected Alpaca crypto symbol response")
            count = save_bars(db, args, batch)
            rows += count
            pages += 1
            token = payload.get("next_page_token")
            if token is not None and not isinstance(token, str):
                raise RuntimeError("invalid Alpaca pagination token")
            db.execute("UPDATE fetch_runs SET pages=?, rows_saved=? WHERE id=?", (pages, rows, run))
            db.commit()
            print(f"Page {pages}: saved {count:,} bars ({rows:,} total)")
            capped = bool(token and args.max_pages and pages >= args.max_pages)
            if not token or capped:
                break
            if token in seen_tokens:
                raise RuntimeError("Alpaca repeated a pagination token")
            seen_tokens.add(token)
        final_status = "partial" if capped else "complete"
        db.execute("UPDATE fetch_runs SET finished_at=?, status=? WHERE id=?",
                   (now(), final_status, run))
        db.commit()
        db.close()
        print(f"History sync {final_status}: {rows:,} bars in {args.db}")
    except (Exception, KeyboardInterrupt) as error:
        db.execute("UPDATE fetch_runs SET finished_at=?, status='failed', error=? WHERE id=?",
                   (now(), str(error)[:1000], run))
        db.commit()
        db.close()
        raise


def history(args: argparse.Namespace) -> None:
    symbols = requested_symbols(args.symbol)
    if isinstance(args.symbol, str):
        args.symbol = symbols[0]
    failures: list[tuple[str, str]] = []
    for symbol in symbols:
        item = argparse.Namespace(**vars(args))
        item.symbol = symbol
        try:
            history_one(item)
        except (RuntimeError, ValueError) as error:
            failures.append((symbol, str(error)))
            print(f"History failed for {symbol}: {error}", file=sys.stderr)
    if failures:
        raise RuntimeError(
            f"history failed for {len(failures)} of {len(symbols)} symbols: "
            + ", ".join(symbol for symbol, _ in failures)
        )


def stored_bar_series(db: sqlite3.Connection) -> list[dict[str, str]]:
    rows = db.execute("""
        SELECT asset_class, symbol, timeframe, feed, adjustment, MAX(timestamp)
        FROM bars
        GROUP BY asset_class, symbol, timeframe, feed, adjustment
        ORDER BY asset_class, symbol, timeframe, feed, adjustment
    """).fetchall()
    keys = ("asset_class", "symbol", "timeframe", "feed", "adjustment", "latest")
    return [dict(zip(keys, row)) for row in rows]


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def update_history(args: argparse.Namespace) -> None:
    """Bring every existing bar series forward to Alpaca's delayed availability edge."""
    end = parse_utc(args.end) if args.end else datetime.now(UTC) - timedelta(minutes=15)
    db = connect(args.db)
    series = stored_bar_series(db)
    db.close()
    if args.symbol:
        requested = {symbol.upper() for symbol in args.symbol}
        series = [item for item in series if item["symbol"].upper() in requested]
    if not series:
        print("No historical bar series to update")
        return
    completed = skipped = failed = 0
    end_text = end.isoformat().replace("+00:00", "Z")
    for item in series:
        if parse_utc(item["latest"]) >= end:
            skipped += 1
            continue
        print(f"Updating {item['asset_class']} {item['symbol']} {item['timeframe']} "
              f"from {item['latest']} through {end_text}")
        history_args = argparse.Namespace(
            db=args.db, asset_class=item["asset_class"], symbol=item["symbol"],
            timeframe=item["timeframe"], start=item["latest"], end=end_text,
            feed=(item["feed"] or "iex") if item["asset_class"] == "stock" else "iex",
            location=(item["feed"] or "us") if item["asset_class"] == "crypto" else "us",
            adjustment=item["adjustment"] or "raw", asof=None,
            limit=args.limit, max_pages=args.max_pages,
        )
        try:
            history(history_args)
            completed += 1
        except (RuntimeError, ValueError) as error:
            failed += 1
            print(f"Update failed for {item['symbol']} {item['timeframe']}: {error}",
                  file=sys.stderr)
    print(f"Daily history update: {completed} updated, {skipped} current, {failed} failed")
    if failed:
        raise SystemExit(1)


def status(args: argparse.Namespace) -> None:
    db = connect(args.db)
    for asset_class, count in db.execute("SELECT asset_class, count(*) FROM assets GROUP BY asset_class"):
        print(f"Assets {asset_class}: {count:,}")
    for asset_class, count in db.execute("SELECT asset_class, count(*) FROM bars GROUP BY asset_class"):
        print(f"Bars {asset_class}: {count:,}")
    assets = db.execute("SELECT count(*) FROM assets").fetchone()[0]
    bars = db.execute("SELECT count(*) FROM bars").fetchone()[0]
    runs = db.execute("SELECT count(*) FROM fetch_runs").fetchone()[0]
    trades = db.execute("SELECT count(*) FROM live_trades").fetchone()[0]
    watched = db.execute("SELECT count(*) FROM stream_watchlist").fetchone()[0]
    books = db.execute("SELECT count(*) FROM live_orderbooks").fetchone()[0]
    events = db.execute("SELECT count(*) FROM live_market_events").fetchone()[0]
    news_count = db.execute("SELECT count(*) FROM news_articles").fetchone()[0]
    analyses = db.execute("SELECT count(*) FROM technical_analysis_snapshots").fetchone()[0]
    print(f"Total: {assets:,} assets, {bars:,} bars, {trades:,} live trades, "
          f"{events:,} market events, {news_count:,} news articles, {books:,} current books, "
          f"{watched:,} watched symbols, {analyses:,} analysis snapshots, {runs:,} fetch runs")
    print(f"Database: {args.db}")


def news(args: argparse.Namespace) -> None:
    db = connect(args.db)
    params: list[object] = []
    where = ""
    if args.symbol:
        where = "WHERE link.symbol=?"
        params.append(args.symbol.upper().replace("/", ""))
    params.append(args.limit)
    rows = db.execute(f"""
        SELECT DISTINCT article.updated_at, article.source, article.headline,
          article.summary, article.url, article.article_id
        FROM news_articles AS article
        LEFT JOIN news_article_symbols AS link USING(article_id)
        {where}
        ORDER BY article.updated_at DESC LIMIT ?
    """, params).fetchall()
    db.close()
    if not rows:
        print("No matching news articles stored")
        return
    for updated, source, headline, summary, url, article_id in rows:
        print(f"[{updated}] {source or 'unknown'} #{article_id}")
        print(headline)
        if summary:
            print(summary)
        if url:
            print(url)
        print()


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="df-fintechterm alpaca")
    commands = root.add_subparsers(required=True)
    item = commands.add_parser("sync-assets", help="save stock and crypto asset catalogs")
    item.add_argument("--status", choices=("active", "inactive", "all"), default="all")
    item.add_argument("--db", type=Path, default=DEFAULT_DB)
    item.set_defaults(run=sync_assets)
    item = commands.add_parser("history", help="save paginated historical bars")
    item.add_argument("symbol", nargs="+", help="one or more symbols; commas are accepted")
    item.add_argument("--class", dest="asset_class", choices=("stock", "crypto"), required=True)
    item.add_argument("--timeframe", type=normalize_timeframe, default="1Day")
    item.add_argument("--start", default="1970-01-01", help="RFC-3339 or YYYY-MM-DD")
    item.add_argument("--end", help="RFC-3339 or YYYY-MM-DD; default is Alpaca's latest")
    item.add_argument("--feed", choices=("iex", "sip", "boats", "otc"), default="iex")
    item.add_argument("--adjustment", default="raw")
    item.add_argument("--asof")
    item.add_argument("--location", choices=("us", "us-1", "eu-1"), default="us")
    item.add_argument("--limit", type=page_limit, default=10000)
    item.add_argument("--max-pages", type=lambda value: positive_int(value, "max-pages"),
                      help="optional safety cap; capped runs are recorded as partial")
    item.add_argument("--db", type=Path, default=DEFAULT_DB)
    item.set_defaults(run=history)
    item = commands.add_parser(
        "update-history", help="increment every stored bar series through the 15-minute delay edge"
    )
    item.add_argument("--symbol", action="append", help="optional symbol filter; repeatable")
    item.add_argument("--end", help="test/override availability edge; default is UTC now minus 15m")
    item.add_argument("--limit", type=page_limit, default=10000)
    item.add_argument("--max-pages", type=lambda value: positive_int(value, "max-pages"))
    item.add_argument("--db", type=Path, default=DEFAULT_DB)
    item.set_defaults(run=update_history)
    item = commands.add_parser("status", help="show local row counts")
    item.add_argument("--db", type=Path, default=DEFAULT_DB)
    item.set_defaults(run=status)
    item = commands.add_parser("news", help="show newest stored real-time news")
    item.add_argument("symbol", nargs="?", help="optional stock or crypto symbol")
    item.add_argument("--limit", type=page_limit, default=10)
    item.add_argument("--db", type=Path, default=DEFAULT_DB)
    item.set_defaults(run=news)
    item = commands.add_parser("timeframes", help="show Alpaca-supported bar windows")
    item.set_defaults(run=lambda _: print(
        "1-59Min (or T), 1-23Hour (or H), 1Day/1D, 1Week/1W, "
        "and 1/2/3/4/6/12Month (or M)"
    ))
    return root


if __name__ == "__main__":
    try:
        arguments = build_parser().parse_args()
        arguments.run(arguments)
    except RuntimeError as error:
        print(f"df-fintechterm alpaca: {error}", file=sys.stderr)
        raise SystemExit(1) from error
