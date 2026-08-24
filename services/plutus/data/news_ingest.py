#!/usr/bin/env python3

import time

import psycopg
import requests
from settings import load_settings


ENV = load_settings(("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "DATABASE_URL"))

API_KEY = ENV["ALPACA_API_KEY"]
API_SECRET = ENV["ALPACA_SECRET_KEY"]
DATABASE_URL = ENV["DATABASE_URL"]

API_URL = "https://data.alpaca.markets/v1beta1/news"

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
}


def fetch_news(symbols, start=None, end=None):
    params = {
        "symbols": ",".join(symbols),
        "limit": 50,
        "sort": "asc",
    }

    if start:
        params["start"] = start

    if end:
        params["end"] = end

    articles = []

    while True:
        response = requests.get(
            API_URL,
            headers=HEADERS,
            params=params,
            timeout=30,
        )

        if response.status_code == 429:
            print("Rate limited. Waiting...")
            time.sleep(10)
            continue

        response.raise_for_status()

        data = response.json()

        page = data.get("news", [])
        articles.extend(page)

        print(
            f"Received {len(page)} articles "
            f"(total {len(articles)})"
        )

        token = data.get("next_page_token")

        if not token:
            break

        params["page_token"] = token

    return articles


def store_news(articles):

    if not articles:
        return 0

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:

            for article in articles:

                cur.execute(
                    """
                    INSERT INTO news (
                        id,
                        created_at,
                        updated_at,
                        headline,
                        summary,
                        author,
                        source,
                        url,
                        symbols,
                        content
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (id)
                    DO UPDATE SET
                        updated_at = EXCLUDED.updated_at,
                        headline = EXCLUDED.headline,
                        summary = EXCLUDED.summary,
                        author = EXCLUDED.author,
                        source = EXCLUDED.source,
                        url = EXCLUDED.url,
                        symbols = EXCLUDED.symbols,
                        content = EXCLUDED.content
                    """,
                    (
                        article["id"],
                        article["created_at"],
                        article.get("updated_at"),
                        article["headline"],
                        article.get("summary"),
                        article.get("author"),
                        article.get("source"),
                        article.get("url"),
                        article.get("symbols", []),
                        article.get("content"),
                    ),
                )

        conn.commit()

    return len(articles)


def main():

    symbols = [
        "SPY",
    ]

    print("Downloading news...")

    articles = fetch_news(symbols)

    print(f"Fetched {len(articles):,} articles.")

    stored = store_news(articles)

    print(f"Stored {stored:,} articles.")


if __name__ == "__main__":
    main()
