#!/usr/bin/env python3

import time
from datetime import datetime, timedelta, timezone

import psycopg
import requests
from settings import load_settings


ENV = load_settings(("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "DATABASE_URL"))

API_KEY = ENV["ALPACA_API_KEY"]
API_SECRET = ENV["ALPACA_SECRET_KEY"]
DATABASE_URL = ENV["DATABASE_URL"]

BASE_URL = "https://data.alpaca.markets/v2/stocks"

SYMBOLS = [
    "SPY",
]

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime.now(timezone.utc)

TIMEFRAME = "1Min"
FEED = "iex"
LIMIT = 10000


HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
}


def fetch_bars(symbol, start, end):
    """Download every page of bars for a symbol/time range."""

    url = f"{BASE_URL}/{symbol}/bars"

    params = {
        "timeframe": TIMEFRAME,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "limit": LIMIT,
        "feed": FEED,
        "adjustment": "all",
        "sort": "asc",
    }

    bars = []

    while True:
        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=30,
        )

        if response.status_code == 429:
            print("Rate limited. Waiting 10 seconds...")
            time.sleep(10)
            continue

        response.raise_for_status()

        data = response.json()

        page = data.get("bars", [])
        bars.extend(page)

        print(
            f"  received {len(page):,} bars "
            f"(total {len(bars):,})"
        )

        token = data.get("next_page_token")

        if not token:
            break

        params["page_token"] = token

    return bars


def store_bars(symbol, bars):
    """Insert bars into PostgreSQL."""

    if not bars:
        return 0

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:

            for bar in bars:
                cur.execute(
                    """
                    INSERT INTO bars (
                        symbol,
                        timestamp,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        trade_count,
                        vwap
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (symbol, timestamp)
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        trade_count = EXCLUDED.trade_count,
                        vwap = EXCLUDED.vwap
                    """,
                    (
                        symbol,
                        bar["t"],
                        bar["o"],
                        bar["h"],
                        bar["l"],
                        bar["c"],
                        bar["v"],
                        bar.get("n"),
                        bar.get("vw"),
                    ),
                )

        conn.commit()

    return len(bars)


def main():
    print(
        f"Downloading {', '.join(SYMBOLS)} "
        f"from {START.date()} to {END.date()}"
    )

    for symbol in SYMBOLS:

        print(f"\n=== {symbol} ===")

        current = START

        while current < END:

            # Keep individual requests reasonably sized.
            chunk_end = min(
                current + timedelta(days=30),
                END,
            )

            print(
                f"\n{current.isoformat()} "
                f"→ {chunk_end.isoformat()}"
            )

            bars = fetch_bars(
                symbol,
                current,
                chunk_end,
            )

            if bars:
                stored = store_bars(symbol, bars)

                print(
                    f"Stored {stored:,} bars."
                )
            else:
                print("No bars returned.")

            current = chunk_end

            # Avoid hammering the API.
            time.sleep(0.25)

    print("\nDone.")


if __name__ == "__main__":
    main()
