"""Deterministically normalize insider features for research."""


def insider_signal(watchlist):
    buyers = int(watchlist.get("unique_buyers_30d") or 0)
    purchases = int(watchlist.get("buy_count_30d") or 0)
    purchase_value = float(watchlist.get("buy_value_30d") or 0)
    sale_value = float(watchlist.get("sell_value_30d") or 0)
    if not buyers or not purchases:
        return {
            "status": "ABSTAIN",
            "reason": "NO_INSIDER_SIGNAL",
        }
    score = float(watchlist.get("insider_score") or 0)
    strength = "strong" if score >= 25 else "moderate" if score >= 10 else "weak"
    flags = []
    if purchase_value < 10_000:
        flags.append("low_purchase_value")
    if sale_value > purchase_value:
        flags.append("sales_exceed_purchases")
    if buyers == 1 and purchases >= 5:
        flags.append("single_buyer_repetition")
    return {
        "status": "ANALYZED",
        "strength": strength,
        "cluster": bool(watchlist.get("cluster_buy_30d")),
        "senior_management": bool(
            watchlist.get("ceo_buy_30d") or watchlist.get("cfo_buy_30d")
        ),
        "risk_flags": flags,
    }
