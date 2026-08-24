#!/usr/bin/env python3
"""One-time builder for the fixed-date QUANT benchmark corpus."""

import argparse
import json
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from candidate_packet import price_summary
from market_summary import reduce_market
from settings import load_settings


SYMBOLS = ["PFE", "OTLK", "CAMP", "HEPA", "ATTO"]
API_URL = "https://data.alpaca.markets/v2/stocks/bars"


def fetch_bars(settings):
    params = {
        "symbols": ",".join(SYMBOLS),
        "timeframe": "1Day",
        "start": "2026-03-01T00:00:00Z",
        "end": "2026-08-15T00:00:00Z",
        "limit": 10000,
        "adjustment": "all",
        "feed": "iex",
        "sort": "asc",
    }
    headers = {
        "APCA-API-KEY-ID": settings["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": settings["ALPACA_SECRET_KEY"],
    }
    collected = {symbol: [] for symbol in SYMBOLS}
    while True:
        response = requests.get(API_URL, params=params, headers=headers, timeout=60)
        response.raise_for_status()
        page = response.json()
        for symbol, bars in page.get("bars", {}).items():
            collected[symbol].extend(bars)
        token = page.get("next_page_token")
        if not token:
            return collected
        params["page_token"] = token


def normalize(rows):
    return [
        {
            "date": row["t"][:10],
            "open": float(row["o"]),
            "high": float(row["h"]),
            "low": float(row["l"]),
            "close": float(row["c"]),
            "volume": int(row["v"]),
        }
        for row in rows[-90:]
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    settings = load_settings(("ALPACA_API_KEY", "ALPACA_SECRET_KEY"))
    bars = fetch_bars(settings)
    summaries = {}
    for symbol in SYMBOLS:
        market = price_summary(normalize(bars[symbol]))
        summaries[symbol] = reduce_market({"symbol": symbol, "market": market})
    corpus = {
        "version": 1,
        "as_of": "2026-08-15T00:00:00Z",
        "source": "alpaca_iex_adjusted_all",
        "symbols": SYMBOLS,
        "summaries": summaries,
    }
    args.output.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
