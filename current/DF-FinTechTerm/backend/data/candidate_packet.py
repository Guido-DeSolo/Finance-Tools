#!/usr/bin/env python3

import argparse
import json
import math
import statistics
import sys
from datetime import date, datetime
from decimal import Decimal

def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def get_top_candidates(conn, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (symbol)
                    symbol,
                    scored_at,
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
                FROM watchlist_scores
                ORDER BY symbol, scored_at DESC
            )
            SELECT *
            FROM latest
            ORDER BY total_score DESC, symbol
            LIMIT %s
            """,
            (limit,),
        )
        columns = [column.name for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_recent_events(conn, symbol, days=90, limit=10):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                filing_day AS filing_date,
                first_trade_date,
                last_trade_date,
                purchase_count,
                unique_buyers,
                purchase_insiders,
                total_purchase_value AS purchase_value,
                total_sale_value AS sale_value,
                ceo_participated AS ceo,
                cfo_participated AS cfo,
                director_participated AS director,
                max_ownership_change,
                cluster,
                filing_count
            FROM insider_events
            WHERE ticker = %s
              AND filing_day >= CURRENT_DATE - %s
            ORDER BY filing_day DESC
            LIMIT %s
            """,
            (symbol, days - 1, limit),
        )
        columns = [column.name for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_recent_news(conn, symbol, days=30, limit=20):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, created_at, headline, summary, source, url
            FROM news
            WHERE %s = ANY(symbols)
              AND created_at >= NOW() - make_interval(days => %s)
            ORDER BY created_at DESC, id
            LIMIT %s
            """,
            (symbol, days, limit),
        )
        columns = [column.name for column in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_recent_bars(conn, symbol, limit=90):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT date, open, high, low, close, volume
            FROM daily_bars
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT %s
            """,
            (symbol, limit),
        )
        return [
            {
                "date": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": row[5],
            }
            for row in reversed(cur.fetchall())
        ]


def price_summary(bars):
    reasons = []

    if len(bars) < 21:
        reasons.append("insufficient_history")

    for bar in bars:
        prices = [bar["open"], bar["high"], bar["low"], bar["close"]]
        if any(not math.isfinite(value) or value <= 0 for value in prices):
            reasons.append("nonpositive_or_nonfinite_price")
            break
        if bar["low"] > min(bar["open"], bar["close"]) or bar["high"] < max(
            bar["open"], bar["close"]
        ):
            reasons.append("invalid_ohlc")
            break

    closes = [bar["close"] for bar in bars]
    if closes:
        if max(closes) > 100_000:
            reasons.append("implausible_price_level")
        if min(closes) > 0 and max(closes) / min(closes) > 100:
            reasons.append("extreme_price_range")

    adjacent_returns = [
        current / previous - 1
        for previous, current in zip(closes, closes[1:])
        if previous > 0
    ]
    if adjacent_returns and max(abs(value) for value in adjacent_returns) > 4:
        reasons.append("extreme_adjacent_jump")

    reasons = sorted(set(reasons))
    result = {
        "source": "alpaca_iex_adjusted_all",
        "quality_pass": not reasons,
        "reasons": reasons,
        "bar_count": len(bars),
        "first_date": bars[0]["date"] if bars else None,
        "last_date": bars[-1]["date"] if bars else None,
    }

    if reasons or not bars:
        result["stats"] = None
        return result

    volumes = [bar["volume"] for bar in bars]
    stats = {
        "last_close": closes[-1],
        "median_volume": statistics.median(volumes),
        "last_volume": volumes[-1],
        "last_volume_vs_median": (
            volumes[-1] / statistics.median(volumes)
            if statistics.median(volumes) > 0
            else None
        ),
    }
    for horizon in (1, 5, 20, 60):
        stats[f"return_{horizon}d"] = (
            closes[-1] / closes[-1 - horizon] - 1
            if len(closes) > horizon
            else None
        )
    recent_20 = bars[-20:]
    recent_returns = adjacent_returns[-20:]
    stats["volatility_20d"] = (
        statistics.pstdev(recent_returns) if len(recent_returns) >= 2 else None
    )
    recent_volumes = [bar["volume"] for bar in recent_20]
    recent_median_volume = statistics.median(recent_volumes)
    stats["volume_ratio_20d"] = (
        recent_volumes[-1] / recent_median_volume
        if recent_median_volume > 0 else None
    )
    high_20d = max(bar["high"] for bar in recent_20)
    low_20d = min(bar["low"] for bar in recent_20)
    stats["distance_from_20d_high"] = closes[-1] / high_20d - 1
    stats["distance_from_20d_low"] = closes[-1] / low_20d - 1
    result["stats"] = stats
    return result


def build_packets(conn, limit):
    packets = []
    for rank, score in enumerate(get_top_candidates(conn, limit), start=1):
        symbol = score["symbol"]
        packets.append(
            {
                "rank": rank,
                "symbol": symbol,
                "watchlist": score,
                "insider_events": get_recent_events(conn, symbol),
                "news": get_recent_news(conn, symbol),
                "market": price_summary(get_recent_bars(conn, symbol)),
            }
        )
    return packets


def require_fields(value, fields, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    missing = sorted(set(fields) - set(value))
    if missing:
        raise ValueError(f"{path} missing required fields: {', '.join(missing)}")


def validate_date(value, path, allow_null=False):
    if value is None and allow_null:
        return
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date string")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{path} is not a valid ISO date: {value!r}") from exc


def validate_finite_numbers(value, path="document"):
    if isinstance(value, dict):
        for key, child in value.items():
            validate_finite_numbers(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_finite_numbers(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} contains a non-finite number")


def validate_document(document):
    require_fields(
        document,
        {"generated_at", "candidate_count", "score_selection", "packets"},
        "document",
    )
    validate_date(document["generated_at"], "document.generated_at")
    if not isinstance(document["packets"], list):
        raise ValueError("document.packets must be an array")
    if document["candidate_count"] != len(document["packets"]):
        raise ValueError("document.candidate_count does not match packets length")

    symbols = set()
    for index, packet in enumerate(document["packets"]):
        path = f"document.packets[{index}]"
        require_fields(
            packet,
            {"rank", "symbol", "watchlist", "insider_events", "news", "market"},
            path,
        )
        if not isinstance(packet["symbol"], str) or not packet["symbol"]:
            raise ValueError(f"{path}.symbol must be a non-empty string")
        if packet["symbol"] in symbols:
            raise ValueError(f"{path}.symbol is duplicated: {packet['symbol']}")
        symbols.add(packet["symbol"])

        require_fields(
            packet["watchlist"],
            {
                "symbol", "scored_at", "total_score", "insider_score",
                "news_score", "market_score",
            },
            f"{path}.watchlist",
        )
        if packet["watchlist"]["symbol"] != packet["symbol"]:
            raise ValueError(f"{path}.watchlist.symbol does not match packet symbol")
        validate_date(packet["watchlist"]["scored_at"], f"{path}.watchlist.scored_at")

        if not isinstance(packet["insider_events"], list):
            raise ValueError(f"{path}.insider_events must be an array")
        for event_index, event in enumerate(packet["insider_events"]):
            event_path = f"{path}.insider_events[{event_index}]"
            require_fields(
                event,
                {
                    "filing_date", "purchase_count", "unique_buyers",
                    "purchase_value", "sale_value", "ceo", "cfo", "director",
                    "cluster", "max_ownership_change",
                },
                event_path,
            )
            validate_date(event["filing_date"], f"{event_path}.filing_date")
            validate_date(event["first_trade_date"], f"{event_path}.first_trade_date")
            validate_date(event["last_trade_date"], f"{event_path}.last_trade_date")

        if not isinstance(packet["news"], list):
            raise ValueError(f"{path}.news must be an array")
        for news_index, article in enumerate(packet["news"]):
            article_path = f"{path}.news[{news_index}]"
            require_fields(
                article,
                {"id", "created_at", "headline", "summary", "source", "url"},
                article_path,
            )
            validate_date(article["created_at"], f"{article_path}.created_at")

        market = packet["market"]
        require_fields(
            market,
            {
                "source", "quality_pass", "reasons", "stats", "bar_count",
                "first_date", "last_date",
            },
            f"{path}.market",
        )
        if not isinstance(market["quality_pass"], bool):
            raise ValueError(f"{path}.market.quality_pass must be boolean")
        if not isinstance(market["reasons"], list) or not all(
            isinstance(reason, str) and reason for reason in market["reasons"]
        ):
            raise ValueError(f"{path}.market.reasons must be an array of strings")
        validate_date(market["first_date"], f"{path}.market.first_date", allow_null=True)
        validate_date(market["last_date"], f"{path}.market.last_date", allow_null=True)
        if market["quality_pass"]:
            if market["reasons"]:
                raise ValueError(f"{path}.market passed quality with rejection reasons")
            if not isinstance(market["stats"], dict):
                raise ValueError(f"{path}.market passed quality without stats")
            require_fields(
                market["stats"],
                {
                    "last_close", "median_volume", "last_volume",
                    "last_volume_vs_median", "return_1d", "return_5d",
                    "return_20d", "return_60d",
                },
                f"{path}.market.stats",
            )
        elif market["stats"] is not None:
            raise ValueError(f"{path}.market failed quality but contains stats")

    validate_finite_numbers(document)


def main():
    import psycopg
    from settings import load_settings

    parser = argparse.ArgumentParser(
        description="Build deterministic JSON packets for top watchlist candidates."
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", help="Write JSON to this path instead of stdout.")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the generated packet contract and fail on any violation.",
    )
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")

    database_url = load_settings(("DATABASE_URL",))["DATABASE_URL"]
    with psycopg.connect(database_url) as conn:
        packets = build_packets(conn, args.limit)
        document = {
            "generated_at": datetime.now().astimezone(),
            "candidate_count": len(packets),
            "score_selection": "latest row per symbol",
            "packets": packets,
        }

    output = json.dumps(document, default=json_default, indent=2, sort_keys=True)
    if args.validate:
        validate_document(json.loads(output))
        print(
            f"Validated {document['candidate_count']} candidate packets.",
            file=sys.stderr,
        )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(output)
            output_file.write("\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
