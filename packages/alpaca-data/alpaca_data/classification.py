"""Classify stocks in the finance database using authoritative SEC SIC data."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .store import DEFAULT_DB, connect, now

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def sic_sector(value: str | int | None) -> str | None:
    if value in (None, ""):
        return None
    code = int(value)
    ranges = (
        (100, 999, "Agriculture, Forestry and Fishing"),
        (1000, 1499, "Mining"),
        (1500, 1799, "Construction"),
        (2000, 3999, "Manufacturing"),
        (4000, 4999, "Transportation, Communications and Utilities"),
        (5000, 5199, "Wholesale Trade"),
        (5200, 5999, "Retail Trade"),
        (6000, 6799, "Finance, Insurance and Real Estate"),
        (7000, 8999, "Services"),
        (9100, 9729, "Public Administration"),
        (9900, 9999, "Nonclassifiable Establishments"),
    )
    return next((label for low, high, label in ranges if low <= code <= high), "Unclassified")


class SecClient:
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent

    def get(self, url: str) -> object:
        request = Request(url, headers={"User-Agent": self.user_agent})
        for attempt in range(5):
            try:
                with urlopen(request, timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                if (error.code == 429 or 500 <= error.code <= 599) and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"SEC HTTP {error.code} for {url}") from error
            except (URLError, TimeoutError, json.JSONDecodeError) as error:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"SEC request failed for {url}: {error}") from error
        raise AssertionError("unreachable")


def ticker_map(payload: object) -> dict[str, dict]:
    if not isinstance(payload, dict):
        raise RuntimeError("unexpected SEC ticker-map response")
    result: dict[str, dict] = {}
    for item in payload.values():
        if isinstance(item, dict) and item.get("ticker") and item.get("cik_str") is not None:
            result[str(item["ticker"]).upper()] = item
    return result


def database_symbols(db) -> list[str]:
    return [row[0] for row in db.execute("""
        SELECT symbol FROM (
            SELECT asset_class, symbol FROM bars
            UNION SELECT asset_class, symbol FROM live_trades
            UNION SELECT asset_class, symbol FROM live_market_events
            UNION SELECT asset_class, symbol FROM live_orderbooks
        ) WHERE asset_class='stock' GROUP BY symbol ORDER BY symbol COLLATE NOCASE
    """)]


def save(db, symbol: str, *, code: str | None, industry: str | None,
         company: str | None, cik: str | None, source: str | None, status: str) -> None:
    db.execute("""
        INSERT INTO symbol_classifications VALUES
          ('stock', ?, 'SEC SIC', ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_class, symbol, classification_system) DO UPDATE SET
          classification_code=excluded.classification_code,
          industry=excluded.industry, sector=excluded.sector,
          company_name=excluded.company_name, cik=excluded.cik,
          source_url=excluded.source_url, status=excluded.status,
          classified_at=excluded.classified_at
    """, (symbol, code, industry, sic_sector(code), company, cik, source, status, now()))


def classify(args: argparse.Namespace) -> None:
    user_agent = os.environ.get("SEC_USER_AGENT")
    if not user_agent:
        raise SystemExit('set SEC_USER_AGENT to your name and email, e.g. "Jane Doe jane@example.com"')
    db = connect(args.db)
    symbols = sorted({value.upper() for value in args.symbols}) if args.symbols else database_symbols(db)
    if not symbols:
        raise SystemExit("no stock symbols with stored market data")
    client = SecClient(user_agent)
    mapping = ticker_map(client.get(TICKERS_URL))
    classified = unmatched = failed = 0
    for symbol in symbols:
        item = mapping.get(symbol)
        if item is None:
            save(db, symbol, code=None, industry=None, company=None, cik=None,
                 source=TICKERS_URL, status="unmatched")
            db.commit()
            print(f"unmatched {symbol}")
            unmatched += 1
            continue
        cik = str(item["cik_str"]).zfill(10)
        source = SUBMISSIONS_URL.format(cik=cik)
        try:
            payload = client.get(source)
            if not isinstance(payload, dict):
                raise RuntimeError("unexpected SEC submissions response")
            code = str(payload.get("sic") or "") or None
            industry = payload.get("sicDescription") or None
            status = "classified" if code and industry else "unclassified"
            save(db, symbol, code=code, industry=industry,
                 company=payload.get("name") or item.get("title"), cik=cik,
                 source=source, status=status)
            db.commit()
            print(f"{status:<12} {symbol:<10} {code or '-':<4} {industry or '-'}")
            classified += status == "classified"
            unmatched += status != "classified"
        except RuntimeError as error:
            save(db, symbol, code=None, industry=None, company=item.get("title"), cik=cik,
                 source=source, status="error")
            db.commit()
            print(f"error        {symbol:<10} {error}")
            failed += 1
        time.sleep(0.12)
    print(f"Classification finished: {classified} classified, {unmatched} unmatched, {failed} failed")
    if failed:
        raise SystemExit(1)


def report(args: argparse.Namespace) -> None:
    db = connect(args.db)
    rows = db.execute("""
        SELECT symbol, sector, industry, classification_code, status, classified_at
        FROM symbol_classifications ORDER BY symbol
    """).fetchall()
    if not rows:
        print("No symbol classifications stored")
        return
    print(f"{'SYMBOL':<10} {'SIC':<5} {'STATUS':<12} {'SECTOR':<45} INDUSTRY")
    for symbol, sector, industry, code, status, _ in rows:
        print(f"{symbol:<10} {code or '-':<5} {status:<12} {sector or '-':<45} {industry or '-'}")


def main() -> None:
    root = argparse.ArgumentParser(prog="df-fintechterm classify")
    root.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = root.add_subparsers(required=True)
    item = commands.add_parser("refresh", help="classify stored stocks using SEC SIC")
    item.add_argument("symbols", nargs="*", help="optional symbols; default is every stock with data")
    item.set_defaults(run=classify)
    item = commands.add_parser("list", help="show stored classifications")
    item.set_defaults(run=report)
    args = root.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
