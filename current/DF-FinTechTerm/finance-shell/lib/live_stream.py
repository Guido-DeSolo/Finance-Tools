"""One Alpaca daemon streaming every symbol in the SQLite watchlist."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from alpaca_store import DEFAULT_DB, connect, now
import live_analysis

NEWS_ENDPOINT = "wss://stream.data.alpaca.markets/v1beta1/news"
NEWSDATA_ENDPOINT = "https://newsdata.io/api/1/latest"


def _websockets():
    try:
        import websockets
    except ImportError as error:
        raise RuntimeError(
            "live streaming requires websockets; install the DF-FinTechTerm requirements first"
        ) from error
    return websockets


def load_watchlist(db: sqlite3.Connection) -> list[sqlite3.Row]:
    db.row_factory = sqlite3.Row
    return db.execute("""
        SELECT asset_class, symbol, feed, location
        FROM stream_watchlist ORDER BY asset_class, feed, location, symbol
    """).fetchall()


def endpoint(asset_class: str, feed: str, location: str) -> str:
    if asset_class == "stock":
        return f"wss://stream.data.alpaca.markets/v2/{feed}"
    return f"wss://stream.data.alpaca.markets/v1beta3/crypto/{location}"


def store_trade(db: sqlite3.Connection, row: sqlite3.Row | dict, trade: dict) -> None:
    if trade.get("T") != "t" or trade.get("S") != row["symbol"]:
        return
    db.execute("""
        INSERT INTO live_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_class, symbol, trade_id, timestamp, feed, location) DO NOTHING
    """, (
        row["asset_class"], trade["S"], str(trade.get("i", "")), trade["t"],
        trade["p"], trade["s"], trade.get("x"), trade.get("z"),
        json.dumps(trade.get("c", []), sort_keys=True), trade.get("tks"),
        row["feed"], row["location"], now(), json.dumps(trade, sort_keys=True),
    ))


def store_event(db: sqlite3.Connection, row: sqlite3.Row | dict, message: dict) -> None:
    """Append one raw market event, ignoring an exact replay after reconnect."""
    raw = json.dumps(message, sort_keys=True, separators=(",", ":"))
    identity = "\0".join((
        row["asset_class"], row["symbol"], row["feed"], row["location"], raw,
    ))
    event_id = hashlib.sha256(identity.encode()).hexdigest()
    db.execute("""
        INSERT INTO live_market_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO NOTHING
    """, (event_id, row["asset_class"], row["symbol"], message["T"],
          row["feed"], row["location"], message["t"], now(), raw))


def store_news(db: sqlite3.Connection, message: dict) -> None:
    if message.get("T") != "n" or message.get("id") is None:
        return
    article_id = str(message["id"])
    raw = json.dumps(message, sort_keys=True, separators=(",", ":"))
    db.execute("""
        INSERT INTO news_articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(article_id) DO UPDATE SET
          headline=excluded.headline, summary=excluded.summary,
          author=excluded.author, created_at=excluded.created_at,
          updated_at=excluded.updated_at, content=excluded.content,
          url=excluded.url, source=excluded.source,
          received_at=excluded.received_at, raw_json=excluded.raw_json
    """, (article_id, message.get("headline") or "", message.get("summary"),
          message.get("author"), message.get("created_at") or now(),
          message.get("updated_at") or message.get("created_at") or now(),
          message.get("content"), message.get("url"), message.get("source"), now(), raw))
    db.execute("DELETE FROM news_article_symbols WHERE article_id=?", (article_id,))
    db.executemany("""
        INSERT OR IGNORE INTO news_article_symbols(article_id, symbol) VALUES (?, ?)
    """, ((article_id, str(symbol).upper()) for symbol in message.get("symbols", []) if symbol))


def fetch_newsdata(api_key: str) -> list[dict]:
    query = urlencode({
        "apikey": api_key,
        "country": "us",
        "language": "en",
        "category": "business,technology,science,environment,domestic,breaking",
    })
    request = Request(f"{NEWSDATA_ENDPOINT}?{query}", headers={"User-Agent": "df-fintechterm/1"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("status") == "error":
        raise RuntimeError(f"NewsData error: {payload.get('results') or payload.get('message')}")
    return payload.get("results") or []


def store_newsdata(db: sqlite3.Connection, article: dict) -> None:
    headline = article.get("title") or ""
    if not headline:
        return
    raw = json.dumps(article, sort_keys=True)
    identity = article.get("article_id") or article.get("link") or headline
    article_id = "newsdata:" + hashlib.sha256(str(identity).encode()).hexdigest()
    published = article.get("pubDate") or now()
    creators = article.get("creator")
    author = ", ".join(creators) if isinstance(creators, list) else creators
    db.execute("""
        INSERT INTO news_articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(article_id) DO UPDATE SET
          headline=excluded.headline, summary=excluded.summary,
          author=excluded.author, updated_at=excluded.updated_at,
          content=excluded.content, url=excluded.url, source=excluded.source,
          received_at=excluded.received_at, raw_json=excluded.raw_json
    """, (article_id, headline, article.get("description"), author,
          published, published, article.get("content"),
          article.get("link"), article.get("source_name") or article.get("source_id"),
          now(), raw))


def _levels(values: Iterable[dict]) -> dict[float, float]:
    return {float(level["p"]): float(level["s"]) for level in values}


def apply_crypto_book(book: dict[str, dict[float, float]], message: dict) -> None:
    if message.get("r"):
        book["bids"].clear()
        book["asks"].clear()
    for source, target in (("b", "bids"), ("a", "asks")):
        for price, size in _levels(message.get(source, [])).items():
            if size == 0:
                book[target].pop(price, None)
            else:
                book[target][price] = size


def store_book(db: sqlite3.Connection, row: sqlite3.Row | dict, message: dict,
               book: dict[str, dict[float, float]] | None = None) -> None:
    if row["asset_class"] == "stock":
        bids = [{"p": message["bp"], "s": message["bs"], "x": message.get("bx")}]
        asks = [{"p": message["ap"], "s": message["as"], "x": message.get("ax")}]
        full_depth = 0
    else:
        if book is None:
            raise ValueError("crypto order-book state is required")
        apply_crypto_book(book, message)
        bids = [{"p": price, "s": size} for price, size in sorted(book["bids"].items(), reverse=True)]
        asks = [{"p": price, "s": size} for price, size in sorted(book["asks"].items())]
        full_depth = 1
    db.execute("""
        INSERT INTO live_orderbooks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_class, symbol, feed, location) DO UPDATE SET
          timestamp=excluded.timestamp, bids_json=excluded.bids_json,
          asks_json=excluded.asks_json, is_full_depth=excluded.is_full_depth,
          received_at=excluded.received_at, raw_json=excluded.raw_json
    """, (row["asset_class"], row["symbol"], row["feed"], row["location"],
          message["t"], json.dumps(bids), json.dumps(asks), full_depth, now(),
          json.dumps(message, sort_keys=True)))


async def stream_group(rows: list[sqlite3.Row], database: Path, key: str, secret: str) -> None:
    websockets = _websockets()
    first = rows[0]
    symbols = [row["symbol"] for row in rows]
    by_symbol = {row["symbol"]: row for row in rows}
    books = {symbol: {"bids": {}, "asks": {}} for symbol in symbols}
    delay = 1
    while True:
        db = connect(database)
        try:
            url = endpoint(first["asset_class"], first["feed"], first["location"])
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as socket:
                await socket.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
                authenticated = False
                async for encoded in socket:
                    for message in json.loads(encoded):
                        kind = message.get("T")
                        if kind == "success" and message.get("msg") == "authenticated":
                            authenticated = True
                            subscription = {"action": "subscribe", "trades": symbols}
                            subscription["quotes" if first["asset_class"] == "stock" else "orderbooks"] = symbols
                            await socket.send(json.dumps(subscription))
                        elif kind == "error":
                            raise RuntimeError(f"Alpaca stream error {message.get('code')}: {message.get('msg')}")
                        elif authenticated and message.get("S") in by_symbol:
                            row = by_symbol[message["S"]]
                            if kind in ("t", "q", "o"):
                                store_event(db, row, message)
                            if kind == "t":
                                store_trade(db, row, message)
                            elif kind == "q" and row["asset_class"] == "stock":
                                store_book(db, row, message)
                            elif kind == "o" and row["asset_class"] == "crypto":
                                store_book(db, row, message, books[row["symbol"]])
                    db.commit()
                delay = 1
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"{first['asset_class']} stream disconnected: {error}; retrying in {delay}s",
                  file=sys.stderr, flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
        finally:
            db.close()


def news_symbol(symbol: str) -> str:
    return symbol.upper().replace("/", "")


async def stream_news(symbols: list[str], database: Path, key: str, secret: str) -> None:
    websockets = _websockets()
    delay = 1
    while True:
        db = connect(database)
        try:
            async with websockets.connect(NEWS_ENDPOINT, ping_interval=20, ping_timeout=20) as socket:
                await socket.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
                authenticated = False
                async for encoded in socket:
                    for message in json.loads(encoded):
                        kind = message.get("T")
                        if kind == "success" and message.get("msg") == "authenticated":
                            authenticated = True
                            await socket.send(json.dumps({"action": "subscribe", "news": symbols}))
                        elif kind == "error":
                            raise RuntimeError(
                                f"Alpaca news error {message.get('code')}: {message.get('msg')}"
                            )
                        elif authenticated and kind == "n":
                            store_news(db, message)
                    db.commit()
                delay = 1
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"news stream disconnected: {error}; retrying in {delay}s",
                  file=sys.stderr, flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
        finally:
            db.close()


async def poll_newsdata(database: Path, api_key: str, interval: int = 300) -> None:
    while True:
        try:
            articles = await asyncio.to_thread(fetch_newsdata, api_key)
            db = connect(database)
            try:
                for article in articles:
                    store_newsdata(db, article)
                db.commit()
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"NewsData poll failed: {error}", file=sys.stderr, flush=True)
        await asyncio.sleep(interval)


async def run(database: Path) -> None:
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Alpaca credentials are not configured")
    db = connect(database)
    rows = load_watchlist(db)
    db.close()
    if not rows:
        raise RuntimeError("watchlist is empty; add a symbol before starting")
    groups: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault((row["asset_class"], row["feed"], row["location"]), []).append(row)
    news_symbols = sorted({news_symbol(row["symbol"]) for row in rows})
    tasks = [stream_group(group, database, key, secret) for group in groups.values()]
    tasks.append(stream_news(news_symbols, database, key, secret))
    newsdata_key = os.environ.get("NEWSDATA_API_KEY")
    if newsdata_key:
        tasks.append(poll_newsdata(database, newsdata_key))
    tasks.append(live_analysis.run(database))
    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    asyncio.run(run(args.db))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"fsh alpaca stream: {error}", file=sys.stderr)
        raise SystemExit(1) from error
