"""Whitelist branch outputs into the compact synthesis contract."""


def build_synthesis_input(symbol, insider, quant, news):
    if insider["status"] == "ANALYZED":
        insider_input = {
            key: insider[key]
            for key in ("status", "strength", "cluster", "senior_management", "risk_flags")
        }
    else:
        insider_input = {"status": "ABSTAIN", "reason": insider["reason"]}

    if quant["status"] == "ANALYZED":
        quant_input = {
            key: quant[key]
            for key in (
                "status", "trend", "momentum", "volatility",
                "volume_confirmation", "preferred_horizon", "signal_strength",
                "risk_flags",
            )
        }
    else:
        quant_input = {"status": "ABSTAIN", "reason": quant["reason"]}

    if news["status"] == "ANALYZED":
        news_input = {
            "status": "ANALYZED",
            "overall_sentiment": news["overall_sentiment"],
            "confidence": news["confidence"],
            "conflicting": news["conflicting_articles"],
            "high_materiality_count": news["high_materiality_count"],
            "sentiment_balance": news["sentiment_balance"],
        }
    else:
        news_input = {"status": "ABSTAIN", "reason": news["reason"]}
    return {
        "symbol": symbol,
        "insider": insider_input,
        "quant": quant_input,
        "news": news_input,
    }
