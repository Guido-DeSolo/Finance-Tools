#!/usr/bin/env python3

import math

def get_candidates(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH recent_insider_events AS (
                SELECT *
                FROM insider_events
                WHERE filing_day >= (CURRENT_TIMESTAMP - INTERVAL '30 days')::date
            ),

            insider_totals AS (
                SELECT
                    event.ticker AS symbol,

                    SUM(event.purchase_count) AS buy_count_30d,

                    COALESCE(
                        SUM(event.total_purchase_value),
                        0
                    ) AS buy_value_30d,

                    COALESCE(
                        SUM(event.total_sale_value),
                        0
                    ) AS sell_value_30d,

                    BOOL_OR(event.ceo_participated) AS ceo_buy_30d,

                    BOOL_OR(event.cfo_participated) AS cfo_buy_30d

                FROM recent_insider_events AS event
                GROUP BY event.ticker
            ),

            insider_buyers AS (
                SELECT
                    event.ticker AS symbol,
                    COUNT(DISTINCT buyer.insider) AS unique_buyers_30d
                FROM recent_insider_events AS event
                CROSS JOIN LATERAL unnest(event.purchase_insiders)
                    AS buyer(insider)
                GROUP BY event.ticker
            ),

            insider AS (
                SELECT
                    totals.symbol,
                    totals.buy_count_30d,
                    COALESCE(buyers.unique_buyers_30d, 0)
                        AS unique_buyers_30d,
                    totals.buy_value_30d,
                    totals.sell_value_30d,
                    totals.ceo_buy_30d,
                    totals.cfo_buy_30d
                FROM insider_totals AS totals
                LEFT JOIN insider_buyers AS buyers
                    USING (symbol)
            ),

            news_counts AS (
                SELECT
                    symbol,

                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - INTERVAL '1 day'
                    ) AS news_1d,

                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - INTERVAL '7 days'
                    ) AS news_7d,

                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - INTERVAL '30 days'
                    ) AS news_30d,

                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - INTERVAL '90 days'
                    ) AS news_90d

                FROM news
                CROSS JOIN LATERAL unnest(symbols) AS symbol

                WHERE created_at >= NOW() - INTERVAL '90 days'

                GROUP BY symbol
            )

            SELECT
                COALESCE(i.symbol, n.symbol) AS symbol,

                COALESCE(i.buy_count_30d, 0),
                COALESCE(i.unique_buyers_30d, 0),
                COALESCE(i.buy_value_30d, 0),
                COALESCE(i.sell_value_30d, 0),

                COALESCE(i.ceo_buy_30d, FALSE),
                COALESCE(i.cfo_buy_30d, FALSE),

                COALESCE(n.news_1d, 0),
                COALESCE(n.news_7d, 0),
                COALESCE(n.news_30d, 0),
                COALESCE(n.news_90d, 0)

            FROM insider i

            FULL OUTER JOIN news_counts n
                ON i.symbol = n.symbol

            WHERE COALESCE(i.symbol, n.symbol) IS NOT NULL

            ORDER BY symbol
            """
        )

        return cur.fetchall()


def insider_score(
    buy_count,
    unique_buyers,
    buy_value,
    sell_value,
    ceo_buy,
    cfo_buy,
):
    score = 0.0

    if buy_count:
        score += math.log2(1 + buy_count) * 2.0

    # Multiple independent insiders is more interesting
    # than one insider buying repeatedly.
    if unique_buyers:
        score += math.log2(1 + unique_buyers) * 5.0

    if ceo_buy:
        score += 4.0

    if cfo_buy:
        score += 4.0

    # Two or more distinct buyers constitutes our
    # first-pass definition of a cluster.
    if unique_buyers >= 2:
        score += 3.0

    if unique_buyers >= 3:
        score += 2.0

    # Dollar-value bonus, logarithmic so a $100m purchase
    # does not completely dominate the ranking.
    if buy_value >= 10_000:
        score += max(
            0.0,
            math.log10(buy_value) - 4,
        ) * 3.0

    if 0 < buy_value < 10_000:
        score -= 3.0

    # Repeated transactions by one person are not a cluster.
    if unique_buyers == 1 and buy_count >= 5:
        score -= math.log2(buy_count) * 2.0

    # Sales are weaker evidence than purchases, so
    # penalize them gently rather than symmetrically.
    if sell_value > 0:
        score -= max(
            0.0,
            math.log10(sell_value) - 5,
        )

    return score


def news_score(
    news_1d,
    news_7d,
    news_30d,
    news_90d,
):
    score = 0.0

    # Recent articles matter more than older ones.
    if news_1d:
        score += math.log2(1 + news_1d) * 5.0

    if news_7d:
        score += math.log2(1 + news_7d) * 2.5

    if news_30d:
        score += math.log2(1 + news_30d)

    if news_90d:
        score += math.log2(1 + news_90d) * 0.25

    # Avoid allowing a huge news torrent to completely
    # overwhelm every other signal.
    return min(score, 20.0)


def save_scores(conn, rows):
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO watchlist_scores (
                    symbol,
                    insider_score,
                    news_score,
                    market_score,
                    total_score,

                    buy_count_30d,
                    unique_buyers_30d,
                    buy_value_30d,
                    sell_value_30d,

                    ceo_buy_30d,
                    cfo_buy_30d,
                    cluster_buy_30d,

                    news_1d,
                    news_7d,
                    news_30d,
                    news_90d
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                row,
            )

    conn.commit()


def main():
    import psycopg
    from settings import load_settings

    database_url = load_settings(("DATABASE_URL",))["DATABASE_URL"]
    with psycopg.connect(database_url) as conn:
        candidates = get_candidates(conn)

        print(
            f"Scoring {len(candidates):,} candidates..."
        )

        scored = []

        for candidate in candidates:
            (
                symbol,
                buy_count,
                unique_buyers,
                buy_value,
                sell_value,
                ceo_buy,
                cfo_buy,
                news_1d,
                news_7d,
                news_30d,
                news_90d,
            ) = candidate

            buy_value = float(buy_value or 0)
            sell_value = float(sell_value or 0)

            i_score = insider_score(
                buy_count,
                unique_buyers,
                buy_value,
                sell_value,
                ceo_buy,
                cfo_buy,
            )

            n_score = news_score(
                news_1d,
                news_7d,
                news_30d,
                news_90d,
            )

            market_score = 0.0

            total = (
                i_score
                + n_score
                + market_score
            )

            cluster = (
                unique_buyers >= 2
            )

            scored.append(
                (
                    symbol,
                    i_score,
                    n_score,
                    market_score,
                    total,

                    buy_count,
                    unique_buyers,
                    buy_value,
                    sell_value,

                    ceo_buy,
                    cfo_buy,
                    cluster,

                    news_1d,
                    news_7d,
                    news_30d,
                    news_90d,
                )
            )

        save_scores(
            conn,
            scored,
        )

    ranked = sorted(
        scored,
        key=lambda r: r[4],
        reverse=True,
    )

    print()
    print("TOP 30 WATCHLIST CANDIDATES")
    print()

    print(
        f"{'SYM':6} "
        f"{'TOTAL':>7} "
        f"{'INS':>7} "
        f"{'NEWS':>7} "
        f"{'BUYS':>5} "
        f"{'BUYERS':>6} "
        f"{'VALUE':>14} "
        f"{'CEO':>4} "
        f"{'CFO':>4}"
    )

    print("-" * 75)

    for row in ranked[:30]:
        (
            symbol,
            i_score,
            n_score,
            market_score,
            total,
            buy_count,
            unique_buyers,
            buy_value,
            sell_value,
            ceo_buy,
            cfo_buy,
            cluster,
            news_1d,
            news_7d,
            news_30d,
            news_90d,
        ) = row

        print(
            f"{symbol:6} "
            f"{total:7.2f} "
            f"{i_score:7.2f} "
            f"{n_score:7.2f} "
            f"{buy_count:5} "
            f"{unique_buyers:6} "
            f"${buy_value:13,.0f} "
            f"{'Y' if ceo_buy else '-':>4} "
            f"{'Y' if cfo_buy else '-':>4}"
        )


if __name__ == "__main__":
    main()
