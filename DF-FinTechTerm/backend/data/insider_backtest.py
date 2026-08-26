#!/usr/bin/env python3

import statistics
import psycopg
from settings import load_settings


ENV = load_settings(("DATABASE_URL",))
DATABASE_URL = ENV["DATABASE_URL"]


def get_purchases(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                ticker,
                filing_date,
                insider,
                title,
                price,
                quantity,
                trade_value,
                ownership_change
            FROM insider_trades
            WHERE trade_type = 'P - Purchase'
            ORDER BY filing_date
            """
        )

        return cur.fetchall()


def get_forward_prices(conn, ticker, filing_date):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                date,
                open,
                close
            FROM daily_bars
            WHERE symbol = %s
              AND date > %s::date
            ORDER BY date
            LIMIT 61
            """,
            (
                ticker,
                filing_date,
            ),
        )

        return cur.fetchall()

def pct_return(start, end):
    if start is None or end is None:
        return None

    if start == 0:
        return None

    return ((end / start) - 1.0) * 100.0


def main():
    results = []

    with psycopg.connect(DATABASE_URL) as conn:

        purchases = get_purchases(conn)

        print(
            f"Found {len(purchases):,} "
            f"open-market purchases."
        )

        for number, purchase in enumerate(
            purchases,
            start=1,
        ):
            (
                trade_id,
                ticker,
                filing_date,
                insider,
                title,
                trade_price,
                quantity,
                trade_value,
                ownership_change,
            ) = purchase

            prices = get_forward_prices(
                conn,
                ticker,
                filing_date,
            )

            if len(prices) < 2:
                continue

            entry_price = float(prices[0][1])

            horizons = {
                1: None,
                5: None,
                20: None,
                60: None,
            }

            for days in horizons:
                if len(prices) > days:
                    horizons[days] = float(
                        prices[days][2]
                    )

            result = {
                "id": trade_id,
                "ticker": ticker,
                "filing_date": filing_date,
                "insider": insider,
                "title": title,
                "trade_value": trade_value,
                "ownership_change": ownership_change,
                "entry_price": entry_price,
                "return_1d": pct_return(
                    entry_price,
                    horizons[1],
                ),
                "return_5d": pct_return(
                    entry_price,
                    horizons[5],
                ),
                "return_20d": pct_return(
                    entry_price,
                    horizons[20],
                ),
                "return_60d": pct_return(
                    entry_price,
                    horizons[60],
                ),
            }

            results.append(result)

            if number % 1000 == 0:
                print(
                    f"Processed "
                    f"{number:,}/"
                    f"{len(purchases):,}"
                )

    print()
    print(
        f"Usable backtest rows: "
        f"{len(results):,}"
    )


    zero_1d = [
        r
        for r in results
        if r["return_1d"] is not None
        and abs(r["return_1d"]) < 0.000001
    ]

    print()
    print(f"1d zero-return examples ({len(zero_1d):,} total):")

    for r in zero_1d[:30]:
        print(
            r["ticker"],
            r["filing_date"],
            r["entry_price"],
            r["return_1d"],
        )

    summarize(results)

    valid = [
        r for r in results
        if r["return_1d"] is not None
    ]

    print("\n20 LARGEST 1-DAY RETURNS")
    for r in sorted(
        valid,
        key=lambda r: r["return_1d"],
        reverse=True,
    )[:20]:
        print(
            f'{r["ticker"]:6} '
            f'{str(r["filing_date"]):25} '
            f'entry=${r["entry_price"]:10.4f} '
            f'return={r["return_1d"]:+10.2f}%'
        )

    print("\n20 SMALLEST 1-DAY RETURNS")
    for r in sorted(
        valid,
        key=lambda r: r["return_1d"],
    )[:20]:
        print(
            f'{r["ticker"]:6} '
            f'{str(r["filing_date"]):25} '
            f'entry=${r["entry_price"]:10.4f} '
            f'return={r["return_1d"]:+10.2f}%'
        )


def summarize(results):
    for field in (
        "return_1d",
        "return_5d",
        "return_20d",
        "return_60d",
    ):
        values = [
            r[field]
            for r in results
            if r[field] is not None
        ]

        if not values:
            continue

        values.sort()

        n = len(values)

        mean = statistics.mean(values)
        median = statistics.median(values)
        stdev = statistics.stdev(values)

        q1 = values[int(n * 0.25)]
        q3 = values[int(n * 0.75)]

        wins = sum(
            value > 0
            for value in values
        )

        win_rate = wins / n * 100

        print(
            f"{field:12} "
            f"N={n:,} "
            f"mean={mean:+7.2f}% "
            f"median={median:+7.2f}% "
            f"win={win_rate:5.1f}% "
            f"Q1={q1:+7.2f}% "
            f"Q3={q3:+7.2f}% "
            f"sd={stdev:7.2f}%"
        )

        print()

        for field in (
            "return_1d",
            "return_5d",
            "return_20d",
            "return_60d",
        ):
            values = [
                r[field]
                for r in results
                if r[field] is not None
            ]

            zeros = sum(
                abs(v) < 0.000001
                for v in values
            )

            print(
                f"{field:12} "
                f"zeros={zeros:,} "
                f"({zeros / len(values) * 100:.2f}%)"
            )


if __name__ == "__main__":
    main()
