#!/usr/bin/env python3

import re
import time
import psycopg
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
from settings import load_settings


ENV = load_settings(("DATABASE_URL",))

DATABASE_URL = ENV["DATABASE_URL"]

URL = "http://openinsider.com/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

def parse_number(value):
    if not value:
        return None

    value = value.strip()

    if value.lower() == "new":
        return None

    value = value.replace(">", "")
    value = value.replace("<", "")

    value = re.sub(r"[$,%+,]", "", value)

    if not value:
        return None

    return float(value)


def parse_integer(value):
    number = parse_number(value)

    if number is None:
        return None

    return int(number)

def fetch_trades(start_date, end_date, page=1):
    params = {
        "fd": -1,
        "fdr": (
            f"{start_date.strftime('%m/%d/%Y')} - "
            f"{end_date.strftime('%m/%d/%Y')}"
        ),

        "td": 0,

        "xp": 1,
        "xs": 1,

        "grp": 0,
        "sortcol": 0,

        "cnt": 1000,
        "page": page,
    }

    while True:
        r = requests.get(
            "http://openinsider.com/screener",
            params=params,
            headers=HEADERS,
            timeout=30,
        )

        if r.status_code == 429:
            print("Rate limited. Sleeping 30 seconds...")
            time.sleep(30)
            continue

        r.raise_for_status()
        break

    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("table", class_="tinytable")

    if table is None:
        return []

    trades = []

    for row in table.select("tbody tr"):
        cells = row.find_all("td")

        if len(cells) < 13:
            continue

        filing_link = cells[1].find("a")

        trades.append({
            "filing_date": cells[1].get_text(" ", strip=True),
            "trade_date": cells[2].get_text(" ", strip=True),
            "ticker": cells[3].get_text(" ", strip=True),
            "company": cells[4].get_text(" ", strip=True),
            "insider": cells[5].get_text(" ", strip=True),
            "title": cells[6].get_text(" ", strip=True),
            "trade_type": cells[7].get_text(" ", strip=True),

            "price": parse_number(
                cells[8].get_text(" ", strip=True)
            ),

            "quantity": parse_integer(
                cells[9].get_text(" ", strip=True)
            ),

            "owned": parse_integer(
                cells[10].get_text(" ", strip=True)
            ),

            "ownership_change": parse_number(
                cells[11].get_text(" ", strip=True)
            ),

            "trade_value": parse_number(
                cells[12].get_text(" ", strip=True)
            ),

            "filing_url": (
                filing_link.get("href")
                if filing_link
                else None
            ),
        })

    return trades

def store_trades(trades):
    inserted = 0

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:

            for trade in trades:
                cur.execute(
                    """
                    INSERT INTO insider_trades (
                        filing_date,
                        trade_date,
                        ticker,
                        company,
                        insider,
                        title,
                        trade_type,
                        price,
                        quantity,
                        owned,
                        ownership_change,
                        trade_value,
                        filing_url
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    ON CONFLICT (
                        filing_url,
                        ticker,
                        insider,
                        trade_date,
                        trade_type,
                        quantity
                    )
                    DO NOTHING
                    """,
                    (
                        trade["filing_date"],
                        trade["trade_date"],
                        trade["ticker"],
                        trade["company"],
                        trade["insider"],
                        trade["title"],
                        trade["trade_type"],
                        trade["price"],
                        trade["quantity"],
                        trade["owned"],
                        trade["ownership_change"],
                        trade["trade_value"],
                        trade["filing_url"],
                    ),
                )

                if cur.rowcount:
                    inserted += 1

        conn.commit()

    return inserted

from datetime import date, timedelta


def month_end(d):
    if d.month == 12:
        next_month = date(d.year + 1, 1, 1)
    else:
        next_month = date(d.year, d.month + 1, 1)

    return next_month - timedelta(days=1)


def main():

    overall_start = date(2022, 8, 15)
    overall_end = date.today()

    current = overall_start

    total_fetched = 0
    total_inserted = 0

    while current <= overall_end:

        end = min(
            month_end(current),
            overall_end,
        )

        print()
        print(
            f"=== {current.isoformat()} "
            f"→ {end.isoformat()} ==="
        )

        for page in range(1, 100):

            print(f"Fetching page {page}...")

            trades = fetch_trades(
                current,
                end,
                page,
            )

            if not trades:
                break

            inserted = store_trades(trades)

            total_fetched += len(trades)
            total_inserted += inserted

            print(
                f"{len(trades):,} fetched, "
                f"{inserted:,} new"
            )

            if len(trades) < 1000:
                break

            time.sleep(1.0)

        if page == 99 and len(trades) == 1000:
            print(
                "WARNING: monthly range hit "
                "99,000-row limit."
            )

        current = end + timedelta(days=1)

        time.sleep(1.0)

    print()
    print("BACKFILL COMPLETE")
    print(f"Fetched:  {total_fetched:,}")
    print(f"Inserted: {total_inserted:,}")

if __name__ == "__main__":
    main()
