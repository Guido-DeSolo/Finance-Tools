#!/usr/bin/env python3

import time
from datetime import date

import psycopg
import requests
from settings import load_settings


ENV = load_settings(("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "DATABASE_URL"))

DATABASE_URL = ENV["DATABASE_URL"]

HEADERS = {
    "APCA-API-KEY-ID": ENV["ALPACA_API_KEY"],
    "APCA-API-SECRET-KEY": ENV["ALPACA_SECRET_KEY"],
}

API_URL = "https://data.alpaca.markets/v2/stocks/bars"

START = "2022-01-01"
END = date.today().isoformat()

BATCH_SIZE = 100
PAGE_LIMIT = 10000

REQUEST_DELAY = 0.5
MAX_BACKOFF = 60


def get_symbols():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ticker
                FROM insider_trades
                WHERE ticker IS NOT NULL
                  AND ticker <> ''
                ORDER BY ticker
                """
            )

            return [
                row[0]
                for row in cur.fetchall()
            ]


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_batch(symbols):
    params = {
        "symbols": ",".join(symbols),
        "timeframe": "1Day",
        "start": START,
        "end": END,
        "limit": PAGE_LIMIT,
        "adjustment": "all",
        "feed": "iex",
        "sort": "asc",
    }

    all_bars = {}

    backoff = 1

    while True:
        r = requests.get(
            API_URL,
            headers=HEADERS,
            params=params,
            timeout=60,
        )

        if r.status_code == 429:
            print(
                f"Rate limited. "
                f"Sleeping {backoff}s..."
            )

            time.sleep(backoff)

            backoff = min(
                backoff * 2,
                MAX_BACKOFF,
            )

            continue

        r.raise_for_status()

        backoff = 1

        data = r.json()

        bars = data.get("bars", {})

        for symbol, rows in bars.items():
            all_bars.setdefault(
                symbol,
                []
            ).extend(rows)

        count = sum(
            len(rows)
            for rows in bars.values()
        )

        print(
            f"  received {count:,} bars"
        )

        token = data.get(
            "next_page_token"
        )

        if not token:
            break

        params["page_token"] = token

        time.sleep(REQUEST_DELAY)

    return all_bars


def store_bars(all_bars):
    inserted = 0

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:

            for symbol, bars in all_bars.items():

                for bar in bars:

                    timestamp = bar["t"]

                    cur.execute(
                        """
                        INSERT INTO daily_bars (
                            symbol,
                            date,
                            open,
                            high,
                            low,
                            close,
                            volume,
                            trade_count,
                            vwap
                        )
                        VALUES (
                            %s,
                            %s::timestamptz::date,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        ON CONFLICT (
                            symbol,
                            date
                        )
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
                            timestamp,
                            bar["o"],
                            bar["h"],
                            bar["l"],
                            bar["c"],
                            bar["v"],
                            bar.get("n"),
                            bar.get("vw"),
                        ),
                    )

                    inserted += 1

        conn.commit()

    return inserted


def main():
    symbols = get_symbols()

    print(
        f"Found {len(symbols):,} "
        f"symbols in insider_trades."
    )

    total = 0

    batches = list(
        chunks(
            symbols,
            BATCH_SIZE,
        )
    )

    for number, batch in enumerate(
        batches,
        start=1,
    ):

        print()
        print(
            f"Batch {number}/"
            f"{len(batches)} "
            f"({len(batch)} symbols)"
        )

        print(
            f"{batch[0]} → {batch[-1]}"
        )

        try:
            bars = fetch_batch(batch)

            stored = store_bars(bars)

            total += stored

            print(
                f"Stored {stored:,} bars."
            )

        except Exception as e:
            print(
                f"ERROR in batch "
                f"{number}: {e}"
            )

        time.sleep(REQUEST_DELAY)

    print()
    print(
        f"Done. Processed "
        f"{total:,} daily bars."
    )


if __name__ == "__main__":
    main()
