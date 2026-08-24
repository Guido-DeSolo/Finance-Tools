"""Deterministically reduce a candidate packet to model-ready evidence."""

import math


def insider_strength(watchlist):
    score = float(watchlist.get("insider_score") or 0)
    if score >= 25:
        return "high"
    if score >= 10:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def percent(value):
    if value is None:
        return None
    return round(float(value) * 100, 2)


def volume_signal(value):
    if value is None:
        return "unavailable"
    if value >= 2:
        return "elevated"
    if value <= 0.5:
        return "low"
    return "normal"


def reduce_packet(packet):
    watchlist = packet["watchlist"]
    market = packet["market"]
    stats = market.get("stats") if market.get("quality_pass") else None
    quality = list(market.get("reasons") or [])

    if stats:
        volume_ratio = stats.get("last_volume_vs_median")
        if volume_ratio is None:
            quality.append("market_volume_ratio_unavailable")
        returns = [stats.get(f"return_{days}d") for days in (1, 5, 20, 60)]
        finite_returns = [
            value for value in returns
            if isinstance(value, (int, float)) and math.isfinite(value)
        ]
        if finite_returns and all(value == 0 for value in finite_returns):
            quality.append("all_available_market_returns_are_zero")

    return {
        "symbol": packet["symbol"],
        "insider": {
            "signal_strength": insider_strength(watchlist),
            "buyers": int(watchlist.get("unique_buyers_30d") or 0),
            "ceo_buy": bool(watchlist.get("ceo_buy_30d")),
            "cfo_buy": bool(watchlist.get("cfo_buy_30d")),
            "cluster_buy": bool(watchlist.get("cluster_buy_30d")),
            "purchase_value": round(float(watchlist.get("buy_value_30d") or 0), 2),
        },
        "news": {
            "count": len(packet["news"]),
            "items": [
                {
                    "id": index,
                    "headline": article["headline"],
                    "summary": article.get("summary") or "",
                }
                for index, article in enumerate(packet["news"])
            ],
        },
        "market": {
            "available": bool(market.get("quality_pass") and stats),
            "return_5d_pct": percent(stats.get("return_5d")) if stats else None,
            "return_20d_pct": percent(stats.get("return_20d")) if stats else None,
            "volume_signal": (
                volume_signal(stats.get("last_volume_vs_median"))
                if stats else "unavailable"
            ),
        },
        "quality": sorted(set(quality)),
    }
