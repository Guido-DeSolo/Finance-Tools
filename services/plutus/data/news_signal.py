"""Deterministically aggregate NEWS v2 article assessments."""


MATERIALITY_WEIGHTS = {"low": 1, "moderate": 2, "high": 3}


def abstain_signal(summary):
    if summary["articles"]:
        raise ValueError("NO_RECENT_NEWS requires an empty article list")
    return {"symbol": summary["symbol"], "status": "ABSTAIN", "reason": "NO_RECENT_NEWS"}


def aggregate_news(summary, model_result):
    if not summary["articles"]:
        return abstain_signal(summary)
    assessments = sorted(model_result["article_assessments"], key=lambda item: item["article_id"])
    counts = {
        sentiment: sum(item["sentiment"] == sentiment for item in assessments)
        for sentiment in ("positive", "negative", "neutral")
    }
    if counts["positive"] and counts["negative"]:
        overall = "mixed"
        confidence = (counts["positive"] + counts["negative"]) / len(assessments)
    elif counts["positive"]:
        overall = "positive"
        confidence = counts["positive"] / len(assessments)
    elif counts["negative"]:
        overall = "negative"
        confidence = counts["negative"] / len(assessments)
    else:
        overall = "neutral"
        confidence = counts["neutral"] / len(assessments)
    return {
        "symbol": summary["symbol"],
        "status": "ANALYZED",
        "overall_sentiment": overall,
        "confidence": round(confidence, 2),
        "conflicting_articles": bool(counts["positive"] and counts["negative"]),
        "news_count": len(assessments),
        "high_materiality_count": sum(
            item["materiality"] == "high" for item in assessments
        ),
        "positive_count": counts["positive"],
        "negative_count": counts["negative"],
        "neutral_count": counts["neutral"],
        "sentiment_balance": counts["positive"] - counts["negative"],
        "maximum_materiality": max(
            (item["materiality"] for item in assessments),
            key=MATERIALITY_WEIGHTS.get,
        ),
        "article_assessments": assessments,
    }
